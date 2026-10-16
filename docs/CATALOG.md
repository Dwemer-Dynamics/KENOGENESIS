# Optional private catalog

KENOGENESIS can work without a catalog. Vanilla references then remain unverified.
Store reference data privately inside the workspace and configure its relative
path through `configure_project` or Project settings.

```json
{
  "game_version": "5.36",
  "provenance": "Describe source, extraction method, license and date here",
  "rows": [
    {"kind": "monster", "name": "Synthetic documentation example", "id": 123}
  ]
}
```

This is a schema example, not actual game data. Supported reference kinds include
`monster`, `weapon`, `terrain`, `class` and `ritual`. Matching is exact for names.
Catalog data is not authoritative proof of engine behavior or full coverage.
Duplicate matches stay unverified; unmatched references are not declared missing.
A catalog/target version mismatch is reported. The catalog hash participates in
the project revision but catalog bytes are never included automatically in exports.

No catalog or extractor is bundled. Do not publish extracted game data without
verifying its distribution rights. Import tools are deliberately separate from
the initial authoring core.
