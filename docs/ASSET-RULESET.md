# Faction asset rules

These rules apply to every new Conquest of Elysium 5 faction (a new class with
its own units) built with KENOGENESIS. Sizes and formats come from the pinned
CoE5 Modding Manual 5.36; page numbers refer to it. Everything else here is an
authoring default, not an engine guarantee.

## Default: complete original artwork

Generate a complete original visual set from the user's faction theme unless the
user explicitly asks for reused artwork or a prototype. A theme alone is enough;
art direction is derived from it and from the resolved gameplay loadouts.

- An original idle (`spr1`) and attack (`spr2`) image for every new monster the
  faction introduces: troops, commanders, summons and every alternate form.
  Forms are separate monster definitions linked by the shapechanging commands
  (`firstshape`, `secondshape`, `growhp`, `shrinkhp`, `growtime`, `growoffs` and
  the plane `...shape` commands, p.18). Resolve each target from source order.
- An original thematic mod banner set with the mod-wide `icon` command.
- Other visuals only where the content uses a documented image command: an
  original `spr` icon for every new magic item (p.10), and an original terrain
  `spr` for a new custom terrain the faction introduces (p.29): 500-999, or
  500-1999 when the target is CoE5 5.41 or later (inferred from the 5.41 release
  notes, not the manual).

CoE5 has no nation flag and no ritual or spell image command. Do not invent flag,
spell or ritual icon requirements. The Steam `banner.png` (p.3) belongs to
publishing, which needs separate authorization; it is not part of the default set.

Selected vanilla monsters that the mod only modifies need no new art unless the
user asks. Do not add unrelated assets or mechanics.

### Placeholders

Images inherited through `copystats` or `copyspr` (p.14), borrowed stock sprites
and the flat default banner written by `create_project` are placeholders. Replace
them before calling the faction complete, unless the user explicitly authorized
reuse or a prototype. Time or convenience does not narrow the scope.

## Sound

Use appropriate built-in sound numbers (weapon `sound`/`flysound`, ritual
`soundfx`) by default. Custom samples (`sample` with a `.sw` file, p.38) are only
added when the user requests them.

## File contract from the manual

- Images are TGA or PNG (p.2). TGA must be 24- or 32-bit, uncompressed or RLE.
  A TGA without transparent pixels has black (0,0,0) made transparent and
  magenta (255,0,255) made a shadow colour.
- `spr1`: 32x32 or 64x64 for normal sized monsters, 128x128 for huge monsters.
  A human should be about 34 pixels tall, with 2 free pixels between the feet
  and the bottom of the image (p.14). `spr1` also sets the attack image.
- `spr2`: the attack image; it must come after `spr1` (p.14).
- `icon`: the banner shown when selecting the mod, 256x64 TGA or PNG (p.3).
- Item `spr`: centred in a 32x32 or 64x64 image; the drawn item no larger than
  40x40, surrounded by black in a 64x64 image (p.10).
- Terrain `spr`: the terrain square image (p.29). The manual gives no size;
  match the comparable vanilla terrain you inspected and record that as unverified.

The manual does not state a facing direction, a palette, how alpha in a PNG is
blended, or whether an alpha-transparent item icon matches the black surround.
Treat those as choices to compare with vanilla art and verify in the game. Use
`drawsize` only for small token fitting, not to hide a wrong scale.

## Production

Generate bitmap artwork with the agent's built-in image generation (imagegen),
one call per monster containing its idle and attack poses. KENOGENESIS has no
embedded image generator; the browser only prepares the agent brief.

Mechanical conversion may split frames, crop transparent margins, resize with
nearest-neighbour sampling, quantize alpha to fully opaque or fully transparent
and align the feet. It must not paint new content. If conversion loses a weapon or
changes a frame's identity, request an imagegen correction instead.

- Keep costume, equipment, palette and apparent scale identical between poses;
  the attack motion must be clear at native size.
- Keep one coherent body scale across the roster, with documented targets for
  humans, mounted figures and larger creatures. Use one uniform factor for both
  poses of each unit, measured from its idle body, not its raised weapon or crest.
- No baked background, checkerboard, labels, borders or semi-transparent fringe.

### CoE5 visual direction and review

Choose comparable vanilla CoE5 units for proportions, equipment readability and
body scale. Keep those references private and record their source/version. Do not
copy the sprites. A reusable CoE5 style baseline needs explicit user approval;
record that approval before promoting a candidate. A faction under review is not
a substitute for vanilla evidence.

- Work in deliberate pixel clusters with a few main shades per material and
  restrained highlights. Colour reduction alone does not make a readable sprite.
- Prefer natural anatomy, modest hands/feet and distinct silhouettes. Armour,
  shields and clothing should read at native size without thick cartoon outlines.
- Keep equipment consistent with the authored loadout. Spears, bowstrings and
  sword blades must remain continuous and recognizable after reduction.
- Match facing across a faction using the inspected CoE5 reference. The pinned
  manual does not mandate facing; do not import Dominions' left-facing rule.
- Compare idle and attack at native size and equal nearest-neighbour zoom, with
  aligned feet and fixed reference scales. Never resize each comparison figure
  independently to make it appear to match.
- Correct named defects such as clipped weapons, lost equipment, inconsistent
  uniforms or unreadable silhouettes. Preserve successful parts of accepted art;
  do not regenerate a whole roster for small artistic differences.
- Record correction prompts and output hashes alongside the original generation.
  Stop when the named defects are resolved and the set is coherent at native size.
  Browser approval is visual approval, not proof of game rendering or balance.

Binary alpha, a transparent background and the converter's clear side/top margins
are authoring policies. The manual's PNG blending behaviour is unspecified. The
documented TGA magenta shadow convention is separate from that binary-alpha policy.
Do not describe these policies as engine restrictions or apply unit constraints to
the mod banner, item icons or terrain squares.

### Reproducible conversion

Use `scripts/prepare-assets.py` for new unit pairs instead of copying a
faction-specific script. The optional `art` dependency supplies Pillow; the core
and browser retain their standard-library-only runtime. If needed, install the
extra with `python -m pip install ".[art]"` in the chosen environment.

Keep the source manifest and its inputs under a private ignored art directory.
For example, `work/<slug>-art/source-manifest.json`:

```json
{
  "schema": 1,
  "units": [{
    "slug": "example_spearman",
    "source": "raw/example_spearman-pair.png",
    "source_sha256": "<SHA-256 of the reviewed raw image>",
    "split_x": 512,
    "canvas": 64,
    "target_body_px": 34,
    "body_reference": {
      "head_top_y": 250,
      "head_band_x": [200, 240],
      "basis": "first_opaque_in_band"
    }
  }]
}
```

The coordinates are illustrative, not defaults. Measure them from the raw image.
`split_x` lies in a transparent gap, with idle on the left and attack on the
right. `head_band_x` is an absolute source interval, right edge excluded, within
the idle half. Its first visible row must match `head_top_y`. If a crown, crest or
weapon obscures that measurement, use `basis: "manual"` and a nonempty `reason`;
the selected row must still contain visible head pixels in the recorded band.
Pixel checks confirm the measurement touches artwork, not that it depicts a head.

```powershell
python scripts/prepare-assets.py work/<slug>-art/source-manifest.json
python scripts/prepare-assets.py work/<slug>-art/source-manifest.json --verify
```

The converter checks input hashes and paths, thresholds source alpha, crops only
transparent margins, and uses one nearest-neighbour factor for both poses. A pair
that cannot fit at its reviewed body scale is rejected; it is never silently
shrunk to accommodate a raised weapon. Request an image correction or explicitly
review a different body target/canvas. It writes separate frames, an asset
manifest and a native/3x contact sheet under `converted/`. Optional
`palette_max_opaque_colors` (2-256, Pillow's optional palette range) selects one
no-dither palette for each pair;
there is no imposed CoE5 palette ceiling.

`--verify` regenerates in memory and compares outputs and records byte-for-byte,
including the contact sheet. It writes nothing. Tool and Pillow versions are
recorded, so pin the environment when preserving a reproducible accepted set.
Existing different outputs are refused unless a new `--output` directory or
explicit `--replace` is chosen. Raw sources must remain outside that directory.
No converter operation changes the mod or integrates a sprite automatically.

## Private provenance and checklist

Keep exact prompts, raw outputs, hashes, conversion records and the asset
checklist in a private ignored folder such as `work/<slug>-art/` or `.local/`.
They must never be placed in the mod folder, declared as export assets, or copied
into public source, documentation or examples.

The checklist maps every required definition (name, source index, role, form)
to its idle and attack paths, and lists the banner, item icons and terrain
images with their status: planned, generated, integrated, blocked.

## Integration

Reread `project_view` and keep its revision for every guarded call. Never
overwrite an existing file; choose new relative paths.

1. Choose new paths for both poses. Call `preview_art_upload` with `frames`, a
   list of `{frame: "spr1"/"spr2", asset_path, content}` objects (`content` is
   base64). Inspect the current/new comparison, pixel facts, warnings and diff.
2. Call `apply_art_upload` with the identical reviewed request and revision. It
   saves both new files and their source patch together, or removes the new files
   on failure. The patch removes `copyspr` and keeps `spr1` then `spr2` after the
   final `copystats`; do not remove `copyspr` in a separate preliminary save.
   Legacy single-frame arguments remain supported. Idle-only updates preserve an
   effective explicit attack frame; `spr2` alone requires an effective `spr1`.
   Borrowed `copyspr` artwork needs both poses unless its attack is already explicit.
3. The banner, item icons and terrain images have no upload operation. Write
   each to a new filename inside `mod/<slug>/`, then change its reference with
   `preview_block_edit`/`apply_block_edit` (`object_index` -1 for `icon`). Leave
   the replaced placeholder file in place.

Preparing a brief in the browser writes nothing and generates nothing.

## Audit before completion

- Every checklist entry has both poses (or its single required image).
- Dimensions follow the file contract. PNG alpha follows the binary authoring
  policy; colour-key TGA respects the documented black/magenta convention.
  The 2-pixel foot margin and baseline match between poses.
- Review each image at native size and enlarged with nearest-neighbour sampling.
- `validate_mod` reports every reference resolved and no missing asset; `spr2`
  follows `spr1`; no `copyspr` remains on a custom-art monster.
- The export manifest lists every image, and contains no prompts, raw outputs or
  checklist files.

The browser's Artwork checklist names inherited placeholders, missing poses,
overwritten references, shared files, unsupported canvases and banner/item/terrain
coverage. It reads saved file facts, not private prompts or generation records.
An absent `spr2` is an unfinished distinct-pose default, not an engine error:
CoE5 uses `spr1` for attacks too. Checklist findings do not change export gates
and cannot establish originality or replace visual approval.

If any required asset is missing or generation is blocked, name the unfinished
assets and the blocker. Never substitute stock art silently, and do not call a
placeholder build complete. File checks are not in-game proof: recruitment-screen
and battle appearance need a separate in-game review.
