"""Bounded container checks; asset rendering and map behavior still need the game."""

import struct
import zlib
from pathlib import PurePosixPath


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_DIMENSION = 8192  # Tool policy, not an engine limit.
MAX_PNG_RAW = 64 * 1024 * 1024  # Tool policy: the largest filtered scanline stream decompressed.
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def png_layout(width, height, depth, colour_type, interlace):
    """(rows, bytes per row) for each filtered pass, excluding the filter byte."""
    bits = depth * PNG_CHANNELS[colour_type]
    out = []
    for x0, y0, dx, dy in ADAM7 if interlace else ((0, 0, 1, 1),):
        w, h = max(0, (width - x0 + dx - 1) // dx), max(0, (height - y0 + dy - 1) // dy)
        if w and h:
            out.append((h, (w * bits + 7) // 8))
    return out


def read_png(data):
    """Check PNG chunks, header and the filtered scanline stream; return (header, raw scanlines).

    Decompression is bounded by the size the header declares, so corrupt or oversized streams fail
    before any pixel is trusted.
    """
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")
    pos, seen, compressed, ihdr = 8, [], bytearray(), None
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        size = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + size]
        if pos + 12 + size > len(data):
            raise ValueError("Truncated PNG payload")
        crc = int.from_bytes(data[pos + 8 + size:pos + 12 + size], "big")
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("Invalid PNG checksum")
        if not seen and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if kind == b"IHDR":
            if seen or size != 13:
                raise ValueError("Invalid PNG header")
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            if b"IDAT" in seen and seen[-1] != b"IDAT":
                raise ValueError("PNG image data chunks are not consecutive")
            compressed.extend(body)
        elif kind not in (b"PLTE", b"IEND") and not kind[0] & 0x20:
            raise ValueError(f"Unsupported critical PNG chunk {kind.decode('latin-1')!r}")
        seen.append(kind)
        pos += size + 12
        if kind == b"IEND":
            break
        if len(compressed) > MAX_PNG_RAW:
            raise ValueError("PNG image data is too large for this tool")
    if seen[-1:] != [b"IEND"] or b"IDAT" not in seen or pos != len(data):
        raise ValueError("Incomplete PNG structure")
    width, height, depth, colour_type, method, filtering, interlace = ihdr
    if not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION:
        raise ValueError(f"Image exceeds tool dimension limit ({MAX_DIMENSION})")
    if depth not in PNG_DEPTHS.get(colour_type, ()) or method or filtering or interlace not in (0, 1):
        raise ValueError(f"Invalid PNG header (bit depth {depth}, colour type {colour_type})")
    if colour_type == 3 and b"PLTE" not in seen:
        raise ValueError("Palette PNG has no palette")
    layout = png_layout(width, height, depth, colour_type, interlace)
    need = sum(rows * (1 + size) for rows, size in layout)
    if need > MAX_PNG_RAW:
        raise ValueError("PNG is too large for this tool")
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(bytes(compressed), need + 1)
    except zlib.error as exc:
        raise ValueError(f"Corrupt PNG stream: {exc}") from exc
    if len(raw) != need or not decoder.eof or decoder.unused_data:
        raise ValueError("PNG image data does not match its header")
    at = 0
    for rows, size in layout:
        for _ in range(rows):
            if raw[at] > 4:
                raise ValueError(f"Invalid PNG row filter {raw[at]}")
            at += size + 1
    return {"width": width, "height": height, "bit_depth": depth, "colour_type": colour_type,
            "interlace": interlace}, raw


def inspect_asset(name, data):
    suffix = PurePosixPath(name).suffix.lower()
    info = {"path": name, "bytes": len(data), "checks": "container only"}
    if suffix == ".png":
        header, _ = read_png(data)
        info.update(width=header["width"], height=header["height"], bit_depth=header["bit_depth"],
                    colour_type=header["colour_type"], interlaced=bool(header["interlace"]))
    elif suffix == ".tga":
        if len(data) < 18 or data[1] != 0 or data[2] not in (2, 10) or data[16] not in (24, 32):
            raise ValueError("Expected true-color 24/32-bit uncompressed or RLE TGA")
        width, height = struct.unpack_from("<HH", data, 12)
        if not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION:
            raise ValueError(f"Image exceeds tool dimension limit ({MAX_DIMENSION})")
        info.update(width=width, height=height)
        pos, total, pixels, stride = 18 + data[0], 0, width * height, data[16] // 8
        while total < pixels:
            if data[2] == 2:
                pos += pixels * stride
                total = pixels
            else:
                if pos >= len(data):
                    raise ValueError("Truncated TGA RLE packet")
                packet = data[pos]
                count = (packet & 127) + 1
                pos += 1 + (stride if packet & 128 else count * stride)
                total += count
            if pos > len(data) or total > pixels:
                raise ValueError("Truncated or overflowing TGA pixel data")
    elif suffix in (".sw", ".sw2"):
        if not data or len(data) % (4 if suffix == ".sw2" else 2):
            raise ValueError("PCM sample must contain complete 16-bit frames")
        info["assumed_sample_rate"] = 22050
        info["limitations"] = "Raw PCM cannot establish its sample rate from file bytes."
    elif suffix == ".coem":
        if not data:
            raise ValueError("Empty map")
        info["checks"] = "opaque map payload; no geometry or gameplay validation"
    elif suffix == ".ttf":
        if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"ttcf"):
            raise ValueError("Invalid font signature")
    else:
        info["checks"] = "declared supplementary file; semantics unverified"
    return info
