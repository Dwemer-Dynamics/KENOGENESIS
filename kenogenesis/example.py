"""Independently authored prototype fixture; no extracted or private assets."""

import struct
from pathlib import Path
from .paths import atomic_write_bytes


def populate(mod_root, slug):
    """Generate a small geometric test citadel and copy the public example source."""
    width = height = 64
    header = bytearray(18)
    header[2], header[16], header[17] = 2, 32, 40
    struct.pack_into("<HH", header, 12, width, height)
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            body = 13 <= x <= 50 and 26 <= y <= 55
            tower = (9 <= x <= 22 or 41 <= x <= 54) and 15 <= y <= 55
            gate = 27 <= x <= 36 and 39 <= y <= 55
            if (body or tower) and not gate:
                pixels.extend((127, 103, 91, 255))
            else:
                pixels.extend((0, 0, 0, 0))
    atomic_write_bytes(mod_root / "citadel.tga", bytes(header + pixels))
    atomic_write_bytes(mod_root / f"{slug}.c5m", (Path(__file__).parent / "example.c5m").read_bytes())
