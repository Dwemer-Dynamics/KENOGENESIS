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

Run `node --check kenogenesis/web/app.js` and Python compile checks. Optional MCP
needs an SDK-backed protocol smoke test, not just successful imports.

## Browser acceptance

At desktop and narrow widths, exercise empty workspace, create/load, object search,
command help, missing catalog, structured field preview/save, source preview/save,
settings preview/save, stale edit handling, static errors and fresh export. Check
keyboard navigation, focus visibility, labels, overflow and preserved drafts.
Record screenshots and browser errors from the exact tested source revision.
HTTP/API tests cannot stand in for browser visual or interaction evidence.

## CoE5 acceptance

Use an isolated game-data location and a uniquely named test game. First verify
the installed engine version and how the actual executable isolates user data.
Do not guess a data-directory option or copy into existing user mods/saves.
If isolation cannot be established, record the blocked runtime checks rather than
changing the user's existing configuration.

Test an independently authored small class/unit/weapon/ritual example:

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

## Current feature limits

- Registry and argument checking cover a curated subset.
- Parsing is line-oriented; multiline strings require source review.
- The browser source editor refuses mixed newline conventions; targeted CLI
  patches can preserve them. Structured fields preserve byte offsets and encoding.
- Global commands and sequential object regions are inspected; cross-context
  engine selector persistence is not fully simulated.
- Inheritance, summon-string grammar, map geometry and arbitrary effects are not resolved.
- Static dependency inspection uses the declared sequence, not a verified engine
  activation order; equal-priority behavior is not established.
- New combat-spell definitions and map generation are not provided.
- Image checks validate containers, not visual quality. Raw PCM sample rate cannot
  be inferred from file bytes.
- A full shipped catalog, automatic extraction and automatic game installation
  are not included.
