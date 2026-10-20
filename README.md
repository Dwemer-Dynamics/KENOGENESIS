# KENOGENESIS

Local, agent-assisted mod authoring for **Conquest of Elysium 5**.

Inspect `.c5m` source, make reviewed changes, check supported commands and assets,
and export a fresh mod package. A command line, local browser and optional MCP
server share the same core. Codex or Claude supplies the AI; KENOGENESIS does not
require an AI account to browse, edit, validate or export.

## Start locally

Requires Python 3.11 or later. The core and browser use the Python standard library.
Run these commands in this source folder. Choose a private project workspace:

```powershell
New-Item -ItemType Directory -Path .\work -Force
python -m kenogenesis --workspace .\work project create my_mod --target-version 5.36
python -m kenogenesis --workspace .\work serve
```

Open **http://127.0.0.1:8766**. Alternatively, on Windows:

```powershell
.\start.ps1 -Workspace .\work -OpenBrowser
```

`-Workspace` is required: a private folder for your projects, created if it does
not exist. The launcher uses `.venv\Scripts\python.exe` in the KENOGENESIS source folder, then
`py -3`, then `python`, and needs Python 3.11 or newer. Pass `-Python <path or
command>` to choose an interpreter explicitly; a missing or older one stops with
a message and exit code 2. `-Port` changes the port and `-OpenBrowser` opens
the loopback address once the server is running. Paths with spaces are passed
through unchanged. Nothing is installed and no settings are changed.
The browser creates and edits workspace projects; it never installs mods into the
game. To import an existing mod, keep its matching folder/file names:

```powershell
python -m kenogenesis --workspace .\work project import my_mod --source C:\Mods\my_mod\my_mod.c5m
```

Import copies referenced assets, not the whole source directory. Use the core
`import_project` operation with `declared_assets` for additional map/support files.

For an independently authored mechanical example in a fresh project:

```powershell
python -m kenogenesis --workspace .\work example --target-version 5.40
```

Use your actual installed version. This example uses a custom test citadel at
terrain ID 500, a unit, weapon and gold-cost summoning ritual. Check that ID against
other enabled mods. Its flat banner and geometric citadel are test assets; unit
appearance is inherited from vanilla references. It is not a balanced faction or
a custom-art showcase. Export it, then follow the separate in-game checklist.

## Default artwork for new factions

New factions get complete **original artwork** by default: an idle and attack
sprite for every new troop, commander, summon and alternate form, plus an
original mod banner and any item or terrain images the content needs. Stock or
copied sprites are placeholders unless you explicitly ask for reuse or a
prototype. Your agent generates the images with its built-in image generation;
KENOGENESIS has no AI provider and sends no requests. The browser prepares an
original-art agent brief from Get started and from each project's Overview. See
[asset rules](docs/ASSET-RULESET.md).

The optional `scripts/prepare-assets.py` tool converts a private, measured source
manifest into unit pairs with a shared body scale, binary alpha, aligned feet and
a native/3x contact sheet. Its `--verify` mode checks byte-for-byte reproduction.
It requires the optional `art` extra (Pillow), not needed by the browser or core.
See the asset rules for the manifest, CoE5 style guidance and review limits.

## Browser workshop

The browser uses Kosmokrator's project sidebar, routed sections, content cards,
unit sheets and review workflow with the KENOGENESIS Void theme. Browse classes,
units, weapons, ritual schools, rituals, items, terrain and events. Use More for
Source, Assets and Docs. Drafts stay in memory across sections; reviewed saves
create backups and receipts. Export includes the saved revision only.

See the [browser guide](docs/WEB-BROWSER.md) for import, editing, artwork,
catalog filters, conflict recovery and export downloads.

## Authoring and validation

- New/selected classes, monsters, weapons and rituals, with curated command help.
- Source-preserving patching and singleton field editing, with preview and backups.
- Revision checks covering source, settings, declared assets, dependencies and catalog.
- Static argument, reference, order, metadata and asset checks.
- Declared-mod conflict reports and comparison with a previous export manifest.
- PNG/TGA, raw sample and font container checks; opaque `.coem` map packaging.
- ZIP/folder exports with explicit payload lists, hashes and validation manifests.
- Labelled rows for recruitment, starting forces, attacks and ritual costs/strings, with
  local and catalog reference checks; documented `new`/`select` and event openers.
- Alternate forms (manual p.18) resolved by source order, documented abilities and
  explicitly stated donor attacks on unit sheets; unknown values stay unknown.
- A per-class Design workspace, read-only unit comparison, private catalog snapshots
  and private, revision-linked evidence records. No balance score is computed.

The command registry is a subset of the official **5.36 modding manual**, not a
complete CoE5 implementation. Unknown commands remain intact and are unverified.
Vanilla references need an optional local catalog; missing catalog data does not
mean that a reference is invalid. Explicit local donor or catalog values can be
shown; game defaults and engine effects are not simulated.
Arbitrary new combat-spell creation and map generation are outside this build.

### CoE5 5.41

Illwinter's CoE5 5.41 release notes (Steam news, 19 Oct 2026, gid 1846651706689977)
announce new commands and raised engine limits. The official modding manual
available then was still 5.36 and documents none of the new commands, so:

- `brigand`, `pickupbrigands`, `adventurer`, `pickupadvent`, `partyleader` and the
  event trigger `+minunitshere` are listed with status `announced`. Their
  signatures, argument counts and (except the trigger) contexts are unknown; they
  are preserved verbatim, reported as unverified and never argument-checked.
- For targets 5.41 or later, `selectterr` 500-1999 opens a new custom terrain.
  This range is inferred from the announced 2000 terrain slots and the reserved
  0-499; it is not documented engine behaviour. Older, unset or unrecognized
  target versions keep the manual's 500-999.
- The other raised limits (monsters, sprites, recruitment lists and limiters,
  ritual effects and strings, terrain groups) are shown for reference only and
  are not enforced. KENOGENESIS's own file, upload and listing caps are tool
  policies and did not change.
- The bug fixes in the notes are game changes; KENOGENESIS neither implements nor
  checks them.

## Agent workflow and export

See [faction design](docs/FACTION-DESIGN.md), [agent usage](docs/AGENT_USAGE.md), [CLI/API reference](docs/CLI_REFERENCE.md),
[validation and game checks](docs/VALIDATION.md) and [catalog format](docs/CATALOG.md).

```powershell
python -m kenogenesis --workspace .\work project inspect my_mod
python -m kenogenesis --workspace .\work validate my_mod
python -m kenogenesis --workspace .\work export my_mod --revision <revision-from-inspect>
```

Exports are fresh files under the project's `exports/` directory. They include
only the `.c5m`, referenced assets and explicit additional files. Dependencies are
listed in the manifest and must be installed separately. Backups, catalogs, catalog
snapshots and evidence records are never copied automatically. **Static success is not proof of loading, gameplay,
save compatibility or balance.**

## Optional MCP

Install only if your agent client needs Model Context Protocol:

```powershell
python -m pip install ".[mcp]"
python -m kenogenesis --workspace C:\Private\CoEProjects mcp
```

Use the source folder as the process working directory, an absolute workspace,
and the same interpreter where MCP is installed. Standard output carries the
protocol; diagnostics use standard error. Without the optional package, `mcp`
names the interpreter that lacks it on standard error and exits with code 3.
Configuration examples are in `examples/`. CLI and browser operation do not
require MCP.

## Checks

```powershell
python -m unittest discover -s tests -v
node --check kenogenesis/web/app.js
```

The focused tests exercise write/export safety and adapter parity. See
`docs/VALIDATION.md` for the separate browser and in-game acceptance checks.

## Foundation and license

Built from Kosmokrator's verified local-first core patterns. Its path and error
primitives are adapted with attribution in [NOTICE](NOTICE). CoE5 parsing and
schemas are separate. Licensed under GPLv3; see [LICENSE](LICENSE).

KENOGENESIS is a project name, not an official Illwinter game term. The game,
manuals and referenced vanilla content belong to their respective owners.
