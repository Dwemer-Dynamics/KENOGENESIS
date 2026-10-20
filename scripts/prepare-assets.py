#!/usr/bin/env python3
"""Reproducible, mechanical CoE5 sprite conversion from a private source manifest.

Requires the optional Pillow art dependency; it is not used by the browser/core.
No painting, generation, source rewriting or integration into a mod happens here.
"""

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

try:
    from PIL import Image, ImageDraw, __version__ as pillow_version
except ImportError:
    raise SystemExit('Pillow is required for this optional converter: python -m pip install ".[art]"')


def private_path(root, relative):
    """Confine manifest inputs and outputs to its private directory."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Use a nonempty relative path with forward slashes")
    path = Path(relative)
    if path.is_absolute() or any(p in ("..", ".") or ":" in p for p in path.parts):
        raise ValueError(f"Unsafe manifest path: {relative}")
    target = root.joinpath(path)
    if not target.resolve().is_relative_to(root) or any(p.is_symlink() for p in (target, *target.parents) if p != root):
        raise ValueError(f"Linked or escaping manifest path: {relative}")
    return target


def integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in {low}..{high}")
    return value


def convert_unit(root, unit, palette_colors):
    """Validate measured anchors, then scale both poses by the same body factor."""
    slug = unit.get("slug", "")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", slug):
        raise ValueError("Each unit needs a unique lowercase slug")
    source = private_path(root, unit["source"])
    raw = source.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    if source_hash != unit.get("source_sha256"):
        raise ValueError(f"{slug}: source SHA-256 differs from the reviewed manifest")
    with Image.open(io.BytesIO(raw)) as original:
        if original.format != "PNG" or original.mode != "RGBA":
            raise ValueError(f"{slug}: raw source must be a PNG with an actual RGBA channel")
        if original.width * original.height > 16 * 1024 * 1024:
            raise ValueError(f"{slug}: source exceeds the converter's 16 megapixel limit")
        image = original.copy()
    split = integer(unit["split_x"], f"{slug} split_x", 1, image.width - 1)
    mask = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    if mask.crop((split - 1, 0, split + 1, image.height)).getbbox():
        raise ValueError(f"{slug}: split crosses visible pixels; record a transparent gap")
    image.putalpha(mask)
    halves = [image.crop((0, 0, split, image.height)), image.crop((split, 0, image.width, image.height))]
    boxes = [frame.getchannel("A").getbbox() for frame in halves]
    if not all(boxes):
        raise ValueError(f"{slug}: idle and attack must both contain visible artwork")
    anchor = unit["body_reference"]
    head = integer(anchor["head_top_y"], f"{slug} head_top_y", boxes[0][1], boxes[0][3] - 1)
    band = anchor["head_band_x"]
    if not isinstance(band, list) or len(band) != 2:
        raise ValueError(f"{slug}: head_band_x must be [left, right_exclusive]")
    left = integer(band[0], f"{slug} head band left", 0, split - 1)
    right = integer(band[1], f"{slug} head band right", left + 1, split)
    band_box = mask.crop((left, 0, right, image.height)).getbbox()
    if not band_box or not mask.crop((left, head, right, head + 1)).getbbox():
        raise ValueError(f"{slug}: the recorded head anchor has no visible pixels")
    basis = anchor.get("basis")
    if basis == "first_opaque_in_band":
        if band_box[1] != head:
            raise ValueError(f"{slug}: head anchor differs from the first visible pixel in its band")
    elif basis == "manual":
        if not isinstance(anchor.get("reason"), str) or not anchor["reason"].strip():
            raise ValueError(f"{slug}: a manual anchor needs a reason excluding a crest/crown/weapon")
    else:
        raise ValueError(f"{slug}: anchor basis must be first_opaque_in_band or manual")
    canvas = unit.get("canvas", 64)
    if type(canvas) is not int or canvas not in (32, 64, 128):
        raise ValueError(f"{slug}: CoE5 unit canvas must be 32, 64 or 128 square")
    body_px = integer(unit["target_body_px"], f"{slug} target_body_px", 1, canvas - 4)
    scale = body_px / (boxes[0][3] - head)
    frames, facts = [], []
    for pose, frame, box in zip(("idle", "attack"), halves, boxes):
        width, height = max(1, round((box[2] - box[0]) * scale)), max(1, round((box[3] - box[1]) * scale))
        if width > canvas - 4 or height > canvas - 4:
            raise ValueError(f"{slug} {pose}: {width}x{height} cannot fit {canvas}px at the reviewed body scale; "
                             "correct the source pose or explicitly review another canvas/body target")
        reduced = frame.crop(box).resize((width, height), Image.Resampling.NEAREST)
        visible = reduced.getchannel("A").getbbox()
        if not visible:
            raise ValueError(f"{slug} {pose}: artwork vanished during reduction; request an image correction")
        reduced = reduced.crop(visible)
        output = Image.new("RGBA", (canvas, canvas))
        output.paste(reduced, ((canvas - reduced.width) // 2, canvas - 2 - reduced.height))
        frames.append(output)
        facts.append({"pose": pose, "source_bbox": list(box), "resized_size": [width, height]})
    if palette_colors is not None:
        # One no-dither palette from visible pixels in both poses; alpha/coverage is preserved.
        colors = []
        for frame in frames:
            rgba = frame.tobytes()
            colors.extend(tuple(rgba[i:i + 3]) for i in range(0, len(rgba), 4) if rgba[i + 3])
        strip = Image.new("RGB", (len(colors), 1))
        strip.putdata(colors)
        palette = strip.quantize(colors=palette_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for i, frame in enumerate(frames):
            quantized = frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGBA")
            quantized.putalpha(frame.getchannel("A"))
            frames[i] = quantized
    outputs = {}
    for frame, fact in zip(frames, facts):
        alpha = frame.getchannel("A")
        bbox = alpha.getbbox()
        if set(alpha.tobytes()) - {0, 255} or not bbox or bbox[3] != canvas - 2:
            raise ValueError(f"{slug}: converted alpha/baseline contract failed")
        buffer = io.BytesIO()
        frame.save(buffer, format="PNG", compress_level=9)
        filename = f"{slug}_{fact['pose']}.png"
        outputs[filename] = buffer.getvalue()
        fact.update({"file": filename, "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
                     "bbox": list(bbox), "dimensions": [canvas, canvas], "binary_alpha": True,
                     "bottom_free_pixels": 2})
    if len({fact["sha256"] for fact in facts}) != 2:
        raise ValueError(f"{slug}: idle and attack are identical after conversion")
    receipt = {"slug": slug, "source": unit["source"], "source_sha256": source_hash,
               "split_x": split, "body_reference": anchor, "target_body_px": body_px,
               "uniform_pair_scale": scale, "frames": facts}
    return receipt, outputs, frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Private source-manifest.json (schema 1)")
    parser.add_argument("--output", default="converted", help="Output directory relative to the manifest")
    parser.add_argument("--verify", action="store_true", help="Read-only byte-for-byte reproduction check")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace converter-owned outputs")
    args = parser.parse_args()
    if args.verify and args.replace:
        parser.error("--verify cannot be combined with --replace")
    source_path = args.manifest.resolve()
    root = source_path.parent
    manifest_bytes = source_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != 1 or not isinstance(manifest.get("units"), list) or not manifest["units"]:
        raise ValueError("Expected schema 1 and a nonempty units list")
    if len(manifest["units"]) > 64:
        raise ValueError("Convert at most 64 units per manifest/contact sheet")
    palette_colors = manifest.get("palette_max_opaque_colors")
    if palette_colors is not None:
        integer(palette_colors, "palette_max_opaque_colors", 2, 256)
    destination = private_path(root, args.output)
    if destination == root or destination.is_file() or source_path.is_relative_to(destination):
        raise ValueError("Output must be a separate directory below the private manifest directory")
    records, all_outputs, sheets = [], {}, []
    for unit in manifest["units"]:
        receipt, outputs, frames = convert_unit(root, unit, palette_colors)
        if any(f in all_outputs for f in outputs):
            raise ValueError("Duplicate unit slug/output filename")
        if any(private_path(root, u["source"]).is_relative_to(destination) for u in manifest["units"]):
            raise ValueError("Raw sources must stay outside the output directory")
        records.append(receipt)
        all_outputs.update(outputs)
        sheets.append((unit["slug"], frames))
    receipt = {"schema": 1, "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
               "tool": {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "pillow": pillow_version},
               "contract": {"alpha": "binary 0/255 authoring policy", "bottom_free_pixels": 2,
                            "scaling": "nearest-neighbour, uniform per idle/attack pair from measured idle body",
                            "palette_max_opaque_colors": palette_colors}, "units": records}
    all_outputs["asset-manifest.json"] = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    canvas = max(frame.width for _, frames in sheets for frame in frames)
    row_height = canvas * 3 + 36
    sheet = Image.new("RGB", (canvas * 8 + 48, row_height * len(sheets)), (28, 28, 32))
    draw = ImageDraw.Draw(sheet)
    for row, (slug, frames) in enumerate(sheets):
        y = row * row_height
        draw.text((8, y + 4), f"{slug}: idle / attack at native size; idle / attack at 3x", fill="white")
        for col, frame in enumerate(frames):
            sheet.paste(frame, (8 + col * canvas, y + 28), frame)
            enlarged = frame.resize((frame.width * 3, frame.height * 3), Image.Resampling.NEAREST)
            sheet.paste(enlarged, (24 + canvas * 2 + col * canvas * 3, y + 28), enlarged)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG", compress_level=9)
    all_outputs["contact-sheet.png"] = buffer.getvalue()
    extras = set(p.name for p in destination.iterdir()) - set(all_outputs) if destination.exists() else set()
    if extras:
        raise ValueError(f"Output directory has files this manifest does not own: {sorted(extras)}")
    for filename, content in all_outputs.items():
        target = private_path(root, f"{args.output}/{filename}")
        if args.verify:
            if not target.is_file() or target.read_bytes() != content:
                raise ValueError(f"{filename} is missing or differs from fresh conversion")
        elif target.exists() and target.read_bytes() != content and not args.replace:
            raise ValueError(f"Refusing to overwrite {filename}; use a new output directory or --replace")
    if not args.verify:
        destination.mkdir(parents=True, exist_ok=True)
        for filename, content in all_outputs.items():
            target = destination / filename
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)
    print(json.dumps({"verified" if args.verify else "converted": True, "units": len(records),
                      "frames": len(records) * 2, "output": str(destination)}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(f"Asset conversion stopped: {exc}")
