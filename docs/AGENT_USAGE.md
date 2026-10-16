# Authoring with KENOGENESIS

1. Establish the user's project, content brief, target game version and testing scope.
   Inspect existing projects. Never seed or replace a user's mod without a request.
2. Read `project_view`. Keep its `revision`. Research commands with
   `lookup_command`; inspect the official manual when coverage is absent.
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
7. Export the reviewed revision. Inspect the manifest and package contents.
   Referenced files and `declared_assets` are the only additional payload.
8. Report source revision, hashes, static checks, browser checks, engine evidence
   and untested behavior separately. No static result proves balance.

## Game-specific constraints

CoE5 commands are not hash-prefixed. A hash starts a comment. Do not translate a
Dominions `.dm` using search-and-replace. CoE5 names, duplicate-name offsets,
automatic identities, rituals and command contexts require their own handling.
Do not allocate Dominions-style numeric monster/nation IDs.

New classes need correctly ordered identity, a real home citadel and starting
forces. A numeric terrain reference existing is not enough to prove it is a
valid home citadel. Ritual-school offsets and summon strings require special
attention. Use the official manual's update guidance and verify in the game.

Structured fields expose explicit authored values only. Copy/inheritance is not
resolved, and removing an inherited ability may require destructive resets.
Never introduce a reset to make a simple field editor appear to work.

## Privacy

Keep projects and assets in a private explicit workspace, not public examples.
Catalogs and extracted resources remain local. Before any future publication,
inspect an explicit source-file allowlist and the full package file list.
Exporting is not publishing or permission to upload to Steam Workshop.
