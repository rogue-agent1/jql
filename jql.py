#!/usr/bin/env python3
"""
jql: A lightweight JSON Swiss Army knife. Pure Python, zero dependencies.
Like jq but simpler, with extras: diff, flatten, csv, stats, schema.

Usage:
    echo '{"a":{"b":1}}' | jql pretty
    echo '{"a":{"b":1}}' | jql get a.b
    jql diff a.json b.json
    echo '[{"name":"a","age":1}]' | jql csv
    echo '{"a":{"b":[1,2]}}' | jql flatten
    echo '{"a":1,"b":"hi","c":[1,2,3]}' | jql stats
    echo '{"a":1,"b":"hi"}' | jql schema
    echo '[1,2,3,4,5]' | jql filter 'x > 2'
    jql merge a.json b.json
"""

import argparse
import csv
import io
import json
import sys
from collections import OrderedDict
from pathlib import Path


def load_json(source: str = None):
    """Load JSON from file path or stdin."""
    if source and source != "-":
        return json.loads(Path(source).read_text())
    return json.load(sys.stdin)


def cmd_pretty(args):
    data = load_json(args.input)
    indent = args.indent or 2
    if args.sort:
        print(json.dumps(data, indent=indent, sort_keys=True, ensure_ascii=False))
    else:
        print(json.dumps(data, indent=indent, ensure_ascii=False))


def cmd_compact(args):
    data = load_json(args.input)
    print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))


def resolve_path(data, path: str):
    """Resolve a dot-notation path with array indexing: a.b[0].c"""
    import re
    parts = re.split(r'\.(?![^\[]*\])', path)
    current = data
    for part in parts:
        # Handle array indices: key[0]
        m = re.match(r'^(\w+)\[(-?\d+)\]$', part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(current, dict):
                current = current[key]
            current = current[idx]
        elif isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(f"Cannot traverse into {type(current).__name__} with key '{part}'")
    return current


def cmd_get(args):
    data = load_json(args.input)
    try:
        result = resolve_path(data, args.path)
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
    except (KeyError, IndexError, TypeError) as e:
        print(f"null", file=sys.stdout)
        sys.exit(1)


def cmd_keys(args):
    data = load_json(args.input)
    if args.path:
        data = resolve_path(data, args.path)
    if isinstance(data, dict):
        for k in data.keys():
            print(k)
    elif isinstance(data, list):
        print(f"[array of {len(data)} items]")
    else:
        print(type(data).__name__)


def cmd_flatten(args):
    data = load_json(args.input)
    sep = args.sep or "."

    def _flatten(obj, prefix=""):
        result = OrderedDict()
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{prefix}{sep}{k}" if prefix else k
                result.update(_flatten(v, new_key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                new_key = f"{prefix}[{i}]"
                result.update(_flatten(v, new_key))
        else:
            result[prefix] = obj
        return result

    print(json.dumps(_flatten(data), indent=2, ensure_ascii=False))


def cmd_unflatten(args):
    data = load_json(args.input)
    sep = args.sep or "."
    import re

    result = {}
    for key, value in data.items():
        parts = key.split(sep)
        d = result
        for i, part in enumerate(parts[:-1]):
            m = re.match(r'^(\w+)\[(\d+)\]$', part)
            if m:
                part = m.group(1)
                idx = int(m.group(2))
                d = d.setdefault(part, [])
                while len(d) <= idx:
                    d.append({})
                d = d[idx]
            else:
                if i + 1 < len(parts):
                    next_part = parts[i + 1]
                    if re.match(r'^\d+$', next_part) or re.match(r'^\w+\[\d+\]$', next_part):
                        d = d.setdefault(part, [])
                    else:
                        d = d.setdefault(part, {})
                else:
                    d = d.setdefault(part, {})
        d[parts[-1]] = value

    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_diff(args):
    a = json.loads(Path(args.file_a).read_text())
    b = json.loads(Path(args.file_b).read_text())

    diffs = []

    def _diff(obj_a, obj_b, path=""):
        if type(obj_a) != type(obj_b):
            diffs.append({"path": path or "(root)", "type": "type_change",
                         "old": f"{type(obj_a).__name__}: {json.dumps(obj_a)[:100]}",
                         "new": f"{type(obj_b).__name__}: {json.dumps(obj_b)[:100]}"})
            return
        if isinstance(obj_a, dict):
            all_keys = set(list(obj_a.keys()) + list(obj_b.keys()))
            for k in sorted(all_keys):
                p = f"{path}.{k}" if path else k
                if k not in obj_a:
                    diffs.append({"path": p, "type": "added", "value": obj_b[k]})
                elif k not in obj_b:
                    diffs.append({"path": p, "type": "removed", "value": obj_a[k]})
                else:
                    _diff(obj_a[k], obj_b[k], p)
        elif isinstance(obj_a, list):
            max_len = max(len(obj_a), len(obj_b))
            for i in range(max_len):
                p = f"{path}[{i}]"
                if i >= len(obj_a):
                    diffs.append({"path": p, "type": "added", "value": obj_b[i]})
                elif i >= len(obj_b):
                    diffs.append({"path": p, "type": "removed", "value": obj_a[i]})
                else:
                    _diff(obj_a[i], obj_b[i], p)
        elif obj_a != obj_b:
            diffs.append({"path": path, "type": "changed", "old": obj_a, "new": obj_b})

    _diff(a, b)

    if not diffs:
        print("✅ No differences.")
        return

    if args.json_output:
        print(json.dumps(diffs, indent=2, ensure_ascii=False))
        return

    for d in diffs:
        if d["type"] == "added":
            val = json.dumps(d["value"])[:80]
            print(f"  + {d['path']}: {val}")
        elif d["type"] == "removed":
            val = json.dumps(d["value"])[:80]
            print(f"  - {d['path']}: {val}")
        elif d["type"] == "changed":
            print(f"  ~ {d['path']}: {json.dumps(d['old'])[:40]} → {json.dumps(d['new'])[:40]}")
        elif d["type"] == "type_change":
            print(f"  ⚡ {d['path']}: {d['old']} → {d['new']}")

    print(f"\n{len(diffs)} difference(s)")


def cmd_csv(args):
    data = load_json(args.input)
    if not isinstance(data, list) or not data:
        print("Error: input must be a non-empty JSON array of objects", file=sys.stderr)
        sys.exit(1)

    # Collect all keys
    keys = OrderedDict()
    for item in data:
        if isinstance(item, dict):
            for k in item.keys():
                keys[k] = True

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(keys.keys()))
    writer.writeheader()
    for item in data:
        if isinstance(item, dict):
            row = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in item.items()}
            writer.writerow(row)

    print(out.getvalue().strip())


def cmd_stats(args):
    data = load_json(args.input)

    def _stats(obj, depth=0):
        if isinstance(obj, dict):
            print(f"{'  ' * depth}object: {len(obj)} keys")
            for k, v in obj.items():
                print(f"{'  ' * (depth + 1)}{k}: ", end="")
                if isinstance(v, dict):
                    _stats(v, depth + 1)
                elif isinstance(v, list):
                    types = set(type(x).__name__ for x in v)
                    print(f"array[{len(v)}] ({', '.join(types) or 'empty'})")
                else:
                    print(f"{type(v).__name__} = {json.dumps(v)[:60]}")
        elif isinstance(obj, list):
            types = set(type(x).__name__ for x in obj)
            print(f"array[{len(obj)}] ({', '.join(types) or 'empty'})")
            if all(isinstance(x, (int, float)) for x in obj) and obj:
                print(f"{'  ' * (depth + 1)}min={min(obj)}, max={max(obj)}, avg={sum(obj)/len(obj):.2f}, sum={sum(obj)}")
        else:
            print(f"{type(obj).__name__}: {json.dumps(obj)[:80]}")

    _stats(data)


def cmd_schema(args):
    data = load_json(args.input)

    def _schema(obj, indent=0):
        pad = "  " * indent
        if isinstance(obj, dict):
            print(f"{pad}{{")
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    print(f"{pad}  {k}: ", end="")
                    _schema(v, indent + 1)
                else:
                    print(f"{pad}  {k}: {type(v).__name__}")
            print(f"{pad}}}")
        elif isinstance(obj, list):
            if not obj:
                print("[]")
            elif isinstance(obj[0], (dict, list)):
                print(f"[  // {len(obj)} items")
                _schema(obj[0], indent + 1)
                print(f"{pad}]")
            else:
                types = set(type(x).__name__ for x in obj)
                print(f"[{', '.join(types)}]  // {len(obj)} items")
        else:
            print(f"{type(obj).__name__}")

    _schema(data)


def cmd_filter(args):
    data = load_json(args.input)
    if not isinstance(data, list):
        print("Error: filter requires a JSON array", file=sys.stderr)
        sys.exit(1)

    expr = args.expr
    results = []
    for item in data:
        try:
            if isinstance(item, (int, float)):
                x = item
                if eval(expr, {"__builtins__": {}}, {"x": x}):
                    results.append(item)
            elif isinstance(item, dict):
                if eval(expr, {"__builtins__": {}}, item):
                    results.append(item)
        except Exception:
            continue

    print(json.dumps(results, indent=2, ensure_ascii=False))


def cmd_merge(args):
    result = {}
    for f in args.files:
        data = json.loads(Path(f).read_text())
        if isinstance(data, dict):
            result.update(data)
        else:
            print(f"Warning: {f} is not an object, skipping", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_count(args):
    data = load_json(args.input)
    if args.path:
        data = resolve_path(data, args.path)
    if isinstance(data, (list, dict)):
        print(len(data))
    elif isinstance(data, str):
        print(len(data))
    else:
        print(1)


def cmd_type(args):
    data = load_json(args.input)
    if args.path:
        data = resolve_path(data, args.path)
    print(type(data).__name__)


def main():
    parser = argparse.ArgumentParser(prog="jql", description="JSON Swiss Army knife")
    sub = parser.add_subparsers(dest="command", required=True)

    # pretty
    p = sub.add_parser("pretty", aliases=["p"], help="Pretty-print JSON")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--indent", "-i", type=int, default=2)
    p.add_argument("--sort", "-s", action="store_true")
    p.set_defaults(func=cmd_pretty)

    # compact
    p = sub.add_parser("compact", aliases=["c"], help="Compact JSON")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_compact)

    # get
    p = sub.add_parser("get", aliases=["g"], help="Get value at path (dot notation)")
    p.add_argument("path", help="Dot-notation path (e.g., a.b[0].c)")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_get)

    # keys
    p = sub.add_parser("keys", aliases=["k"], help="List keys")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--path", "-p")
    p.set_defaults(func=cmd_keys)

    # flatten
    p = sub.add_parser("flatten", aliases=["f"], help="Flatten nested JSON")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--sep", default=".")
    p.set_defaults(func=cmd_flatten)

    # unflatten
    p = sub.add_parser("unflatten", help="Unflatten dotted keys")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--sep", default=".")
    p.set_defaults(func=cmd_unflatten)

    # diff
    p = sub.add_parser("diff", aliases=["d"], help="Diff two JSON files")
    p.add_argument("file_a")
    p.add_argument("file_b")
    p.add_argument("--json", dest="json_output", action="store_true")
    p.set_defaults(func=cmd_diff)

    # csv
    p = sub.add_parser("csv", help="Convert JSON array to CSV")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_csv)

    # stats
    p = sub.add_parser("stats", help="Show structure stats")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_stats)

    # schema
    p = sub.add_parser("schema", help="Infer schema from data")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_schema)

    # filter
    p = sub.add_parser("filter", help="Filter array with expression")
    p.add_argument("expr", help="Python expression (use 'x' for scalars, dict keys for objects)")
    p.add_argument("input", nargs="?", default="-")
    p.set_defaults(func=cmd_filter)

    # merge
    p = sub.add_parser("merge", aliases=["m"], help="Merge multiple JSON files")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_merge)

    # count
    p = sub.add_parser("count", help="Count items")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--path", "-p")
    p.set_defaults(func=cmd_count)

    # type
    p = sub.add_parser("type", help="Show type at path")
    p.add_argument("input", nargs="?", default="-")
    p.add_argument("--path", "-p")
    p.set_defaults(func=cmd_type)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
