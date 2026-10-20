# Authoring with KENOGENESIS

1. Establish the user's project, content brief, target game version and testing scope.
   Inspect existing projects. Never seed or replace a user's mod without a request.
   For a new faction, plan its gameplay loop and original artwork from the start
   and write the private design record before the first source edit (see below).
2. Read `project_view` (or the resolved `project_model`). Keep its `revision`. Research commands with
   `lookup_command`, which covers the whole pinned manual index: `curated` entries have
   argument checks; `documented` entries (`validated: false`) are preserved but not checked.
   Inspect the official manual for an `unknown` name or when coverage is absent.
3. Use `search_game_data` only with provenance/version disclosures. A missing
   catalog leaves vanilla references unverified. Never invent a catalog entry.
4. Use `preview_fields` for explicit singleton commands. For repeatable commands,
   definitions, donor resets or unsupported fields, use `preview_patch` with an
   exact unique old span. Preserve unknown commands, order, comments and encoding.
5. Inspect the returned diff and validation. Apply the identical request using
   `apply_fields` or `apply_patch`. If revisions conflict, reread; keep the draft.
6. Run `validate_mod` and `compatibility`. Fix errors and explain warnings and
   unverified coverage. Check the prior export manifest when changing an existing
   mod; adding/reordering definitions can affect saves.
7. When export is in scope, export the reviewed revision. Inspect the manifest
   and package contents.
   Referenced files and `declared_assets` are the only additional payload.
   An export meant for installation must first pass the
   [command support and deployment gate](#command-support-and-deployment-gate).
8. Report source revision, hashes, static checks, browser checks, engine evidence
   and untested behavior separately. No static result proves balance. Record
   observations with `record_evidence` only when the user asks; use the
   `game_user_reported` category only for what the user saw in the game. Its
   optional `observation` fields (version, tester, class, opponents, map, turns,
   outcome, reference SHA-256) are the user's report; never fill them yourself.
   For a new faction, finish with the coverage table from the design record.

For a new faction, plan with [FACTION-DESIGN.md](FACTION-DESIGN.md) and review
`design_report`. `compare_units` and `compare_classes` show source-backed values
and differences only; unknown cells stay unknown, and none of them computes balance.
`compare_classes` also returns a `dashboard` of the same figures (roster variety,
cost and stat spreads with unknown counts, ritual access); it is not a score.
Use `catalog_page` and `catalog_entry` to browse the local catalog read-only.
Private planning notes may live in `<project>/docs/*.md` (`list_project_docs`,
`read_project_doc`); they are read-only and never exported.

## Building a new faction

Applies to the `create` and `build` authoring modes, not to an artwork-only pass.

1. Read [FACTION-DESIGN.md](FACTION-DESIGN.md). Choose one to three relevant
   vanilla comparators and label every reference with its source and version.
2. A theme-only request leaves the design to you: make reasonable decisions
   without asking for routine approval, and record the reasons. Explicitly
   requested features are requirements.
3. Before the first guarded source edit (after `create_project` in `create`
   mode), write the private design record, such as `<project>/docs/design.md`:
   comparators; identity, playstyle and intended weaknesses; the resource loop
   (access, collection, income, spending, replenishment); recruitment with
   chance, count, gold, gold die, iron and extra costs kept separate, and native,
   conditional and hired offers distinguished; home and start; early, middle and
   late progression that fits the archetype; combat casting, ritual knowledge
   and learning, and items as separate decisions; and the coverage table. It is
   a private note, not a product file; it is never exported.
4. Define in reference order (FACTION-DESIGN [Order matters](FACTION-DESIGN.md#order-matters)):
   for example `newritpow` before units whose `power` uses a relative school,
   and named monsters, weapons and terrain before the lines that name them.
   Check each command's signature with `lookup_command`; label documented
   commands that are not argument-checked as documented-but-unvalidated.
5. Audit reachability: every new unit, item, ritual, upgrade and form has an
   acquisition route with prerequisites and costs. Trace summons and forms through
   reachable parents, support definitions through their consumers, and unlocks
   from the starting state without circular prerequisites. Do not make every
   summon known from the start unless the record gives that knowledge policy
   a reason.
6. Report every coverage row with its status. `implemented` means authored,
   reachable and statically valid with its artwork; runtime behaviour nobody has
   observed stays `unverified in game`. A requested feature that is not done is
   `missing` or `blocked`, never an intentional omission. Static, browser and
   package checks do not show that the faction is playable or balanced.

Follow the user's scope for export and testing. Export when the task includes it;
never install, launch the game, upload or publish without separate
authorization, and do not add new approval steps for work the user already asked for.

## Command support and deployment gate

This is a written procedure for agents and reviewers. Nothing in KENOGENESIS
enforces it automatically, and following it reduces but cannot rule out engine
rejections.

**Scope.** It applies to every command line you author or change, in any
context (classes, monsters, weapons, items, rituals, terrain). Preserving
unknown commands is import and round-trip behaviour; it is not approval to
author them or to deploy them.

**Authoring check.** Before writing a new command, confirm its exact CoE5
spelling, the object context that accepts it, its arguments and the game version
from the official CoE5 manual (the pinned copy and `lookup_command`). Do not
transfer Dominions commands or syntax. Registry coverage is incomplete in both
directions: a `curated` entry is argument-checked; a `documented` entry, or a
name the registry lacks or flags for this context, needs a manual reading. The
manual can permit a command the registry does not cover for that context (for
example, monster commands it allows on magic items), so never delete a flagged
line on registry absence alone, and never invent a substitute command.

**Deployment gate.** Before an export intended for installation or deployment:

1. Read every `validate_mod` error, warning and `unverified`/`unknown_command`
   diagnostic individually. `static_ok` and a zero error count are not enough.
2. Resolve each newly authored command in that list to one of:
   - *documented*: the official manual gives its exact spelling, context and
     signature. Note the source, page and context in the private project record,
     then it may pass manual review.
   - *blocked*: unknown, or known only from a release note or announcement
     without a documented signature. It blocks normal deployment until
     documented syntax or exact-version game evidence exists. Fix or remove it in
     the source through the guarded edit flow, or keep the export as
     review-only.
3. With explicit authorization, a blocked command may be tried only as an
   experiment in an isolated install, with the uncertainty recorded. The result
   is evidence for that game version only.

Do not weaken or bypass validation, globally reject unknown imported commands,
or drop them to pass the gate. Separately authorized validator improvements are
outside this procedure. An export for review or archive may preserve unknown
commands but must not be described as ready to install.

**Freeze and deploy.** Tie the review to one source revision and its export
hashes, and keep the backup the guarded flow creates. Any edit invalidates the
review: revalidate, re-export and re-inspect. When installation is authorized,
verify that the installed files match the reviewed export hashes. When game
testing is authorized, explicitly enable the mod and start a new game with the
mod's class; reaching the main menu proves nothing. Record the game version,
source revision, install hashes and any engine error verbatim. Nothing is engine
verified without that matching evidence (see [VALIDATION.md](VALIDATION.md#coe5-acceptance)).

**After an engine command error.** Do not patch only the reported line. Audit
all authored source for the same command and for related commands of the same
origin or context, correct them through guarded patches, then revalidate,
re-export, redeploy when authorized and re-test the exact new revision.

## Default artwork scope

A request to build a new faction includes its complete original artwork by
default, even when the user describes only a theme. Follow
[ASSET-RULESET.md](ASSET-RULESET.md): an original idle/attack pair for every new
troop, commander, summon and alternate form, an original thematic mod banner
(`icon`), and only those extra visuals the content uses through documented image
commands (new item icons, new custom terrain). CoE5 has no flag or spell icon
command; do not invent one. Built-in sounds are the default.

Generate bitmap art with your built-in imagegen. KENOGENESIS has no image
generator, AI provider or credentials, and the browser's original-art brief
generates nothing by itself. Follow the brief's authoring mode: `create` runs
`create_project`; `build` means the project already exists with no class or
monster definitions, so build the faction there without `create_project`;
`art` changes artwork only. Keep prompts, raw outputs, conversion records and
the asset checklist private and out of the export.

Stock, copied or default images are placeholders unless the user explicitly asks
for reuse or a prototype. Before completion, audit both poses, native size,
alpha, references and the export manifest. If art is missing or generation is
blocked, name the unfinished assets instead of silently borrowing stock art.
Existing files are never overwritten; add new paths through the guarded review.

Use the private source manifest and `scripts/prepare-assets.py` described in the
asset rules for repeatable unit conversion. Run its read-only `--verify` after
conversion. Compare against private, versioned CoE5 references and fix named visual
defects; do not copy Dominions facing, palettes or image-command requirements.
Keep optional art-tool dependencies separate from the browser/core runtime.

## Game-specific constraints

CoE5 commands are not hash-prefixed. A hash starts a comment. Do not translate a
Dominions `.dm` using search-and-replace. CoE5 names, duplicate-name offsets,
automatic identities, rituals and command contexts require their own handling.
Do not allocate Dominions-style numeric monster/nation IDs.

New classes need correctly ordered identity, a real home citadel and starting
forces. A numeric terrain reference existing is not enough to prove it is a
valid home citadel. Ritual-school offsets and summon strings require special
attention. Use the official manual's update guidance and verify in the game.

Structured fields edit explicit authored lines only: a field shows and changes
the value written in this block, never a copied one. Separately, the read-only
browse model (`project_model`, `compare_units`, `compare_classes`) resolves a
few scalar values (hit points, magic resistance, strength, armor, morale, rank)
from an explicit local `copystats` donor or a uniquely named catalog row and
labels their source. It also reports attacks explicitly stated by a supported
copy donor, with partial coverage labelled. Copied abilities, general command
inheritance and game defaults are not resolved. Removing an inherited ability may require destructive
resets. Never introduce a reset to make a simple field editor appear to work.

## Privacy

Keep projects and assets in a private explicit workspace, not public examples.
Catalogs and extracted resources remain local. Before any future publication,
inspect an explicit source-file allowlist and the full package file list.
Exporting is not publishing or permission to upload to Steam Workshop.
