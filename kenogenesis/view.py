"""Read-only browser view model built from one guarded snapshot.

Everything shown is either authored in the saved .c5m, resolved from another definition in the same
mod (with its line), read from the configured local catalog (with provenance), or explicitly
unresolved. Inherited and default values are never guessed. No write happens here.
"""

import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .assets import inspect_asset
from .commands import (ANNOUNCED_COMMANDS, ASSET_ARGS, MANUAL, OPENERS, SCHEMAS, TABLES, announced_entry, command_status,
                       game_profile, is_custom_terrain, manual_entry)
from .parser import parse
from .paths import contained, exact_case_lookup, is_link, mod_relpath_problems

IMAGE_EXT = {".png", ".tga"}
MAX_LISTED_FILES = 2000

KIND_LABEL = {"monster": "Unit", "weapon": "Weapon", "class": "Class", "school": "Ritual school", "ritual": "Ritual",
              "item": "Magic item", "terrain": "Terrain", "terraingroup": "Terrain group", "event": "Event"}
LABELS = {
    "icon": "Mod banner", "description": "Mod description", "modprio": "Load priority", "mapfile": "Map file",
    "sample": "Sound sample", "fontfile": "Font file", "translation": "Translation",
    "name": "Name", "hp": "Hit points", "mr": "Magic resistance", "str": "Strength", "armor": "Armor", "mor": "Morale",
    "rank": "Deployment rank", "spr1": "Sprite", "spr2": "Attack sprite", "descr": "Description",
    "copystats": "Copies stats from", "copyspr": "Copies sprite of", "clearweapons": "Clears weapons", "clearspec": "Clears special abilities",
    "meleeweapon": "Melee weapon", "meleeweaponbonus": "Bonus melee weapon", "rangedweapon": "Ranged weapon",
    "rangedweaponbonus": "Bonus ranged weapon", "power": "Ritual school", "allrit": "Knows all rituals of school",
    "spellweapon": "Cast spell", "spellweaponbonus": "Bonus cast spell", "spellweapon50": "Cast spell (50%)",
    "spellweaponsingle": "Cast single spell", "human": "Human", "undead": "Undead", "animal": "Animal", "inanimate": "Lifeless",
    "holy": "Holy", "flying": "Flying", "slow": "Slow", "fast": "Fast", "noleader": "No leader",
    "range": "Range", "init": "Initiative", "dmgtype": "Damage type", "dmg": "Damage", "aoe": "Area of effect",
    "sound": "Hit sound", "look": "Hit effect", "flymode": "Fly mode", "flylook": "Projectile look", "flysound": "Projectile sound",
    "nextwep": "Chained weapon", "trgrank": "Target rank",
    "setclassname": "Class name", "classdescr": "Class description", "classabdescr": "Ability description",
    "hometerr": "Home citadel terrain", "startplane": "Start plane", "createcit": "Start-plane citadel", "goldbonus": "Gold income bonus (%)",
    "ironbonus": "Iron income bonus (%)", "clearstartunits": "Clears starting army", "clearstartterr": "Clears starting terrain",
    "clearrec": "Clears recruitment", "otherplanar": "Survives without an Elysium citadel", "setmaincom": "Main commander",
    "addstartcom": "Starting commander", "addstartunits": "Starting units", "addstartterr": "Starting terrain",
    "addunitrec": "Recruitable unit", "addmercrec": "Recruitable mercenary", "addcomrec": "Recruitable commander",
    "recxcost": "Extra recruitment cost", "ritpow": "Ritual school", "level": "Level", "cost": "Cost", "terr": "Terrain restriction",
    "copyritual": "Copies ritual", "clearritspec": "Clears ritual specials", "addstring": "String", "summoning": "Summoning",
    "defctrl": "Default control (%)", "soundfx": "Sound effect", "free": "Always known",
    "spr": "Sprite", "gold": "Gold income", "iron": "Iron income", "citadel": "Citadel", "endevent": "End of event",
}
ROW_ARGS = {"addunitrec": ["Unit", "Chance %", "Count", "Gold", "Gold die", "Iron"],
            "addmercrec": ["Unit", "Chance %", "Count", "Gold", "Gold die", "Iron"],
            "addcomrec": ["Commander", "Chance %", "Gold", "Gold die", "Iron"],
            "addstartunits": ["Unit", "Count"], "addstartcom": ["Commander"], "addstartterr": ["Terrain"],
            "recxcost": ["Resource", "Amount"], "cost": ["Resource", "Amount"], "addstring": ["String"],
            "meleeweapon": ["Damage", "Weapon"], "meleeweaponbonus": ["Damage", "Weapon"], "rangedweapon": ["Damage", "Weapon"],
            "rangedweaponbonus": ["Damage", "Weapon"], "power": ["School"], "spellweapon": ["Path", "Level"],
            "spellweaponbonus": ["Path", "Level"], "spellweapon50": ["Path", "Level"], "spellweaponsingle": ["Path", "Level"]}
CHOICES = {"dmgtype": "dmgtype", "flymode": "flymode", "startplane": "plane", "trgrank": "trgrank"}
RANK = {"-1": "back", "0": "mid", "1": "front"}
MONSTER_STATS = ["hp", "mr", "str", "armor", "mor", "rank"]
MONSTER_FLAGS = ["human", "undead", "animal", "inanimate", "holy", "flying", "slow", "fast", "noleader"]
WEAPON_KEYS = ["range", "init", "dmgtype", "dmg", "aoe", "trgrank", "look", "sound", "flymode", "flylook", "flysound", "nextwep"]
ATTACKS = ("meleeweapon", "meleeweaponbonus", "rangedweapon", "rangedweaponbonus")
# Every documented `<dmg> "weapon"` attack command (manual pp.14-15); only ATTACKS have curated argument checks.
ALL_ATTACKS = ATTACKS + ("meleeweaponspec", "meleeweapon50s", "rangedweapon25", "rangedweapon50", "rangedweapon50s",
                         "rangedweapon50x", "siegeweapon", "assassinweapon", "prebatweapon")
SPELLS = ("spellweapon", "spellweaponbonus", "spellweapon50", "spellweaponsingle")
# Alternate forms (manual p.18): "next"/"previous" are adjacent monster definitions in creation order and value
# offsets count from this monster. Only new monsters of this file are resolved, by source order.
SHAPES = {"firstshape": ("next", "becomes when slain"), "secondshape": ("previous", "reverts after combat to"),
          "growhp": ("previous", "grows at high hit points into"), "shrinkhp": ("next", "shrinks at low hit points into"),
          "growtime": ("next", "grows over time into"), "split": ("next", "splits into"), "reform": ("previous", "reforms into"),
          "mastery": ("offset", "levels up into"),
          **{f"{plane}shape": ("offset", f"in {label} becomes") for plane, label in (
              ("land", "land squares"), ("water", "the sea"), ("elysium", "Elysium"), ("celestial", "the Celestial plane"),
              ("sky", "the Sky plane"), ("agartha", "Agartha"), ("inferno", "the Inferno"), ("hades", "Hades"),
              ("aztlan", "Aztlan"), ("primal", "the Primal plane"), ("elemental", "the Elemental planes"), ("void", "the Void"))}}
SHOWN_ELSEWHERE = set(MONSTER_STATS) | set(MONSTER_FLAGS) | set(ALL_ATTACKS) | set(SPELLS) | set(SHAPES) | {
    "power", "allrit", "spr1", "spr2", "descr", "name", "copystats", "copyspr", "clearweapons", "clearspec", "clearmove", "growoffs"}
REF_KIND = {"copystats": "monster", "copyspr": "monster", "setmaincom": "monster", "addstartcom": "monster",
            "addstartunits": "monster", "addunitrec": "monster", "addmercrec": "monster", "addcomrec": "monster",
            **{c: "weapon" for c in ALL_ATTACKS},
            "nextwep": "weapon", "copyritual": "ritual", "hometerr": "terrain", "createcit": "terrain", "addstartterr": "terrain"}
REF_ARG = {c: 1 for c in ALL_ATTACKS}
RELATION = {"copystats": "copies stats from", "copyspr": "copies the sprite of", "setmaincom": "has as main commander",
            "addstartcom": "starts with commander", "addstartunits": "starts with", "addunitrec": "recruits",
            "addmercrec": "recruits as mercenary", "addcomrec": "recruits commander", "meleeweapon": "is armed with",
            "meleeweaponbonus": "is armed with", "rangedweapon": "is armed with", "rangedweaponbonus": "is armed with",
            **{c: "is armed with" for c in ALL_ATTACKS[4:]},
            "nextwep": "chains into", "copyritual": "copies ritual", "hometerr": "has as home citadel",
            "createcit": "has as start-plane citadel", "addstartterr": "starts with terrain", "addstring": "summons",
            "power": "casts rituals of", "ritpow": "belongs to school", "allrit": "knows all rituals of"}
FORMS = {
    "global": [("icon", "file"), ("description", "textarea"), ("modprio", "int")],
    "monster": [("name", "text"), ("hp", "int"), ("mr", "int"), ("str", "int"), ("armor", "int"), ("mor", "int"),
                ("rank", "rank"), ("descr", "textarea"), ("spr1", "file"), ("spr2", "file")] + [(f, "flag") for f in MONSTER_FLAGS],
    "weapon": [(k, "choice" if k in CHOICES else "text" if k == "nextwep" else "int") for k in WEAPON_KEYS],
    "class": [("setclassname", "text"), ("classdescr", "textarea"), ("classabdescr", "textarea"), ("hometerr", "terrain"),
              ("startplane", "choice"), ("createcit", "terrain"), ("goldbonus", "int"), ("ironbonus", "int"),
              ("setmaincom", "monster"), ("otherplanar", "flag")],
    "ritual": [("ritpow", "int"), ("level", "int"), ("terr", "int"), ("defctrl", "int"), ("soundfx", "int"),
               ("summoning", "flag"), ("free", "flag")],
    "terrain": [("name", "text"), ("spr", "file"), ("gold", "int"), ("iron", "int"), ("citadel", "flag")],
}
LABELS.update({"meleeweaponspec": "Special melee weapon", "meleeweapon50s": "Melee weapon (50%, skip)",
               "rangedweapon25": "Ranged weapon (25%)", "rangedweapon50": "Ranged weapon (50%)",
               "rangedweapon50s": "Ranged weapon (skip in melee)", "rangedweapon50x": "Ranged weapon (50%, skip)",
               "siegeweapon": "Siege weapon", "assassinweapon": "Assassination weapon", "prebatweapon": "Pre-battle effect",
               "firstshape": "Becomes next monster when slain", "secondshape": "Reverts to previous monster after combat",
               "growhp": "Grows at hit points", "shrinkhp": "Shrinks at hit points", "growtime": "Grows after turns",
               "growoffs": "Growth target offset", "split": "Splits at damage %", "reform": "Reforms chance %",
               "mastery": "Level-up form offset", "clearmove": "Clears movement"})
ROW_ARGS.update({c: ["Damage", "Weapon"] for c in ALL_ATTACKS})
ROWS = {"monster": [("Attacks", list(ALL_ATTACKS)), ("Ritual power", ["power"]), ("Combat spells", list(SPELLS))],
        "class": [("Starting army", ["addstartcom", "addstartunits"]), ("Starting terrain", ["addstartterr"]),
                  ("Recruitment", ["addunitrec", "addcomrec", "addmercrec", "recxcost"])],
        "ritual": [("Costs", ["cost"]), ("Strings (summons)", ["addstring"])]}
# Which row column names another definition or a numbered manual table, for pickers and reference checks.
ROW_REFS = {**{c: ["monster"] for c in ("addunitrec", "addmercrec", "addcomrec", "addstartunits", "addstartcom")},
            **{c: [None, "weapon"] for c in ALL_ATTACKS}, "addstartterr": ["terrain"]}
ROW_TABLES = {"cost": ["resource"], "recxcost": ["resource"], "power": ["ritpow"], **{c: ["path"] for c in SPELLS}}
# Row arguments that also take 0/negative school numbers counted back over newritpow blocks above the line (manual p.17).
# Only power documents this; ritpow and allrit keep their table numbers.
RELATIVE_SCHOOLS = {"power": {"arg": 0, "page": 17, "zero": "latest newritpow above this line", "negative": "earlier newritpow, counting back"}}
# How each block kind can open (manual pp.4-38). Select openers name existing game content; no IDs are allocated.
OPENER_MODES = {"monster": ["newmonster", "selectmonster"], "weapon": ["newweapon", "selectweapon"], "class": ["newclass", "selectclass"],
                "school": ["newritpow"], "ritual": ["newritual", "selectritual"], "item": ["newitem", "selectitem"],
                "terrain": ["selectterr"], "terraingroup": ["selectterrgroup"], "event": ["playerevent", "squareevent"]}


def label(command):
    return LABELS.get(command, command)


def signature_args(kind, command):
    """Curated argument codes, or codes derived from the manual signature (s/i/r, ? when optional)."""
    spec = SCHEMAS.get((kind, command)) or SCHEMAS.get(("global", command))
    if spec:
        return spec["args"], "curated"
    entry = manual_entry(kind, command)
    if entry:
        return [a["type"] + ("?" if a.get("optional") else "") for a in entry["args"]], "documented"
    return [], "unknown"


def opener_specs():
    """Opening modes per block kind with named arguments from the manual and the curated check codes."""
    out = {}
    for kind, commands in OPENER_MODES.items():
        rows = []
        for command in commands:
            entry = manual_entry("global", command) or {}
            codes, status = signature_args("global", command)
            names = [a.get("name") for a in entry.get("args", [])]
            rows.append({"command": command, "new": command.startswith("new") or command.endswith("event"),
                         "signature": entry.get("signature", command), "page": entry.get("page"), "summary": entry.get("summary", ""),
                         "args": [{"code": code, "name": names[i] if i < len(names) and names[i] else f"argument {i + 1}",
                                   "optional": code.endswith("?"), "min": 0 if command in ("selectmonster", "selectritual") and i == 1 else None}
                                  for i, code in enumerate(codes)], "status": status})
        out[kind] = rows
    return out


def arg_value(st, i=0):
    return st["args"][i]["value"] if len(st["args"]) > i else None


def catalog_scalar(row, key, version):
    """Read a printed scalar without reviving a value overwritten by a later catalog copy."""
    statements = parse("\n".join(s for s in row.get("statements", []) if isinstance(s, str)).encode("utf-8"))["statements"]
    last_copy = max((s["line"] for s in statements if s["command"] == "copystats"), default=0)
    live = [s for s in statements if s["command"] == key and s["line"] > last_copy]
    value = arg_value(live[-1]) if live else row.get(key) if not last_copy else None
    if value is not None:
        return {"value": str(value), "source": "catalog", "note": f"Explicit local catalog value (game {version})."}
    return {"value": None, "source": "unresolved", "note": "Not printed after the last copystats; copied values and game defaults are not resolved."}


def as_int(v):
    return int(v) if isinstance(v, str) and re.fullmatch(r"-?\d+", v) else None


def table_label(table, value):
    return TABLES.get(table, {}).get(str(value))


def form_specs():
    """Structured form fields with labels, types, documented ranges and manual pages, per block kind."""
    out = {}
    for kind, fields in FORMS.items():
        rows = []
        for key, typ in fields:
            spec = SCHEMAS.get((kind if kind != "global" else "global", key)) or SCHEMAS.get(("global", key))
            entry = manual_entry(kind, key) or {}
            item = {"key": key, "label": label(key), "type": typ, "page": (spec or {}).get("page") or entry.get("page"),
                    "help": entry.get("summary", ""), "signature": entry.get("signature", key)}
            sig = (spec or {}).get("args", [])
            if sig and ":" in sig[0]:
                _, lo, hi = sig[0].rstrip("?").split(":")
                item["min"], item["max"] = int(lo), int(hi)
            if typ == "choice":
                item["choices"] = [{"value": k, "label": v} for k, v in sorted(TABLES.get(CHOICES[key], {}).items(), key=lambda x: int(x[0]))]
            if typ == "rank":
                item["choices"] = [{"value": k, "label": v} for k, v in RANK.items()]
            rows.append(item)
        groups = []
        for title, commands in ROWS.get(kind, []):
            entries = []
            for c in commands:
                codes, status = signature_args(kind, c)
                entry = manual_entry(kind, c) or {}
                names = [a.get("name") for a in entry.get("args", [])]
                columns = ROW_ARGS.get(c) or names
                refs, tables = ROW_REFS.get(c, []), ROW_TABLES.get(c, [])
                entries.append({"command": c, "label": label(c), "columns": columns, "args": codes, "status": status,
                                "page": (SCHEMAS.get((kind, c)) or {}).get("page") or entry.get("page"),
                                "signature": entry.get("signature", c), "summary": entry.get("summary", ""),
                                "refs": [refs[i] if i < len(refs) else None for i in range(len(codes))],
                                "choices": [[{"value": k, "label": v} for k, v in sorted(TABLES.get(tables[i], {}).items(), key=lambda x: int(x[0]))]
                                            if i < len(tables) and tables[i] else None for i in range(len(codes))]})
                if c in RELATIVE_SCHOOLS:
                    entries[-1]["relative"] = RELATIVE_SCHOOLS[c]
            groups.append({"title": title, "commands": entries})
        out[kind] = {"fields": rows, "rows": groups}
    return out


def registry():
    """Every command the reference lists: curated (checked) entries, the manual's documented ones and release-note
    names marked announced (no signature; the editor does not offer them)."""
    from .manual_data import MANUAL_COMMANDS
    seen, out = set(), []
    for (ctx, cmd), spec in SCHEMAS.items():
        entry = manual_entry(ctx, cmd) or {}
        out.append({"command": cmd, "context": ctx, "status": "curated", "page": spec["page"], "args": spec["args"],
                    "repeat": spec["repeat"], "label": label(cmd), "signature": entry.get("signature", cmd),
                    "summary": entry.get("summary", ""), "note": spec["note"],
                    "arg_names": [a.get("name") for a in entry.get("args", [])]})
        seen.add((ctx, cmd))
    for entry in MANUAL_COMMANDS:
        key = (entry["context"], entry["command"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"command": entry["command"], "context": entry["context"], "status": "documented", "page": entry["page"],
                    "manual_args": entry["args"], "label": label(entry["command"]), "signature": entry["signature"],
                    "summary": entry["summary"]})
    for cmd, ctx in ANNOUNCED_COMMANDS.items():
        entry = announced_entry(ctx, cmd)
        out.append({"command": cmd, "context": ctx, "status": "announced", "page": None, "label": label(cmd),
                    "signature": None, "summary": entry["note"], "minimum_version": entry["minimum_version"]})
    return out


def file_url(slug, path, png=False):
    return f"/api/projects/{quote(slug)}/files/{'/'.join(quote(p) for p in path.split('/'))}" + ("?format=png" if png else "")


class Model:
    def __init__(self, core, snapshot, report, exports):
        self.core, self.s, self.report = core, snapshot, report
        self.mod = snapshot["mods"][-1]
        self.slug = self.mod["slug"]
        self.parsed = self.mod["parsed"]
        self.data = self.mod["data"]
        self.objects = self.parsed["objects"]
        self.exports = exports
        self.catalog = snapshot["catalog"]
        self.mod_root = contained(snapshot["root"], f"mod/{self.slug}")
        self.asset_index = {}

    # ----- lookups -----
    def defs(self, kind):
        return [o for o in self.objects if o["kind"] == kind]

    def catalog_rows(self, kind, name):
        if not self.catalog:
            return []
        return [i for i, r in enumerate(self.catalog["rows"]) if r.get("kind") == kind and (r.get("name") == name or str(r.get("id", "")) == str(name))]

    def resolve(self, kind, ref, line):
        """Resolve a name/number reference to a local definition, a catalog row, or explicit uncertainty."""
        if ref is None or ref == "":
            return {"status": "unresolved", "name": None, "note": "no argument"}
        name, offset = ref, 0
        m = re.fullmatch(r"(\d+):(.+)", str(ref))
        if m and kind == "monster":
            offset, name = int(m.group(1)), m.group(2)
        if kind == "terrain":
            hits = [o for o in self.defs("terrain") if o["name"] == str(ref)]
        else:
            hits = [o for o in self.defs(kind) if o["name"] == name]
        loose = [] if hits else [o for o in self.defs(kind) if o["name"].casefold() == str(name).casefold()]
        pool = hits or loose
        if pool:
            target = pool[min(offset, len(pool) - 1)] if offset < len(pool) else None
            if target is not None:
                status = "local" if target["line"] < line else "later"
                out = {"status": status, "index": target["index"], "name": target["name"], "kind": kind,
                       "new": target["opener"].startswith("new") or self.is_custom_terrain(target)}
                if loose:
                    out["note"] = "Matched ignoring letter case; the game's name matching is not verified."
                if status == "later":
                    out["note"] = "Defined later in this file; the manual requires prerequisites first."
                if len(pool) > 1 and not m:
                    out["note"] = f"{len(pool)} definitions share this name; the first is used unless an offset is given."
                return out
        rows = self.catalog_rows(kind, name)
        if len(rows) == 1:
            row = self.catalog["rows"][rows[0]]
            return {"status": "catalog", "catalog": rows[0], "name": row.get("name"), "id": row.get("id"), "kind": kind}
        if len(rows) > 1:
            return {"status": "ambiguous", "name": name, "kind": kind, "note": f"{len(rows)} catalog rows match."}
        note = "Not defined in this mod; a vanilla reference cannot be verified without a catalog." if not self.catalog else \
            "Not defined in this mod or found in the catalog."
        return {"status": "unresolved", "name": name, "kind": kind, "note": note}

    def is_custom_terrain(self, o):
        return o["opener"] == "selectterr" and is_custom_terrain(o["name"], self.s["meta"].get("target_version"))

    @staticmethod
    def _citadel_state(statements):
        """Last explicit citadel or clear in source order: ("citadel"|"clearspec"|"clearfort", line) or None."""
        state = None
        for st in statements:
            if st["command"] in ("citadel", "clearspec", "clearfort"):
                state = (st["command"], st["line"])
        return state

    def citadel_evidence(self, target):
        """Source-backed citadel evidence for a resolved terrain reference. Local blocks take precedence; a local
        clear never keeps a catalog citadel; unknown values stay unknown (citadel None)."""
        status = target.get("status")
        if status in ("ambiguous", "unresolved"):
            return {"status": status, "citadel": None, "note": f"Terrain reference is {status}: {target.get('note') or 'no match'}"}
        number = str(target.get("name"))
        local = [o for o in self.defs("terrain") if o["name"] == number] if status in ("local", "later") else []
        if local:
            state = self._citadel_state([st for o in local for st in o["statements"]])
            if state and state[0] == "citadel":
                return {"status": "local", "citadel": True, "source": "authored", "line": state[1],
                        "note": f"citadel on line {state[1]} of this mod."}
            if state:
                return {"status": "cleared", "citadel": None, "source": "authored", "line": state[1], "command": state[0],
                        "note": f"{state[0]} on line {state[1]} comes after any citadel; whether it removes citadel is not "
                                "documented precisely, so no catalog citadel is assumed."}
            if self.is_custom_terrain(local[0]):
                return {"status": "not_marked", "citadel": False, "source": "authored", "line": local[0]["line"],
                        "note": "New custom terrain without a citadel statement."}
        rows = [target["catalog"]] if status == "catalog" else self.catalog_rows("terrain", number)
        prefix = "The local block sets no citadel or clear, so the existing terrain's value applies. " if local else ""
        if not self.catalog:
            return {"status": "unresolved", "citadel": None, "note": prefix + "The existing terrain's citadel status needs a catalog."}
        if len(rows) > 1:
            return {"status": "ambiguous", "citadel": None, "note": prefix + f"{len(rows)} catalog terrain rows match."}
        if not rows:
            return {"status": "unresolved", "citadel": None, "note": prefix + "The terrain is not in the catalog."}
        row = self.catalog["rows"][rows[0]]
        state = self._citadel_state(parse("\n".join(s for s in row.get("statements", []) if isinstance(s, str)).encode("utf-8"))["statements"])
        version, target_version = self.catalog["game_version"], self.s["meta"].get("target_version")
        out = {"source": "catalog", "catalog": rows[0], "game_version": version, "catalog_source": self.s.get("catalog_source") or "configured",
               "provenance": f"{row.get('source_file', 'catalog')}:{row.get('source_line', '?')}",
               "version_mismatch": version != target_version}
        mismatch = f" The catalog describes game {version}; the project targets {target_version or 'no version'}." if out["version_mismatch"] else ""
        if state and state[0] == "citadel":
            return {**out, "status": "catalog", "citadel": True,
                    "note": prefix + f"The local catalog row ({out['provenance']}, game {version}) states citadel." + mismatch}
        if state:
            return {**out, "status": "unresolved", "citadel": None,
                    "note": prefix + f"The catalog row ({out['provenance']}, game {version}) ends with {state[0]}; "
                            "its effect on citadel is not documented precisely." + mismatch}
        return {**out, "status": "not_marked", "citadel": False,
                "note": prefix + f"The local catalog row ({out['provenance']}, game {version}) states no citadel"
                        + (f" after {state[0]}." if state else ".") + mismatch}

    def schools_before(self, line):
        return [o for o in self.defs("school") if o["line"] < line]

    def school_ref(self, value, line, relative_allowed=True):
        v = as_int(value)
        if v is None:
            return {"status": "unresolved", "note": "not a number"}
        if v > 0:
            return {"status": "vanilla", "value": v, "name": table_label("ritpow", v) or f"school {v}",
                    "note": "Existing CoE5 ritual school (manual p.24 table)."}
        if not relative_allowed:
            return {"status": "unresolved", "value": v, "note": "Relative numbers are documented for power, not ritpow."}
        before = self.schools_before(line)
        if 1 - v > len(before):
            return {"status": "unresolved", "value": v, "note": "No new ritual school this far back in this file; it may come from another mod."}
        school = before[v - 1] if v < 0 else before[-1]
        return {"status": "local", "index": school["index"], "value": v, "name": self.school_name(school),
                "note": "0 is the latest school created before this line, -1 the one before (manual p.17)."}

    def school_name(self, school):
        ordinal = self.defs("school").index(school) + 1
        return f"New ritual school {ordinal}"

    # ----- fields -----
    def field(self, obj, command, i=0):
        sts = [st for st in obj["statements"] if st["command"] == command]
        if not sts:
            return None
        st = sts[-1]
        return {"value": arg_value(st, i), "line": st["line"], "source": "authored", "count": len(sts)}

    def stat(self, obj, key, seen=None):
        """One monster stat: authored, from a local donor, from the catalog, or explicitly unresolved."""
        sts = obj["statements"]
        copies = [st for st in sts if st["command"] == "copystats"]
        last_copy = copies[-1]["line"] if copies else 0
        authored = [st for st in sts if st["command"] == key]
        live = [st for st in authored if st["line"] > last_copy]
        if live:
            st = live[-1]
            return {"value": arg_value(st), "source": "authored", "line": st["line"]}
        overwritten = [st["line"] for st in authored]
        if copies:
            donor = self.resolve("monster", arg_value(copies[-1]), copies[-1]["line"])
            note = f"Line {', '.join(map(str, overwritten))} is replaced by the later copystats. " if overwritten else ""
            if donor["status"] in ("local", "later") and (seen or set()).isdisjoint({donor["index"]}) and donor["status"] == "local":
                inner = self.stat(self.objects[donor["index"]], key, (seen or set()) | {obj["index"]})
                if inner["value"] is not None:
                    return {"value": inner["value"], "source": "donor", "line": inner.get("line"), "via": donor["name"],
                            "note": note + f"From {donor['name']} (copystats line {copies[-1]['line']})."}
                return {"value": None, "source": "unresolved", "via": donor["name"], "note": note + f"{donor['name']} does not resolve {key}: {inner.get('note', '')}"}
            if donor["status"] == "catalog":
                row = self.catalog["rows"][donor["catalog"]]
                value = catalog_scalar(row, key, self.catalog["game_version"])
                return {**value, "via": donor["name"], "note": note + value["note"]}
            return {"value": None, "source": "unresolved", "via": donor.get("name"),
                    "note": note + f"Inherited from {donor.get('name')}; not resolved ({donor.get('note', 'no catalog value')})."}
        if obj["opener"] == "selectmonster":
            rows = self.catalog_rows("monster", obj["name"])
            if len(rows) == 1:
                return catalog_scalar(self.catalog["rows"][rows[0]], key, self.catalog["game_version"])
            return {"value": None, "source": "unresolved", "note": "Vanilla value of the selected monster; needs a catalog."}
        return {"value": None, "source": "default", "note": "Not set and no copystats: the game default is not modelled."}

    # ----- alternate forms and inherited attacks -----
    def shape_links(self, o):
        """Alternate-form targets of one monster, resolved only by new-monster source order in this file."""
        reset = max((st["line"] for st in o["statements"] if st["command"] in ("copystats", "clearspec")), default=0)
        # A later setting replaces the earlier one; never keep an edge disabled by a later zero.
        latest = {st["command"]: st for st in o["statements"] if st["line"] > reset}
        sts = sorted(latest.values(), key=lambda st: st["line"])
        growoffs = next((st for st in reversed(sts) if st["command"] == "growoffs"), None)
        order = [x for x in self.objects if x["kind"] == "monster" and x["opener"] == "newmonster"]
        out = []
        for st in sts:
            c = st["command"]
            if c not in SHAPES:
                continue
            mode, relation = SHAPES[c]
            value = as_int(arg_value(st))
            if c in ("firstshape", "secondshape") and value != 1:
                continue  # 0 switches the form off (manual p.18).
            note = ""
            if mode == "offset":
                offset = value
            elif c == "growtime" and growoffs:
                offset, note = as_int(arg_value(growoffs)), f"Offset from growoffs on line {growoffs['line']}. "
            else:
                offset = 1 if mode == "next" else -1
            link = {"command": c, "line": st["line"], "value": arg_value(st), "relation": relation, "offset": offset}
            if not offset:
                link["target"] = {"status": "unresolved", "kind": "monster", "note": note + "No usable monster offset."}
            elif o["opener"] != "newmonster":
                link["target"] = {"status": "unresolved", "kind": "monster",
                                  "note": "Counts from the selected monster's place in the game's own order; not resolved."}
            else:
                pos = order.index(o) + offset
                if 0 <= pos < len(order):
                    t = order[pos]
                    link["target"] = {"status": "local", "index": t["index"], "name": t["name"], "kind": "monster", "new": True,
                                      "note": note + "Resolved by new-monster order in this file (manual p.18); adding or moving "
                                              "monsters changes it. Verify in game."}
                else:
                    link["target"] = {"status": "unresolved", "kind": "monster",
                                      "note": note + "Outside this file's new monsters; the order across mods is not verified."}
            out.append(link)
        return out

    def attack_rows(self, sts, after=0):
        after = max(after, max((st["line"] for st in sts if st["command"] in ("copystats", "clearweapons")), default=0))
        return [{"command": st["command"], "label": label(st["command"]), "dmg": arg_value(st, 0), "line": st["line"],
                 "ref": arg_value(st, 1)} for st in sts if st["command"] in ALL_ATTACKS and st["line"] > after]

    def inherited_attacks(self, o, seen=frozenset()):
        """Attacks a copystats donor states explicitly; combinations the manual does not describe stay partial."""
        sts = o["statements"]
        copies = [st for st in sts if st["command"] == "copystats"]
        if not copies:
            return None
        last = copies[-1]
        clear = next((st for st in sts if st["command"] == "clearweapons" and st["line"] > last["line"]), None)
        if clear:
            return {"status": "cleared", "line": clear["line"], "via": arg_value(last),
                    "note": f"clearweapons on line {clear['line']} removes the attacks copied on line {last['line']}."}
        donor = self.resolve("monster", arg_value(last), last["line"])
        base = {"via": donor.get("name") or arg_value(last), "line": last["line"], "weapons": []}
        if donor["status"] == "local" and donor["index"] not in seen | {o["index"]}:
            d = self.objects[donor["index"]]
            inner = self.inherited_attacks(d, seen | {o["index"]})
            d_copy = max([st["line"] for st in d["statements"] if st["command"] == "copystats"], default=0)
            own = [dict(w, weapon=self.resolve("weapon", w["ref"], w["line"]), source=d["name"]) for w in self.attack_rows(d["statements"], d_copy)]
            if inner is None or inner["status"] == "cleared":
                return {**base, "status": "resolved", "weapons": own,
                        "note": f"From {d['name']} (copystats line {last['line']}), which states these attacks itself."}
            return {**base, "status": "partial", "weapons": own + inner.get("weapons", []),
                    "note": f"{d['name']} copies another monster too; whether its own attacks add to or replace the copied ones is not modelled."}
        if donor["status"] == "catalog":
            row = self.catalog["rows"][donor["catalog"]]
            parsed = parse("\n".join(x for x in row.get("statements", []) if isinstance(x, str)).encode("utf-8"))
            rows = self.attack_rows(parsed["statements"])
            copied = any(st["command"] == "copystats" for st in parsed["statements"])
            return {**base, "status": "partial" if copied else "catalog",
                    "weapons": [dict(w, weapon=self.resolve("weapon", w["ref"], o["line"]), source="catalog", line=None) for w in rows],
                    "note": f"Explicit attack commands in the local catalog row (game {self.catalog['game_version']}); "
                            + ("that row also copies another monster, which is not resolved." if copied else "game defaults are not modelled.")}
        if donor["status"] == "local":
            return {**base, "status": "unresolved", "note": "Copy chain loops back to this unit; not resolved."}
        return {**base, "status": "unresolved", "note": donor.get("note") or "Donor not resolved."}

    # ----- views -----
    def statements(self, obj):
        codec = self.parsed["encoding"].replace("-sig", "")
        out = []
        for st in obj["statements"]:
            code = self.data[st["start"] + st["indent"]:st["code_end"]].decode(codec)
            entry = manual_entry(st["context"], st["command"]) or {}
            out.append({"line": st["line"], "command": st["command"], "args": [a["value"] for a in st["args"]],
                        "quoted": [a["quoted"] for a in st["args"]], "code": code, "status": command_status(st["context"], st["command"]),
                        "page": (SCHEMAS.get((st["context"], st["command"])) or SCHEMAS.get(("global", st["command"])) or {}).get("page") or entry.get("page"),
                        "label": label(st["command"]), "opener": st["command"] in OPENERS})
        return out

    def source_text(self, obj):
        codec = self.parsed["encoding"].replace("-sig", "")
        first, last = obj["statements"][0], obj["statements"][-1]
        return self.data[first["start"]:last["end"]].decode(codec).rstrip("\r\n"), last["line"]

    def sprite(self, path, line, command):
        if not path:
            return None
        info = self.asset_index.get(path) or {"status": "missing"}
        ok = info.get("status") == "ok"
        return {"path": path, "line": line, "command": command, "status": info.get("status"),
                "url": file_url(self.slug, path, png=path.lower().endswith(".tga")) if ok and Path(path).suffix.lower() in IMAGE_EXT else None,
                "width": info.get("width"), "height": info.get("height"), "problem": info.get("problem")}

    def monster_view(self, o):
        sts = o["statements"]
        donor_st = next((st for st in reversed(sts) if st["command"] == "copystats"), None)
        spr_st = next((st for st in reversed(sts) if st["command"] == "copyspr"), None)
        donor = dict(self.resolve("monster", arg_value(donor_st), donor_st["line"]), command="copystats", line=donor_st["line"],
                     ref=arg_value(donor_st)) if donor_st else None
        stats = {k: self.stat(o, k) for k in MONSTER_STATS}
        flag_reset = max((st["line"] for st in sts if st["command"] in ("copystats", "clearspec")), default=0)
        flags = [{"command": st["command"], "label": label(st["command"]), "line": st["line"]} for st in sts
                 if st["command"] in MONSTER_FLAGS and st["line"] > flag_reset]
        clears = [{"command": st["command"], "line": st["line"]} for st in sts if st["command"].startswith("clear")]
        last_copy = donor_st["line"] if donor_st else 0
        attack_reset = max(last_copy, max((st["line"] for st in sts if st["command"] == "clearweapons"), default=0))
        weapons = []
        for st in sts:
            if st["command"] in ALL_ATTACKS and st["line"] > attack_reset:
                ref = arg_value(st, 1)
                weapons.append({"command": st["command"], "label": label(st["command"]), "dmg": arg_value(st, 0), "line": st["line"],
                                "weapon": self.resolve("weapon", ref, st["line"]), "ref": ref,
                                "note": f"Authored before copystats on line {last_copy}, which may replace it." if st["line"] < last_copy else None})
        clearspec = [st["line"] for st in sts if st["command"] == "clearspec"]
        abilities = []
        for st in sts:
            c = st["command"]
            if c in OPENERS or c in SHOWN_ELSEWHERE:
                continue
            entry = manual_entry("monster", c) or {}
            notes = [f"Authored before copystats on line {last_copy}, which may replace it."] if st["line"] < last_copy else []
            later = [n for n in clearspec if n > st["line"]]
            if later:
                notes.append(f"clearspec on line {later[0]} may remove it.")
            abilities.append({"command": c, "label": label(c), "args": [a["value"] for a in st["args"]], "line": st["line"],
                              "status": command_status("monster", c), "summary": entry.get("summary"), "page": entry.get("page"),
                              "note": " ".join(notes) or None})
        resets = [{"command": st["command"], "label": label(st["command"]), "line": st["line"], "ref": arg_value(st)}
                  for st in sts if st["command"] in ("copystats", "copyspr") or st["command"].startswith("clear")]
        cleared = any(st["command"] == "clearweapons" for st in sts)
        weapons_status = "authored" if weapons and (cleared or not donor_st) else "partial" if weapons else "cleared" if cleared else \
            "inherited" if donor_st else "none"
        spells = [{"command": st["command"], "label": label(st["command"]), "path": arg_value(st, 0),
                   "path_label": table_label("path", arg_value(st, 0)), "level": arg_value(st, 1), "line": st["line"]}
                  for st in sts if st["command"] in SPELLS]
        powers = [dict(self.school_ref(arg_value(st), st["line"]), line=st["line"]) for st in sts if st["command"] == "power"]
        allrit = [{"value": arg_value(st), "line": st["line"], "name": "all schools" if arg_value(st) == "-1" else table_label("ritpow", arg_value(st))}
                  for st in sts if st["command"] == "allrit"]
        s1 = next((st for st in reversed(sts) if st["command"] == "spr1"), None)
        s2 = next((st for st in reversed(sts) if st["command"] == "spr2"), None)
        sprites = {"idle": self.sprite(arg_value(s1), s1["line"], "spr1") if s1 else None,
                   "attack": self.sprite(arg_value(s2), s2["line"], "spr2") if s2 else None}
        if s1 and donor_st and s1["line"] < donor_st["line"]:
            sprites["overwritten"] = {"line": s1["line"], "by": donor_st["line"]}
        if not s1:
            src = spr_st or donor_st
            sprites["inherited"] = ({"command": src["command"], "line": src["line"], "ref": arg_value(src),
                                     "target": self.resolve("monster", arg_value(src), src["line"])} if src else None)
        descr = self.field(o, "descr")
        return {"stats": stats, "donor": donor, "flags": flags, "clears": clears, "weapons": weapons, "weapons_status": weapons_status,
                "inherited_weapons": self.inherited_attacks(o), "abilities": abilities, "resets": resets, "forms": self.shape_links(o),
                "spells": spells, "powers": powers, "allrit": allrit, "sprites": sprites,
                "description": descr["value"].replace("^", "\n") if descr else None,
                "rename": (self.field(o, "name") or {}).get("value")}

    def weapon_view(self, o):
        out = {}
        for key in WEAPON_KEYS:
            f = self.field(o, key)
            if f:
                f["label"] = label(key)
                if key in CHOICES:
                    f["meaning"] = table_label(CHOICES[key], f["value"])
                if key == "nextwep":
                    f["target"] = self.resolve("weapon", f["value"], f["line"])
                out[key] = f
        specials = [{"command": st["command"], "line": st["line"], "summary": (manual_entry("weapon", st["command"]) or {}).get("summary")}
                    for st in o["statements"] if st["command"] not in OPENERS and st["command"] not in WEAPON_KEYS]
        return {"fields": out, "specials": specials,
                "defaults": "Unset values use the game defaults stated in the manual (range, init 2, dmgtype 3, dmg 0); not modelled here." if o["opener"] == "newweapon"
                else "Unset values keep the existing weapon's values; not resolved without a catalog."}

    def class_view(self, o):
        sts = o["statements"]
        f = lambda c: self.field(o, c)
        view = {k: f(k) for k in ("setclassname", "classdescr", "classabdescr", "hometerr", "startplane", "createcit", "goldbonus", "ironbonus")}
        for k in ("classdescr", "classabdescr"):
            if view[k]:
                view[k]["value"] = view[k]["value"].replace("^", "\n")
        for k in ("hometerr", "createcit"):
            if view[k]:
                target = self.resolve("terrain", view[k]["value"], view[k]["line"])
                if target["status"] in ("local", "later"):
                    target["label"] = (self.field(self.objects[target["index"]], "name") or {}).get("value")
                evidence = self.citadel_evidence(target)
                target["citadel"], target["citadel_evidence"] = evidence["citadel"], evidence
                view[k]["target"] = target
        if view["startplane"]:
            view["startplane"]["meaning"] = table_label("plane", view["startplane"]["value"])
        mc = next((st for st in reversed(sts) if st["command"] == "setmaincom"), None)
        view["main_commander"] = dict(self.resolve("monster", arg_value(mc), mc["line"]), line=mc["line"], ref=arg_value(mc)) if mc else None
        army, current = [], None
        for st in sts:
            if st["command"] == "addstartcom":
                current = {"commander": dict(self.resolve("monster", arg_value(st), st["line"]), ref=arg_value(st)), "line": st["line"], "units": []}
                army.append(current)
            elif st["command"] == "addstartunits":
                entry = {"monster": dict(self.resolve("monster", arg_value(st), st["line"]), ref=arg_value(st)), "count": arg_value(st, 1), "line": st["line"]}
                if current:
                    current["units"].append(entry)
                else:
                    army.append({"commander": None, "line": st["line"], "units": [entry]})
        rec = {"units": [], "commanders": [], "mercs": []}
        last = None
        for st in sts:
            c = st["command"]
            if c in ("addunitrec", "addmercrec", "addcomrec"):
                a = [arg_value(st, i) for i in range(6)]
                entry = {"command": c, "monster": dict(self.resolve("monster", a[0], st["line"]), ref=a[0]), "chance": a[1], "line": st["line"],
                         "extra": [], "modifiers": []}
                if c == "addcomrec":
                    entry.update(gold=a[2], gold_die=a[3], iron=a[4])
                else:
                    entry.update(count=a[2], gold=a[3], gold_die=a[4], iron=a[5])
                rec["commanders" if c == "addcomrec" else "mercs" if c == "addmercrec" else "units"].append(entry)
                last = entry
            elif last and c == "recxcost":
                last["extra"].append({"resource": arg_value(st), "label": table_label("resource", arg_value(st)), "amount": arg_value(st, 1), "line": st["line"]})
            elif last and c in ("templerec", "libraryrec", "atavirec", "reclimiter", "recterr"):
                last["modifiers"].append({"command": c, "args": [x["value"] for x in st["args"]], "line": st["line"]})
        terr = [dict(self.resolve("terrain", arg_value(st), st["line"]), value=arg_value(st), line=st["line"]) for st in sts if st["command"] == "addstartterr"]
        clears = [{"command": st["command"], "line": st["line"], "label": label(st["command"])} for st in sts
                  if st["command"] in ("clearrec", "clearstartunits", "clearstartterr", "otherplanar", "stdtroops", "nostdtroops")]
        view.update(army=army, recruitment=rec, start_terrain=terr, clears=clears,
                    number=o["name"] if o["opener"] == "selectclass" else None,
                    number_label=table_label("class", o["name"]) if o["opener"] == "selectclass" else None)
        return view

    def ritual_view(self, o):
        sts = o["statements"]
        rp = next((st for st in reversed(sts) if st["command"] == "ritpow"), None)
        if rp:
            school = dict(self.school_ref(arg_value(rp), rp["line"], relative_allowed=False), line=rp["line"])
        elif o["opener"] == "newritual":
            before = self.schools_before(o["line"])
            school = ({"status": "local", "index": before[-1]["index"], "name": self.school_name(before[-1]),
                       "note": "No ritpow: the latest newritpow before this ritual is used (manual p.32)."} if before else
                      {"status": "unresolved", "note": "No ritpow and no earlier newritpow in this file."})
        else:
            school = {"status": "unchanged", "note": "Selected ritual keeps its school unless ritpow is set."}
        costs = [{"resource": arg_value(st), "label": table_label("resource", arg_value(st)), "amount": arg_value(st, 1), "line": st["line"]}
                 for st in sts if st["command"] == "cost"]
        summoning = any(st["command"] == "summoning" for st in sts)
        strings = []
        for st in sts:
            if st["command"] == "addstring":
                text = arg_value(st) or ""
                parts = []
                for piece in text.split("&"):
                    m = re.fullmatch(r"\s*(?:(c)\*|([0-9d+]+)\*)?\s*(.*?)\s*", piece)
                    commander, count, name = (m.group(1), m.group(2), m.group(3)) if m else (None, None, piece.strip())
                    parts.append({"commander": bool(commander), "count": count, "name": name,
                                  "target": self.resolve("monster", name, st["line"]) if summoning else None})
                strings.append({"text": text, "line": st["line"], "parts": parts})
        level = self.field(o, "level")
        return {"school": school, "level": level, "costs": costs, "summoning": summoning, "strings": strings,
                "terr": self.field(o, "terr"), "defctrl": self.field(o, "defctrl"),
                "free": any(st["command"] == "free" for st in sts),
                "copy": (lambda st: dict(self.resolve("ritual", arg_value(st), st["line"]), line=st["line"]) if st else None)(
                    next((st for st in sts if st["command"] == "copyritual"), None)),
                "string_note": "Summon string grammar and name matching follow manual p.33; results need game testing."}

    def terrain_view(self, o):
        spr = self.field(o, "spr")
        attrs = [{"command": st["command"], "line": st["line"], "args": [a["value"] for a in st["args"]],
                  "summary": (manual_entry("terrain", st["command"]) or {}).get("summary")}
                 for st in o["statements"] if st["command"] not in OPENERS and st["command"] not in ("name", "spr", "gold", "iron")]
        return {"number": o["name"], "custom": self.is_custom_terrain(o), "name": self.field(o, "name"),
                "gold": self.field(o, "gold"), "iron": self.field(o, "iron"), "attributes": attrs,
                "citadel": any(st["command"] == "citadel" for st in o["statements"]),
                "sprite": self.sprite(spr["value"], spr["line"], "spr") if spr else None,
                "note": None if self.is_custom_terrain(o) else "Modifies an existing terrain; unset values keep the game's values."}

    def item_view(self, o):
        t = self.field(o, "type")
        spr = self.field(o, "spr")
        if t:
            t["meaning"] = table_label("itemtype", t["value"])
        return {"type": t, "sprite": self.sprite(spr["value"], spr["line"], "spr") if spr else None,
                "descr": (self.field(o, "descr") or {}).get("value")}

    def event_view(self, o):
        sts = [st for st in o["statements"] if st["command"] not in OPENERS and st["command"] != "endevent"]
        return {"triggers": [st["line"] for st in sts if st["command"][:1] in "+-"],
                "actions": [st["line"] for st in sts if st["command"][:1] not in "+-"],
                "closed": any(st["command"] == "endevent" for st in o["statements"])}

    # ----- graph -----
    def edges(self):
        out = []
        for o in self.objects:
            for st in o["statements"]:
                c = st["command"]
                if c in REF_KIND and st["context"] == o["kind"]:
                    ref = arg_value(st, REF_ARG.get(c, 0))
                    target = self.resolve(REF_KIND[c], ref, st["line"])
                    out.append({"from": o["index"], "command": c, "line": st["line"], "ref": ref, "to": target,
                                "relation": RELATION.get(c, "refers to")})
                elif c == "addstring" and o["kind"] == "ritual" and any(x["command"] == "summoning" for x in o["statements"]):
                    for part in self.ritual_view(o)["strings"]:
                        if part["line"] == st["line"]:
                            for p in part["parts"]:
                                out.append({"from": o["index"], "command": c, "line": st["line"], "ref": p["name"],
                                            "to": p["target"], "relation": "summons"})
                elif c in ("power",) and o["kind"] == "monster":
                    target = self.school_ref(arg_value(st), st["line"])
                    out.append({"from": o["index"], "command": c, "line": st["line"], "ref": arg_value(st),
                                "to": dict(target, kind="school"), "relation": RELATION[c]})
                elif c == "ritpow" and o["kind"] == "ritual":
                    out.append({"from": o["index"], "command": c, "line": st["line"], "ref": arg_value(st),
                                "to": dict(self.school_ref(arg_value(st), st["line"], False), kind="school"), "relation": RELATION[c]})
            if o["kind"] == "monster":
                for link in self.shape_links(o):
                    out.append({"from": o["index"], "command": link["command"], "line": link["line"], "ref": link["value"],
                                "to": link["target"], "relation": link["relation"], "form": True})
            if o["kind"] == "ritual" and o["opener"] == "newritual" and not any(st["command"] == "ritpow" for st in o["statements"]):
                school = self.ritual_view(o)["school"]
                if school["status"] == "local":
                    out.append({"from": o["index"], "command": "(implicit)", "line": o["line"], "ref": None,
                                "to": dict(school, kind="school"), "relation": "belongs to school"})
        return out

    # ----- assets -----
    def assets(self):
        refs = {}
        for st in self.parsed["statements"]:
            i = ASSET_ARGS.get(st["command"])
            if i is not None and len(st["args"]) > i:
                o = self.objects[st["object"]] if st["object"] is not None else None
                refs.setdefault(st["args"][i]["value"], []).append({"command": st["command"], "line": st["line"],
                                                                     "object": o["index"] if o else None, "name": o["name"] if o else "Mod info",
                                                                     "kind": o["kind"] if o else "global"})
        declared = set(self.s["meta"].get("declared_assets", []))
        names, skipped = set(refs) | declared, []
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.mod_root):
            base = Path(dirpath)
            dirnames[:] = sorted(d for d in dirnames if not is_link(base / d))
            for fn in sorted(filenames):
                rel = (base / fn).relative_to(self.mod_root).as_posix()
                if rel == f"{self.slug}.c5m":
                    continue
                count += 1
                if count > MAX_LISTED_FILES:
                    skipped.append({"path": rel, "reason": f"listing limited to {MAX_LISTED_FILES} files"})
                    continue
                if is_link(base / fn):
                    skipped.append({"path": rel, "reason": "symbolic link or junction (never read)"})
                    continue
                names.add(rel)
        out = []
        for name in sorted(names):
            entry = {"path": name, "used_by": refs.get(name, []), "declared": name in declared, "status": "ok"}
            problems = mod_relpath_problems(name)
            found, reason = (None, "unsafe") if problems else exact_case_lookup(self.mod_root, name)
            if found is None:
                entry["status"] = "case_mismatch" if reason == "case_mismatch" else "missing" if reason in ("missing", "not_a_file") else "unsafe"
                entry["problem"] = "; ".join(problems) if problems else {"case_mismatch": "letter case differs from the file on disk",
                                                                        "symlink": "path traverses a link"}.get(reason, "file is not in the mod folder")
            else:
                try:
                    data = found.read_bytes() if found.stat().st_size <= 16 * 1024 * 1024 else None
                    if data is None:
                        raise ValueError("over the 16 MiB tool limit")
                    entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                    info = inspect_asset(name, data)
                    entry.update({k: info[k] for k in ("width", "height") if k in info}, checks=info.get("checks"))
                    if name.lower().endswith(".tga") and len(data) > 16:
                        entry["depth"] = data[16]
                except (OSError, ValueError) as exc:
                    entry.update(status="invalid", problem=str(exc))
            suffix = PurePosixPath(name).suffix.lower()
            entry["format"] = suffix.lstrip(".") or "file"
            entry["included"] = bool(entry["used_by"]) or entry["declared"]
            if entry["status"] == "ok":
                entry["url"] = file_url(self.slug, name)
                if suffix in IMAGE_EXT:
                    entry["preview"] = file_url(self.slug, name, png=suffix == ".tga")
            out.append(entry)
            self.asset_index[name] = entry
        return out, skipped

    # ----- artwork readiness: an artist checklist from saved files; it never changes validation or export -----
    def artwork(self, objs, banner):
        """Name what new content still needs. File facts only: nothing here can show an image is original."""
        from .core import default_banner
        units = {k: [] for k in ("ready", "placeholder", "unset", "single_pose", "missing_file", "overwritten",
                                 "copyspr", "shared", "canvas", "selected")}
        uses, by_hash = {}, {}
        for o in objs:
            if o["kind"] != "monster":
                continue
            for pose in ("idle", "attack"):
                frame = o["view"]["sprites"][pose]
                if frame:
                    uses.setdefault(frame["path"], set()).add(o["index"])
                    digest = (self.asset_index.get(frame["path"]) or {}).get("sha256")
                    if digest:
                        by_hash.setdefault(digest, set()).add(frame["path"])
        for o in objs:
            if o["kind"] != "monster":
                continue
            row = {"index": o["index"], "name": o["display"], "line": o["line"], "role": o.get("role"),
                   "form_of": [objs[i]["display"] for i in o.get("form_of", [])]}
            if not o["new"]:
                units["selected"].append(row)
                continue
            sp = o["view"]["sprites"]
            idle, attack = sp["idle"], sp["attack"]
            sts = o["statements"]
            copy_lines = [s["line"] for s in sts if s["command"] in ("copystats", "copyspr")]
            copyspr = [s["line"] for s in sts if s["command"] == "copyspr"]
            problems = []
            if not idle:
                inh = sp.get("inherited")
                units["placeholder" if inh else "unset"].append(
                    dict(row, detail=f"Images come from {inh['command']} {inh['ref']} (line {inh['line']})." if inh else
                         "No spr1 and no copy command: the unit has no image of its own."))
                continue
            overwritten = []
            for command, frame in (("spr1", idle), ("spr2", attack)):
                if frame and frame["line"] < max(copy_lines, default=0):
                    overwritten.append(f"{command} on line {frame['line']} is replaced by the copy command on line {max(copy_lines)}")
                elif command == "spr2" and frame and frame["line"] < idle["line"]:
                    overwritten.append(f"spr2 on line {frame['line']} is replaced by spr1 on line {idle['line']} (manual p.14)")
            if overwritten:
                units["overwritten"].append(dict(row, detail="; ".join(overwritten) + "."))
                problems.append("overwritten")
            if copyspr:
                units["copyspr"].append(dict(row, detail=f"copyspr remains on line {', '.join(map(str, copyspr))}."))
                problems.append("copyspr")
            for pose, frame in (("idle", idle), ("attack", attack)):
                if frame and frame["status"] != "ok":
                    units["missing_file"].append(dict(row, detail=f"{pose} {frame['path']}: {frame.get('problem') or frame['status']}."))
                    problems.append("missing")
                elif frame and (frame["width"] != frame["height"] or frame["width"] not in (32, 64, 128)):
                    units["canvas"].append(dict(row, detail=f"{pose} {frame['path']} is {frame['width']}x{frame['height']}; "
                                                "unit canvases are 32x32, 64x64 or 128x128 (manual p.14)."))
                    problems.append("canvas")
            frames = [f for f in (idle, attack) if f and f["status"] == "ok"]
            shared = []
            for f in frames:
                others = uses.get(f["path"], set()) - {o["index"]}
                digest = (self.asset_index.get(f["path"]) or {}).get("sha256")
                copies = sorted(by_hash.get(digest, set()) - {f["path"]}) if digest else []
                if others:
                    shared.append(f"{f['path']} is also used by {', '.join(objs[i]['display'] for i in sorted(others))}")
                if copies:
                    shared.append(f"{f['path']} has the same bytes as {', '.join(copies)}")
            if attack and attack["path"] == idle["path"]:
                shared.append("idle and attack name the same file")
            if shared:
                units["shared"].append(dict(row, detail="; ".join(dict.fromkeys(shared)) + "."))
                problems.append("shared")
            if not attack:
                units["single_pose"].append(dict(row, detail="No spr2: the game shows spr1 for attacks too (manual p.14); "
                                                 "a distinct attack pose is not authored."))
                problems.append("single")
            if not problems:
                units["ready"].append(row)
        required = sum(o["kind"] == "monster" and o["new"] for o in objs)
        banner_row = {"status": "unset", "detail": "No icon command: the mod has no banner (256x64, manual p.3)."}
        if banner:
            entry = self.asset_index.get(banner["path"]) or {}
            banner_row = {"path": banner["path"], "line": banner["line"], "status": banner["status"] or "missing"}
            if banner["status"] != "ok":
                banner_row["detail"] = banner.get("problem") or "The banner file is missing."
            elif entry.get("sha256") == hashlib.sha256(default_banner()).hexdigest():
                banner_row.update(status="placeholder", detail="The flat banner written by create_project is a placeholder.")
            elif (banner["width"], banner["height"]) != (256, 64):
                banner_row.update(status="size", detail=f"{banner['width']}x{banner['height']}; the banner is 256x64 (manual p.3).")

        def image_rows(kind, sizes, page):
            out = []
            for o in objs:
                if o["kind"] != kind or not o["new"]:
                    continue
                spr = o["view"].get("sprite")
                row = {"index": o["index"], "name": o["display"], "line": o["line"], "path": spr["path"] if spr else None}
                if not spr:
                    row.update(status="unset", detail="No spr command.")
                elif spr["status"] != "ok":
                    row.update(status="missing_file", detail=spr.get("problem") or "The file is missing.")
                elif sizes and (spr["width"], spr["height"]) not in sizes:
                    row.update(status="size", detail=f"{spr['width']}x{spr['height']}; the manual gives "
                               f"{' or '.join(f'{w}x{h}' for w, h in sizes)} (p.{page}).")
                else:
                    row["status"] = "ok"
                out.append(row)
            return out

        return {"units": units, "required_units": required, "banner": banner_row,
                "items": image_rows("item", [(32, 32), (64, 64)], 10), "terrain": image_rows("terrain", None, 29),
                "notes": ["File checks cannot show whether an image is original or matches the theme.",
                          "Inherited, copied and stock images are placeholders unless the user explicitly asked for reuse or a prototype.",
                          "Selected vanilla monsters need no new art unless the user asks for it.",
                          "This checklist does not change validation or export."]}

    # ----- whole model -----
    def build(self):
        assets, skipped = self.assets()
        report = self.report
        diags_by_line = {}
        for d in report["diagnostics"]:
            if d.get("line") and d.get("file") == f"{self.slug}/{self.slug}.c5m":
                diags_by_line.setdefault(d["line"], []).append(d)
        edges = self.edges()
        objs = []
        builders = {"monster": self.monster_view, "weapon": self.weapon_view, "class": self.class_view, "ritual": self.ritual_view,
                    "terrain": self.terrain_view, "item": self.item_view, "event": self.event_view}
        for o in self.objects:
            text, end_line = self.source_text(o)
            lines = range(o["line"], end_line + 1)
            display = o["name"]
            if o["kind"] == "terrain":
                display = (self.field(o, "name") or {}).get("value") or f"Terrain {o['name']}"
            elif o["kind"] == "school":
                display = self.school_name(o)
            elif o["kind"] == "event":
                display = f"{'Player' if o['opener'] == 'playerevent' else 'Square'} event (line {o['line']})"
            elif o["kind"] == "terraingroup":
                display = (self.field(o, "setname") or {}).get("value") or f"Terrain group {o['name']}"
            elif o["kind"] == "class" and not display:
                display = f"Class {o['name']}" if o["opener"] == "selectclass" else "(unnamed class)"
            elif o["kind"] == "class" and o["opener"] == "selectclass":
                display = (self.field(o, "setclassname") or {}).get("value") or table_label("class", o["name"]) or f"Class {o['name']}"
            entry = {"index": o["index"], "kind": o["kind"], "kind_label": KIND_LABEL.get(o["kind"], o["kind"]), "opener": o["opener"],
                     "name": o["name"], "display": display or "(unnamed)", "new": o["opener"].startswith("new") or self.is_custom_terrain(o),
                     "line": o["line"], "end_line": end_line, "text": text, "statements": self.statements(o),
                     "diagnostics": [d for n in lines for d in diags_by_line.get(n, [])],
                     "uses": [e for e in edges if e["from"] == o["index"]],
                     "used_by": [e for e in edges if e["to"].get("index") == o["index"] and e["to"].get("status") in ("local", "later")]}
            if o["kind"] in builders:
                entry["view"] = builders[o["kind"]](o)
            objs.append(entry)
        # Roles from class lists: commanders are named by setmaincom/addstartcom/addcomrec, troops by the others.
        for e in edges:
            t = e["to"]
            if t.get("kind") == "monster" and t.get("status") in ("local", "later"):
                target = objs[t["index"]]
                bucket = target.setdefault("roles", [])
                bucket.append({"from": e["from"], "command": e["command"], "line": e["line"], "relation": e["relation"],
                               "from_kind": objs[e["from"]]["kind"]})
        for o in objs:
            if o["kind"] == "monster":
                cmds = {r["command"] for r in o.get("roles", [])}
                o["role"] = ("commander" if cmds & {"setmaincom", "addstartcom", "addcomrec"} else
                             "troop" if cmds & {"addunitrec", "addmercrec", "addstartunits"} else
                             "summon" if "addstring" in cmds else "form" if cmds & set(SHAPES) else "unassigned")
                o["classes"] = sorted({r["from"] for r in o.get("roles", []) if r["from_kind"] == "class"})
                o["form_of"] = sorted({r["from"] for r in o.get("roles", []) if r["command"] in SHAPES})
        # Alternate forms share the class scope of the units they come from; the visited set guards form cycles.
        form_edges = [e for e in edges if e.get("form") and e["to"].get("status") == "local"]
        for o in objs:
            if o["kind"] != "monster" or not o["classes"]:
                continue
            seen, queue = {o["index"]}, [o["index"]]
            while queue:
                current = queue.pop()
                for e in form_edges:
                    if e["from"] == current and e["to"]["index"] not in seen:
                        seen.add(e["to"]["index"])
                        queue.append(e["to"]["index"])
                        target = objs[e["to"]["index"]]
                        target["form_classes"] = sorted(set(target.get("form_classes", [])) | set(o["classes"]))
        global_sts = [st for st in self.parsed["statements"] if st["object"] is None]
        gobj = {"statements": global_sts}
        mod_info = {k: self.field(gobj, k) for k in ("icon", "description", "modprio")}
        banner = None
        if mod_info["icon"]:
            banner = self.sprite(mod_info["icon"]["value"], mod_info["icon"]["line"], "icon")
        codec = self.parsed["encoding"].replace("-sig", "")
        g_statements = []
        for st in global_sts:
            entry = manual_entry("global", st["command"]) or {}
            g_statements.append({"line": st["line"], "command": st["command"], "args": [a["value"] for a in st["args"]],
                                 "code": self.data[st["start"] + st["indent"]:st["code_end"]].decode(codec),
                                 "status": command_status("global", st["command"]), "label": label(st["command"]), "page": entry.get("page")})
        counts = {k: sum(o["kind"] == k for o in objs) for k in KIND_LABEL}
        counts.update(assets=len(assets), missing_assets=sum(a["status"] != "ok" and bool(a["used_by"]) for a in assets),
                      statements=len(self.parsed["statements"]), unknown_commands=sum(d["code"] == "unknown_command" for d in report["diagnostics"]))
        meta = self.s["meta"]
        latest = self.exports[0] if self.exports else None
        sprites = {"custom": 0, "inherited": 0, "missing": [], "none": 0}
        for o in objs:
            if o["kind"] != "monster":
                continue
            sp = o["view"]["sprites"]
            if sp["idle"]:
                if sp["idle"]["status"] == "ok":
                    sprites["custom"] += 1
                else:
                    sprites["missing"].append({"index": o["index"], "name": o["display"], "path": sp["idle"]["path"], "line": sp["idle"]["line"]})
            elif sp.get("inherited"):
                sprites["inherited"] += 1
            else:
                sprites["none"] += 1
        return {
            "project": {"slug": self.slug, "name": meta["name"], "target_version": meta.get("target_version"),
                        "manual_version": meta.get("manual_version"), "dependencies": meta.get("dependencies", []),
                        "catalog": meta.get("catalog"), "declared_assets": meta.get("declared_assets", []), "banner": banner},
            "revision": self.s["revision"],
            "provenance": {"file": f"{self.slug}.c5m", "path": f"mod/{self.slug}/{self.slug}.c5m", "revision": self.s["revision"],
                           "sha256": hashlib.sha256(self.data).hexdigest(), "encoding": self.parsed["encoding"],
                           "newline": "CRLF" if b"\r\n" in self.data else "LF", "bytes": len(self.data),
                           "lines": len(self.parsed["source"].splitlines())},
            "inputs": self.s["inputs"],
            "manual": MANUAL, "game_profile": game_profile(meta.get("target_version")), "mod_info": mod_info, "global_statements": g_statements,
            "objects": objs, "edges": edges, "counts": counts, "assets": assets, "assets_skipped": skipped,
            "validation": report, "catalog": self.core._catalog_info(self.s),
            "exports": self.exports[:5], "latest_export": latest,
            "readiness": {"sprites": sprites, "artwork": self.artwork(objs, banner), "static_ok": report["static_ok"], "counts": report["counts"]},
            "limitations": report["limitations"] + [
                "Copy inheritance is shown only where a donor in this mod or the local catalog states the value.",
                "Summon strings, ritual effects and events are listed as written; their game effects are not simulated."],
        }
