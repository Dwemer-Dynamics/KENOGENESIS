# Evidence and acceptance checks

## Automated static checks

Run `python -m unittest discover -s tests -v`. The focused suite checks:

- CoE5 comments and object parsing rather than Dominions syntax.
- Preview purity, byte preservation, newline/BOM preservation and backups.
- Stale revisions after source, asset, settings, catalog and dependency changes.
- Writer locking and concurrent edits.
- Class metadata and forward-reference errors.
- Unknown command preservation and unverified diagnostics.
- Case-sensitive paths, traversal rejection, export allowlists and fresh outputs.
- Opaque map packaging, definition-order warnings and CLI/HTTP parity.
- Browser mutation rejection without origin/token authority.
- Linked new-unit/class transactions, catalog snapshot guards and private evidence records.
- Settings previews that report compatibility impact without writing, bounded private project
  notes (no traversal, secrets-like names, oversize files or export), validated optional
  game-observation fields, rejected malformed catalog conditions, and comparisons that keep
  unknown values unknown rather than zero.

Evidence records (Evidence section, `record_evidence`) keep static, browser, packaging and
user-reported game observations apart. They are linked to one revision, stay private and
never mark a mod as engine verified.

Run `node --check kenogenesis/web/app.js` and Python compile checks. Optional MCP
needs an SDK-backed protocol smoke test, not just successful imports.

## Browser acceptance

At desktop and narrow widths, exercise empty workspace, create/load, object search,
command help, missing catalog, structured field preview/save, source preview/save,
settings preview/save, stale edit handling, static errors and fresh export. Check
keyboard navigation, focus visibility, labels, overflow and preserved drafts.
Record screenshots and browser errors from the exact tested source revision.
HTTP/API tests cannot stand in for browser visual or interaction evidence.
Browser checks may preview a game observation form but must never save a
`game_user_reported` record for a game nobody played.

## CoE5 acceptance

Use an isolated game-data location and a uniquely named test game. First verify
the installed engine version and how the actual executable isolates user data.
Do not guess a data-directory option or copy into existing user mods/saves.
If isolation cannot be established, record the blocked runtime checks rather than
changing the user's existing configuration.

Test an independently authored small class/unit/weapon/ritual example (a
smoke test, not full-faction coverage; see [Full-faction acceptance](#full-faction-acceptance)):

1. Verify exact exported file hashes at the isolated install destination.
2. Discover/enable the mod and start a new game with its class.
3. Confirm a valid home citadel, main commander and starting troops.
4. Recruit the intended unit and confirm costs/counts.
5. Cast the intended ritual; verify costs, availability and results.
6. Inspect a combat replay for the custom attack and inherited/custom appearance.
7. Save and reload the test game.
8. Separately test a baseline save after an append-only update and a selected
   declared-mod combination. Do not generalize these results to all mods or saves.

Record game version, source revision, export/install hashes, actions, logs,
screenshots, observations and restoration state. A successful game launch alone
does not prove the remaining mechanics. No automated result proves balance.

## Full-faction acceptance

These cases check a complete faction built from a design record (see
[FACTION-DESIGN.md](FACTION-DESIGN.md#5-private-design-and-coverage-record)). Use
the coverage table as the list of what to check; one passing case covers only
what it exercised.

Static and browser cases, run against the reviewed revision:

1. Every coverage row names its authored definition, acquisition route,
   prerequisites, costs, artwork and status. No requested feature is marked as
   an intentional omission; unfinished ones are `missing` or `blocked`.
2. Every new unit, item, ritual, upgrade and form is reachable through a stated
   route; summons and forms have reachable parents and support has a consumer.
   Trace unlocks from the start without circular prerequisites.
3. `validate_mod` reports no errors; warnings and documented-but-unvalidated
   commands are explained. Definition order satisfies every reference.
4. The browser Design view and Faction design checklist show the expected home,
   starting forces, recruitment rows and rituals. A checklist row marked Present
   shows presence only, not complete economy or progression.
5. The Artwork checklist lists every new image; when export is in scope,
   the reviewed export manifest does too.

Game cases, run only when the user's scope includes game testing and an
isolated install is established (see CoE5 acceptance above). When the scope is
static or browser only, list each of these as `deferred` in the report:

1. A new game starts with the class on a valid home citadel with its main
   commander and starting forces.
2. Each resource is attainable, produces income or stock, can be spent and is
   replenished as designed.
3. Recruitment rows, conditional offers and hired outsiders appear under their
   stated conditions with the stated costs and counts.
4. Each ritual is known or learnable as designed and shows the expected caster
   level, cost and result.
5. Each item, upgrade and form can be acquired by its stated route.
6. Combat casting and custom attacks behave as intended in a combat replay, and
   the artwork appears for every unit and form.
7. The game saves and reloads; any AI-opponent tests are run only if authorized.

Record each case as passed, failed, blocked or deferred with its evidence
category. No combination of these results proves balance, and static, browser
or package results never make a faction playable or engine verified.

## Current feature limits

- Registry and argument checking cover a curated subset.
- CoE5 5.41 commands are known only by name from release notes (status `announced`);
  their arguments are not checked. The 5.41 custom terrain range 500-1999 is inferred,
  and the announced 5.41 engine limits are not enforced. More than 128 recruitment
  entries is an error unless the target is 5.41 or later, where it is unverified (raised,
  no number given).
- Parsing is line-oriented; multiline strings require source review.
- The browser source editor refuses mixed newline conventions; targeted CLI
  patches can preserve them. Structured fields preserve byte offsets and encoding.
- Global commands and sequential object regions are inspected; cross-context
  engine selector persistence is not fully simulated.
- Inheritance is resolved only for explicit local donors or catalog values; summon-string
  grammar, map geometry and arbitrary effects are not resolved.
- Alternate forms are resolved by new-monster order within one file (manual p.18); order
  across mods is not verified.
- Static dependency inspection uses the declared sequence, not a verified engine
  activation order; equal-priority behavior is not established.
- New combat-spell definitions and map generation are not provided.
- Image checks validate containers, not visual quality. Raw PCM sample rate cannot
  be inferred from file bytes.
- A full shipped catalog, automatic extraction and automatic game installation
  are not included.
