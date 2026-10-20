"""Read-only design views: unit comparison and a per-class roster/economy/ritual workspace.

Values are shown as authored, resolved from a local donor, read from the local catalog with its version,
or left unknown. Nothing here scores balance, simulates recruitment rolls or claims game verification.
"""

from .errors import KenoError
from .parser import parse
from .view import ALL_ATTACKS, MONSTER_FLAGS, MONSTER_STATS, Model, as_int, catalog_scalar, table_label

STAT_LABELS = {"hp": "Hit points", "mr": "Magic resistance", "str": "Strength", "armor": "Armor", "mor": "Morale", "rank": "Rank"}
# Recruitment row arguments after the unit name, as written (manual p.29). No roll or income is simulated.
REC_ARGS = {"addunitrec": ("chance", "count", "gold", "gold_die", "iron"), "addmercrec": ("chance", "count", "gold", "gold_die", "iron"),
            "addcomrec": ("chance", "gold", "gold_die", "iron")}
REC_GROUP = {"addunitrec": "unit", "addmercrec": "mercenary", "addcomrec": "commander"}
CLASS_KINDS = ("class", "class_selection")


def _parsed_row(row):
    return parse("\n".join(x for x in row.get("statements", []) if isinstance(x, str)).encode("utf-8"))["statements"]


def _recruit_rows(statements):
    """Recruitment rows of one class block as written; recxcost attaches to the row above it (manual p.29)."""
    rows, last = [], None
    for st in statements:
        c, args = st["command"], [a["value"] for a in st["args"]]
        if c in REC_ARGS:
            last = {"group": REC_GROUP[c], "command": c, "unit": args[0] if args else None, "line": st["line"], "extra_costs": [],
                    **{k: (args[i + 1] if len(args) > i + 1 else None) for i, k in enumerate(REC_ARGS[c])}}
            rows.append(last)
        elif c == "recxcost" and last:
            last["extra_costs"].append({"resource": table_label("resource", args[0]) if args else None, "raw": args[0] if args else None,
                                        "amount": args[1] if len(args) > 1 else None, "line": st["line"]})
    return rows


def _schools_from(statements, where):
    """Ritual schools stated by power/allrit in explicit statements; relative (0/negative) power stays unresolved here."""
    out = []
    for st in statements:
        if st["command"] not in ("power", "allrit") or not st["args"]:
            continue
        value = st["args"][0]["value"]
        n = as_int(value)
        if st["command"] == "allrit":
            name = "all schools" if value == "-1" else table_label("ritpow", value) or f"school {value}"
            out.append({"school": name, "status": "stated", "all": True, "where": where})
        elif n is not None and n > 0:
            out.append({"school": table_label("ritpow", n) or f"school {n}", "status": "stated", "all": False, "where": where})
        else:
            out.append({"school": f"relative school {value}", "status": "unresolved", "all": False, "where": where,
                        "note": "0 and negative power count back over newritpow blocks in the defining file; not resolved from a catalog row."})
    return out


def _model(core, project, built=False):
    snapshot = core._snapshot(project)
    report = core._validate(snapshot)
    model = Model(core, snapshot, report, [])
    return snapshot, model, (model.build() if built else None)


def _local_column(model, o, class_rows):
    view = model.monster_view(o)
    attacks = [{"command": w["command"], "dmg": w["dmg"], "weapon": w["ref"], "line": w["line"], "source": "authored", "note": w.get("note")}
               for w in view["weapons"]]
    inherited = view["inherited_weapons"]
    if inherited and inherited.get("weapons"):
        attacks += [{"command": w["command"], "dmg": w["dmg"], "weapon": w["ref"], "line": w.get("line"),
                     "source": f"inherited ({inherited['status']})", "note": inherited.get("note")} for w in inherited["weapons"]]
    sp = view["sprites"]
    frame = lambda f: {k: f.get(k) for k in ("path", "line", "command", "status", "url", "width", "height")} if f else None
    sprites = {"idle": frame(sp.get("idle")), "attack": frame(sp.get("attack")),
               "inherited": {"command": sp["inherited"]["command"], "ref": sp["inherited"]["ref"], "line": sp["inherited"]["line"]}
               if sp.get("inherited") else None}
    recruitment = [dict(r, cls=cls["label"], class_index=cls["index"], source="authored")
                   for cls, rows in class_rows for r in rows if r["target"].get("index") == o["index"]]
    schools = [{"school": p.get("name") or p.get("value"), "all": False, "where": "this unit", "line": p["line"],
                "status": p["status"], "note": p.get("note")} for p in view["powers"]]
    schools += [{"school": a["name"] or a["value"], "all": True, "where": "this unit", "line": a["line"], "status": "stated"} for a in view["allrit"]]
    return {"type": "local", "index": o["index"], "name": o["name"], "new": o["opener"] == "newmonster",
            "provenance": f"{model.slug}.c5m:{o['line']}", "revision": model.s["revision"],
            "stats": {k: model.stat(o, k) for k in MONSTER_STATS}, "attacks": attacks,
            "attacks_status": view["weapons_status"], "inherited_attacks": inherited,
            "abilities": sorted({f["command"] for f in view["flags"]} | {a["command"] for a in view["abilities"]}),
            "sprites": sprites,
            "recruitment": {"rows": recruitment, "coverage": "this mod", "note": "Rows in this mod's class blocks that name this unit."},
            "rituals": {"schools": schools, "coverage": "partial" if view["donor"] else "explicit",
                        "note": "power and allrit stated on this unit" + ("; ritual access copied through copystats is not resolved." if view["donor"] else ".")}}


def _catalog_column(model, index, class_rows):
    catalog = model.catalog
    if catalog is None or not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(catalog["rows"]):
        raise KenoError("not_found", "Choose a row from the configured catalog.")
    row = catalog["rows"][index]
    if row.get("kind") != "monster":
        raise KenoError("bad_reference", "Compare units with monster rows only.")
    parsed = parse("\n".join(x for x in row.get("statements", []) if isinstance(x, str)).encode("utf-8"))
    copied = [st["args"][0]["value"] for st in parsed["statements"] if st["command"] == "copystats" and st["args"]]
    stats = {k: catalog_scalar(row, k, catalog["game_version"]) for k in MONSTER_STATS}
    attacks = [{"command": st["command"], "dmg": st["dmg"], "weapon": st["ref"], "line": None, "source": "catalog"}
               for st in model.attack_rows(parsed["statements"])]
    warnings = []
    if (row.get("name_count") or 1) > 1:
        warnings.append(f"{row['name_count']} catalog rows share this name (this is {row.get('name_ordinal', 0) + 1}); "
                        "which one a name reference selects is not documented.")
    if catalog["game_version"] != model.s["meta"].get("target_version"):
        warnings.append(f"Catalog describes game {catalog['game_version']}; the project targets {model.s['meta'].get('target_version') or 'no version'}.")
    flags = set(MONSTER_FLAGS)
    abilities = sorted({st["command"] for st in parsed["statements"]
                        if st["command"] in flags or st["command"] not in set(MONSTER_STATS) | set(ALL_ATTACKS) | {"copystats", "copyspr", "name", "descr", "spr1", "spr2"}})
    # Catalog class rows (only for a uniquely named row) and this mod's class rows that resolve to this exact row.
    unique = (row.get("name_count") or 1) == 1
    recruitment = []
    if unique:
        for ci, crow in enumerate(catalog["rows"]):
            if crow.get("kind") in CLASS_KINDS:
                recruitment += [dict(r, cls=crow.get("name") or f"catalog class {ci}", class_catalog_index=ci, source="catalog",
                                     provenance=f"{crow.get('source_file', 'catalog')}:{crow.get('source_line', '?')}")
                                for r in _recruit_rows(_parsed_row(crow)) if r["unit"] == row.get("name")]
    recruitment += [dict(r, cls=cls["label"], class_index=cls["index"], source="authored")
                    for cls, rows in class_rows for r in rows if r["target"].get("catalog") == index]
    has_classes = any(r.get("kind") in CLASS_KINDS for r in catalog["rows"])
    rec_note = ("Duplicate name: catalog class rows naming it cannot be attributed to this row; only this mod's resolved rows are shown."
                if not unique else "Catalog class rows and this mod's class rows naming this unit." if has_classes else
                "The catalog has no class rows, so vanilla recruitment is unknown; only this mod's rows are shown.")
    for r in recruitment:
        r.pop("target", None)
    return {"type": "catalog", "catalog_index": index, "name": row.get("name"), "id": row.get("id"),
            "provenance": f"{row.get('source_file', 'catalog')}:{row.get('source_line', '?')}",
            "game_version": catalog["game_version"], "catalog_source": model.s.get("catalog_source"),
            "stats": stats, "attacks": attacks, "attacks_status": "partial" if copied else "catalog",
            "abilities": abilities, "warnings": warnings,
            "sprites": None, "sprite_note": "The catalog holds statements only; no game image is shown or substituted.",
            "recruitment": {"rows": recruitment, "coverage": "catalog" if has_classes and unique else "partial", "note": rec_note},
            "rituals": {"schools": _schools_from(parsed["statements"], "catalog row"), "coverage": "partial" if copied else "catalog",
                        "note": "power and allrit printed in the catalog row" + ("; the row also copies another monster, not resolved." if copied else ".")}}


def compare_units(core, project, object_index, references):
    snapshot, model, _ = _model(core, project)
    objects = model.objects
    if not isinstance(object_index, int) or isinstance(object_index, bool) or not 0 <= object_index < len(objects) \
            or objects[object_index]["kind"] != "monster":
        raise KenoError("bad_object", "Choose a unit from the saved project.")
    if not isinstance(references, list) or not 1 <= len(references) <= 4:
        raise KenoError("bad_reference", "Choose one to four references to compare.")
    model.assets()  # fills the sprite index so local frames carry their preview URL and native size
    class_rows = [(dict(c, label=(model.field(c, "setclassname") or {}).get("value") or c["name"] or f"class at line {c['line']}"),
                   [dict(r, target=model.resolve("monster", r["unit"], r["line"])) for r in _recruit_rows(c["statements"])])
                  for c in model.defs("class")]
    columns = [_local_column(model, objects[object_index], class_rows)]
    for ref in references:
        if not isinstance(ref, dict) or len(ref) != 1:
            raise KenoError("bad_reference", "Each reference is {object_index} or {catalog_index}.")
        if "object_index" in ref:
            i = ref["object_index"]
            if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(objects) or objects[i]["kind"] != "monster":
                raise KenoError("bad_reference", "A local reference must be a unit of this project.")
            columns.append(_local_column(model, objects[i], class_rows))
        elif "catalog_index" in ref:
            columns.append(_catalog_column(model, ref["catalog_index"], class_rows))
        else:
            raise KenoError("bad_reference", "Each reference is {object_index} or {catalog_index}.")
    target = columns[0]
    rows, differences, unresolved = [], [], []
    for key in MONSTER_STATS:
        cells = [c["stats"][key] for c in columns]
        rows.append({"key": key, "label": STAT_LABELS[key], "cells": cells})
        for column, cell in zip(columns[1:], cells[1:]):
            if cells[0]["value"] is None or cell["value"] is None:
                unresolved.append({"key": key, "reference": column["name"]})
            elif cells[0]["value"] != cell["value"]:
                differences.append({"key": key, "label": STAT_LABELS[key], "reference": column["name"],
                                    "unit": cells[0]["value"], "other": cell["value"],
                                    "unit_source": cells[0].get("line") or cells[0]["source"], "other_source": cell.get("line") or column["provenance"]})
    for column in columns[1:]:
        mine, theirs = set(target["abilities"]), set(column["abilities"])
        if mine != theirs:
            differences.append({"key": "abilities", "label": "Explicit abilities", "reference": column["name"],
                                "unit": sorted(mine - theirs), "other": sorted(theirs - mine)})
    return {"revision": snapshot["revision"], "catalog": core._catalog_info(snapshot), "columns": columns, "rows": rows,
            "differences": differences, "unresolved": unresolved, "engine_verified": False,
            "notes": ["Only explicit, source-backed values are compared; unknown values are never filled in.",
                      "Ability lists hold explicit commands; inherited abilities and game defaults are not resolved.",
                      "Recruitment rows and ritual schools are listed as written; recruitment rolls, income and ritual effects are not simulated.",
                      "A comparison is not a balance judgement or game evidence."]}


def _school_key(ref):
    if ref.get("status") == "local":
        return ("local", ref.get("index"))
    if ref.get("status") == "vanilla":
        return ("vanilla", ref.get("value"))
    return None


def _class_reach(objs, rituals, c):
    """Units of one local class (including their forms), the ritual schools their power/allrit reach and this mod's
    rituals of those schools. Shared by the Design overview and the class comparison."""
    members = [o for o in objs if o["kind"] == "monster" and (c["index"] in o.get("classes", []) or c["index"] in o.get("form_classes", []))]
    schools = {}
    for o in members:
        for power in o["view"]["powers"]:
            key = _school_key(power)
            if key:
                schools.setdefault(key, {"school": power.get("name") or power.get("value"), "via": []})["via"].append({"unit": o["display"], "line": power["line"]})
        for a in o["view"]["allrit"]:
            schools.setdefault(("vanilla", int(a["value"])) if str(a["value"]).lstrip("-").isdigit() else ("note", a["value"]),
                               {"school": a["name"] or a["value"], "via": []})["via"].append({"unit": o["display"], "line": a["line"], "all": True})
    reachable = []
    for r in rituals:
        key = _school_key(r["view"]["school"])
        if key and key in schools:
            reachable.append({"index": r["index"], "name": r["display"], "school": schools[key]["school"], "level": (r["view"]["level"] or {}).get("value"),
                              "costs": [{"resource": x["label"] or x["resource"], "amount": x["amount"], "line": x["line"]} for x in r["view"]["costs"]],
                              "summoning": r["view"]["summoning"], "summons": [p["name"] for s in r["view"]["strings"] for p in s["parts"]] if r["view"]["summoning"] else [],
                              "free": r["view"]["free"], "line": r["line"]})
    resources = {}
    for r in reachable:
        for cost in r["costs"]:
            resources.setdefault(cost["resource"], []).append(r["name"])
    return members, schools, reachable, resources


def design_report(core, project, class_index=None):
    snapshot, model, built = _model(core, project, built=True)
    objs = built["objects"]
    classes = [o for o in objs if o["kind"] == "class"]
    if class_index is not None:
        if not isinstance(class_index, int) or isinstance(class_index, bool) or not any(o["index"] == class_index for o in classes):
            raise KenoError("bad_object", "Choose a class from the saved project.")
        classes = [o for o in classes if o["index"] == class_index]
    rituals = [o for o in objs if o["kind"] == "ritual"]
    art_rows = {r["index"]: state for state, rows in built["readiness"]["artwork"]["units"].items() for r in rows}
    out = []
    for c in classes:
        v = c["view"]
        recruit = []
        for group, rows in (("unit", v["recruitment"]["units"]), ("commander", v["recruitment"]["commanders"]), ("mercenary", v["recruitment"]["mercs"])):
            for r in rows:
                recruit.append({"group": group, "command": r["command"], "line": r["line"], "unit": r["monster"].get("name") or r["monster"].get("ref"),
                                "reference": r["monster"], "chance": r["chance"], "count": r.get("count"), "gold": r["gold"],
                                "gold_die": r["gold_die"], "iron": r["iron"],
                                "extra_costs": [{"resource": x["label"] or x["resource"], "amount": x["amount"], "line": x["line"]} for x in r["extra"]],
                                "modifiers": r["modifiers"]})
        members, schools, reachable, resources = _class_reach(objs, rituals, c)
        home = v.get("hometerr") or {}
        evidence = (home.get("target") or {}).get("citadel_evidence") or {}
        checks = [
            {"key": "identity", "label": "Class identity", "ok": bool(v.get("setclassname") and v.get("classdescr")),
             "detail": "Name and description authored." if v.get("setclassname") and v.get("classdescr") else "Add setclassname and classdescr."},
            {"key": "home", "label": "Home citadel", "ok": evidence.get("citadel") is True,
             "evidence": evidence.get("status") or "missing", "line": evidence.get("line"), "game_version": evidence.get("game_version"),
             "catalog_source": evidence.get("catalog_source"), "version_mismatch": evidence.get("version_mismatch"),
             "detail": "No hometerr; a class needs a home citadel terrain." if not home else
             f"hometerr {home.get('value')}: {evidence.get('note', 'not resolved')} "
             + ("Static source evidence only; still verify in game." if evidence.get("citadel") is True else
                "A number alone does not prove a valid home.")},
            {"key": "commander", "label": "Main commander", "ok": bool(v.get("main_commander")),
             "detail": "Declared." if v.get("main_commander") else "No setmaincom."},
            {"key": "start", "label": "Starting forces", "ok": any(a["units"] for a in v["army"]),
             "detail": f"{sum(len(a['units']) for a in v['army'])} starting unit rows."},
            {"key": "recruitment", "label": "Recruitment", "ok": bool(recruit), "detail": f"{len(recruit)} recruitment rows."},
            {"key": "rituals", "label": "Ritual access", "ok": bool(reachable) or not schools,
             "detail": f"{len(schools)} schools through units, {len(reachable)} rituals of those schools defined in this mod."},
            {"key": "art", "label": "Original artwork", "ok": all(art_rows.get(o["index"]) in ("ready", "selected") for o in members),
             "detail": f"{sum(art_rows.get(o['index']) == 'ready' for o in members)} of {sum(o['new'] for o in members)} new units have idle and attack files."},
        ]
        out.append({"index": c["index"], "name": c["display"], "line": c["line"], "new": c["new"],
                    "home": {"hometerr": home.get("value"), "target": home.get("target"),
                             "startplane": (v.get("startplane") or {}).get("meaning") or (v.get("startplane") or {}).get("value"),
                             "createcit": (v.get("createcit") or {}).get("value"),
                             "goldbonus": (v.get("goldbonus") or {}).get("value"), "ironbonus": (v.get("ironbonus") or {}).get("value")},
                    "main_commander": v.get("main_commander"), "army": v["army"], "start_terrain": v["start_terrain"],
                    "recruitment": recruit, "clears": v["clears"],
                    "roster": [{"index": o["index"], "name": o["display"], "role": o.get("role"), "new": o["new"],
                                "form_only": c["index"] not in o.get("classes", []), "art": art_rows.get(o["index"])} for o in members],
                    "schools": [{"school": s["school"], "via": s["via"]} for s in schools.values()],
                    "rituals": reachable, "ritual_resources": [{"resource": k, "rituals": v2} for k, v2 in sorted(resources.items())],
                    "checks": checks})
    return {"revision": snapshot["revision"], "classes": out, "engine_verified": False,
            "notes": ["Figures are authored values with their source lines. No overall balance score is computed.",
                      "Recruitment chances, counts and costs are listed as written; the game's recruitment rolls and income are not simulated.",
                      "Rituals are matched to schools reached through class units' power and allrit commands in this mod only.",
                      "Home citadel evidence is this mod's terrain blocks first, then the local catalog row with its game version; "
                      "unresolved or ambiguous terrain is never assumed to be a citadel.",
                      "Checks are authoring reminders, not game verification."]}


# ----- class comparison: a side-by-side table of authored or catalog-printed values; unknown coverage is labelled -----
def _local_class(objs, rituals, c):
    v = c["view"]
    rec = [{"group": g, "unit": r["monster"].get("name") or r["monster"].get("ref"), "chance": r["chance"], "count": r.get("count"),
            "gold": r["gold"], "gold_die": r["gold_die"], "iron": r["iron"], "line": r["line"],
            "extra_costs": [{"resource": x["label"] or x["resource"], "amount": x["amount"]} for x in r["extra"]]}
           for g, rows in (("unit", v["recruitment"]["units"]), ("commander", v["recruitment"]["commanders"]), ("mercenary", v["recruitment"]["mercs"]))
           for r in rows]
    refs = [r["monster"] for rows in (v["recruitment"]["units"], v["recruitment"]["commanders"], v["recruitment"]["mercs"]) for r in rows]
    _, schools, reachable, resources = _class_reach(objs, rituals, c)
    selected = c["opener"] == "selectclass"
    value = lambda k: (v.get(k) or {}).get("value")
    return {"type": "local", "index": c["index"], "name": c["display"], "provenance": f"line {c['line']}", "selected": selected,
            "recruitment": rec, "main_commander": (v.get("main_commander") or {}).get("name") or (v.get("main_commander") or {}).get("ref"),
            "start_commanders": sum(1 for a in v["army"] if a["commander"]),
            "start_units": [{"unit": u["monster"].get("name") or u["monster"].get("ref"), "count": u["count"]} for a in v["army"] for u in a["units"]],
            "goldbonus": value("goldbonus"), "ironbonus": value("ironbonus"),
            "schools": [s["school"] for s in schools.values()], "rituals": len(reachable),
            "coverage": "partial" if selected else "authored",
            "warnings": ["Selected class: only rows in this block are shown; the existing class's own rows are not resolved."] if selected else [],
            "_dash": {"refs": refs, "complete": not selected,
                      "resources": [{"resource": k, "rituals": len(names)} for k, names in sorted(resources.items())]}}


def _catalog_class(model, index):
    catalog = model.catalog
    if catalog is None or not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(catalog["rows"]):
        raise KenoError("not_found", "Choose a class row from the configured catalog.")
    row = catalog["rows"][index]
    if row.get("kind") not in CLASS_KINDS:
        raise KenoError("bad_reference", "Compare classes with catalog class rows only.")
    sts = _parsed_row(row)
    last = lambda k: next((st["args"][0]["value"] for st in reversed(sts) if st["command"] == k and st["args"]), None)
    rec = _recruit_rows(sts)
    starts = [{"unit": st["args"][0]["value"] if st["args"] else None, "count": st["args"][1]["value"] if len(st["args"]) > 1 else None}
              for st in sts if st["command"] == "addstartunits"]
    # Schools come from the catalog monster rows these names select, only where exactly one row has the name.
    names = {r["unit"] for r in rec} | {s["unit"] for s in starts} | {last("setmaincom")} - {None}
    schools, unresolved = [], 0
    for name in sorted(n for n in names if n):
        hits = [r for r in catalog["rows"] if r.get("kind") == "monster" and r.get("name") == name]
        if len(hits) != 1:
            unresolved += 1
            continue
        parsed = _parsed_row(hits[0])
        unresolved += any(st["command"] == "copystats" for st in parsed)
        schools += [s["school"] for s in _schools_from(parsed, name) if s["status"] == "stated"]
    warnings = []
    if catalog["game_version"] != model.s["meta"].get("target_version"):
        warnings.append(f"Catalog describes game {catalog['game_version']}; the project targets {model.s['meta'].get('target_version') or 'no version'}.")
    if unresolved:
        warnings.append(f"{unresolved} unit name(s) are missing, duplicated or copy another monster in the catalog; their ritual access is not counted.")
    return {"type": "catalog", "catalog_index": index, "name": row.get("name") or f"catalog class {index}",
            "provenance": f"{row.get('source_file', 'catalog')}:{row.get('source_line', '?')}", "game_version": catalog["game_version"],
            "recruitment": rec, "main_commander": last("setmaincom"),
            "start_commanders": sum(st["command"] == "addstartcom" for st in sts), "start_units": starts,
            "goldbonus": last("goldbonus"), "ironbonus": last("ironbonus"), "schools": sorted(set(schools)), "rituals": None,
            "coverage": "partial", "warnings": [*warnings, "Only this catalog row is counted; other selection blocks and game defaults are not merged."],
            "_dash": {"complete": False, "resources": None}}


def compare_classes(core, project, class_index, references):
    snapshot, model, built = _model(core, project, built=True)
    objs = built["objects"]
    classes = {o["index"]: o for o in objs if o["kind"] == "class"}
    rituals = [o for o in objs if o["kind"] == "ritual"]
    if not isinstance(class_index, int) or isinstance(class_index, bool) or class_index not in classes:
        raise KenoError("bad_object", "Choose a class from the saved project.")
    if not isinstance(references, list) or not 1 <= len(references) <= 4:
        raise KenoError("bad_reference", "Choose one to four classes to compare.")
    columns = [_local_class(objs, rituals, classes[class_index])]
    for ref in references:
        if not isinstance(ref, dict) or len(ref) != 1 or not ({"object_index", "catalog_index"} & set(ref)):
            raise KenoError("bad_reference", "Each reference is {object_index} or {catalog_index}.")
        if "object_index" in ref:
            if ref["object_index"] not in classes or isinstance(ref["object_index"], bool):
                raise KenoError("bad_reference", "A local reference must be a class of this project.")
            columns.append(_local_class(objs, rituals, classes[ref["object_index"]]))
        else:
            columns.append(_catalog_class(model, ref["catalog_index"]))

    def listed(col, groups, key):
        rows = [r for r in col["recruitment"] if groups is None or r["group"] in groups]
        return " · ".join(f"{r['unit']} {r.get(key) if r.get(key) is not None else '?'}" for r in rows) or None

    def cell(value, note=None):
        return {"value": None if value in (None, "") else str(value), "note": note}

    unknown = lambda col: "Not printed in the catalog row." if col["type"] == "catalog" else \
        "Selected class keeps its existing value; not resolved." if col.get("selected") else "Not set in this mod."
    specs = [
        ("units", "Recruitable unit rows", lambda c: cell(sum(r["group"] == "unit" for r in c["recruitment"]))),
        ("commanders", "Recruitable commander rows", lambda c: cell(sum(r["group"] == "commander" for r in c["recruitment"]))),
        ("mercs", "Mercenary rows", lambda c: cell(sum(r["group"] == "mercenary" for r in c["recruitment"]))),
        ("main", "Main commander", lambda c: cell(c["main_commander"], None if c["main_commander"] else unknown(c))),
        ("startcom", "Additional starting commander rows", lambda c: cell(c["start_commanders"])),
        ("startunits", "Starting units (as written)", lambda c: cell(" · ".join(f"{s['count'] or '?'} × {s['unit']}" for s in c["start_units"]) or None,
                                                                  None if c["start_units"] else unknown(c))),
        ("chance", "Chance % per row", lambda c: cell(listed(c, None, "chance"))),
        ("count", "Count per row", lambda c: cell(listed(c, ("unit", "mercenary"), "count"))),
        ("gold", "Gold per row", lambda c: cell(listed(c, None, "gold"))),
        ("gold_die", "Gold die per row (as written)", lambda c: cell(listed(c, None, "gold_die"))),
        ("iron", "Iron per row", lambda c: cell(listed(c, None, "iron"))),
        ("extra", "Extra recruitment costs", lambda c: cell(" · ".join(f"{r['unit']} {x['amount']} {x['resource'] or x.get('raw')}"
                                                                         for r in c["recruitment"] for x in r["extra_costs"]) or None,
                                                       None if any(r["extra_costs"] for r in c["recruitment"]) else
                                                       "No recxcost printed in the catalog row." if c["type"] == "catalog" else "No recxcost in this block.")),
        ("goldbonus", "Gold income bonus %", lambda c: cell(c["goldbonus"], None if c["goldbonus"] is not None else unknown(c))),
        ("ironbonus", "Iron income bonus %", lambda c: cell(c["ironbonus"], None if c["ironbonus"] is not None else unknown(c))),
        ("schools", "Ritual schools through units", lambda c: cell(", ".join(c["schools"]) or None,
                                                                   None if c["schools"] else "None stated" + (" (partial coverage)." if c["coverage"] == "partial" else "."))),
        ("rituals", "Rituals of those schools in this mod", lambda c: cell(c["rituals"], None if c["rituals"] is not None else
                                                                           "Catalog rituals are not matched to classes.")),
    ]
    rows = [{"key": key, "label": label, "cells": [fn(c) for c in columns]} for key, label, fn in specs]
    dashboard = _dashboard(model, columns)
    for col in columns:
        col.pop("_dash", None)
    return {"revision": snapshot["revision"], "catalog": core._catalog_info(snapshot), "columns": columns, "rows": rows,
            "dashboard": dashboard, "engine_verified": False,
            "notes": ["Values are as written in this mod or printed in the catalog row; ? and empty cells are unknown, never zero.",
                      "Recruitment chances, counts, gold dice and income are not simulated, and no balance score is computed.",
                      "Ritual schools come from power and allrit on the class's units; catalog classes count only uniquely named catalog units."]}


# ----- class comparison dashboard: the same source-backed figures summarised for plotting; unknowns are counted apart -----
DASH_STATS = [("hp", "Hit points"), ("str", "Strength"), ("armor", "Armor"), ("mr", "Magic resistance"), ("mor", "Morale")]
MARKERS = "ABCDE"
DASH_HELP = [
    "Chance is the raw <chance> percentage written in a recruitment row (manual p.27-28). How the game uses it "
    "when it builds the recruitment list is not simulated here.",
    "Count is the <nbr> of units one addunitrec or addmercrec row recruits; addcomrec rows have no count.",
    "Gold and gold die are the row's two gold arguments, shown as written. How the game combines them into a "
    "price is not modelled, so no average or final price is computed.",
    "Iron is the row's iron argument. recxcost adds a special-resource cost to the row above it and is listed separately.",
    "Gold and iron income bonuses are the class's percentage modifiers, not income amounts.",
    "Stats are each recruitable unit's explicit value: authored here, copied from an explicit local donor, or printed "
    "in a uniquely named catalog row. Unknown values are counted apart and never drawn as zero.",
    "Ritual schools are reached through the class's units' power and allrit; resources are those of this mod's "
    "rituals in those schools. Catalog rituals are not matched to classes.",
    "Nothing here is a balance score, a recruitment simulation or game evidence.",
]


def _number(value):
    return as_int(str(value)) if value is not None else None


def _spread(values):
    known = [n for n in (_number(v) for v in values) if n is not None]
    return {"min": min(known) if known else None, "max": max(known) if known else None,
            "known": len(known), "unknown": len(values) - len(known)}


def _unit_stats(model, column, ref, name):
    """Explicit stats of one recruitable unit and where they come from; anything unresolved stays None."""
    catalog = model.catalog
    if column["type"] == "local":
        if ref and ref.get("status") in ("local", "later") and ref.get("index") is not None:
            obj = model.objects[ref["index"]]
            return "this mod", {k: model.stat(obj, k) for k, _ in DASH_STATS}
        if ref and ref.get("status") == "catalog":
            row = catalog["rows"][ref["catalog"]]
            return "catalog row", {k: catalog_scalar(row, k, catalog["game_version"]) for k, _ in DASH_STATS}
        note = (ref or {}).get("note") or "Unit reference not resolved."
    else:
        hits = [r for r in catalog["rows"] if r.get("kind") == "monster" and r.get("name") == name] if catalog and name else []
        if len(hits) == 1:
            return "catalog row", {k: catalog_scalar(hits[0], k, catalog["game_version"]) for k, _ in DASH_STATS}
        note = "Duplicated name in the catalog; not attributed to one row." if hits else "No catalog monster row has this name."
    return "unresolved", {k: {"value": None, "source": "unresolved", "note": note} for k, _ in DASH_STATS}


def _dashboard(model, columns):
    """Per column: distinct recruitable unit names per group, the spread of known chance/gold/iron figures and unit
    stats (unknowns counted, never zero), income bonuses and ritual access. Every per-unit value keeps its source."""
    out = []
    for i, col in enumerate(columns):
        dash = col.get("_dash") or {}
        refs = dash.get("refs") or [None] * len(col["recruitment"])
        units = []
        for row, ref in zip(col["recruitment"], refs):
            origin, stats = _unit_stats(model, col, ref, row["unit"])
            units.append({"group": row["group"], "unit": row["unit"], "chance": row["chance"], "count": row.get("count"),
                          "gold": row["gold"], "gold_die": row["gold_die"], "iron": row["iron"],
                          "extra_costs": row["extra_costs"], "line": row.get("line"), "stats_from": origin,
                          "stats": {k: dict(v) for k, v in stats.items()}})
        distinct = lambda group: len({u["unit"] for u in units if u["group"] == group and u["unit"]})
        complete = dash.get("complete", False)
        out.append({
            "marker": MARKERS[i], "name": col["name"], "type": col["type"], "provenance": col["provenance"],
            "game_version": col.get("game_version"), "catalog_index": col.get("catalog_index"), "index": col.get("index"),
            "recruitment_complete": complete,
            "roster": {"troops": distinct("unit"), "commanders": distinct("commander"), "mercenaries": distinct("mercenary"),
                       "start_unit_types": len({s["unit"] for s in col["start_units"] if s["unit"]}),
                       "note": None if complete else "Partial: only rows written in this block or row are counted; "
                                                     "other blocks and game defaults are not merged."},
            "costs": {k: _spread([u[k] for u in units]) for k in ("chance", "gold", "gold_die", "iron")},
            "stats": {k: _spread([u["stats"][k]["value"] for u in units]) for k, _ in DASH_STATS},
            "income": {"goldbonus": col["goldbonus"], "ironbonus": col["ironbonus"]},
            "rituals": {"schools": col["schools"], "rituals": col["rituals"], "resources": dash.get("resources"),
                        "coverage": col["coverage"],
                        "note": "Catalog rituals are not matched to classes; resources are unknown." if col["type"] == "catalog" else
                                "Rituals of this mod in schools reached through the class's units."},
            "units": units})
    return {"columns": out, "stat_keys": [list(x) for x in DASH_STATS], "help": DASH_HELP, "engine_verified": False}
