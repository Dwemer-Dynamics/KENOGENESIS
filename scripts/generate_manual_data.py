"""Regenerate kenogenesis/manual_data.py from text extracted from Illwinter's CoE5 Modding Manual.

Usage: python scripts/generate_manual_data.py <manual.txt>

<manual.txt> is page-marked text ("=== PAGE n ===") extracted locally from the official PDF
(https://www.illwinter.com/coe5/coe5modding.pdf). The extracted text stays outside the source tree.
The output keeps command names, argument signatures, page numbers, a short first-sentence summary
and the manual's numbered value tables. It is reference data for labels and the advanced editor;
the curated validation registry in commands.py is separate and unchanged by this script.
"""

import json
import re
import sys
from pathlib import Path

SECTIONS = {"Mod Info": "global", "Maps": "global", "Fonts & Translation": "global", "Weapon Modding": "weapon",
            "Magic Item Modding": "item", "Monster Modding": "monster", "Class Modding": "class",
            "Terrain Modding": "terrain", "Terrain Group Modding": "terraingroup", "Ritual Modding": "ritual",
            "Sound Sample Modding": "global", "Misc Modding": "global", "Events": "event", "Updating a Mod": None}
GLOBAL = {"newmonster", "selectmonster", "newweapon", "selectweapon", "newclass", "selectclass", "newritpow",
          "newritual", "selectritual", "newitem", "selectitem", "selectterr", "selectterrgroup", "playerevent",
          "squareevent", "icon", "description", "modprio", "mapfile", "fontfile", "translation", "sample",
          "sampleismusic", "sampleisloopmusic", "playercolor"}
TABLES = {"Damage Types (dmgtype)": "dmgtype", "Resource Types": "resource", "Plane Numbers": "plane",
          "Class Numbers": "class", "Ritual schools (pow nbr)": "ritpow", "Magic Paths (path)": "path",
          "Negative terrain numbers": "terrain_group", "Target Ranks (trgrank)": "trgrank", "Fly Modes (flymode)": "flymode",
          "Magic Item Types": "itemtype", "Objectives": "objective"}
ARG = r'(?:\[?\s*<[^>]*>\s*\]?|\[?\s*["“][^"”]*["”]\s*\]?|\|)'
ARGS_ONLY = re.compile(rf"^\s*(?:{ARG}\s*)+$")
CMD = re.compile(r"^(\+?[a-z][a-z0-9_]*)(?:\s+(.*))?$")
ROW = re.compile(r"^(-?\d+)\s*(?:=\s*)?(.+)$")


def parse_args(sig):
    out = []
    for m in re.finditer(ARG, sig):
        tok = m.group().strip()
        if tok == "|":
            if out:
                out[-1]["alternative"] = True
            continue
        optional = tok.startswith("[")
        tok = tok.strip("[] ")
        quoted = tok[0] in "\"“"
        name = tok.strip('<>"“” ')
        arg = {"name": name, "type": "s" if quoted else "i", "optional": optional}
        rng = re.search(r"(-?\d+)\s*-\s*(-?\d+)$", name)
        if rng and not quoted:
            arg["min"], arg["max"] = int(rng.group(1)), int(rng.group(2))
        out.append(arg)
    # "weapon name" | <nbr> means either a quoted name or a number.
    merged = []
    for arg in out:
        if merged and merged[-1].pop("alternative", False):
            merged[-1]["type"] = "r"
            continue
        merged.append(arg)
    for arg in merged:
        arg.pop("alternative", None)
    return merged


def main(path):
    text = Path(path).read_text("utf-8")
    pages = re.split(r"^=== PAGE (\d+) ===$", text, flags=re.M)
    lines = []
    for i in range(1, len(pages), 2):
        page = int(pages[i])
        for line in pages[i + 1].splitlines():
            lines.append((page, line.replace("’", "'").rstrip()))
    index_start = next(i for i, (p, _) in enumerate(lines) if p == 41)
    index = {}
    for _, line in lines[index_start:]:
        m = re.match(r"^(\+?[a-z][a-z0-9_]*)\b.*?\s(\d+(?:,\s*\d+)*)$", line.strip())
        if m:
            index[m.group(1)] = [int(x) for x in m.group(2).split(",")]
    body = lines[:index_start]
    # Subsection titles from the table of contents end a command description.
    subsections = {re.sub(r"\s+\d+$", "", line).strip() for page, line in lines if page == 1 and re.search(r"\s\d+$", line)}
    commands, tables, context, i = [], {}, None, 0
    seen = set()
    while i < len(body):
        page, line = body[i]
        s = line.strip()
        if s in SECTIONS and page > 1:
            context = SECTIONS[s]
            i += 1
            continue
        if s in TABLES and page > 1:
            rows, j = {}, i + 1
            while j < len(body):
                t = body[j][1].strip()
                m = ROW.match(t)
                if m and not t.isdigit():
                    rows[m.group(1)] = m.group(2).strip()
                elif t.isdigit() or not t:
                    pass
                else:
                    break
                j += 1
            tables.setdefault(TABLES[s], {}).update(rows)
            i = j
            continue
        m = CMD.match(s)
        if context and m and m.group(1) in index and (not m.group(2) or ARGS_ONLY.match(m.group(2))):
            name, sig = m.group(1), m.group(2) or ""
            j = i + 1
            while j < len(body) and ARGS_ONLY.match(body[j][1].strip() or "x"):
                sig += " " + body[j][1].strip()
                j += 1
            descr = []
            while j < len(body):
                t = body[j][1].strip()
                n = CMD.match(t)
                if (n and n.group(1) in index and (not n.group(2) or ARGS_ONLY.match(n.group(2)))) or t in SECTIONS or t in TABLES or t in subsections:
                    break
                if t and not t.isdigit():
                    descr.append(t)
                j += 1
            ctx = "global" if name in GLOBAL else context
            key = (ctx, name)
            tabular = bool(descr) and re.match(r"^[a-z_]+\s+-?\d+\s+[a-z_]+\s+-?\d+", " ".join(descr[:3]))
            if descr and key not in seen and not tabular:
                seen.add(key)
                words = " ".join(descr)
                summary = re.split(r"(?<=[.!?])\s", words, maxsplit=1)[0][:200]
                commands.append({"command": name, "context": ctx, "signature": f"{name} {sig}".strip(),
                                 "args": parse_args(sig), "page": page, "summary": summary})
            i = j
            continue
        i += 1
    out = Path(__file__).resolve().parent.parent / "kenogenesis" / "manual_data.py"
    header = ('"""Generated by scripts/generate_manual_data.py from Illwinter\'s CoE5 Modding Manual 5.36.\n\n'
              "Command names, argument signatures, page numbers, a first-sentence summary and numbered value tables,\n"
              "for labels and the advanced editor. Reference only: curated argument checks live in commands.py.\n"
              'Do not edit by hand; regenerate from the official manual instead.\n"""\n\n')
    body_text = ("MANUAL_COMMANDS = " + json.dumps(commands, ensure_ascii=True, indent=1) + "\n\n"
                 "TABLES = " + json.dumps(tables, ensure_ascii=True, indent=1, sort_keys=True) + "\n")
    out.write_text(header + body_text.replace(": true", ": True").replace(": false", ": False"), "utf-8")
    print(f"{len(commands)} commands, {len(index)} index entries, tables: {sorted(tables)}", file=sys.stderr)
    missing = sorted(set(index) - {c["command"] for c in commands})
    print(f"index entries without a parsed signature: {len(missing)}: {missing[:60]}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
