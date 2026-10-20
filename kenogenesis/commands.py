"""Curated CoE5 schemas; no Dominions command tables or numeric allocations.

Signatures and pages refer to Illwinter's CoE5 Modding Manual 5.36.
Unknown commands are preserved and reported as unverified, never discarded.
The 5.41 overlay below comes from Illwinter's release notes, not from the manual.
"""

import re

MANUAL = {"version": "5.36", "url": "https://www.illwinter.com/coe5/coe5modding.pdf"}
OPENERS = {"newmonster": "monster", "selectmonster": "monster", "newweapon": "weapon",
           "selectweapon": "weapon", "newclass": "class", "selectclass": "class",
           "newritpow": "school", "newritual": "ritual", "selectritual": "ritual",
           "newitem": "item", "selectitem": "item", "selectterr": "terrain",
           "selectterrgroup": "terraingroup", "playerevent": "event", "squareevent": "event"}
SCHEMAS = {}


def register(contexts, name, args, page, note="", repeat=False):
    """Attach one signature to each documented context without copying registry entries."""
    for context in contexts.split():
        SCHEMAS[context, name] = {"command": name, "context": context, "args": args.split(),
                                  "page": page, "manual": MANUAL, "note": note, "repeat": repeat}


# s=quoted string, i=integer, r=quoted string or number, ?=optional.
for name in ("icon", "description", "mapfile"):
    register("global", name, "s", 3, repeat=name == "mapfile")
register("global", "modprio", "i:1:9", 3)
register("global", "sample", "i:0:249 s", 38, repeat=True)
register("global", "fontfile", "i:0:2 s", 3, repeat=True)
register("global", "translation", "s s", 3, repeat=True)
for name, context in OPENERS.items():
    if name in ("newclass", "newritpow", "playerevent", "squareevent"):
        args = ""
    elif name == "selectmonster":
        args = "s i?"
    elif name == "selectritual":
        args = "s i?"
    elif name in ("selectclass", "selectterr", "selectterrgroup"):
        args = "i"
    elif name.startswith("new") or name == "selectitem":
        args = "s"  # selectitem takes a name only (manual p.10); selectweapon also accepts a number.
    else:
        args = "r"
    page = {"monster": 13, "weapon": 4, "class": 27, "school": 32, "ritual": 32,
            "item": 10, "terrain": 29, "terraingroup": 32, "event": 38}[context]
    register("global", name, args, page,
             "Offset must be nonnegative." if name == "selectmonster" else "")
for name in ("hp", "mr", "str", "armor", "mor"):
    register("monster", name, "i", 14)
register("monster", "rank", "i:-1:1", 14)
for name in ("spr1", "spr2", "descr", "name", "copystats", "copyspr"):
    register("monster", name, "s", 14)
for name in ("clearweapons", "clearspec"):
    register("monster", name, "", 14)
for name in ("human", "undead", "animal", "inanimate", "holy", "flying", "slow", "fast", "noleader"):
    register("monster", name, "", 15 if name in ("flying", "slow", "fast") else 20)
for name in ("meleeweapon", "meleeweaponbonus", "rangedweapon", "rangedweaponbonus"):
    register("monster", name, "i s", 14, repeat=True)
register("monster", "power", "i", 17, "Zero refers to the latest new ritual school; negatives to earlier new schools.", True)
register("monster", "allrit", "i", 17)
for name in ("spellweapon", "spellweaponbonus", "spellweapon50", "spellweaponsingle"):
    register("monster", name, "i i:1:3", 15, repeat=True)
for name in ("range", "init", "dmgtype", "dmg", "aoe", "sound", "look", "flymode", "flylook", "flysound"):
    register("weapon", name, "i", 4)
register("weapon", "nextwep", "r", 5)
for name in ("setclassname", "classdescr", "classabdescr"):
    register("class", name, "s", 27)
for name in ("hometerr", "startplane", "createcit", "goldbonus", "ironbonus"):
    register("class", name, "i", 27)
for name in ("clearstartunits", "clearstartterr", "clearrec", "otherplanar"):
    register("class", name, "", 27)
for name in ("setmaincom", "addstartcom"):
    register("class", name, "s", 27, repeat=name == "addstartcom")
register("class", "addstartunits", "s i", 27, repeat=True)
register("class", "addstartterr", "i", 27, repeat=True)
for name in ("addunitrec", "addmercrec"):
    register("class", name, "s i:0:100 i i i i", 27, repeat=True)
register("class", "addcomrec", "s i:0:100 i i i", 28, repeat=True)
register("class", "recxcost", "i i", 28, repeat=True)
register("ritual", "ritpow", "i", 32)
register("ritual", "level", "i:1:9", 32)
register("ritual", "cost", "i i", 32, repeat=True)
register("ritual", "terr", "i", 32)
register("ritual", "copyritual", "s", 32)
register("ritual", "clearritspec", "", 32)
register("ritual", "addstring", "s", 33, repeat=True)
register("ritual", "summoning", "", 33)
register("ritual", "defctrl", "i:0:100", 33)
register("ritual", "soundfx", "i", 37)
register("ritual", "free", "", 35)
# Minimal source-level citadel support is needed for the independent example.
for name in ("name", "spr"):
    register("terrain", name, "s", 29)
for name in ("gold", "iron"):
    register("terrain", name, "i", 29)
register("terrain", "citadel", "", 30)
register("event", "endevent", "", 38)
ASSET_ARGS = {"icon": 0, "mapfile": 0, "sample": 1, "fontfile": 1, "spr1": 0, "spr2": 0, "spr": 0}


# Manual-derived reference index (names, signatures, pages); see manual_data.py. Not used for curated checks.
from .manual_data import MANUAL_COMMANDS, TABLES  # noqa: E402

MANUAL_INDEX = {}
for _entry in MANUAL_COMMANDS:
    MANUAL_INDEX.setdefault((_entry["context"], _entry["command"]), _entry)
CONTEXTS = sorted({ctx for ctx, _ in MANUAL_INDEX} | {ctx for ctx, _ in SCHEMAS})
LOOKUP_LIMIT = 1000


def _lookup_entry(ctx, cmd):
    """One reference entry. Curated entries keep their original schema fields (args codes, note, repeat) and add the
    manual's signature; documented-only entries carry the manual's signature and argument names but no checked codes."""
    doc, curated = MANUAL_INDEX.get((ctx, cmd)), SCHEMAS.get((ctx, cmd))
    arguments = [{k: a[k] for k in ("name", "type", "optional", "min", "max") if k in a} for a in (doc or {}).get("args", [])]
    common = {"signature": (doc or {}).get("signature", cmd), "summary": (doc or {}).get("summary", ""), "arguments": arguments,
              "manual_page": (doc or curated)["page"]}
    if curated:
        return {**curated, **common, "status": "curated", "validated": True,
                "source": "KENOGENESIS curated schema checked against the pinned manual" + ("" if doc else " (no manual index row)")}
    return {"command": cmd, "context": ctx, "page": doc["page"], "manual": MANUAL, **common, "status": "documented",
            "validated": False, "repeat": None,
            "note": "Documented in the pinned manual. KENOGENESIS preserves it but does not check its arguments.",
            "source": "Manual index generated from the CoE5 Modding Manual (manual_data.py)"}


COVERAGE = "curated subset plus the full manual index; 5.41 release-note names are listed as announced"


def lookup(command=None, context=None, query=None, status=None, limit=200):
    """Curated and documented-only commands of the pinned manual, plus names announced only in release notes. A named
    command looked up in a block context also matches its global form (block openers and mod-wide commands may appear
    anywhere) and an announced name whose context the notes do not state. Unknown names are reported, never invented."""
    if context is not None and context not in CONTEXTS:
        return {"manual": MANUAL, "coverage": COVERAGE, "entries": [], "total": 0,
                "status": "unknown_context", "contexts": CONTEXTS,
                "limitations": ["Contexts are the manual's block kinds; see contexts."]}
    if status not in (None, "curated", "documented", "announced"):
        raise ValueError("status is curated, documented, announced or omitted")
    limit = max(1, min(int(limit), LOOKUP_LIMIT))
    q = (query or "").strip().casefold()[:60]
    keys = sorted(set(MANUAL_INDEX) | set(SCHEMAS), key=lambda k: (k[0] != "global", k[0], k[1]))
    picked = []
    for ctx, cmd in keys:
        if command and cmd != command:
            continue
        if context and ctx != context and not (command and ctx == "global"):
            continue
        entry = _lookup_entry(ctx, cmd)
        if status and entry["status"] != status:
            continue
        if q and q not in f"{cmd} {entry['summary']}".casefold():
            continue
        if context and ctx != context:
            entry["matched_via"] = "global"
        picked.append(entry)
    for cmd, ctx in ANNOUNCED_COMMANDS.items():
        if (command and cmd != command) or (context and ctx != context and not (command and ctx is None)):
            continue
        if status not in (None, "announced") or (q and q not in cmd.casefold()):
            continue
        entry = announced_entry(ctx, cmd)
        if context and ctx != context:
            entry["matched_via"] = "context_not_announced"
        picked.append(entry)
    result = {"manual": MANUAL, "release_notes": [RELEASE_541], "coverage": COVERAGE, "entries": picked[:limit],
              "total": len(picked), "truncated": len(picked) > limit,
              "counts": {s: sum(e["status"] == s for e in picked) for s in ("curated", "documented", "announced")},
              "limitations": ["Only curated entries have argument checks; documented entries are preserved verbatim.",
                              "Announced entries come from release notes, not the manual: signature, arguments and "
                              "(unless stated) context are unknown.",
                              "No arbitrary new combat-spell authoring or complete engine simulation."]}
    if command and not picked:
        result.update(status="unknown", note="Not in the curated schema or the pinned manual index. Preserve it verbatim and "
                                             "check the official manual or game version before relying on it.")
    return result


def manual_entry(context, command):
    """The manual's documented signature for a command in this context (or globally), or None."""
    return MANUAL_INDEX.get(("global", command)) or MANUAL_INDEX.get((context, command))


def command_status(context, command):
    if SCHEMAS.get(("global", command)) or SCHEMAS.get((context, command)):
        return "curated"
    if manual_entry(context, command):
        return "documented"
    return "announced" if announced_entry(context, command) else "unknown"


KNOWN_COMMANDS = {cmd for (_, cmd) in SCHEMAS} | {cmd for (_, cmd) in MANUAL_INDEX}


# Release-note overlay. The pinned manual stays 5.36; no signature, argument count or context below comes from it.
RELEASE_541 = {"version": "5.41", "title": "Conquest of Elysium 5.41", "author": "johan", "date": "2026-10-19",
               "source": "Steam news, ISteamNews/GetNewsForApp appid 1606340, gid 1846651706689977",
               "url": "https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1846651706689977",
               "api": "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1606340&count=20&maxlength=0&format=json",
               "manual_version": MANUAL["version"],
               "note": "The official manual available on the release date was still 5.36 and documents none of the announced "
                       "commands. Bug fixes listed in the notes (long description scrollbar, sprite unloading) are game "
                       "changes; KENOGENESIS does not implement or check them."}
# Context is given only where the notes state it ("new event trigger"); None means the notes do not say.
ANNOUNCED_COMMANDS = {"brigand": None, "pickupbrigands": None, "adventurer": None, "pickupadvent": None,
                      "partyleader": None, "+minunitshere": "event"}
# Engine limits as announced. None means "increased" without a number. They are reference only: whether a count is
# total or custom, and its scope, is not stated, so KENOGENESIS enforces none of them.
LIMITS_541 = [{"limit": "recruitment list length", "before": None, "after": None, "note": "Increased; no number announced."},
              {"limit": "recruitment limiters", "before": 8, "after": 12},
              {"limit": "sprites", "before": None, "after": None, "note": "Increased; no number announced."},
              {"limit": "monsters", "before": 5000, "after": 6000},
              {"limit": "ritual effects", "before": 14, "after": 20},
              {"limit": "ritual strings", "before": 48, "after": 58,
               "note": "Scope not stated in the release notes; not a reinterpretation of the manual's "
                       "15 addstring alternatives per ritual."},
              {"limit": "terrain groups", "before": 200, "after": 500},
              {"limit": "terrain slots", "before": 1000, "after": 2000,
               "note": "Total slots. KENOGENESIS infers custom numbers 500-1999 from this and the reserved 0-499; "
                       "the engine's allocation above 999 is not documented."}]


def parse_version(text):
    """(major, minor) for a CoE5 version written like 5.41; None when unset or in any other form."""
    match = re.fullmatch(r"(\d+)\.(\d{2})", text.strip()) if isinstance(text, str) else None
    return (int(match[1]), int(match[2])) if match else None


def game_profile(target_version):
    """How the project's target version is read: which documentation applies and the custom terrain numbers used.
    Unset or unrecognized targets keep the manual's 500-999 range rather than being assumed to be 5.41."""
    parsed = parse_version(target_version)
    if not target_version:
        status = "unset"
    elif parsed is None:
        status = "unrecognized"
    else:
        status = "5.41_or_later" if parsed >= (5, 41) else "before_5.41"
    later = status == "5.41_or_later"
    terrain = {"first": 500, "last": 1999 if later else 999,
               "basis": "Inferred from the 5.41 release notes (2000 total terrain slots, 0-499 reserved); unverified in the engine."
               if later else f"Manual {MANUAL['version']} custom terrain numbers."}
    notes = {"unset": "No target version: 5.41 release-note changes are not applied; announced commands stay unverified.",
             "unrecognized": "Target version is not in the form 5.41: 5.41 release-note changes are not applied.",
             "before_5.41": "Target predates 5.41: release-note additions do not apply.",
             "5.41_or_later": "Manual 5.36 is the documentation baseline; 5.41 additions are known only from release notes."}
    return {"target_version": target_version, "status": status, "manual": MANUAL,
            "release_notes": [RELEASE_541] if later else [], "custom_terrain": terrain,
            "announced_limits": LIMITS_541 if later else [], "note": notes[status]}


def is_custom_terrain(number, target_version):
    """Whether a selectterr number opens a new custom terrain for this target (see game_profile)."""
    terrain = game_profile(target_version)["custom_terrain"]
    return isinstance(number, str) and number.isdigit() and terrain["first"] <= int(number) <= terrain["last"]


def announced_entry(context, command):
    """A command named only in the 5.41 release notes, when its announced context (if any) matches."""
    if command not in ANNOUNCED_COMMANDS or ANNOUNCED_COMMANDS[command] not in (None, context):
        return None
    return {"command": command, "context": ANNOUNCED_COMMANDS[command], "status": "announced", "validated": False,
            "minimum_version": RELEASE_541["version"], "release": RELEASE_541, "signature": None, "arguments": None,
            "manual_page": None, "page": None, "repeat": None, "summary": "",
            "note": "Announced in the CoE5 5.41 release notes. Its arguments" + ("" if ANNOUNCED_COMMANDS[command] else ", context")
                    + " and effects are not documented in the pinned manual; KENOGENESIS preserves it without checks.",
            "source": "Release-note overlay (" + RELEASE_541["source"] + ")"}
