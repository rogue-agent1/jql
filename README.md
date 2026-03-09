# jql

JSON Swiss Army knife. Like jq but simpler, with extras.

**Pure Python, zero dependencies.**

## Commands

```bash
# Pretty-print
echo '{"a":1}' | jql pretty

# Get value at path (dot notation + array indexing)
echo '{"users":[{"name":"Alice"}]}' | jql get 'users[0].name'
# Alice

# Flatten nested JSON
echo '{"a":{"b":1},"c":[2,3]}' | jql flatten
# {"a.b": 1, "c[0]": 2, "c[1]": 3}

# Diff two JSON files
jql diff old.json new.json
#   ~ name: "v1" → "v2"
#   + newField: true
#   - removed: 42

# Convert array to CSV
echo '[{"name":"Alice","age":30}]' | jql csv
# name,age
# Alice,30

# Filter arrays
echo '[1,5,3,8,2]' | jql filter 'x > 4'
# [5, 8]

# Infer schema
echo '{"a":1,"b":"hi"}' | jql schema
# { a: int, b: str }

# Stats
echo '[1,2,3,4,5]' | jql stats
# array[5] (int)
#   min=1, max=5, avg=3.00, sum=15

# Also: compact, keys, unflatten, merge, count, type
```

## All Commands

| Command | Description |
|---------|-------------|
| `pretty` | Pretty-print with optional sort |
| `compact` | Minify JSON |
| `get` | Extract value at dot-notation path |
| `keys` | List object keys |
| `flatten` | Flatten nested structure |
| `unflatten` | Restore flat keys to nested |
| `diff` | Structural diff of two files |
| `csv` | Array of objects → CSV |
| `stats` | Structure overview with numeric stats |
| `schema` | Infer type schema from data |
| `filter` | Filter array with Python expression |
| `merge` | Deep merge multiple JSON files |
| `count` | Count items |
| `type` | Show type at path |

## License

MIT
