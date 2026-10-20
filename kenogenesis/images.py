"""Bounded browser previews for mod images: TGA is decoded and re-encoded as PNG, never trusted as-is.

decode_tga and encode_png are adapted from Kosmokrator's tga.py (GPLv3, see NOTICE). Only the
true-colour 24/32-bit raw or RLE TGA the CoE5 manual allows is decoded; anything else is refused.
"""

import struct
import zlib

from .assets import inspect_asset, read_png

MAX_PREVIEW_PIXELS = 2048 * 2048  # Tool policy for browser previews, not an engine limit.


def decode_tga(data, max_pixels=MAX_PREVIEW_PIXELS, key_colours=True):
    """Return (width, height, top-down RGBA bytes) for a 24/32-bit type 2 or 10 TGA.

    key_colours applies the manual's black/magenta rule to a TGA without transparency; False returns the
    stored channels (24-bit pixels then have alpha 255).
    """
    if len(data) < 18:
        raise ValueError("TGA header is truncated")
    id_len, cmap_type, img_type = data[0], data[1], data[2]
    w, h = struct.unpack("<HH", data[12:16])
    depth, desc = data[16], data[17]
    if cmap_type != 0 or img_type not in (2, 10) or depth not in (24, 32):
        raise ValueError(f"unsupported TGA (type {img_type}, colour map {cmap_type}, {depth} bit)")
    if not w or not h or w * h > max_pixels:
        raise ValueError(f"TGA size {w}x{h} is empty or too large to preview")
    bpp = depth // 8
    pos = 18 + id_len
    need = w * h * bpp
    if img_type == 2:
        raw = data[pos:pos + need]
    else:
        out = bytearray()
        while len(out) < need:
            if pos >= len(data):
                break
            hdr = data[pos]
            pos += 1
            n = (hdr & 0x7F) + 1
            if hdr & 0x80:
                out += data[pos:pos + bpp] * n
                pos += bpp
            else:
                out += data[pos:pos + n * bpp]
                pos += n * bpp
        raw = bytes(out[:need])
    if len(raw) < need:
        raise ValueError("TGA pixel data is shorter than its header declares")
    rows = []
    stride = w * bpp
    for y in range(h):
        line = raw[y * stride:(y + 1) * stride]
        row = bytearray(w * 4)
        row[0::4], row[1::4], row[2::4] = line[2::bpp], line[1::bpp], line[0::bpp]
        row[3::4] = line[3::4] if bpp == 4 else b"\xff" * w
        rows.append(bytes(row))
    if not desc & 0x20:  # bit 5 clear = bottom-left origin, rows stored bottom-up
        rows.reverse()
    if desc & 0x10:  # bit 4 set = right-to-left columns
        rows = [b"".join(r[i:i + 4] for i in range(len(r) - 4, -4, -4)) for r in rows]
    rgba = b"".join(rows)
    if key_colours and (bpp == 3 or rgba[3::4] == b"\xff" * (w * h)):
        # Manual p.2: a TGA without transparent pixels shows black as transparent and magenta as shadow.
        rgba = bytearray(rgba)
        for i in range(0, len(rgba), 4):
            r, g, b = rgba[i], rgba[i + 1], rgba[i + 2]
            if r == g == b == 0:
                rgba[i + 3] = 0
            elif (r, g, b) == (255, 0, 255):
                rgba[i:i + 4] = b"\x00\x00\x00\x80"
        rgba = bytes(rgba)
    return w, h, rgba


def encode_png(width, height, rgba):
    """Minimal RGBA PNG (filter 0 rows, zlib) used to preview TGA files in a browser."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png_rgba(data, max_pixels=MAX_PREVIEW_PIXELS):
    """Return (width, height, RGBA bytes) for an 8-bit RGBA non-interlaced PNG; other types are refused."""
    header, raw = read_png(data)
    w, h = header["width"], header["height"]
    if (header["bit_depth"], header["colour_type"], header["interlace"]) != (8, 6, 0):
        raise ValueError(f"Unit frames must be 8-bit RGBA non-interlaced PNG (this file is {header['bit_depth']}-bit, "
                         f"colour type {header['colour_type']}{', interlaced' if header['interlace'] else ''}).")
    if w * h > max_pixels:
        raise ValueError(f"PNG size {w}x{h} is too large to decode")
    stride, out, prev = w * 4, bytearray(), bytearray(w * 4)
    for y in range(h):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride) if kind else ():
            a, b, c = (line[x - 4] if x >= 4 else 0), prev[x], (prev[x - 4] if x >= 4 else 0)
            line[x] = (line[x] + (a, b, (a + b) >> 1, _paeth(a, b, c))[kind - 1]) & 0xff
        out += line
        prev = line
    return w, h, bytes(out)


UNIT_CANVASES = (32, 64, 128)  # spr1/spr2 sizes from the CoE5 manual, p.14.


def unit_frame_facts(name, data):
    """Decode one unit frame and report its pixel facts and authoring warnings, or raise ValueError.

    Canvas sizes follow the manual. Rejecting empty frames and partial alpha is KENOGENESIS authoring
    policy for crisp sprites; the manual does not say how the engine blends PNG alpha.
    """
    info = inspect_asset(name, data)
    w, h = info.get("width"), info.get("height")
    if w != h or w not in UNIT_CANVASES:
        raise ValueError(f"{w}x{h} is not a CoE5 unit canvas; use 32x32, 64x64 or 128x128 (manual p.14).")
    shadow = None
    if name.lower().endswith(".png"):
        _, _, rgba = decode_png_rgba(data)
        alpha = rgba[3::4]
        partial = sum(1 for a in alpha if a not in (0, 255))
        if partial:
            raise ValueError(f"{partial} pixel(s) are partly transparent. KENOGENESIS requires each pixel fully opaque "
                             "or fully transparent (authoring policy; PNG alpha blending in CoE5 is not documented).")
        drawn = [a == 255 for a in alpha]
        transparency = "alpha channel"
    elif name.lower().endswith(".tga"):
        _, _, rgba = decode_tga(data, key_colours=False)
        alpha = rgba[3::4]
        if data[16] == 24 or alpha == b"\xff" * (w * h):
            # Manual p.2: black is transparent and magenta is shadow when the TGA has no transparent pixels.
            colours = [rgba[i:i + 3] for i in range(0, len(rgba), 4)]
            drawn = [c not in (b"\x00\x00\x00", b"\xff\x00\xff") for c in colours]
            shadow = sum(c == b"\xff\x00\xff" for c in colours)
            transparency = "colour key (black transparent, magenta shadow)"
        else:
            partial = sum(1 for a in alpha if a not in (0, 255))
            if partial:
                raise ValueError(f"{partial} pixel(s) are partly transparent. KENOGENESIS requires each pixel fully "
                                 "opaque or fully transparent (authoring policy, not a documented engine rule).")
            drawn = [a == 255 for a in alpha]
            transparency = "alpha channel"
    else:
        raise ValueError("Unit frames are PNG or TGA.")
    rows = [y for y in range(h) if any(drawn[y * w:(y + 1) * w])]
    if not rows:
        raise ValueError("The frame has no visible pixels.")
    cols = [x for x in range(w) if any(drawn[x::w])]
    x0, y0, x1, y1 = cols[0], rows[0], cols[-1], rows[-1]
    margins = {"left": x0, "top": y0, "right": w - 1 - x1, "bottom": h - 1 - y1}
    warnings = []
    if margins["bottom"] != 2:
        warnings.append(f"{margins['bottom']} free row(s) under the lowest pixel; the manual asks for 2 free pixels "
                        "between the feet and the bottom edge (p.14).")
    edges = [side for side in ("left", "top", "right") if not margins[side]]
    if edges:
        warnings.append(f"The figure touches the {', '.join(edges)} edge; check that nothing is clipped.")
    if w == 128:
        warnings.append("128x128 is the manual's canvas for huge monsters (p.14); confirm this unit is meant to be huge.")
    facts = {"width": w, "height": h, "format": name.rsplit(".", 1)[-1].lower(), "transparency": transparency,
             "bbox": [x0, y0, x1, y1], "figure": [x1 - x0 + 1, y1 - y0 + 1], "margins": margins,
             "visible_pixels": sum(drawn), "warnings": warnings}
    if shadow is not None:
        facts["shadow_pixels"] = shadow
    return facts


def pair_warnings(idle, attack):
    """Consistency warnings between idle and attack facts (either may be None)."""
    if not idle or not attack:
        return []
    out = []
    if (idle["width"], idle["height"]) != (attack["width"], attack["height"]):
        out.append(f"Idle is {idle['width']}x{idle['height']} but attack is {attack['width']}x{attack['height']}; the unit may jump between poses.")
    if idle["margins"]["bottom"] != attack["margins"]["bottom"]:
        out.append(f"Baselines differ: {idle['margins']['bottom']} free row(s) under idle, {attack['margins']['bottom']} under attack.")
    if abs(idle["figure"][1] - attack["figure"][1]) > max(2, idle["figure"][1] // 5):
        out.append(f"Figure heights differ ({idle['figure'][1]} px idle, {attack['figure'][1]} px attack); check that the scale matches.")
    if idle["transparency"] != attack["transparency"]:
        out.append("Idle and attack use different transparency (alpha channel versus colour key).")
    return out


def preview_png(name, data):
    """PNG bytes safe to show in the browser, or ValueError. PNGs are checked, TGAs converted."""
    lower = name.lower()
    if lower.endswith(".png"):
        info = inspect_asset(name, data)
        if info["width"] * info["height"] > MAX_PREVIEW_PIXELS:
            raise ValueError("PNG is too large to preview")
        return data
    if lower.endswith(".tga"):
        inspect_asset(name, data)
        return encode_png(*decode_tga(data))
    raise ValueError("Not a previewable image")
