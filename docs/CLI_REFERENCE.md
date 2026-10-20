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
| `lookup_command` | optional `command`, `context`, `query` (name or summary text), `status` (`curated` or `documented`), `limit` (default 200, at most 1000) |
| `search_game_data` | `project`, optional `query`, `kind`, `limit` |
| `preview_patch`, `apply_patch` | `project`, `expected_revision`, exact unique `old`, `new` |
| `preview_fields`, `apply_fields` | `project`, `expected_revision`, `object_index`, `command`, `arguments` |
| `configure_project` | `project`, `expected_revision`, optional `dependencies`, `catalog`, `target_version`, `declared_assets`, `preview` |
| `validate_mod` | `project` |
| `compatibility` | `project`, optional `baseline` manifest path relative to project |
| `export_mod` | `project`, `expected_revision`, optional `format`: `zip` or `folder` |
| `preview_block_edit`, `apply_block_edit` | `project`, `expected_revision`, `object_index` (-1 for mod-wide), `changes`, optional `mode`: edit/new/delete, `opener` |
| `preview_import_upload`, `import_upload` | fresh `slug`, `source`: filename/base64, optional `assets`: path/base64 entries, `name`, `target_version` |
| `preview_art_upload`, `apply_art_upload` | `project`, `expected_revision`, `object_index` (a unit), and either `frames`: one or two `{frame: spr1/spr2, asset_path, content}` entries, or the single-frame `frame`, new `asset_path`, base64 `content` |
| `list_exports` | `project` |
| `preview_workshop_stage`, `stage_workshop_bundle` | `project`, `expected_revision`, `export_id` of an existing export of that revision, `banner`: filename/base64 of a square PNG, optional `visibility`: `private` (default), `friends` or `public`. Preview writes nothing; staging saves a new private ZIP under `.kenogenesis/workshop-stages/` and never uploads |
| `list_workshop_stages` | `project` (read-only stage receipts with each bundle hash re-checked) |
| `preview_catalog_import`, `apply_catalog_import` | `project`, `expected_revision`, `game_version`, `provenance`, new catalog `name`, and either `files` (filename/base64) or local `paths` (CLI/MCP only) |
| `project_model` | `project` (read-only resolved model: objects, edges, readiness, provenance, catalog and snapshot state) |
| `compare_units` | `project`, `object_index` (a unit), `references`: 1-4 of `{object_index}` or `{catalog_index}` (read-only) |
| `compare_classes` | `project`, `class_index` (a class), `references`: 1-4 of `{object_index}` (another class) or `{catalog_index}` (a catalog class row) (read-only) |
| `design_report` | `project`, optional `class_index` (read-only roster, recruitment, start and ritual access per class) |
| `list_project_docs`, `read_project_doc` | `project`, and for reading `name` of one top-level `.md` file in `<project>/docs/` (read-only private notes) |
| `preview_catalog_snapshot`, `apply_catalog_snapshot` | `project`, `expected_revision`, optional `action`: `capture` (default) or `release` |
| `catalog_page` | `project`, optional `query`, `kind`, `sort` (`name`, `id`, `kind`), `order`, `page`, `per` (at most 100), `conditions` (up to eight `{field, op, value}`) (read-only, the browser catalog's view) |
| `catalog_entry` | `project`, `index` of one catalog row (read-only; includes this project's lines that reference it) |
| `list_evidence` | `project` (read-only; never creates files) |
| `record_evidence` | `project`, `expected_revision`, `category`, `summary`, optional `details`, `reference`, `references`, `observation`, `preview` (default true) |

Unit artwork: send idle and attack together in `frames`, preview, then apply the
identical request. Each new path must not exist. The preview returns `frames` (per
frame `facts` including `warnings`, and a PNG `preview`), `current` (facts for the frames
kept from the source), `pair_warnings`, `notes`, `changes` and the diff. Apply writes
every new file and the source change together; a stale revision or failed write
removes the new files. The patch removes `copyspr` and keeps `spr1` then `spr2`
after the last `copystats`. A single-frame request is the same operation with one
entry: an idle-only upload keeps an existing `spr2` after the new `spr1`; `spr2`
alone needs an explicit `spr1` that no later copy replaces; a unit with `copyspr`
needs both frames unless it has its own `spr2`. Frames must be 32x32, 64x64 or
128x128, 8-bit RGBA PNG or 24/32-bit TGA. Empty frames and partial alpha are
refused as KENOGENESIS authoring policy, not as documented engine rules. Banner,
item and terrain images have no upload operation; use a new file plus
`preview_block_edit`/`apply_block_edit`.

`python -m kenogenesis --workspace DIR catalog import PROJECT --revision REV --name NAME
--game-version 5.22 --provenance TEXT --source FILE.c5m [--source ...] [--apply]` reviews
or saves a reference catalog (see `CATALOG.md`). Without `--apply` nothing is written.

`lookup_command` covers the whole pinned CoE5 Modding Manual 5.36 index (891 command and
context pairs, 845 command names). Each entry has `command`, `context`, `status`,
`validated`, `signature`, `summary`, `arguments` (manual names with `type` s/i/r, `optional`
and any documented `min`/`max`), `manual_page` and `source`. `curated` entries
(`validated: true`) keep their original schema fields, including the checked `args` codes,
`note` and `repeat`. `documented` entries (`validated: false`) come from the manual index
only: KENOGENESIS preserves them and does not check their arguments. With `context`, a
named command that the manual documents as global (block openers, mod-wide commands)
also matches and says `matched_via: "global"`. An unknown name returns no entries and
`status: "unknown"`; an unknown context returns `status: "unknown_context"` and the list
of `contexts`. Results report `total`, `counts` and `truncated`. The `commands` shortcut
takes the same filters: `commands [NAME] [--context C] [--query TEXT] [--status S] [--limit N]`.

`catalog_page` and `catalog_entry` read the project's configured local catalog (or its
private snapshot) exactly as the browser catalog does; they extract and write nothing.

`project_view` keeps its original shape. `project_model` returns the same resolved model as
the browser's project page (`GET /api/projects/<slug>`, also `GET /api/project_model`).

`preview_block_edit` with `mode: "new"` accepts `insert_before` (a block index) and one
`linked` edit `{object_index, changes}` of an existing block. Both are reviewed and saved as
one source change; the new block is placed before the linked block so it is defined first.
The browser uses this to add a new unit with one class row (`addunitrec`, `addcomrec`,
`addmercrec`, `addstartunits` or `addstartcom`). Summon strings are not connected this way.
Previews include `form_changes` when an edit moves the target of an alternate-form command.

Catalog snapshots copy the configured catalog's exact bytes to
`<project>/.kenogenesis/catalog-snapshots/<sha256>.json` (new or byte-identical only) and record
it in `project.json` with a backup. Its hash joins the project revision. Status is `current`,
`stale` (configured catalog changed), `offline` (configured catalog unavailable; references use
the snapshot), `invalid` or `unused` (no catalog configured). `release` removes the record and
keeps the file. Snapshots are never exported.

Evidence records are new files under `<project>/.kenogenesis/evidence/`, linked to the revision
checked under the project lock. Categories: `static`, `browser`, `packaging`,
`game_user_reported`. Text is plain and bounded (summary 200, details 4000, reference 200
characters). Records never set `engine_verified`, do not change the project revision and are
never exported. Optional `references` holds up to eight `{kind, label, sha256}` entries:
`kind` is `screenshot`, `log`, `save`, `report`, `package` or `other`, `label` is plain text
up to 200 characters and `sha256` is optional (64 hex characters). They are the user's own
labels for files kept privately; nothing is attached, opened or dereferenced. Empty rows
are dropped; a hash needs a label. The single `reference` text remains supported. A `game_user_reported` record may add an optional `observation` with
`game_version` (as reported, not checked), `tester`, `class_played`, `opponents`, `map`,
`outcome` (plain text), `turns` (0-100000) and `reference_sha256` (64 hex characters of a
file the user keeps; nothing is attached). Other categories refuse these fields, and the
record states that the user, not KENOGENESIS, observed the game. Older records stay readable.

`compare_units` columns also carry `sprites` (local idle/attack file, URL and native size;
`null` for catalog rows, which hold no images), `recruitment` (class rows naming the unit,
from this mod and, for a uniquely named catalog row, catalog class rows) and `rituals`
(`power`/`allrit` as stated). `compare_classes` returns `rows` of per-column cells
`{value, note}`: roster counts, chance, count, gold, gold die, iron and extra costs as
written, income bonuses, and ritual schools through the class's units. A `null` value is
unknown or not covered, never zero. Neither operation simulates recruitment or scores balance.
`compare_classes` also returns `dashboard`: per column a `marker` letter, `roster` (distinct
unit names per recruitment group and starting unit types; `recruitment_complete` is false for
selected classes and all catalog rows; other blocks and game defaults are not merged),
`costs` and `stats` (`min`, `max`, `known` and `unknown` counts of chance, gold, gold die,
iron, and recruitable units' hit points, strength, armor, magic resistance and morale),
`income`, `rituals` (schools, rituals of this mod, resources; `resources` is `null` for
catalog columns) and `units` (each recruitment row with its explicit stats and their
source: this mod, a uniquely named catalog row, or unresolved). `help` explains the raw
figures. References are required for both comparison operations.

`export_mod` returns `export_id`, `format`, `files` (path, SHA-256, bytes), `archive_sha256`
(ZIP only), `manifest_path`, `revision`, `dependencies`, `counts` and static `warnings`.

`list_project_docs`/`read_project_doc` read only top-level `.md` files of `<project>/docs/`:
exact-case names, up to 256 KiB, UTF-8, no links, subfolders or names suggesting secrets or
backups. They never write, and these notes are never exported. The browser serves them at
`GET /api/projects/<slug>/docs` and `GET /api/projects/<slug>/docs/<name>`.

`configure_project` defaults to preview. Set `preview:false` to apply. Its result includes
`compatibility_impact`: the static cross-mod and reference findings that the candidate
settings add, remove or keep, and the declared order before and after. It is computed
from in-memory snapshots, so a preview writes nothing; it never says which mod wins an
overlap, because the engine's order is not verified. Dependency
projects must be a flat list inside the same workspace. Catalog paths are relative
to that workspace; an empty string clears the catalog. Additional asset paths are
relative to the mod folder and must exist. These settings do not activate mods in
the game. A project may be referenced as a dependency only with no dependencies
of its own; list the complete flat set explicitly.

Tool policy limits: 16 MiB per input file, 32 dependencies, 8192 pixels per image
dimension, 1 MiB per ordinary browser mutation. Upload bodies allow 12 MiB of JSON;
imports contain at most 8 MiB of decoded files and artwork is limited to 2 MiB.
These are protective implementation limits,
not CoE5 engine limits. Unknown command arguments are not validated.

`compatibility` inspects declared inputs; it cannot prove actual mod activation,
equal-priority order, arbitrary effects or multiplayer compatibility. Baseline
comparison reports definition-order risks without promising save compatibility.

`serve` accepts `--port` and `--open-browser`, which opens the exact loopback address after
the server binds. `GET /api/meta` reports the serving interpreter (`runtime.python_executable`,
`python_version`, `platform`) so the browser's command-line instructions name the same Python.
`mcp` needs the optional SDK; without it the command writes a diagnostic naming the
interpreter to standard error (never to the protocol stream) and exits with code 3.

The browser's GET requests are read-only. Mutations are POST operations protected
by loopback Host/Origin checks and a per-server token. It does not expose arbitrary
filesystem reads, execute source commands or install content into the game.
