"""Bounded container checks; asset rendering and map behavior still need the game."""

import struct
import zlib
from pathlib import PurePosixPath


def inspect_asset(name, data):
    suffix = PurePosixPath(name).suffix.lower()
    info = {"path": name, "bytes": len(data), "checks": "container only"}
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid PNG signature")
        pos, seen, compressed = 8, [], bytearray()
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
            if kind == b"IHDR":
                if size != 13:
                    raise ValueError("Invalid PNG header")
                info["width"], info["height"] = struct.unpack(">II", body[:8])
                if not 0 < info["width"] <= 8192 or not 0 < info["height"] <= 8192:
                    raise ValueError("Image exceeds tool dimension limit (8192)")
            if kind == b"IDAT":
                compressed.extend(body)
            seen.append(kind)
            pos += size + 12
            if kind == b"IEND":
                break
        if not seen or seen[0] != b"IHDR" or seen[-1] != b"IEND" or b"IDAT" not in seen or pos != len(data):
            raise ValueError("Incomplete PNG structure")
        # Bounded decompression rejects corrupt streams without trusting image dimensions.
        decoder = zlib.decompressobj()
        decoder.decompress(compressed, 64 * 1024 * 1024)
        if not decoder.eof:
            raise ValueError("Corrupt or oversized PNG stream")
    elif suffix == ".tga":
        if len(data) < 18 or data[1] != 0 or data[2] not in (2, 10) or data[16] not in (24, 32):
            raise ValueError("Expected true-color 24/32-bit uncompressed or RLE TGA")
        width, height = struct.unpack_from("<HH", data, 12)
        if not 0 < width <= 8192 or not 0 < height <= 8192:
            raise ValueError("Image exceeds tool dimension limit (8192)")
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
