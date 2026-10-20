# KENOGENESIS agent entry point

Read `docs/AGENT_USAGE.md` before authoring a mod. The product name is KENOGENESIS.
This is a separate CoE5 project; never change Kosmokrator as part of its work.

Keep private mods, user artwork, extracted game data, catalogs, prompts and test
saves outside public source, documentation and examples. `work/` and `.local/`
are local ignored directories. Export only the explicitly reviewed file set.

CoE5 uses `.c5m` commands without hash prefixes; `#` starts comments. Do not port
Dominions IDs, syntax, nation rules or maps. Research commands against the pinned
CoE5 manual and record actual game/catalog versions. Preserve unknown commands.

Use inspect → preview → apply → validate → export with the same reviewed input
revision. Never rewrite a whole mod through a serializer or resolve stale drafts
by silently reapplying them. Static, browser, packaging and in-game evidence are
separate. Do not call a mod playable or balanced on static evidence.

For maintenance, use existing focused tests and proportional probes. UI work
follows the maintainer's applicable Claude delegation/fallback rule. Publishing,
releases, remote repositories and modifications to existing game installations
need separate authorization.

## Required review checks

- For authored attacks, resolve the referenced weapon's semantics against the
  pinned manual and versioned data. Natural-weapon damage and fixed-weapon damage
  bonuses differ: audit zero values and record intentional non-damaging attacks.
  A clean validator result does not replace this check.
- Compare both final converted poses with the unit's authored equipment,
  including starting items, at native size and equal nearest-neighbour zoom.
  A recognizable weapon in the raw image is insufficient if reduction makes it
  read as another weapon. Correct the named defect and inspect the result again.
- For responsive UI changes, inspect actual rendered content at narrow,
  intermediate and wide widths, including the reported failing width. Check
  label/value separation, readable secondary panels and container overflow;
  passing phone and wide-desktop checks alone is insufficient. Preserve focused
  before/after evidence and report the widths actually tested.
- After a fix, review the saved source, final assets and rendered result again.
  Distinguish confirmed defects from historical-data discrepancies and runtime
  uncertainty; do not change documented syntax on speculation or claim game proof
  from static, visual or package checks.
