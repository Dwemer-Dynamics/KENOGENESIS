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

## Private snapshots

`preview_catalog_snapshot`/`apply_catalog_snapshot` (Overview → Local catalog) keep an exact
copy of the configured catalog inside the project's private `.kenogenesis` folder. The
snapshot hash is part of the project revision. When the configured catalog is missing or
invalid, references use the snapshot and the browser says so; otherwise the configured
catalog is used and the snapshot is reported as current or stale. Snapshots are never
exported, and taking one does not change what you may redistribute.

No catalog or extractor is bundled. Do not publish extracted game data without
verifying its distribution rights.

## Importing local reference .c5m files

`preview_catalog_import` / `apply_catalog_import` (CLI `catalog import`, or
Overview → Local catalog → Import reference catalog in the browser) build a
catalog from local reference files written in mod format, such as community
"Monster/Weapon/Class/... Data vX.YY.c5m" files you have obtained yourself. The
browser sends the selected files' contents; it never asks the server to read a path.

- The import is a new file, `catalogs/<name>.json` inside the workspace. Existing
  catalogs are never overwritten. Saving also points the project at the new
  catalog (with a `project.json` backup), so the project revision changes.
- `game_version` is the version the files describe, not the installed game. A
  version printed in a filename that differs from it, and a difference from the
  project's target version, are reported. Catalog matches then stay unverified.
- `sources` records each file's name, size, SHA-256 and row counts; your
  `provenance` text should name the origin, exact revision and license.
- One row per opener (`newmonster`, `newweapon`, `newclass`, `newritual`,
  `newitem`, `selectterr`, `selectclass`, `selectritual`). `id` is the printed
  index comment (`id_source: printed_comment`) or the numeric `select` argument
  (`id_source: argument`). `select` openers other than `selectterr` become
  `<kind>_selection` rows, so they do not make definition names ambiguous.
- Duplicate names stay separate rows, with `name_ordinal` (file order) and
  `name_count`. The ordinal is not proof of the engine's selection offset.
- `source_file`, `source_line`, `source_offset` and `source_end` locate each row's
  exact bytes. `statements` holds every explicit command verbatim. Commands that
  appear once with one argument are also copied as fields such as `hp`.
- Commented lines (for example untranslated `# fx` notes), game defaults and
  copied values are not imported or inferred. Strings that continue over raw line
  breaks stay verbatim in `statements`, are listed in `multiline_commands` and are
  not copied as fields. The engine's reading of raw line breaks is not verified.
