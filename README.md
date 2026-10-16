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

Open **http://127.0.0.1:8766**. Alternatively:

```powershell
.\start.ps1 -Workspace .\work -Python python
```

Choose your installed interpreter with `-Python` if `python` is unavailable.
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

## Supported first slice

- New/selected classes, monsters, weapons and rituals, with curated command help.
- Source-preserving patching and singleton field editing, with preview and backups.
- Revision checks covering source, settings, declared assets, dependencies and catalog.
- Static argument, reference, order, metadata and asset checks.
- Declared-mod conflict reports and comparison with a previous export manifest.
- PNG/TGA, raw sample and font container checks; opaque `.coem` map packaging.
- ZIP/folder exports with explicit payload lists, hashes and validation manifests.

The command registry is a subset of the official **5.36 modding manual**, not a
complete CoE5 implementation. Unknown commands remain intact and are unverified.
Vanilla references need an optional local catalog; missing catalog data does not
mean that a reference is invalid. Inherited stats and effects are not simulated.
Arbitrary new combat-spell creation and map generation are outside this build.

## Agent workflow and export

See [agent usage](docs/AGENT_USAGE.md), [CLI/API reference](docs/CLI_REFERENCE.md),
[validation and game checks](docs/VALIDATION.md) and [catalog format](docs/CATALOG.md).

```powershell
python -m kenogenesis --workspace .\work project inspect my_mod
python -m kenogenesis --workspace .\work validate my_mod
python -m kenogenesis --workspace .\work export my_mod --revision <revision-from-inspect>
```

Exports are fresh files under the project's `exports/` directory. They include
only the `.c5m`, referenced assets and explicit additional files. Dependencies are
listed in the manifest and must be installed separately. Backups and catalogs are
never copied automatically. **Static success is not proof of loading, gameplay,
save compatibility or balance.**

## Optional MCP

Install only if your agent client needs Model Context Protocol:

```powershell
python -m pip install ".[mcp]"
python -m kenogenesis --workspace C:\Private\CoEProjects mcp
```

Use the source folder as the process working directory, an absolute workspace,
and the same interpreter where MCP is installed. Standard output carries the
protocol; diagnostics use standard error. Configuration examples are in
`examples/`. CLI and browser operation do not require MCP.

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
