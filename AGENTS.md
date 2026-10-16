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
