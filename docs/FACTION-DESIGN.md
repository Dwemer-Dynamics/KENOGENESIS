# Designing a CoE5 faction

In Conquest of Elysium 5 a playable faction is a class. A class that feels like
a vanilla one is a complete, asymmetric gameplay loop: what it collects, what it
spends it on, how it grows from the first turns to the late game, and where it
is weak. It is not a quota of units, items, spell paths or ritual tiers.

Command details are in the pinned CoE5 Modding Manual 5.36; check each one with
`lookup_command`. Primary sources: the
[CoE5 manual](https://www.illwinter.com/coe5/coe5manual.html) and the
[CoE5 modding manual](https://www.illwinter.com/coe5/coe5modding.html). This
guide is about design, not balance: static checks cannot show that a class is
fun, fair or even playable.

Jump to [comparators](#1-choose-vanilla-comparators), the
[gameplay loop](#2-gameplay-loop-worksheet), [magic and items](#3-magic-and-items-three-separate-decisions),
[reachability](#4-reachability-and-acquisition-audit), the
[design record](#5-private-design-and-coverage-record), the
[checklist](#checklist), [source order](#order-matters) or
[evidence](#separate-evidence).

## Requested and chosen features

- A theme-only request ("build me a faction about X") leaves the design to the
  author. Make reasonable design decisions yourself and record why; routine
  choices do not need extra approval.
- A feature the user explicitly asked for is a requirement. Implement it with a
  route and evidence, or leave it `missing` or `blocked` with the reason. Never
  mark a requested feature as an intentional omission or as complete without it.
- An optional feature you choose not to add needs a short reason in the design
  record ("martial class: no bespoke items; uses shared loot").

## 1. Choose vanilla comparators

Pick one to three vanilla player classes whose play pattern is close to the
theme. Use them to decide the loop, not to copy values. For each, record:

- the source and its version (game version, manual version, or a private catalog
  with its version and provenance);
- the observed strengths, weaknesses and resource loop;
- which parts you adopt, change or reject, and why.

Version evidence matters. A catalog extracted from an older release is
historical, not current engine source; label it with its version, and
re-check anything you rely on against the manual for the target game version.
For example, a reference extracted from 5.22, a target game of 5.40 and the
pinned 5.36 modding manual are three different versions; record all three.
A row in a catalog is not proof that a class is a playable template: internal
classes, explanatory selectors, conditional or repeated offers and optional
hired mages all appear as rows, and some built-in behaviour is hardcoded rather
than written as commands. Never paste catalog rows or game text into a mod or
public document.

Pattern-level examples (original summaries checked against the official player
manual; not templates, counts or quotas, and not a claim about which classes
are playable in a given version):

| Archetype | Loop pattern |
|---|---|
| Baron | Military and income strength with varied recruits and levies. The baron's own levy powers differ from the combat magic of a wizard hired from outside. |
| Senator | Conventional armies with economic and political progression and conditional recruitment. Little starting battle magic does not make it incomplete. |
| Druid | Forest and herb expansion feeds nature rituals; apprentices grow into masters and stronger summons. |
| Necromancer | Corpses and Hands of Glory feed undead production and advancement; costs and insanity constrain it. |
| Warlock | Several gem resources support separate elemental branches, with apprentices and later specialisation rather than one undifferentiated summon list. |
| Witch | Fungi and suitable territory feed its own ritual and creature loop, with apprentice and later magic development. |
| Enchanter | Constructs trade gold, materials and sometimes locations for durable specialists; the opportunity cost is part of the design. |
| Dwarf Queen | Worker production, conversion that can cost gold as well as iron, and gem-supported elite upgrades; plain cash recruitment is not its main model. |

## 2. Gameplay-loop worksheet

Answer each item in the private design record.

- **Identity**: the one thing that makes the class play differently; intended
  playstyle; intended weaknesses and how an opponent can exploit them.
- **Resource loop**: where the resource comes from (terrain, sites, units,
  events) → how it is reached or collected → income per turn or per action →
  what it is spent on → how it is replenished or runs out. Say which parts are
  built-in game behaviour rather than mod commands.
- **Recruitment**: keep chance, count, gold, gold die, iron and extra costs
  separate. Distinguish the native roster, conditional offers (terrain, sites,
  events) and outsiders hired as mercenaries. A missing recruitment route is a
  design decision only if you wrote it down.
- **Home and start**: a terrain that is a real citadel, start plane, main
  commander, starting commanders and troops, and any starting terrain.
- **Progression**: what changes in the early, middle and late game. Casters can
  progress through learning and mastery; martial or economic classes can
  progress through upgrades, conversion, conditional recruits, sites or events.
  Pick what fits the archetype: not every class needs three mage tiers.

## 3. Magic and items: three separate decisions

1. **Combat casting**: which units cast in battle, through existing combat-magic
   paths and spells the manual documents. KENOGENESIS does not define new combat
   spells; do not invent them.
2. **Rituals**: which schools and rituals exist; which are known at the start
   and which must be learned; caster level and mastery; resource cost; and the
   result (summon, upgrade, terrain or other effect). `allrit` grants a whole
   school's rituals: use it as a deliberate knowledge policy with a written
   rationale, not by default and not as a blanket ban. Making every summon known
   from turn one usually removes progression.
3. **Items**: whether the class relies on shared loot, starting equipment or its
   own items; which slots its units have; and how each item is acquired. Shared
   loot is a valid choice, and bespoke items are allowed whenever the design or
   the user needs them. A unit's weapon is not an equippable magic item.

Several mastery, item and recruitment commands are documented in the manual but
not argument-checked by KENOGENESIS (`lookup_command` shows `validated: false`).
They are preserved as written; label them as documented-but-unvalidated and do
not treat a clean static result as proof of their effect. Use the signature
`lookup_command` returns; do not copy argument forms from older data dumps (one
historical dump writes `power` with two fields, which differs from the
documented signature).

## 4. Reachability and acquisition audit

Every authored unit, item, ritual, upgrade and alternate form needs a route a
player can actually reach: start, recruitment row, conditional offer, ritual,
upgrade, form change, event or loot. For each one record the route, its
prerequisites and its costs. Summon-only bodies and alternate forms still need a
reachable summoner or parent form: naming them as internal is not an acquisition
route. Support definitions such as helper weapons must name their reachable
consumer; unused support content must be explained or removed from the plan.
Check the whole chain from the starting state: the first needed resource,
recruit or ritual must be available without circular prerequisites or an
unobtainable cost. Trace each later unlock back to that starting route.

## 5. Private design and coverage record

Before the first guarded source edit, write a private design record, for example
`<project>/docs/design.md`. It is a private authoring note: KENOGENESIS lists
and reads it (`list_project_docs`, `read_project_doc`) but never edits or exports
it, and it is not a product schema. It holds the comparators, the worksheet
answers and a coverage table:

| Requested or chosen feature | Authored definition | Acquisition route and prerequisites | Progression and resource costs | Artwork | Evidence (static / browser / package / game) | Status |
|---|---|---|---|---|---|---|

Status is one of:

- `implemented`: authored, reachable through a stated route, statically valid and
  with its artwork done. This is static coverage only: label any game behaviour
  that nobody has observed as `unverified in game`.
- `omitted (optional)`: not requested; the reason is written down.
- `blocked` or `unverified`: depends on unsupported, documented-only or untested
  behaviour; say what blocks it.
- `missing`: not done yet. A requested feature stays `missing` until it is
  implemented.

Keep the record up to date through the build and use it for the final report.

## Checklist

| Part | Decide | Commands (manual page) |
|---|---|---|
| Identity | Name, description, playstyle, intended weaknesses | `newclass` then `setclassname`, `classdescr`, `classabdescr` (p.27) |
| Economy and recruitment | Resource loop; troops and commanders, how often, how many, for how much gold and iron; conditional and hired offers | `addunitrec`, `addcomrec`, `addmercrec`, `recxcost`, `goldbonus`, `ironbonus` (pp.27-28) |
| Home and start | A real home citadel terrain, start plane, main commander and starting army | `hometerr`, `startplane`, `createcit`, `setmaincom`, `addstartcom`, `addstartunits`, `addstartterr` (p.27) |
| Progression | Early, middle and late game changes that fit the archetype | Depends on the route: rituals, upgrades, forms, recruitment, events |
| Combat casting | Which units cast in battle, through existing paths | Look up with `lookup_command` |
| Rituals | Schools, starting knowledge and learning, caster level, cost and result | `newritpow`, `power`, `allrit`, `newritual`, `ritpow`, `level`, `cost`, `summoning`, `addstring` (pp.17, 32-33) |
| Items | Shared loot or own items, slots and acquisition | `newitem`, `selectitem` and slot commands; look up with `lookup_command` |
| Alternate forms | Shapes, growth, plane forms and splits, if the theme needs them | `firstshape`, `secondshape`, `growhp`, `shrinkhp`, `growtime`, `*shape` (p.18) |
| Planes, terrain and events | Plane or terrain roles and events, if the theme needs them | `startplane`, `selectterr`, `selectterrgroup`, `playerevent`, `squareevent` (pp.27-38) |
| Original artwork | Idle and attack images for every new unit and form, and a 256×64 banner | `spr1`, `spr2`, `icon` (pp.3, 14); see [ASSET-RULESET.md](ASSET-RULESET.md) |
| Evidence | What was checked statically, in the browser, in a package and in the game | Evidence section; see [VALIDATION.md](VALIDATION.md) |

The browser's Faction design checklist shows which parts are present in the
saved source. A row marked Present means something exists, not that the economy,
progression or acquisition routes are complete; use the design record for that.

## Order matters

Order follows references; there is no single universal order.

- Define whatever a line names by name (monsters, weapons, terrain) before that
  line. A new unit connected to a class from the unit form is inserted before
  that class for this reason.
- `setclassname` must immediately follow `newclass`.
- Ritual school numbers `0`, `-1` and so on count back from the latest
  `newritpow` above the line (p.17). Put each `newritpow` before the units and
  rituals that refer to it by a relative number.
- Alternate-form commands count new monsters in creation order (p.18). Adding,
  removing or moving a monster can change which monster a form reaches; the
  review lists such changes.

## Home citadel

A terrain number in `hometerr` is not proof of a valid home. Use a terrain that
is a citadel and check the start in the game.

## Recruitment and starting forces

Chances, counts, gold, gold die and iron are shown as written in the Design
section. KENOGENESIS does not simulate recruitment rolls, income or combat and
does not compute a balance score. Compare units with chosen references only to
see source-backed differences.

## Separate evidence

Record static checks, browser checks, packaging checks and game observations as
separate evidence. Only an in-game observation says anything about game
behavior, and one observation covers only what was tested. Static, browser or
package results never show that a class is playable, balanced or engine
verified. The full-faction game cases are in [VALIDATION.md](VALIDATION.md#full-faction-acceptance).
