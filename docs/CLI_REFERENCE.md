# CLI and core operations

All commands require an existing `--workspace DIRECTORY` before the subcommand.
`python -m kenogenesis --help` shows shortcuts. Operations emit an `ok` envelope:
`{"ok":true,"result":...}` or `{"ok":false,"error":{"code":...,"message":...}}`.
Failures exit nonzero. The `validate` shortcut exits 2 for static errors.

Use the complete shared API through:

```text
python -m kenogenesis --workspace DIR run OPERATION --args-file request.json
```

The request file is a UTF-8 JSON object. It handles multiline source without shell
quoting. For example, a field preview request:

```json
{
  "project": "my_mod",
  "expected_revision": "replace-with-current-revision",
  "object_index": 0,
  "command": "hp",
  "arguments": [9]
}
```

| Operation | Arguments |
|---|---|
| `list_projects` | none |
| `create_project` | `slug`, optional `name`, `target_version` |
| `build_example` | optional fresh `slug`, `target_version` |
| `import_project` | `slug`, `source`, optional `declared_assets`, `target_version` |
| `project_view` | `project` |
| `lookup_command` | optional `command`, `context` |
| `search_game_data` | `project`, optional `query`, `kind`, `limit` |
| `preview_patch`, `apply_patch` | `project`, `expected_revision`, exact unique `old`, `new` |
| `preview_fields`, `apply_fields` | `project`, `expected_revision`, `object_index`, `command`, `arguments` |
| `configure_project` | `project`, `expected_revision`, optional `dependencies`, `catalog`, `target_version`, `declared_assets`, `preview` |
| `validate_mod` | `project` |
| `compatibility` | `project`, optional `baseline` manifest path relative to project |
| `export_mod` | `project`, `expected_revision`, optional `format`: `zip` or `folder` |

`configure_project` defaults to preview. Set `preview:false` to apply. Dependency
projects must be a flat list inside the same workspace. Catalog paths are relative
to that workspace; an empty string clears the catalog. Additional asset paths are
relative to the mod folder and must exist. These settings do not activate mods in
the game. A project may be referenced as a dependency only with no dependencies
of its own; list the complete flat set explicitly.

Tool policy limits: 16 MiB per input file, 32 dependencies, 8192 pixels per image
dimension, 1 MiB per browser mutation. These are protective implementation limits,
not CoE5 engine limits. Unknown command arguments are not validated.

`compatibility` inspects declared inputs; it cannot prove actual mod activation,
equal-priority order, arbitrary effects or multiplayer compatibility. Baseline
comparison reports definition-order risks without promising save compatibility.

The browser's GET requests are read-only. Mutations are POST operations protected
by loopback Host/Origin checks and a per-server token. It does not expose arbitrary
filesystem reads, execute source commands or install content into the game.
