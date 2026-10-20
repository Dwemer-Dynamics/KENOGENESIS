# The KENOGENESIS workshop

Use the Projects sidebar to open a mod, create a project or import a `.c5m` with
its selected assets. Import creates a new project and refuses an existing folder.
You can choose individual files or an asset folder. Review and correct relative
paths before importing; nested folders must match the paths in the mod source.
The folder name, file sizes (8 MiB in total, at most 200 assets) and asset paths
are checked in the browser before review, and a name that is already used points
to the existing project instead. A file that cannot be read is reported and not
selected; while files are still being read, review waits. After the import, the
page shows the new project's revision with **Open** and **Import another mod**.

## Browse a project

Overview shows the saved revision's validation, referenced files, sprites and
latest export. The Class selector filters Overview and Units. All classes and
Not tied to a class are available alongside individual classes.

Units opens a searchable roster and a detailed sheet. Underlined values were
authored in this mod. A question mark means a value is unresolved or its game
default is not modelled. Copy inheritance is resolved only from explicit local
definitions or the configured catalog; values are never guessed.

The sheet lists documented abilities with their manual summary, attacks a
`copystats` donor states explicitly (marked partial when the donor copies again),
and the copy and reset order. Alternate forms (`firstshape`, `growhp`,
`landshape` and the other p.18 commands) are resolved by new-monster order in
this file and appear in Related content. Forms share the class scope of the unit
they come from and are grouped as Alternate forms in the roster and artwork
lists. **Value origins** (titled **Inheritance and value origins** when the unit
copies another) lists each stat, both sprites, attacks and abilities with its
origin: authored here, copied from an explicit local donor, read from a unique
catalog row, unresolved or a game default that is not modelled. Unknown values
show ? and are never filled in as zero. Abilities copied through `copystats` are
not resolved. The copy and reset order is listed in the same disclosure.

**Compare with references** shows a unit beside up to four chosen units or
catalog rows: idle and attack frames of this project's units at whole-pixel
zoom (catalog rows hold no images, so none are shown), stats, attacks, explicit
abilities, recruitment rows that name the unit (gold, gold die, iron, chance,
count and extra costs as written, from this mod's classes and, for a uniquely
named catalog row, catalog class rows), ritual schools from `power` and
`allrit`, and each column's source, catalog version and duplicate-name
warnings. Unknown values are not compared, and nothing is scored or simulated.
The chosen references are kept in the address (`?refs=u:3,cat:12`; older
`?ref=cat:N` links still work), so reload, Back and shared links show the same
comparison. References that no longer exist are listed with the reason and can
be removed or cleared; they are never silently dropped. A catalog row that is
missing or is not a monster is listed the same way.

### Links name positions

CoE5 definitions have no stable ID in KENOGENESIS: a unit or other definition
is named in the address by its source position (`units/6`). Definition, edit,
duplicate and Advanced block links, source-line links, numeric class scope,
and unit/class comparison choices record the saved revision with `?rev=`
(the first 16 hex digits). Catalog comparison rows are covered by that pin too.
A matching revision opens normally. Any changed revision requires explicit
reselection, including changes made in this tab: names and matching neighbours
do not prove identity, particularly for duplicate names. A stale link opens no
sheet, editor, source line or comparison. It offers a fresh list (with class
scope reset) and, where available, an explicit browse-only choice to view what
is at the old position now. No old bookmark is automatically rebound.

Older links without `?rev=` still open with a clear unchecked-position warning.
**Keep this link for the saved revision** records the revision after you check
the displayed names. Numeric remembered class choices are used only for the
revision where they were selected; older choices reset to All classes.
A reviewed edit of one existing block can renew its current address because it
does not change definition positions. Removal returns to the list. Other
positional drafts remain available for explicit recovery after a revision
change; their target is never guessed. Comparison replies from a newer saved
revision are refused and offer a read-only reload.

**Design** (Build) shows each class's home, starting forces, recruitment rows
(chance, count, gold, gold die, iron and extra costs as written), rituals reached
through its units' schools and the roster with artwork state. It computes no
balance score and simulates no recruitment rolls. **Compare classes** puts one
class beside up to four other classes of the project or catalog class rows:
roster counts, main commander, starting units, chance, count, gold, gold die,
iron and extra costs per recruitment row, income bonuses and ritual schools
reached through the class's units. Cells show ? with a note when a value is not
written, not printed in the catalog or only partly covered (selected classes,
duplicate or copying catalog units). Overview's **Faction design
checklist** summarises the same parts; see [FACTION-DESIGN.md](FACTION-DESIGN.md).
A Present row there means the part is present in the saved source. It does not show
that the economy, progression or acquisition routes are complete; that is
tracked in the agent's private design and coverage record.

Above the table, **Comparison overview** draws the same figures. Each class has
a letter, a marker shape and its own labelled row in every chart. Roster variety
bars count distinct troop, commander, mercenary and starting unit names; a
hatched bar means partial coverage (a selected class or any catalog row; other
selection blocks and game defaults are not merged). Strip charts place every recruitment row's
gold, gold die, iron and chance, and every recruitable unit's explicit hit
points, strength, armor, magic resistance and morale, on a shared scale, with
the range and the number of unknown values written beside them. Unknown values
are never drawn as zero. A table lists income bonuses, ritual schools, rituals
and their resources (unknown for catalog classes), and **Exact values per
recruitment row** gives every figure with its source line or catalog row. **How
to read these figures** explains CoE5's raw chance, count, gold, gold die and
iron arguments; nothing is rolled, priced, simulated or scored. The chosen
classes are kept in the address (`?cmp=<class>&crefs=u:3,cat:12`, separate from
the class filter and from unit references), so reload, Back and shared links
reproduce the comparison; classes that no longer exist are listed and never
silently dropped.

Classes, Weapons, Ritual schools, Rituals, Items, Terrain and Events show their
own cards, relationships and source links. Source, Assets, Other definitions and
Docs are in More. The Catalog link opens a separate read-only inspector.

## Review and save

Open Edit on a definition to change labelled fields or individual command rows.
Repeated values (recruitment, starting army and terrain, attacks, ritual power,
costs and strings) are labelled rows with named arguments. Optional arguments
may be left empty only at the end. Unit, weapon and terrain arguments suggest
local names and catalog rows and say whether a name is defined here, defined
later, ambiguous, from the catalog (with version) or unverified. **All commands
(advanced)** lists every authored line and has a searchable command picker.
Advanced tools also provides a source editor and mod-wide information fields.

A value that cannot be used (a missing required argument, a gap before a later
optional one, a non-number or a value outside the documented range) is marked on
its own field with a message that stays until you edit it, and focus moves to
the first such field. Nothing is added or reviewed, and the draft is kept.

A new definition chooses how its block opens: a new definition or a documented
select command (`selectmonster` with an optional non-negative offset,
`selectclass`, `selectterr`, `selectterrgroup` and others), or a player or
square event. No ID is allocated. A new unit can be connected to one class as a
recruitable unit or commander, mercenary, starting units or starting commander;
the review then shows both blocks, the unit is inserted before that class, and
one save writes both. Summons are added afterwards in the ritual's Strings rows.
Duplicates and catalog templates use the same review workflow.

Review shows a changes table and the exact source diff. Back to the form retains
your entries. When the server refuses a value it names (for example evidence
details with a control character, a dependency or an asset path), that field is
marked and focused with the reason; other refusals are shown above the form. Save reviewed change checks the revision again and creates a
backup. A receipt shows the saved file, backup and revision. Earlier receipts
remain available while you navigate within the project.

If a file changed outside the workshop, saving is refused. Reload latest file
(keep my form) retains the editable draft. Review the new diff before saving.
The workshop never silently reapplies an old review.

Drafts remain in memory while navigating. Closing or reloading the browser can
lose them; the browser warns while unsaved drafts exist. The header and Export
page list unsaved drafts. Export includes saved files only.

If one section cannot load (for example the source, Design, Evidence, a guide or
the catalog), its normal navigation stays available: the project header and
section controls where offered, or the catalog link back to the project. The
section shows the reason with **Retry**, which loads that section again.
If the project itself cannot be read, the page shows a focused title, the reason,
Retry and a link home. Errors say whether the local server did not respond, sent
a reply that could not be read, or refused the request with its own code and
details. An unreachable server is not restarted for you: start it again the way
you launched it (the error offers the start command for the Python serving this
page when known), then use Retry. Drafts stay in the open tab. A failed review or
save is never resent automatically; your entries are kept, and **Reload latest
file (keep my form)** loads the latest saved revision, so you can see whether a
save completed before you review again.

## Artwork and assets

A unit's Upload artwork form takes the idle (`spr1`) and attack (`spr2`) frames
together. Each pose shows the current image beside the newly chosen file. Zoom
(Native, 2×, 3×, 4×) is a radio group that scales every frame by whole pixels;
arrow keys move between sizes. Choose a new relative filename for each frame:
existing artwork is never overwritten.

Review decodes every frame. It refuses unit canvases other than 32×32, 64×64 or
128×128 (manual p.14), PNGs that are not 8-bit RGBA non-interlaced, TGAs that
are not 24/32-bit, corrupt files, frames with no visible pixels and partly
transparent pixels. The last two are KENOGENESIS authoring rules; the manual does
not say how the engine blends PNG alpha. A 24-bit TGA uses the manual's colour
key: black is transparent and magenta is shadow. Each frame lists its canvas,
transparency, figure box and free pixels on each side, with warnings for a foot
margin other than 2 pixels, a figure touching an edge and a 128×128 (huge)
canvas. The pair is checked for different sizes, baselines, figure heights or
transparency and identical files.

One save writes both new files and the source change, or nothing: a stale
revision or any write failure removes the new files. The source change removes
`copyspr` from that unit and places `spr1` then `spr2` after its last
`copystats`. An idle-only upload keeps an existing attack frame after the new
`spr1`; without one, the review notes that `spr1` is shown for attacks too. A
unit that uses `copyspr` needs both frames unless it already has its own `spr2`.

Assets previews supported PNG and TGA files and lists their size, short hash,
references and download link. A summary counts the files listed, those included
in the export (referenced or declared), unreferenced files and files that are
missing, unsafe or invalid. **Used by** links each reference to its definition
(or to the mod information editor for mod-wide lines such as `icon`) and shows
the command and source line. **Copy hash** copies the full SHA-256 and keeps the
outcome on the card; if clipboard access is refused, the full hash is shown
selected for copying by hand. Referenced and declared files are always listed.
The folder listing itself stops after 2000 files and never reads linked files;
skipped file paths are counted by reason and listed. Linked folders are never
followed. Referenced and declared paths are checked separately, so a skipped
path may still appear in the gallery. Unreferenced files are not exported. Map payloads are listed as opaque files;
this workshop does not interpret their geometry.

### Artwork checklist

Overview's Artwork row and **Artwork checklist** come from the saved revision.
They list new units by state: missing or invalid files, inherited placeholders
(`copystats` or `copyspr`), no image, a sprite replaced by a later copy or `spr1`, remaining
`copyspr`, files shared with another unit or identical in bytes, unsupported
canvases, idle only and both poses set. Selected vanilla monsters need no new art
by default. The checklist also covers the mod banner (the flat `create_project`
banner is a placeholder), new magic item icons and new custom terrain images.

Idle only is informational: the game uses `spr1` for both poses, but a distinct
attack pose has not been authored. The checklist does not change validation or
export, and file checks cannot show that an image is original. Reuse or a
prototype is the user's explicit choice; the checklist still lists those images.

Banner, item and terrain images have no upload form. Add the file under a new
name in the mod folder, then change the `icon` or `spr` line in a reviewed block
edit. Those images receive container and size checks only.

## Original-art agent brief

New factions get complete original artwork by default (see
[ASSET-RULESET.md](ASSET-RULESET.md)). Get started and each project's Overview
offer **Original artwork: agent brief**. The faction theme is prefilled from
the project or display name and can be edited, and an optional intended
playstyle can be added; both are design input kept in this browser tab only.
Copy brief text or Download brief JSON, then give it to Codex or Claude
Code opened on the KENOGENESIS folder. The result of each copy or download
stays on screen. If the browser refuses clipboard access, the brief appears as
selected text to copy by hand. There is no image model in the browser.

On Get started, a three-step progress shows Prepare the brief, Hand it to your
agent and Return and open the project. After a copy or download, **Reload
projects and check** reloads the project list and looks for the exact folder
name you entered: it links to that project when it exists and otherwise says it
has not been created yet. Nothing on this page creates a project except
**Create empty project**. Changing the folder name, display name, version,
theme or playstyle after a copy or download marks that copy as out of date and
returns the progress to step 1; copy or download the brief again. The Get
started fields are kept for this browser tab, so a reload restores them; **Clear
form** empties them.

The brief names the workspace, project slug, the saved revision of an existing
project, the theme, the files to read first, the guarded inspect, preview and
apply steps, and the asset upload rules. For an existing project it lists the
roster with each idle and attack file status, inherited images, `copyspr` lines,
form commands, new items, custom terrain and the banner.

Project existence and authoring mode are separate; the brief text and JSON
(`authoring_mode`, `project.exists`, `project.empty`) state both:

- **create** (Get started): the project does not exist yet; the agent runs
  `create_project`, builds the faction, then generates its artwork.
- **build** (Overview of an existing project with no class and no monster
  definitions): the agent must not run `create_project`; it builds the faction
  in that project with guarded edits, then generates its artwork.
- **art** (Overview of a populated faction): artwork only; gameplay values stay
  unchanged.

For **create** and **build**, the brief text and JSON (`design_requirements`)
also carry the faction design contract from [FACTION-DESIGN.md](FACTION-DESIGN.md):
a complete, original gameplay loop rather than a small roster with every summon
known. The agent picks one to three version-labelled vanilla comparators;
records identity, playstyle and intended weaknesses, the resource loop,
recruitment costs and offer types, home and start, and early, middle and late
progression; treats combat casting, ritual knowledge and learning, and items as
separate decisions; audits how every new unit, item, ritual, upgrade and form is
acquired; and writes a private design and coverage record (for example
`<project>/docs/design.md`, never exported) before the first source edit.
A theme-only brief lets the agent make routine design decisions itself;
requested features are implemented or reported as missing or blocked. Game
checks stay deferred unless testing is in scope. The **art** brief has no
design contract and asks for no gameplay changes.

On Get started, Copy and Download are disabled when the folder name matches an
existing project; the status links to that project's Overview brief.

Preparing a brief generates, uploads and saves nothing, and never touches the
project's source or artwork. The agent generates the images with its built-in
image generation and saves them through the guarded review. Create empty project
still creates a plain project and then opens its Overview with the brief.

## Catalog, validation and export

Configure a local catalog in Overview's project settings. Its game version and
provenance are shown. Missing or invalid catalogs leave vanilla references
unverified. Inspector categories and filter columns come from that catalog. The
inspector shows results beside the selected row (stacked on narrow screens).
Up and Down arrows (Home, End) move through the results; Enter or a click opens a
row beside the list, and the address keeps the search, filters and chosen row.
Choosing a row, a category, sorting, a page or a condition adds a browser history
entry; one burst of typing in the search adds a single entry. Back and Forward
restore that list, filters, page and row, and return focus to the row (or the
search box).
Results refresh in place, so the search box keeps focus, and a status line
reports loading and counts. Conditions appear as chips you can edit or remove;
**Reset all** clears search, category, sorting and conditions. A condition is
checked before it is added (a column, a value unless it is "is present" or "is
missing", a number for greater/less comparisons). A malformed or unknown
condition in the address is not applied: the inspector says so and offers
Reset filters or Reset all instead of showing unfiltered rows. A catalog row's
page shows its source file and line, catalog hash, duplicate-name
and version warnings and its statements with manual labels.

Overview → Local catalog can review a private **snapshot** of the configured
catalog. Its status is current, stale, offline (references use the snapshot),
invalid or unused, and the header shows when the snapshot is in use. Snapshots
change the project revision and are never exported.

Validation separates errors, warnings and unverified coverage. Source links open
the relevant line. **Check compatibility** lists the declared load order (not a
verified engine order), cross-mod and reference findings and, against an earlier
export chosen from the list, which kinds of definitions were appended, reordered
or removed. If the export history cannot be read, the page says so and offers
Retry instead of reporting no earlier exports. In Project settings, **Dependency
projects** lists each declared dependency with its state (project, not found,
unreadable, duplicate or this project). Add a readable project from the picker
or enter a folder name, move entries up or down, or remove them; unresolved
entries stay editable. The declared order ends with this project. Changes are
saved only through the same reviewed settings change, and any edit clears an
earlier review. The
settings review shows the compatibility impact of the candidate settings: new
findings, findings no longer reported (for example a reference that now matches
a dependency's definition) and unchanged ones, plus the declared order before
and after. It is computed without saving and never says which mod wins an
overlap; the declared order is not a verified engine order.

**Evidence** records private observations about the saved revision: static,
browser, packaging or user-reported game checks. Records are plain text, linked
to a revision, never exported and never mark a mod as verified. A game
observation can add optional details: the CoE5 version you played (as you
report it), tester, class played, opponents, map, turns, outcome and the
SHA-256 of a screenshot, log or save you keep privately (nothing is attached).
They are labelled as reported by you; KENOGENESIS never runs or watches the game.
Any record can list up to eight typed references (screenshot, log, saved game,
report, package or other), each a label you choose and an optional SHA-256. They
describe files you keep; nothing is uploaded, attached or opened.

Export is blocked by static errors or a changed revision. Export a ZIP or
folder, then use the export history to download the ZIP and its manifest. After
an export, **Export result** lists its id, format, revision, files with
SHA-256 hashes, the archive hash (ZIP only), manifest, warnings and download
links. **Copy file and archive hashes** copies the export id, revision, archive
hash, manifest path and every file hash; if clipboard access is refused, the
text is shown selected for copying by hand. It stays for this browser tab while you navigate. Static errors and a
changed revision are reported separately, with a link to Validation or a reload
of the latest saved revision. **Re-validate** reads the saved project again; if
the server does not answer or refuses, the reason appears beside it with
**Retry**, the last loaded validation and your drafts are kept, and nothing is
exported. The Export tab is flagged *blocked* while static
errors prevent export and *outdated* when the latest export is of an older
revision; an outdated project can be exported again at once.
Dependencies are listed separately and are not bundled automatically. The
**Distribution handoff** checklist covers what to check before giving the ZIP to
someone; nothing is installed or published. The export manifest is written to
be shared: its catalog entry is a summary (available, game version, SHA-256, row
count, configured or snapshot, snapshot status) without the catalog's
provenance text, file path or snapshot details, and catalog diagnostics in its
validation report use fixed wording without local paths. Browser downloads of earlier manifests receive the same privacy filtering
without rewriting the original on-disk receipt. Copies downloaded before this
change may still include private details; download them again before sharing. Assets can show the printable header
of a `.coem` map; map content is not interpreted.

**Tools** has a searchable command reference for the pinned manual, links to
reference catalog import, the unit artwork conversion steps and the command-line
and agent entry points, and lists what is not provided. Command-line examples
use the Python that serves the browser and quote paths for your shell
(PowerShell on Windows); JSON arguments go in a request file. Docs render tables, and
heading links within and between guides open at the heading.

Within a project, Docs (in More) lists the KENOGENESIS guides and, separately,
**Project notes (private)**: Markdown files placed directly in the project's
`docs/` folder (`<workspace>/<slug>/docs/*.md`). Notes are read-only and shown
as text, never as HTML. Only top-level `.md` files up to 256 KiB in UTF-8 are
read; subfolders, links or junctions, other file types, mod files and names
suggesting secrets or backups (such as `token`, `password` or `backup`) are
skipped and listed as not shown. Notes are never edited here and never exported.

Static validation and browser testing do not prove that a mod loads or behaves
correctly in Conquest of Elysium 5. Verify game behavior separately.

## Maps and distribution

CoE5 includes its own Map Editor under Mods. Create or edit maps there, then
include the `.coem` file through `mapfile` in the mod folder. See Illwinter's
[CoE5 player manual](https://www.illwinter.com/coe5/coe5manual.html).

For distribution, review the exported same-named mod folder, `.c5m`, referenced
files and manifest. Illwinter documents Workshop upload from the game's Mods
menu by right-clicking the mod. See the
[official CoE5 modding manual](https://www.illwinter.com/coe5/coe5modding.html).
KENOGENESIS prepares the package; uploading remains a separate user action.

**Prepare for CoE5 Workshop** on Export stages a private local ZIP for that
upload path. Choose an existing export of the saved revision (export first if
none is listed), a visibility (private by default) and a square PNG banner
(256x256 suggested by the modding page; it is copied unchanged). The review
lists every file and hash: the export's mod folder plus `banner.png` and
`coe5ws.txt` (`Visibility="private"`, `"friends"` or `"public"`). The
export is re-read and compared with the saved project, and staging stops if
the mod already contains a `banner.png` or `coe5ws.txt`. Saving creates a new
bundle and receipt in the project's private `.kenogenesis/workshop-stages`
folder, separate from exports; the source and revision do not change. The
stage history offers each bundle for download while it matches its receipt.
Staging is not an upload: KENOGENESIS never contacts Steam.

## Keyboard and narrow screens

Use the skip link to reach the main area. Left and Right move through project
tabs. More supports arrow keys and Escape. `/` focuses search, list arrows move
between units, and Escape clears search or returns from review. Preview opens a
pinned information card with a close control. Opening a unit or another
definition moves focus to its heading. A source link focuses the linked line:
only the code pane scrolls to it, and its accessible label provides the line
number and text.

At narrow widths, Projects toggles the sidebar and section tabs scroll sideways.
The unit list has its own show/hide control when the layout stacks. Comparison
tables scroll sideways and can be focused for keyboard scrolling; their first
column names each row. In the stacked catalog inspector, opening a row moves
focus to it and **Back to results** returns to that row in the list.

Remembered preferences (class filter, last project, export result, brief theme,
Get started fields) use browser storage when it is available; when storage is
blocked or holds something unexpected they are simply not remembered.
