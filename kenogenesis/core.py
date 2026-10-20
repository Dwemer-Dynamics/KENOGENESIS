"""Shared CLI/browser/MCP operations, using Kosmokrator guarded-authoring patterns."""

import contextlib
import difflib
import hashlib
import json
import os
import re
import secrets
import struct
import time
import zipfile
from pathlib import Path

from . import __version__
from .assets import inspect_asset
from .commands import ASSET_ARGS, MANUAL, OPENERS, SCHEMAS, lookup, manual_entry
from .errors import KenoError
from .parser import check_arguments, decode, parse
from .paths import SLUG_RE, atomic_write_bytes, contained, exact_case_lookup, is_link, mod_relpath_problems, resolve_workspace

MAX_FILE = 16 * 1024 * 1024  # Tool policy, not a game limit.
SNAPSHOT_DIR = ".kenogenesis/catalog-snapshots"  # Private per-project catalog copies; never exported.
SUPPORTED = {"monster", "weapon", "class", "ritual", "school"}
REFERENCES = {"copystats": (0, "monster"), "copyspr": (0, "monster"),
              "setmaincom": (0, "monster"), "addstartcom": (0, "monster"),
              "addstartunits": (0, "monster"), "addunitrec": (0, "monster"),
              "addmercrec": (0, "monster"), "addcomrec": (0, "monster"),
              "meleeweapon": (1, "weapon"), "meleeweaponbonus": (1, "weapon"),
              "rangedweapon": (1, "weapon"), "rangedweaponbonus": (1, "weapon"),
              "copyritual": (0, "ritual"), "hometerr": (0, "terrain"), "createcit": (0, "terrain")}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def default_banner():
    """The original flat 256x64 test banner create_project writes; readiness treats it as a placeholder."""
    banner = bytearray(18)
    banner[2], banner[16], banner[17] = 2, 24, 32
    struct.pack_into("<HH", banner, 12, 256, 64)
    return bytes(banner) + bytes((42, 24, 18)) * (256 * 64)


def tool_fingerprint():
    """Identify the exact installed runtime sources without requiring Git or exposing local paths."""
    root = Path(__file__).parent
    files = [*root.glob("*.py"), *root.glob("*.c5m"), *(root / "web").glob("*")]
    digests = {path.relative_to(root).as_posix(): sha(path.read_bytes()) for path in files if path.is_file()}
    return sha(json.dumps(digests, sort_keys=True).encode())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_file(path):
    if path.stat().st_size > MAX_FILE:
        raise KenoError("file_too_large", "File exceeds the 16 MiB tool limit.", file=path.name)
    return path.read_bytes()


def read_json(path):
    try:
        return json.loads(read_file(path).decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise KenoError("bad_json", f"Invalid JSON in {path.name}.") from exc


def check_metadata(meta, slug):
    """Validate both saved and proposed metadata before it can affect paths or writes."""
    if not isinstance(meta, dict) or meta.get("schema") != 1 or meta.get("slug") != slug:
        raise KenoError("bad_project", "Project identity or schema does not match.")
    for key in ("name", "manual_version"):
        if not isinstance(meta.get(key), str):
            raise KenoError("bad_project", f"{key} must be a string.")
    for key in ("target_version", "catalog"):
        if meta.get(key) is not None and not isinstance(meta[key], str):
            raise KenoError("bad_project", f"{key} must be a string or null.")
    for key in ("dependencies", "declared_assets"):
        if not isinstance(meta.get(key), list) or not all(isinstance(item, str) for item in meta[key]):
            raise KenoError("bad_project", f"{key} must be a list of strings.")
    snap = meta.get("catalog_snapshot")
    if snap is not None and (not isinstance(snap, dict) or not isinstance(snap.get("sha256"), str)
                             or not re.fullmatch(r"[0-9a-f]{64}", snap["sha256"])
                             or snap.get("path") != f"{SNAPSHOT_DIR}/{snap['sha256']}.json"
                             or not isinstance(snap.get("game_version"), str)
                             or not all(snap.get(k) is None or isinstance(snap[k], str) for k in ("source", "captured_at_revision"))):
        raise KenoError("bad_project", "catalog_snapshot must name a private snapshot file and its SHA-256.")


def parse_catalog(data):
    """Decode catalog bytes and check the minimum schema shared by configured catalogs and snapshots."""
    catalog = json.loads(data)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("rows"), list) or not catalog.get("provenance") or not isinstance(catalog.get("game_version"), str):
        raise KenoError("bad_catalog", "Catalog requires game_version, provenance and rows.")
    for row in catalog["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("kind"), str) or not isinstance(row.get("name"), str):
            raise KenoError("bad_catalog", "Each catalog row requires string kind and name fields.")
    return catalog


def safe_asset(root, name):
    if mod_relpath_problems(name):
        raise KenoError("bad_asset_path", "Asset path fails portable containment policy.", asset=name)
    contained(root, name)
    found, reason = exact_case_lookup(root, name)
    if found is None:
        raise KenoError("asset_missing", f"Asset is unavailable: {reason}.", asset=name)
    return found


def asset_refs(parsed):
    refs = []
    for st in parsed["statements"]:
        index = ASSET_ARGS.get(st["command"])
        if index is not None and len(st["args"]) > index:
            refs.append((st["args"][index]["value"], st["command"], st["line"]))
    return refs


@contextlib.contextmanager
def project_lock(root):
    """Exclusive writer lease; never remove another writer's lock or guess it is stale."""
    lock = contained(root, ".kenogenesis.lock")
    token = secrets.token_hex(16).encode()
    try:
        with lock.open("xb") as stream:
            stream.write(token)
    except FileExistsError as exc:
        raise KenoError("project_locked", "Another operation holds this project lock.") from exc
    try:
        yield
    finally:
        if lock.exists() and lock.read_bytes() == token:
            lock.unlink()


def envelope(function, **arguments):
    try:
        return {"ok": True, "result": function(**arguments)}
    except KenoError as exc:
        return {"ok": False, "error": exc.to_dict()}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "error": {"code": "invalid_operation", "message": str(exc)}}


class Kenogenesis:
    def __init__(self, workspace: str):
        self.workspace = resolve_workspace(workspace)

    def _project(self, project):
        if not isinstance(project, str) or not SLUG_RE.fullmatch(project):
            raise KenoError("bad_project", "Use a lowercase project slug: 2–48 letters, digits or underscores.")
        root = contained(self.workspace, project)
        meta_path = contained(root, "project.json")
        meta = read_json(meta_path)
        check_metadata(meta, project)
        return root, meta

    def list_projects(self):
        results = []
        for root in sorted(self.workspace.iterdir()):
            if SLUG_RE.fullmatch(root.name) and root.is_dir():
                try:
                    _, meta = self._project(root.name)
                    results.append({"slug": root.name, "name": meta["name"]})
                except (OSError, KenoError, ValueError, TypeError):
                    continue
        return {"projects": results}

    def create_project(self, slug: str, name: str | None = None, target_version: str | None = None):
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            raise KenoError("bad_project", "Use a lowercase slug of 2–48 letters, digits or underscores.")
        meta = {"schema": 1, "slug": slug, "name": name or slug, "target_version": target_version,
                "manual_version": MANUAL["version"], "dependencies": [], "catalog": None,
                "declared_assets": []}
        check_metadata(meta, slug)
        root = contained(self.workspace, slug)
        if root.exists():
            raise KenoError("dest_exists", "Project already exists; nothing was overwritten.")
        root.mkdir()
        mod = root / "mod" / slug
        mod.mkdir(parents=True)
        (mod / "banner.tga").write_bytes(default_banner())
        (mod / f"{slug}.c5m").write_bytes(b'icon "banner.tga"\ndescription "A local KENOGENESIS project."\n')
        (root / "project.json").write_bytes(json_bytes(meta))
        return self.project_view(slug)

    def import_project(self, slug: str, source: str, declared_assets: list[str] | None = None, target_version: str | None = None):
        """Copy only the chosen mod and its declared files; never recursively import a user folder."""
        src = Path(source).absolute()
        if src.suffix.lower() != ".c5m" or src.stem != slug or src.parent.name != slug:
            raise KenoError("bad_import", "Import requires <slug>/<slug>.c5m with matching folder and project slug.")
        # The caller explicitly authorizes this read root, but links inside it remain forbidden.
        src = contained(src.parent, src.name)
        data = read_file(src)
        refs = {name for name, _, _ in asset_refs(parse(data))} | set(declared_assets or [])
        payload = {name: read_file(safe_asset(src.parent, name)) for name in sorted(refs)}
        self.create_project(slug, target_version=target_version)
        root, meta = self._project(slug)
        mod = root / "mod" / slug
        (mod / f"{slug}.c5m").write_bytes(data)
        for name, contents in payload.items():
            destination = contained(mod, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
        meta["declared_assets"] = sorted(set(declared_assets or []))
        (root / "project.json").write_bytes(json_bytes(meta))
        return self.project_view(slug)

    def build_example(self, slug: str = "proving_ground", target_version: str | None = None):
        """Create an explicitly requested independent prototype, never in an existing project."""
        from .example import populate
        self.create_project(slug, name="KENOGENESIS Proving Ground", target_version=target_version)
        root, _ = self._project(slug)
        with project_lock(root):
            populate(contained(root, f"mod/{slug}"), slug)
        return self.project_view(slug)

    def _snapshot(self, project, source_override=None, metadata_override=None, asset_overrides=None):
        """Hash every declared input, including dependency assets and catalog, into a review revision."""
        root, meta = self._project(project)
        if metadata_override is not None:
            check_metadata(metadata_override, project)
            meta = metadata_override
        dependencies = meta.get("dependencies", [])
        if not isinstance(dependencies, list) or len(set(dependencies)) != len(dependencies) or project in dependencies or len(dependencies) > 32:
            raise KenoError("bad_dependencies", "Declare up to 32 unique direct dependency projects.", field="dependencies")
        inputs, mods, catalog, captured = {}, [], None, {}
        catalog_issue, catalog_bytes, catalog_source, snapshot_state = None, None, None, None
        for slug in [*dependencies, project]:
            dep_root, dep_meta = self._project(slug)
            meta_path = contained(dep_root, "project.json")
            meta_bytes = read_file(meta_path)
            if json.loads(meta_bytes) != dep_meta or (slug == project and metadata_override is None and dep_meta != meta):
                raise KenoError("inputs_changed", "Project settings changed while reading; inspect again.")
            captured[meta_path] = sha(meta_bytes)
            if slug == project and metadata_override is not None:
                dep_meta = metadata_override
                meta_bytes = json_bytes(dep_meta)
            if slug != project and dep_meta.get("dependencies"):
                raise KenoError("nested_dependencies", f"Dependency {slug} has its own dependencies. List a flat dependency set; nested dependencies are not resolved.",
                                field="dependencies", dependency=slug)
            mod_root = contained(dep_root, f"mod/{slug}")
            mod_path = contained(mod_root, f"{slug}.c5m")
            data = read_file(mod_path)
            captured[mod_path] = sha(data)
            if slug == project and source_override is not None:
                data = source_override
            parsed = parse(data)
            inputs[f"{slug}/project.json"] = sha(meta_bytes)
            inputs[f"{slug}/{slug}.c5m"] = sha(data)
            assets, issues = {}, []
            declarations = dep_meta.get("declared_assets", [])
            if not isinstance(declarations, list) or not all(isinstance(x, str) for x in declarations):
                raise KenoError("bad_assets", "declared_assets must be a list of relative filenames.")
            names = {name for name, _, _ in asset_refs(parsed)} | set(declarations)
            for name in sorted(names):
                if slug == project and asset_overrides and name in asset_overrides:
                    assets[name] = asset_overrides[name]
                    inputs[f"{slug}/{name}"] = sha(assets[name])
                    continue
                try:
                    asset_path = safe_asset(mod_root, name)
                    asset = read_file(asset_path)
                    captured[asset_path] = sha(asset)
                    assets[name] = asset
                    inputs[f"{slug}/{name}"] = sha(asset)
                except (OSError, KenoError) as exc:
                    inputs[f"{slug}/{name}"] = "unavailable"
                    issues.append({"severity": "error", "code": "asset_unavailable", "file": f"{slug}.c5m",
                                   "line": next((line for ref, _, line in asset_refs(parsed) if ref == name), 0),
                                   "message": f"{name}: {exc}"})
            mods.append({"slug": slug, "meta": dep_meta, "data": data, "parsed": parsed,
                         "assets": assets, "issues": issues})
        if meta.get("catalog"):
            cat_path = contained(self.workspace, meta["catalog"])
            inputs["catalog"] = "unavailable"
            try:
                cat_data = read_file(cat_path)
                captured[cat_path] = sha(cat_data)
                inputs["catalog"] = sha(cat_data)
                catalog, catalog_bytes, catalog_source = parse_catalog(cat_data), cat_data, "configured"
            except (OSError, ValueError, KenoError) as exc:
                catalog_issue = f"Configured catalog is unavailable or invalid: {exc}"
        snap = meta.get("catalog_snapshot")
        if snap:
            # An explicit private copy: hashed into the revision, used only while the configured catalog is unavailable.
            inputs["catalog_snapshot"] = "unavailable"
            snapshot_state = {"path": snap["path"], "sha256": snap["sha256"], "source": snap.get("source"),
                              "game_version": snap["game_version"], "captured_at_revision": snap.get("captured_at_revision")}
            try:
                snap_path = contained(root, snap["path"])
                snap_data = read_file(snap_path)
                captured[snap_path] = sha(snap_data)
                inputs["catalog_snapshot"] = sha(snap_data)
                if sha(snap_data) != snap["sha256"]:
                    raise KenoError("bad_catalog", "snapshot bytes no longer match the recorded SHA-256")
                snap_catalog = parse_catalog(snap_data)
                if not meta.get("catalog"):
                    snapshot_state.update(status="unused", note="No catalog is configured, so the snapshot is not used.")
                elif catalog is None:
                    snapshot_state.update(status="offline", note="The configured catalog is unavailable; references use this snapshot.")
                    catalog, catalog_source = snap_catalog, "snapshot"
                elif inputs["catalog"] == snap["sha256"]:
                    snapshot_state.update(status="current", note="The configured catalog matches this snapshot.")
                else:
                    snapshot_state.update(status="stale", note="The configured catalog changed after this snapshot; references use the configured catalog.")
            except (OSError, ValueError, KenoError) as exc:
                snapshot_state.update(status="invalid", note=f"Snapshot is unavailable or invalid: {exc}")
        if any(sha(read_file(path)) != expected for path, expected in captured.items()):
            raise KenoError("inputs_changed", "Project inputs changed while reading; inspect again.")
        revision = sha(json.dumps(inputs, sort_keys=True).encode())
        return {"root": root, "meta": meta, "mods": mods, "catalog": catalog, "catalog_issue": catalog_issue,
                "revision": revision, "inputs": inputs, "catalog_bytes": catalog_bytes, "catalog_source": catalog_source,
                "catalog_snapshot": snapshot_state}

    def project_view(self, project: str):
        snapshot = self._snapshot(project)
        mod = snapshot["mods"][-1]
        report = self._validate(snapshot)
        return {"project": project, "metadata": snapshot["meta"], "revision": snapshot["revision"],
                "source_sha256": sha(mod["data"]), "source": mod["parsed"]["source"],
                "encoding": mod["parsed"]["encoding"], "objects": mod["parsed"]["objects"],
                "validation": report, "assets": list(mod["assets"]),
                "manual": MANUAL, "catalog": self._catalog_info(snapshot)}

    def _catalog_info(self, snapshot):
        catalog = snapshot["catalog"]
        extra = {"snapshot": snapshot["catalog_snapshot"]} if snapshot.get("catalog_snapshot") else {}
        if catalog is None:
            return {"available": False, "note": snapshot["catalog_issue"] or "Vanilla references cannot be verified without a catalog.", **extra}
        source = snapshot.get("catalog_source") or "configured"
        return {"available": True, "game_version": catalog["game_version"], "provenance": catalog["provenance"],
                "sha256": snapshot["inputs"]["catalog_snapshot" if source == "snapshot" else "catalog"],
                "rows": len(catalog["rows"]), "source": source, **extra}

    def _distribution_catalog(self, info, configured=None):
        """Allowlisted catalog facts for new manifests and historical browser downloads; never include private metadata."""
        snap = info.get("snapshot")
        return {"available": info.get("available", False), "game_version": info.get("game_version"), "sha256": info.get("sha256"),
                "rows": info.get("rows"), "source": info.get("source"), "configured": info.get("configured", configured),
                "snapshot_status": snap.get("status") if isinstance(snap, dict) else info.get("snapshot_status"),
                "note": "Private catalog provenance, paths and snapshot details stay in the workspace."}

    def _distribution_validation(self, report):
        """The validation report for an export manifest: catalog diagnostics get fixed text and workspace paths are removed."""
        root = str(Path(self.workspace).resolve())
        def message(d):
            if d.get("code") == "catalog_unavailable":
                return "The configured catalog was unavailable or invalid; details stay in the private workspace."
            return d["message"].replace(root, "<workspace>").replace(str(self.workspace), "<workspace>")
        return {**report, "diagnostics": [dict(d, message=message(d)) for d in report["diagnostics"]]}

    def lookup_command(self, command: str | None = None, context: str | None = None, query: str | None = None,
                       status: str | None = None, limit: int = 200):
        """Curated (argument-checked) and documented-only commands of the pinned CoE5 manual, with signatures,
        manual pages and argument names. status filters curated or documented; query matches name or summary."""
        return lookup(command, context, query, status, limit)

    def search_game_data(self, project: str, query: str = "", kind: str | None = None, limit: int = 30):
        snapshot = self._snapshot(project)
        catalog = snapshot["catalog"]
        if catalog is None:
            return {"catalog": self._catalog_info(snapshot), "rows": [], "unverified": True}
        rows = [row for row in catalog["rows"] if (not kind or row["kind"] == kind)
                and query.casefold() in row["name"].casefold()]
        return {"catalog": self._catalog_info(snapshot), "rows": rows[:max(1, min(int(limit), 100))],
                "total": len(rows), "unverified": catalog["game_version"] != snapshot["meta"].get("target_version")}

    def _validate(self, snapshot):
        diagnostics, targets, definitions = [], {}, {}
        new_sequence, assets_report = [], []
        catalog = snapshot["catalog"]
        rows = catalog["rows"] if catalog else []
        all_new = {}
        for mod in snapshot["mods"]:
            for obj in mod["parsed"]["objects"]:
                custom_terrain = obj["opener"] == "selectterr" and obj["name"].isdigit() and 500 <= int(obj["name"]) <= 999
                if (obj["opener"].startswith("new") or custom_terrain) and obj["name"]:
                    all_new.setdefault((obj["kind"], obj["name"]), []).append((mod["slug"], obj["line"]))
        for mod in snapshot["mods"]:
            parsed, slug = mod["parsed"], mod["slug"]

            def issue(severity, code, message, line=0):
                diagnostics.append({"severity": severity, "code": code, "message": message,
                                    "file": f"{slug}/{slug}.c5m", "line": line})

            for diagnostic in [*parsed["diagnostics"], *mod["issues"]]:
                issue(diagnostic["severity"], diagnostic["code"], diagnostic["message"], diagnostic.get("line", 0))
            if b"\x00" in mod["data"]:
                issue("error", "binary_source", "NUL byte in text source.")
            if parsed["encoding"] != "utf-8" or any(ord(char) > 127 for char in parsed["source"]):
                issue("unverified", "encoding", "Non-ASCII source or BOM needs engine confirmation; bytes will be preserved.")
            global_commands = {st["command"] for st in parsed["statements"]}
            for required in ("icon", "description"):
                if required not in global_commands:
                    issue("error", "required_metadata", f"Missing {required}.")
            school_count = 0
            for st in parsed["statements"]:
                command, args = st["command"], st["args"]
                spec = SCHEMAS.get(("global", command)) or SCHEMAS.get((st["context"], command))
                if spec is None:
                    documented = manual_entry(st["context"], command)
                    if documented:
                        issue("unverified", "uncurated_command", f"{command}: documented in the manual (p.{documented['page']}) but its "
                              "arguments and effects are not checked here; preserved verbatim.", st["line"])
                    else:
                        issue("unverified", "unknown_command", f"{command}: outside the curated registry; preserved verbatim.", st["line"])
                    continue
                error = check_arguments(st, spec)
                if error:
                    issue("error", "arguments", f"{command}: {error}", st["line"])
                    continue
                if command == "selectmonster" and len(args) > 1 and int(args[1]["value"]) < 0:
                    issue("error", "arguments", "selectmonster offsets cannot be negative.", st["line"])
                    continue
                if command == "newritpow":
                    school_count += 1
                if command == "power" and int(args[0]["value"]) <= 0:
                    if 1 - int(args[0]["value"]) > school_count:
                        issue("unverified", "ritual_school", "Relative ritual school is not defined earlier in this mod; check dependency load order.", st["line"])
                if command in OPENERS:
                    obj = parsed["objects"][st["object"]]
                    custom_terrain = command == "selectterr" and args and args[0]["value"].isdigit() and 500 <= int(args[0]["value"]) <= 999
                    if obj["kind"] not in SUPPORTED and not custom_terrain:
                        issue("unverified", "unsupported_context", f"{obj['kind']} semantics are not implemented.", st["line"])
                    if command.startswith("new") or custom_terrain:
                        if not custom_terrain:
                            new_sequence.append({"project": slug, "kind": obj["kind"], "name": obj["name"]})
                        if obj["name"]:
                            key = (obj["kind"], obj["name"])
                            definitions.setdefault(key, []).append((slug, st["line"]))
                            if len(all_new.get(key, [])) > 1:
                                issue("warning", "ambiguous_name", f"Multiple new {key[0]} definitions named {key[1]}; offsets may matter.", st["line"])
                    elif args:
                        key = (obj["kind"], args[0]["value"])
                        targets.setdefault(key, set()).add(slug)
                    if custom_terrain:
                        targets.setdefault(("terrain", obj["name"]), set()).add(slug)
                ref_spec = REFERENCES.get(command)
                if ref_spec and st["context"] in SUPPORTED:
                    index, kind = ref_spec
                    name = args[index]["value"]
                    key = kind, name
                    local = definitions.get(key, [])
                    matches = [row for row in rows if row["kind"] == kind and
                               (row["name"] == name or str(row.get("id", "")) == name)]
                    if key in all_new and not local and not matches:
                        issue("error", "forward_reference", f"{command} references {name} before its local definition.", st["line"])
                    elif not local:
                        if len(matches) != 1:
                            issue("unverified", "reference", f"{kind} reference {name!r} cannot be uniquely verified.", st["line"])
                if command == "addstring":
                    issue("unverified", "ritual_string", "Summoning string grammar and target resolution require game testing.", st["line"])
                if command in ASSET_ARGS:
                    name = args[ASSET_ARGS[command]]["value"]
                    suffix = Path(name).suffix.lower()
                    allowed = {"icon": (".png", ".tga"), "spr1": (".png", ".tga"), "spr2": (".png", ".tga"), "spr": (".png", ".tga"),
                               "mapfile": (".coem",), "sample": (".sw", ".sw2"), "fontfile": (".ttf",)}[command]
                    if suffix not in allowed:
                        issue("error", "asset_format", f"{command} requires one of {allowed}.", st["line"])
            for obj in parsed["objects"]:
                statements = obj["statements"]
                commands = [st["command"] for st in statements]
                if obj["opener"] == "newclass":
                    if len(commands) < 2 or commands[1] != "setclassname":
                        issue("error", "class_name_order", "setclassname must immediately follow newclass.", obj["line"])
                    if "hometerr" not in commands:
                        issue("error", "class_home", "New class requires hometerr.", obj["line"])
                    if "setmaincom" not in commands:
                        issue("warning", "class_commander", "No main commander is declared.", obj["line"])
                    if sum(c in ("addunitrec", "addcomrec", "addmercrec") for c in commands) > 128:
                        issue("error", "recruitment_limit", "More than 128 recruitment entries.", obj["line"])
                if obj["kind"] == "monster" and "spr2" in commands and ("spr1" not in commands or commands.index("spr2") < commands.index("spr1")):
                    issue("warning", "sprite_order", "spr2 must follow spr1; inherited graphics are not resolved.", obj["line"])
                if obj["kind"] == "ritual" and commands.count("cost") > 4:
                    issue("error", "ritual_cost_limit", "Ritual has more than four resource costs.", obj["line"])
                if obj["kind"] == "event" and "endevent" not in commands:
                    issue("error", "unclosed_event", "Event is missing endevent.", obj["line"])
            for name, data in mod["assets"].items():
                try:
                    info = inspect_asset(name, data)
                    info["project"] = slug
                    assets_report.append(info)
                    if any(ref == name and cmd == "icon" for ref, cmd, _ in asset_refs(parsed)) and (info.get("width"), info.get("height")) != (256, 64):
                        issue("error", "icon_size", f"{name}: mod icon must be 256×64.")
                    if Path(name).suffix.lower() == ".coem":
                        issue("unverified", "map_semantics", f"{name}: packaged as an opaque map; geometry and dependencies are unverified.")
                except (ValueError, struct.error) as exc:
                    issue("error", "asset_invalid", f"{name}: {exc}")
        for (kind, name), mods in targets.items():
            if len(mods) > 1:
                diagnostics.append({"severity": "warning", "code": "overlapping_target", "line": 0,
                                    "file": "dependencies", "message": f"{kind} {name} modified by {', '.join(sorted(mods))}."})
        if not snapshot["meta"].get("target_version"):
            diagnostics.append({"severity": "unverified", "code": "game_version", "line": 0, "file": "project.json",
                                "message": "Target game version has not been recorded."})
        elif snapshot["meta"]["target_version"] != MANUAL["version"]:
            diagnostics.append({"severity": "unverified", "code": "manual_version", "line": 0, "file": "project.json",
                                "message": f"Target game version differs from the {MANUAL['version']} documentation baseline."})
        if catalog and catalog["game_version"] != snapshot["meta"].get("target_version"):
            diagnostics.append({"severity": "unverified", "code": "catalog_version", "line": 0, "file": "catalog",
                                "message": "Catalog and target game versions do not match."})
        if snapshot["catalog_issue"]:
            diagnostics.append({"severity": "unverified", "code": "catalog_unavailable", "line": 0,
                                "file": "catalog", "message": snapshot["catalog_issue"]})
        counts = {level: sum(d["severity"] == level for d in diagnostics) for level in ("error", "warning", "unverified")}
        return {"revision": snapshot["revision"], "static_ok": counts["error"] == 0, "counts": counts,
                "diagnostics": diagnostics, "assets": assets_report, "new_sequence": new_sequence,
                "coverage": "curated subset; no engine execution", "engine_verified": False,
                "limitations": ["No inheritance/effect simulation or arbitrary combat-spell authoring.",
                                "Equal-priority mod ordering and undeclared mods are not resolved.",
                                "Static success does not prove loading, save compatibility, gameplay or balance."]}

    def validate_mod(self, project: str):
        return self._validate(self._snapshot(project))

    def _check_revision(self, snapshot, expected_revision):
        if not expected_revision or expected_revision != snapshot["revision"]:
            raise KenoError("stale_revision", "Project inputs changed; inspect again and preserve your draft.",
                            actual_revision=snapshot["revision"])

    def _candidate(self, snapshot, old, new):
        data = snapshot["mods"][-1]["data"]
        _, encoding, _ = decode(data)
        codec = encoding.replace("-sig", "")
        if not isinstance(old, str) or not isinstance(new, str):
            raise KenoError("bad_patch", "Supply an old span and replacement text.")
        if not old:
            if data not in (b"", b"\xef\xbb\xbf"):
                raise KenoError("bad_patch", "An empty old span is allowed only when the saved source is empty.")
            return data + new.encode(codec)
        old_bytes, new_bytes = old.encode(codec), new.encode(codec)
        if data.count(old_bytes) != 1:
            raise KenoError("ambiguous_patch", "The old span must match exactly once.")
        candidate = data.replace(old_bytes, new_bytes, 1)
        if len(candidate) > MAX_FILE:
            raise KenoError("file_too_large", "Candidate exceeds the source limit.")
        return candidate

    def preview_patch(self, project: str, expected_revision: str, old: str, new: str):
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        candidate = self._candidate(snapshot, old, new)
        return self._preview_result(project, snapshot, candidate)

    def _preview_result(self, project, snapshot, candidate, asset_overrides=None):
        before = decode(snapshot["mods"][-1]["data"])[0]
        after = decode(candidate)[0]
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            fromfile=f"{project}.c5m", tofile=f"{project}.c5m"))
        proposed = self._snapshot(project, candidate, asset_overrides=asset_overrides)
        result = {"revision": snapshot["revision"], "candidate_sha256": sha(candidate), "diff": diff,
                  "validation": self._validate(proposed), "written": False}
        moved = self._form_changes(snapshot, proposed)
        if moved:
            result["form_changes"] = moved
        return result

    def _form_changes(self, snapshot, proposed):
        """Alternate-form commands whose resolved target changes because monsters were added, removed or moved."""
        from .view import Model

        def links(s):
            model, out, seen = Model(self, s, {"diagnostics": []}, []), {}, {}
            for o in model.objects:
                if o["kind"] == "monster":
                    seen[o["name"]] = seen.get(o["name"], 0) + 1
                    for link in model.shape_links(o):
                        out[(o["name"], seen[o["name"]], link["command"])] = link["target"].get("name") if link["target"]["status"] == "local" else None
            return out
        before, after = links(snapshot), links(proposed)
        return [{"unit": key[0], "command": key[2], "before": before[key], "after": after[key],
                 "note": "Form targets count new monsters in source order (manual p.18); this change moves the target."}
                for key in sorted(set(before) & set(after), key=str) if before[key] != after[key]]

    def apply_patch(self, project: str, expected_revision: str, old: str, new: str):
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            candidate = self._candidate(snapshot, old, new)
            result = self._preview_result(project, snapshot, candidate)
            receipt = self._write_source(project, snapshot, candidate)
            result.update(written=True, **receipt, revision=self._snapshot(project)["revision"])
        return result

    def _write_source(self, project, snapshot, candidate):
        """The single source write: re-check the revision, keep a backup, replace atomically; returns a receipt."""
        self._check_revision(self._snapshot(project), snapshot["revision"])
        backups = contained(snapshot["root"], ".kenogenesis/backups")
        backups.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns()}-{secrets.token_hex(4)}.c5m"
        before = snapshot["mods"][-1]["data"]
        with contained(snapshot["root"], backups / name).open("xb") as stream:
            stream.write(before)
        atomic_write_bytes(contained(snapshot["root"], f"mod/{project}/{project}.c5m"), candidate)
        return {"file": f"mod/{project}/{project}.c5m", "backup": f".kenogenesis/backups/{name}",
                "before_revision": snapshot["revision"], "before_sha256": sha(before), "after_sha256": sha(candidate)}

    def _field_candidate(self, snapshot, object_index, command, arguments):
        """Edit one explicit singleton command; never infer inherited values or erase donor abilities."""
        parsed = snapshot["mods"][-1]["parsed"]
        if not isinstance(object_index, int) or not 0 <= object_index < len(parsed["objects"]):
            raise KenoError("bad_object", "Choose an object from the current project view.")
        obj = parsed["objects"][object_index]
        if parsed["diagnostics"]:
            raise KenoError("source_edit_required", "Fix parser errors in source before using structured fields.")
        spec = SCHEMAS.get((obj["kind"], command))
        if spec is None or spec["repeat"] or command in OPENERS or command in ("copystats", "copyspr", "clearweapons", "clearspec", "clearrec", "clearstartunits", "clearstartterr"):
            raise KenoError("source_edit_required", "Use a reviewed source patch for this command.")
        if not isinstance(arguments, list) or not all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in arguments):
            raise KenoError("bad_arguments", "Arguments must be strings or integers.")
        if any(isinstance(v, str) and (any(c in v for c in ('"', '\\', '#')) or any(ord(c) < 32 for c in v)) for v in arguments):
            raise KenoError("bad_arguments", "Strings must contain no control characters, quotes, backslashes or hash.")
        line = command + "".join(" " + (json.dumps(v, ensure_ascii=False) if isinstance(v, str) else str(v)) for v in arguments)
        trial = parse(line.encode("utf-8"))["statements"][0]
        error = check_arguments(trial, spec)
        if error:
            raise KenoError("bad_arguments", error)
        matches = [st for st in obj["statements"] if st["command"] == command]
        if len(matches) > 1:
            raise KenoError("ambiguous_field", "Repeated singleton command needs source review.")
        if any(st["command"] in ("copystats", "copyspr") for st in obj["statements"][(obj["statements"].index(matches[0]) + 1 if matches else 0):]) and matches:
            raise KenoError("reset_after_field", "A later copy command may overwrite this field; review source.")
        data = snapshot["mods"][-1]["data"]
        codec = parsed["encoding"].replace("-sig", "")
        if matches:
            st = matches[0]
            start = st["start"] + st["indent"]
            return data[:start] + line.encode(codec) + data[st["code_end"]:]
        if command == "setclassname" and obj["opener"] == "newclass":
            insertion = obj["statements"][0]["end"]
        else:
            insertion = obj["end"]
        newline = b"\r\n" if b"\r\n" in data else b"\n"
        prefix = b"" if insertion == 0 or data[:insertion].endswith(b"\n") else newline
        return data[:insertion] + prefix + line.encode(codec) + newline + data[insertion:]

    def preview_fields(self, project: str, expected_revision: str, object_index: int, command: str, arguments: list[str | int]):
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        return self._preview_result(project, snapshot, self._field_candidate(snapshot, object_index, command, arguments))

    def apply_fields(self, project: str, expected_revision: str, object_index: int, command: str, arguments: list[str | int]):
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            candidate = self._field_candidate(snapshot, object_index, command, arguments)
            result = self._preview_result(project, snapshot, candidate)
            receipt = self._write_source(project, snapshot, candidate)
            result.update(written=True, **receipt, revision=self._snapshot(project)["revision"])
        return result

    def configure_project(self, project: str, expected_revision: str, dependencies: list[str] | None = None,
                          catalog: str | None = None, target_version: str | None = None,
                          declared_assets: list[str] | None = None, preview: bool = True):
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            meta = dict(snapshot["meta"])
            for key, value in (("dependencies", dependencies), ("catalog", catalog), ("target_version", target_version), ("declared_assets", declared_assets)):
                if value is not None:
                    meta[key] = value
            if not isinstance(meta["dependencies"], list) or len(meta["dependencies"]) > 32 or len(set(meta["dependencies"])) != len(meta["dependencies"]) or project in meta["dependencies"]:
                raise KenoError("bad_dependencies", "Use a flat list of up to 32 unique dependency slugs, not including this project.",
                                field="dependencies")
            for dependency in meta["dependencies"]:
                try:
                    self._project(dependency)
                except (OSError, KenoError, ValueError) as exc:
                    raise KenoError("bad_dependencies", f"Dependency {dependency} is not a readable project: {exc}",
                                    field="dependencies", dependency=dependency) from exc
            if meta.get("catalog"):
                try:
                    contained(self.workspace, meta["catalog"])
                except (OSError, KenoError, ValueError) as exc:
                    raise KenoError("bad_catalog", f"Catalog path: {exc}", field="catalog") from exc
            if not isinstance(meta["declared_assets"], list) or not all(isinstance(name, str) for name in meta["declared_assets"]):
                raise KenoError("bad_assets", "declared_assets must be a list of relative filenames.", field="declared_assets")
            for name in meta["declared_assets"]:
                try:
                    safe_asset(contained(root, f"mod/{project}"), name)
                except (OSError, KenoError, ValueError) as exc:
                    raise KenoError("bad_assets", f"{name}: {exc}", field="declared_assets", asset=name) from exc
            candidate = self._snapshot(project, metadata_override=meta)
            if candidate["catalog_issue"]:
                raise KenoError("bad_catalog", candidate["catalog_issue"], field="catalog")
            self._check_revision(self._snapshot(project), expected_revision)
            impact = self._compat_impact(snapshot, candidate)
            diff = "".join(difflib.unified_diff(json_bytes(snapshot["meta"]).decode().splitlines(True),
                                                json_bytes(meta).decode().splitlines(True), fromfile="project.json", tofile="project.json"))
            receipt = {}
            if not preview:
                backup = contained(root, ".kenogenesis/backups")
                backup.mkdir(parents=True, exist_ok=True)
                name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
                with contained(root, backup / name).open("xb") as stream:
                    stream.write(json_bytes(snapshot["meta"]))
                atomic_write_bytes(contained(root, "project.json"), json_bytes(meta))
                receipt = {"file": "project.json", "backup": f".kenogenesis/backups/{name}", "before_revision": snapshot["revision"]}
            return {"diff": diff, "written": not preview, "validation": self._validate(candidate), **receipt,
                    "compatibility_impact": impact,
                    "revision": snapshot["revision"] if preview else self._snapshot(project)["revision"]}

    COMPAT_CODES = ("overlapping_target", "ambiguous_name", "forward_reference", "reference", "ritual_school")

    def _compat_findings(self, snapshot):
        return [d for d in self._validate(snapshot)["diagnostics"] if d["code"] in self.COMPAT_CODES]

    @staticmethod
    def _declared_inputs(snapshot):
        out = []
        for mod in snapshot["mods"]:
            values = [st["args"][0]["value"] for st in mod["parsed"]["statements"] if st["command"] == "modprio" and st["args"]]
            out.append({"project": mod["slug"], "modprio": values[-1] if values else "5"})
        return out

    def _compat_impact(self, snapshot, candidate):
        """Static cross-mod findings before and after a settings change, compared by code, place and message.
        Both sides come from the same validator over in-memory snapshots; nothing is written or ranked."""
        key = lambda d: (d["code"], d.get("file"), d.get("line"), d["message"])
        before, after = self._compat_findings(snapshot), self._compat_findings(candidate)
        old, new = {key(d) for d in before}, {key(d) for d in after}
        return {"added": [d for d in after if key(d) not in old], "removed": [d for d in before if key(d) not in new],
                "remaining": [d for d in after if key(d) in old],
                "declared_order": {"before": self._declared_inputs(snapshot), "after": self._declared_inputs(candidate)},
                "engine_verified": False,
                "note": "Static findings over the declared order only. The engine's activation order and equal-priority "
                        "behavior are not verified, so no mod is said to win an overlap."}

    # ----- reference catalog import: local vanilla-reference .c5m files into the private workspace -----
    CATALOG_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}[a-z0-9]$")

    def _catalog_sources(self, files, paths):
        import base64
        import binascii
        sources = []
        if bool(files) == bool(paths):
            raise KenoError("bad_catalog", "Supply reference files either as uploaded content or as local paths.", field="files")
        if files:
            if not isinstance(files, list) or not all(isinstance(f, dict) and isinstance(f.get("filename"), str) and isinstance(f.get("base64"), str) for f in files):
                raise KenoError("bad_catalog", "Each file needs a filename and content.", field="files")
            try:
                sources = [(f["filename"].replace("\\", "/").split("/")[-1], base64.b64decode(f["base64"], validate=True)) for f in files]
            except (binascii.Error, ValueError) as exc:
                raise KenoError("bad_catalog", f"File content is not valid base64: {exc}") from exc
        else:
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise KenoError("bad_catalog", "paths must be a list of local .c5m files.", field="paths")
            for raw in paths:
                src = Path(raw).absolute()
                # The caller authorizes each chosen file's folder as a read root; links stay forbidden.
                sources.append((src.name, read_file(contained(src.parent, src.name))))
        if any(len(data) > MAX_FILE for _, data in sources) or sum(len(data) for _, data in sources) > 8 * 1024 * 1024:
            raise KenoError("import_too_large", "Reference files are limited to 8 MiB in total (tool policy).")
        return sources

    def _catalog_candidate(self, project, snapshot, game_version, provenance, name, files, paths):
        from .catalog_import import build_catalog, catalog_bytes
        if not isinstance(name, str) or not self.CATALOG_NAME.fullmatch(name):
            raise KenoError("bad_catalog", "Name the catalog with 2-64 lowercase letters, digits, dots, dashes or underscores.", field="name")
        relative = f"catalogs/{name}.json"
        target = contained(self.workspace, relative)
        if target.exists():
            raise KenoError("dest_exists", "A catalog with this name already exists; choose a new name. Catalogs are never overwritten.", field="name")
        catalog, review = build_catalog(self._catalog_sources(files, paths), game_version, provenance)
        blob = catalog_bytes(catalog)
        if len(blob) > MAX_FILE:
            raise KenoError("file_too_large", "The resulting catalog exceeds the 16 MiB tool limit; import fewer files.")
        target_version = snapshot["meta"].get("target_version")
        if target_version != catalog["game_version"]:
            review["warnings"].insert(0, f"Catalog describes game {catalog['game_version']} but the project targets "
                                         f"{target_version or 'no version'}; catalog references stay unverified.")
        meta = {**snapshot["meta"], "catalog": relative}
        diff = "".join(difflib.unified_diff(json_bytes(snapshot["meta"]).decode().splitlines(True),
                                            json_bytes(meta).decode().splitlines(True), fromfile="project.json", tofile="project.json"))
        return target, blob, meta, {**review, "catalog_path": relative, "catalog_sha256": sha(blob), "catalog_bytes": len(blob),
                                    "previous_catalog": snapshot["meta"].get("catalog"), "diff": diff}

    def preview_catalog_import(self, project: str, expected_revision: str, game_version: str, provenance: str, name: str,
                               files: list | None = None, paths: list[str] | None = None):
        """Review a catalog built from local reference files; nothing is written."""
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        _, _, _, review = self._catalog_candidate(project, snapshot, game_version, provenance, name, files, paths)
        return {**review, "written": False, "revision": snapshot["revision"]}

    def apply_catalog_import(self, project: str, expected_revision: str, game_version: str, provenance: str, name: str,
                             files: list | None = None, paths: list[str] | None = None):
        """Save a new private catalog and point the project at it; the revision changes with the catalog hash."""
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            target, blob, meta, review = self._catalog_candidate(project, snapshot, game_version, provenance, name, files, paths)
            target.parent.mkdir(parents=True, exist_ok=True)
            created = False
            try:
                with contained(self.workspace, target).open("xb") as stream:
                    created = True
                    stream.write(blob)
                    stream.flush()
                    os.fsync(stream.fileno())
                candidate = self._snapshot(project, metadata_override=meta)
                if candidate["catalog_issue"]:
                    raise KenoError("bad_catalog", candidate["catalog_issue"])
                self._check_revision(self._snapshot(project), expected_revision)
                backup = contained(root, ".kenogenesis/backups")
                backup.mkdir(parents=True, exist_ok=True)
                backup_name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
                with contained(root, backup / backup_name).open("xb") as stream:
                    stream.write(json_bytes(snapshot["meta"]))
                atomic_write_bytes(contained(root, "project.json"), json_bytes(meta))
            except Exception:
                if created:
                    target.unlink()
                raise
            return {**review, "written": True, "file": "project.json", "backup": f".kenogenesis/backups/{backup_name}",
                    "before_revision": snapshot["revision"], "revision": self._snapshot(project)["revision"]}

    def compatibility(self, project: str, baseline: str | None = None):
        snapshot = self._snapshot(project)
        report = self._validate(snapshot)
        priorities = self._declared_inputs(snapshot)
        change_review = None
        if baseline:
            baseline_path = contained(snapshot["root"], baseline)
            receipt = read_json(baseline_path)
            if receipt.get("tool") != "KENOGENESIS" or receipt.get("project") != project:
                raise KenoError("bad_baseline", "Choose a KENOGENESIS manifest for this project.")
            previous = receipt.get("validation", {}).get("new_sequence")
            if not isinstance(previous, list):
                raise KenoError("bad_baseline", "Baseline requires an export manifest with new_sequence.")
            now = report["new_sequence"]
            kinds = {entry["kind"] for entry in [*previous, *now]}
            risks = [kind for kind in sorted(kinds) if
                     [entry for entry in now if entry["kind"] == kind][:sum(e["kind"] == kind for e in previous)] !=
                     [entry for entry in previous if entry["kind"] == kind]]
            details = []
            for kind in sorted(kinds):
                old = [(e.get("project"), e.get("name")) for e in previous if e.get("kind") == kind]
                new = [(e["project"], e["name"]) for e in now if e["kind"] == kind]
                first = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b), None)
                if first is None and len(new) < len(old):
                    first = len(new)
                details.append({"kind": kind, "baseline_count": len(old), "current_count": len(new),
                                "status": "reordered_or_removed" if kind in risks else "appended" if len(new) > len(old) else "unchanged",
                                "first_difference": first,
                                "removed": [n for p, n in old if (p, n) not in new], "added": [n for p, n in new if (p, n) not in old]})
            change_review = {"definition_order_risks": risks, "baseline_sha256": sha(read_file(baseline_path)),
                             "baseline_revision": receipt.get("revision"), "baseline": baseline, "kinds": details,
                             "note": "Append-only comparison is a static warning, never proof of save compatibility."}
        return {"revision": snapshot["revision"], "declared_inputs": priorities,
                "load_order_note": "declared_inputs follow the dependency list, then this project. That is the declared "
                                   "order only; the engine's activation order and equal-priority behavior are not verified.",
                "diagnostics": [d for d in report["diagnostics"] if d["code"] in self.COMPAT_CODES],
                "change_review": change_review, "limitations": report["limitations"], "engine_verified": False}

    # ----- additive read-only views shared by CLI, MCP and HTTP -----
    def project_model(self, project: str):
        """The resolved browser model (objects, edges, readiness, provenance, catalog state); read-only."""
        return self.browser_model(project)

    def compare_units(self, project: str, object_index: int, references: list[dict[str, int]]):
        """Compare one unit with 1-4 references, each {"object_index": n} (a unit of this project) or {"catalog_index": n}
        (a catalog monster row). Values keep their source and unknowns stay unknown."""
        from .design import compare_units
        return compare_units(self, project, object_index, references)

    def design_report(self, project: str, class_index: int | None = None):
        """Class roster, recruitment, starting forces and ritual resources as authored; no balance score."""
        from .design import design_report
        return design_report(self, project, class_index)

    def compare_classes(self, project: str, class_index: int, references: list[dict[str, int]]):
        """One class beside 1-4 references, each {"object_index": n} (a class of this project) or {"catalog_index": n}
        (a catalog class row): roster counts, recruitment as written, income bonuses, ritual schools reached through
        units, and a dashboard of the same source-backed figures. Unknown coverage is labelled; no score."""
        from .design import compare_classes
        return compare_classes(self, project, class_index, references)

    # ----- private catalog snapshot: an explicit, guarded copy kept beside the project -----
    def _catalog_snapshot_plan(self, snapshot, action):
        meta = dict(snapshot["meta"])
        blob = None
        if action == "capture":
            if snapshot["catalog_source"] != "configured":
                raise KenoError("bad_catalog", "Configure a valid local catalog before capturing a snapshot.")
            digest = snapshot["inputs"]["catalog"]
            blob = snapshot["catalog_bytes"]
            meta["catalog_snapshot"] = {"path": f"{SNAPSHOT_DIR}/{digest}.json", "sha256": digest, "source": meta.get("catalog"),
                                        "game_version": snapshot["catalog"]["game_version"], "captured_at_revision": snapshot["revision"]}
        elif action == "release":
            if not meta.get("catalog_snapshot"):
                raise KenoError("no_snapshot", "This project has no catalog snapshot.")
            meta["catalog_snapshot"] = None
        else:
            raise KenoError("bad_action", "Action is capture or release.")
        diff = "".join(difflib.unified_diff(json_bytes(snapshot["meta"]).decode().splitlines(True),
                                            json_bytes(meta).decode().splitlines(True), fromfile="project.json", tofile="project.json"))
        return meta, blob, diff

    def preview_catalog_snapshot(self, project: str, expected_revision: str, action: str = "capture"):
        """Review capturing (or releasing) a private snapshot of the configured catalog; nothing is written."""
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        meta, blob, diff = self._catalog_snapshot_plan(snapshot, action)
        target = (meta.get("catalog_snapshot") or {}).get("path")
        return {"action": action, "diff": diff, "written": False, "revision": snapshot["revision"],
                "snapshot_path": target, "snapshot_bytes": len(blob) if blob else None,
                "note": "The snapshot stays in the project's private .kenogenesis folder and is never exported or redistributed."}

    def apply_catalog_snapshot(self, project: str, expected_revision: str, action: str = "capture"):
        """Write the snapshot file (new or byte-identical only) and record it in project.json, or nothing."""
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            meta, blob, diff = self._catalog_snapshot_plan(snapshot, action)
            created = None
            try:
                if blob is not None:
                    folder = contained(root, SNAPSHOT_DIR)
                    folder.mkdir(parents=True, exist_ok=True)
                    target = contained(root, meta["catalog_snapshot"]["path"])
                    if target.exists():
                        if is_link(target) or read_file(target) != blob:
                            raise KenoError("dest_exists", "A different file already uses this snapshot name; nothing was overwritten.")
                    else:
                        with target.open("xb") as stream:
                            created = target
                            stream.write(blob)
                            stream.flush()
                            os.fsync(stream.fileno())
                if blob is not None and self._snapshot(project, metadata_override=meta)["catalog_snapshot"]["status"] == "invalid":
                    raise KenoError("bad_catalog", "The snapshot could not be verified after writing.")
                self._check_revision(self._snapshot(project), expected_revision)
                backup = contained(root, ".kenogenesis/backups")
                backup.mkdir(parents=True, exist_ok=True)
                name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
                with contained(root, backup / name).open("xb") as stream:
                    stream.write(json_bytes(snapshot["meta"]))
                atomic_write_bytes(contained(root, "project.json"), json_bytes(meta))
            except BaseException:
                if created is not None:
                    with contextlib.suppress(OSError):
                        created.unlink()
                raise
            return {"action": action, "diff": diff, "written": True, "file": "project.json", "backup": f".kenogenesis/backups/{name}",
                    "snapshot_path": (meta.get("catalog_snapshot") or {}).get("path"), "before_revision": snapshot["revision"],
                    "revision": self._snapshot(project)["revision"]}

    # ----- private evidence records: observations about one revision; never exported -----
    def list_evidence(self, project: str):
        """Read evidence records; this never creates folders or files."""
        from .records import list_records
        snapshot = self._snapshot(project)
        return list_records(snapshot["root"], snapshot["revision"])

    def record_evidence(self, project: str, expected_revision: str, category: str, summary: str, details: str = "",
                        reference: str = "", preview: bool = True, observation: dict | None = None,
                        references: list[dict] | None = None):
        """Review (preview=True) or save one plain-text observation linked to the current revision.
        observation holds optional structured fields for a user-reported game check only. references is an
        optional list of up to eight {"kind","label","sha256"?} private labels; nothing is attached or opened."""
        from .records import build_record, write_record
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            record = build_record(project, snapshot["revision"], sha(snapshot["mods"][-1]["data"]), category, summary, details, reference,
                                  observation, references)
            if preview:
                return {"record": record, "written": False, "revision": snapshot["revision"]}
            path = write_record(root, record)
            return {"record": record, "written": True, "file": path, "revision": snapshot["revision"]}

    def export_mod(self, project: str, expected_revision: str, format: str = "zip"):
        root, _ = self._project(project)
        if format not in ("zip", "folder"):
            raise KenoError("bad_format", "Choose zip or folder.")
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            report = self._validate(snapshot)
            if not report["static_ok"]:
                raise KenoError("validation_failed", "Fix static errors before exporting.", counts=report["counts"])
            mod = snapshot["mods"][-1]
            payload = {f"{project}/{project}.c5m": mod["data"]}
            payload.update({f"{project}/{name}": data for name, data in mod["assets"].items()})
            exports = contained(root, "exports")
            exports.mkdir(exist_ok=True)
            export_id = f"{time.time_ns()}-{secrets.token_hex(4)}"
            destination = contained(root, f"exports/{export_id}" + (".zip" if format == "zip" else ""))
            if format == "zip":
                with destination.open("xb") as stream:
                    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                        for name, data in sorted(payload.items()):
                            archive.writestr(name, data)
                with destination.open("rb") as stream:
                    archive_sha = hashlib.file_digest(stream, "sha256").hexdigest()
            else:
                destination.mkdir()
                for name, data in payload.items():
                    target = contained(destination, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write(data)
                archive_sha = None
            receipt = {"tool": "KENOGENESIS", "tool_version": __version__, "tool_source_sha256": tool_fingerprint(), "project": project,
                       "revision": snapshot["revision"], "source_sha256": sha(mod["data"]),
                       "manual": MANUAL, "target_version": snapshot["meta"].get("target_version"),
                       "catalog": self._distribution_catalog(self._catalog_info(snapshot), bool(snapshot["meta"].get("catalog"))), "dependencies": snapshot["meta"]["dependencies"],
                       "files": [{"path": name, "sha256": sha(data), "bytes": len(data)} for name, data in sorted(payload.items())],
                       "archive_sha256": archive_sha, "validation": self._distribution_validation(report),
                       "manifest_scope": "distribution",
                       "note": "Dependencies must be installed separately. Static checks only; not proof of game behavior."}
            manifest = contained(root, f"exports/{export_id}.manifest.json")
            with manifest.open("xb") as stream:
                stream.write(json_bytes(receipt))
            warnings = [d["message"] for d in report["diagnostics"] if d["severity"] == "warning"]
            return {"export_id": export_id, "path": str(destination), "manifest": str(manifest),
                    "manifest_path": f"exports/{export_id}.manifest.json", "format": format, "files": receipt["files"],
                    "archive_sha256": archive_sha, "revision": snapshot["revision"], "dependencies": receipt["dependencies"],
                    "counts": report["counts"], "warnings": warnings[:50], "engine_verified": False}

    # ----- block edits: typed line changes as exact byte splices (see blockedit.py) -----
    def _block_candidate(self, snapshot, object_index, changes, mode, opener, insert_before=None, linked=None):
        from .blockedit import candidate
        mod = snapshot["mods"][-1]
        if linked is not None:
            # One reviewed transaction: edit an existing block, then insert the new block before it so it is defined first.
            if mode != "new" or not isinstance(linked, dict) or set(linked) != {"object_index", "changes"}:
                raise KenoError("bad_changes", "linked is {object_index, changes} and accompanies a new block only.")
            target = linked["object_index"]
            edited, linked_summary, _ = candidate(mod["parsed"], mod["data"], target, linked["changes"], "edit")
            if not linked_summary:
                raise KenoError("bad_changes", "The linked block edit changes nothing.")
            before = target if insert_before is None else insert_before
            if not isinstance(before, int) or isinstance(before, bool) or before > target:
                raise KenoError("bad_changes", "The new block must come before the block that refers to it.", field="insert_before")
            data, summary, index = candidate(parse(edited), edited, None, changes, "new", opener, before)
            label = mod["parsed"]["objects"][target]
            summary = summary + [dict(s, block=f"{label['opener']} {label['name']}".strip(), block_line=label["line"]) for s in linked_summary]
            if len(data) > MAX_FILE:
                raise KenoError("file_too_large", "Candidate exceeds the source limit.")
            return data, summary, index
        if mode == "delete":
            from .view import Model
            model = Model(self, snapshot, {"diagnostics": []}, [])
            users = [e for e in model.edges() if e["to"].get("index") == object_index and e["to"].get("status") in ("local", "later")
                     and e["from"] != object_index]
            if users:
                raise KenoError("block_in_use", "Other blocks in this mod refer to this one; remove those references first.",
                                used_by=[{"index": e["from"], "command": e["command"], "line": e["line"]} for e in users])
        data, summary, index = candidate(mod["parsed"], mod["data"], object_index, changes, mode, opener, insert_before)
        if len(data) > MAX_FILE:
            raise KenoError("file_too_large", "Candidate exceeds the source limit.")
        return data, summary, index

    def preview_block_edit(self, project: str, expected_revision: str, object_index: int | None = None, changes: list | None = None,
                           mode: str = "edit", opener: dict | None = None, insert_before: int | None = None, linked: dict | None = None):
        """Preview typed line changes to one block (object_index; -1 = mod-wide commands), a new block or a removal.

        A new block may be inserted before another (insert_before) and carry one linked edit of an existing block
        (linked: {object_index, changes}); both are reviewed and saved as one source change.
        """
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        data, summary, index = self._block_candidate(snapshot, object_index, changes or [], mode, opener, insert_before, linked)
        result = self._preview_result(project, snapshot, data)
        result.update(changes=summary, changed=data != snapshot["mods"][-1]["data"], object_index=index, mode=mode)
        return result

    def apply_block_edit(self, project: str, expected_revision: str, object_index: int | None = None, changes: list | None = None,
                         mode: str = "edit", opener: dict | None = None, insert_before: int | None = None, linked: dict | None = None):
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            data, summary, index = self._block_candidate(snapshot, object_index, changes or [], mode, opener, insert_before, linked)
            result = self._preview_result(project, snapshot, data)
            result.update(changes=summary, object_index=index, mode=mode)
            if data == snapshot["mods"][-1]["data"]:
                result.update(changed=False, written=False)
                return result
            receipt = self._write_source(project, snapshot, data)
            result.update(changed=True, written=True, **receipt, revision=self._snapshot(project)["revision"])
        return result

    # ----- unit artwork: new frame files and one exact sprite patch, reviewed and saved together -----
    def _art_frames(self, frame, asset_path, content, frames):
        """Normalise a paired `frames` request or the legacy single-frame arguments; decode and check pixels."""
        import base64
        import binascii
        from .images import unit_frame_facts
        if frames is None:
            if frame is None or asset_path is None or content is None:
                raise KenoError("bad_art", "Send frames, or frame with asset_path and content.")
            frames = [{"frame": frame, "asset_path": asset_path, "content": content}]
        elif frame is not None or asset_path is not None or content is not None:
            raise KenoError("bad_art", "Send either frames or the single-frame arguments, not both.")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 2 or \
                not all(isinstance(f, dict) and set(f) == {"frame", "asset_path", "content"} for f in frames):
            raise KenoError("bad_art", "frames is a list of one or two {frame, asset_path, content} objects.")
        out = {}
        for f in frames:
            name, path, data = f["frame"], f["asset_path"], f["content"]
            if name not in ("spr1", "spr2") or name in out:
                raise KenoError("bad_art", "Each frame is spr1 (idle) or spr2 (attack), at most once.")
            if not isinstance(path, str) or mod_relpath_problems(path) or not path.lower().endswith((".png", ".tga")):
                raise KenoError("bad_art", f"{name}: choose a new relative .png or .tga path.", field=name)
            if not isinstance(data, str) or len(data) > 3 * 1024 * 1024:
                raise KenoError("bad_art", f"{name}: artwork uploads are limited to 2 MiB.", field=name)
            try:
                blob = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise KenoError("bad_art", f"{name}: content is not valid base64.", field=name) from exc
            if not blob or len(blob) > 2 * 1024 * 1024:
                raise KenoError("bad_art", f"{name}: artwork uploads are limited to 2 MiB.", field=name)
            try:
                facts = unit_frame_facts(path, blob)
            except (ValueError, struct.error) as exc:
                raise KenoError("bad_art", f"{name} rejected: {exc}", field=name) from exc
            out[name] = {"path": path, "blob": blob, "facts": facts}
        if len(out) == 2 and out["spr1"]["path"].casefold() == out["spr2"]["path"].casefold():
            raise KenoError("bad_art", "Idle and attack need two different new files.")
        return {k: out[k] for k in ("spr1", "spr2") if k in out}

    def _art_candidate(self, snapshot, object_index, frames):
        """Plan the sprite patch without touching disk: drop copyspr, keep spr1 then spr2 after the last copy."""
        from .blockedit import format_line
        from .images import pair_warnings, unit_frame_facts
        mod = snapshot["mods"][-1]
        parsed, data = mod["parsed"], mod["data"]
        if not isinstance(object_index, int) or isinstance(object_index, bool) or not 0 <= object_index < len(parsed["objects"]) \
                or parsed["objects"][object_index]["kind"] != "monster":
            raise KenoError("bad_object", "Choose a unit from the saved project.")
        if parsed["diagnostics"]:
            raise KenoError("source_edit_required", "Fix parser errors in the source before adding artwork.")
        mod_root = contained(snapshot["root"], f"mod/{mod['slug']}")
        targets = {}
        for name, f in frames.items():
            target = contained(mod_root, f["path"])
            if target.exists() or exact_case_lookup(mod_root, f["path"])[1] == "case_mismatch":
                raise KenoError("dest_exists", f"{name}: a file already exists at {f['path']}. Choose a new filename; "
                                "existing artwork is never overwritten.", field=name)
            targets[name] = target
        sts = parsed["objects"][object_index]["statements"]
        codec = parsed["encoding"].replace("-sig", "")
        newline = "\r\n" if b"\r\n" in data else "\n"
        found = {c: [st for st in sts if st["command"] == c] for c in ("spr1", "spr2")}
        for c, hits in found.items():
            if len(hits) > 1:
                raise KenoError("ambiguous_field", f"{c} appears {len(hits)} times in this unit; resolve it in the line editor.",
                                lines=[st["line"] for st in hits])
        s1, s2 = (found["spr1"] or [None])[0], (found["spr2"] or [None])[0]
        copyspr = [st for st in sts if st["command"] == "copyspr"]
        last_copy = max([st["line"] for st in sts if st["command"] in ("copystats", "copyspr")], default=0)
        live1 = s1 if s1 and s1["line"] > last_copy else None
        live2 = s2 if s2 and s2["line"] > last_copy and (live1 is None or s2["line"] > live1["line"]) else None
        new1, new2 = frames.get("spr1"), frames.get("spr2")
        if not new1 and not live1:
            why = f" spr1 on line {s1['line']} is replaced by the copy command on line {last_copy}." if s1 else ""
            raise KenoError("art_needs_idle", "Add the idle frame (spr1) in the same request: spr2 must follow an explicit "
                            "spr1 that no later copy command replaces (manual p.14)." + why, field="spr1")
        if copyspr and not new2 and not live2:
            raise KenoError("art_pair_required", "This unit borrows its images with copyspr. Add idle and attack together so "
                            "copyspr can be removed without losing the attack pose.", lines=[st["line"] for st in copyspr])
        body = [st for st in sts if st["command"] not in OPENERS]
        indent = data[body[-1]["start"]:body[-1]["start"] + body[-1]["indent"]].decode(codec) if body else ""
        splices, changes, notes = [], [], []

        def code(st):
            return data[st["start"] + st["indent"]:st["end"]].decode(codec).rstrip("\r\n")

        def remove(st, note=None):
            splices.append((st["start"], st["end"], b"", len(splices)))
            changes.append({"op": "remove", "command": st["command"], "line": st["line"], "before": code(st), "after": None, "note": note})

        def replace(st, line):
            splices.append((st["start"] + st["indent"], st["code_end"], line.encode(codec), len(splices)))
            changes.append({"op": "change", "command": st["command"], "line": st["line"], "before": code(st), "after": line})

        def insert(position, line, command, op="add", before=None):
            lead = "" if position == 0 or data[:position].endswith(b"\n") else newline
            splices.append((position, position, (lead + indent + line + newline).encode(codec), len(splices)))
            changes.append({"op": op, "command": command, "line": None, "before": before, "after": line})

        for st in copyspr:
            remove(st, "Removed so the donor's images no longer replace this unit's frames.")
        line1 = format_line("spr1", [new1["path"]]) if new1 else None
        line2 = format_line("spr2", [new2["path"]]) if new2 else None
        if live1:
            if line1:
                replace(live1, line1)
            if line2 and live2:
                replace(live2, line2)
            elif line2:
                if s2:
                    remove(s2, "Moved after spr1: spr1 also sets the attack image, so spr2 must follow it.")
                insert(live1["end"], line2, "spr2")
        else:
            end = sts[-1]["end"]
            if s1:
                remove(s1, f"Replaced by the copy command on line {last_copy}; the new spr1 follows it.")
            insert(end, line1, "spr1")
            if line2:
                if s2:
                    remove(s2, "Moved after the new spr1.")
                insert(end, line2, "spr2")
            elif s2 and s2["line"] > last_copy:
                # Keep an attack image that applies today: it has to stay after the new spr1.
                remove(s2, "Moved after the new spr1 so the existing attack image keeps applying.")
                insert(end, code(s2), "spr2", "move", code(s2))
        if new1 and not new2 and not live2 and not (not live1 and s2 and s2["line"] > last_copy):
            notes.append("spr1 also sets the attack image (manual p.14). Until a spr2 is added, the game shows this idle "
                         "frame for attacks too; a distinct attack pose is still unauthored.")
        if s2 and not new2 and s2["line"] <= last_copy:
            notes.append(f"spr2 on line {s2['line']} is replaced by the copy command on line {last_copy} and was left unchanged.")
        out = data
        for start, stop, text, _ in sorted(splices, key=lambda x: (x[0], x[3]), reverse=True):
            out = out[:start] + text + out[stop:]
        if len(out) > MAX_FILE:
            raise KenoError("file_too_large", "Candidate exceeds the source limit.")
        current = {}
        for name, st in (("spr1", live1), ("spr2", live2 or (s2 if s2 and s2["line"] > last_copy else None))):
            if st is None or not st["args"] or (name == "spr2" and live1 and st["line"] < live1["line"]):
                continue
            path = st["args"][0]["value"]
            entry = {"path": path, "line": st["line"]}
            try:
                entry["facts"] = unit_frame_facts(path, mod["assets"][path])
            except KeyError:
                entry["problem"] = "file unavailable"
            except (ValueError, struct.error) as exc:
                entry["problem"] = str(exc)
            current[name] = entry
        final = {k: (frames[k]["facts"] if k in frames else (current.get(k) or {}).get("facts")) for k in ("spr1", "spr2")}
        warnings = pair_warnings(final["spr1"], final["spr2"])
        if any(k not in frames and k in current and "facts" not in current[k] for k in ("spr1", "spr2")):
            warnings.append("The frame kept from the saved source could not be decoded, so the pair was not compared.")
        if new1 and new2 and sha(new1["blob"]) == sha(new2["blob"]):
            warnings.append("Idle and attack files are identical; the unit has no distinct attack pose.")
        return out, changes, notes, warnings, current, targets

    def _art_result(self, project, snapshot, object_index, frame, asset_path, content, frames):
        import base64
        from .images import preview_png
        chosen = self._art_frames(frame, asset_path, content, frames)
        data, changes, notes, warnings, current, targets = self._art_candidate(snapshot, object_index, chosen)
        result = self._preview_result(project, snapshot, data, {f["path"]: f["blob"] for f in chosen.values()})
        reviewed = {name: {"path": f["path"], "bytes": len(f["blob"]), "sha256": sha(f["blob"]), "facts": f["facts"],
                           "preview": base64.b64encode(preview_png(f["path"], f["blob"])).decode("ascii")}
                    for name, f in chosen.items()}
        result.update(changes=changes, notes=notes, pair_warnings=warnings, current=current, frames=reviewed,
                      object_index=object_index, art_preview=next(iter(reviewed.values()))["preview"],
                      assets=[{"path": f["path"], "frame": name, "bytes": f["bytes"], "sha256": f["sha256"]} for name, f in reviewed.items()])
        return result, data, chosen, targets

    def preview_art_upload(self, project: str, expected_revision: str, object_index: int, frame: str | None = None,
                           asset_path: str | None = None, content: str | None = None, frames: list | None = None):
        """Review new unit frames (frames: spr1 and/or spr2) with their pixel checks and exact source patch."""
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        return self._art_result(project, snapshot, object_index, frame, asset_path, content, frames)[0]

    def apply_art_upload(self, project: str, expected_revision: str, object_index: int, frame: str | None = None,
                         asset_path: str | None = None, content: str | None = None, frames: list | None = None):
        """Save the reviewed frames and their source patch together; any failure removes every new file."""
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            result, data, chosen, targets = self._art_result(project, snapshot, object_index, frame, asset_path, content, frames)
            self._check_revision(self._snapshot(project), expected_revision)
            mod_root = contained(snapshot["root"], f"mod/{project}")
            created, made_dirs = [], []
            try:
                for name, target in targets.items():
                    missing, parent = [], target.parent
                    while parent != mod_root and not parent.exists():
                        missing.append(parent)
                        parent = parent.parent
                    for folder in reversed(missing):
                        contained(mod_root, folder)
                        folder.mkdir()
                        made_dirs.append(folder)
                    contained(mod_root, target)
                    with target.open("xb") as stream:
                        created.append(target)
                        stream.write(chosen[name]["blob"])
                        stream.flush()
                        os.fsync(stream.fileno())
                fresh = self._snapshot(project)
                ignore = {f"{project}/{f['path']}" for f in chosen.values()}
                if {k: v for k, v in fresh["inputs"].items() if k not in ignore} != {k: v for k, v in snapshot["inputs"].items() if k not in ignore}:
                    raise KenoError("inputs_changed", "Project inputs changed while saving artwork; the new files were removed.")
                receipt = self._write_source(project, fresh, data)
            except BaseException:
                for path in reversed(created):
                    with contextlib.suppress(OSError):
                        path.unlink()
                for folder in reversed(made_dirs):
                    with contextlib.suppress(OSError):
                        folder.rmdir()
                raise
            result.update(written=True, changed=True, **receipt, revision=self._snapshot(project)["revision"])
            result["before_revision"] = expected_revision
            for item in result["frames"].values():
                item.pop("preview", None)
            result.pop("art_preview", None)
            return result

    # ----- browser upload import: bytes arrive in the request; no server path is read -----
    def _upload_payload(self, slug, source, assets):
        import base64
        import binascii
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            raise KenoError("bad_project", "Use a lowercase slug of 2-48 letters, digits or underscores.", field="slug")
        if not isinstance(source, dict) or not isinstance(source.get("filename"), str) or not isinstance(source.get("base64"), str):
            raise KenoError("bad_import", "Choose one .c5m file.", field="source")
        if not source["filename"].lower().endswith(".c5m"):
            raise KenoError("bad_import", "The mod file must end in .c5m.", field="source")
        assets = assets or []
        if not isinstance(assets, list) or len(assets) > 200:
            raise KenoError("bad_import", "Add at most 200 asset files.", field="assets")
        total, files = 0, {}
        try:
            data = base64.b64decode(source["base64"], validate=True)
            for i, a in enumerate(assets):
                if not isinstance(a, dict) or not isinstance(a.get("path"), str) or not isinstance(a.get("base64"), str):
                    raise KenoError("bad_import", "Each asset needs a path and content.", field=f"assets.{i}")
                path = a["path"].strip()
                problems = mod_relpath_problems(path)
                if problems or path.lower().endswith(".c5m") or path in files:
                    raise KenoError("bad_asset_path", f"{path}: {'; '.join(problems) or 'duplicate or a second .c5m'}", field=f"assets.{i}")
                files[path] = base64.b64decode(a["base64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise KenoError("bad_import", f"File content is not valid base64: {exc}") from exc
        # Refuse Windows file/directory and case collisions before creating a project.
        prefixes = {}
        file_names = {name.casefold() for name in files}
        for name in files:
            parts = name.split("/")
            for count in range(1, len(parts) + 1):
                prefix = "/".join(parts[:count])
                folded = prefix.casefold()
                if (folded in prefixes and prefixes[folded] != prefix) or (count < len(parts) and folded in file_names):
                    raise KenoError("bad_asset_path", "Uploaded paths collide as files, directories or letter case.")
                prefixes[folded] = prefix
        for blob in [data, *files.values()]:
            total += len(blob)
            if len(blob) > MAX_FILE:
                raise KenoError("file_too_large", "A file exceeds the 16 MiB tool limit.")
        if total > 8 * 1024 * 1024:
            raise KenoError("import_too_large", "Uploads are limited to 8 MiB in total (tool policy).")
        return data, files

    def _upload_review(self, slug, source, data, files):
        parsed = parse(data)
        refs = {name for name, _, _ in asset_refs(parsed)}
        warnings = [f"{d['message']} (line {d['line']})" for d in parsed["diagnostics"]]
        if source["filename"] != f"{slug}.c5m":
            warnings.append(f"The file is saved as {slug}.c5m; the game requires the folder and .c5m to share the mod name (manual p.2).")
        if b"\x00" in data:
            warnings.append("The file contains NUL bytes; it may not be a text mod.")
        rows = []
        for path, blob in sorted(files.items()):
            entry = {"path": path, "bytes": len(blob), "sha256": sha(blob), "referenced": path in refs}
            try:
                info = inspect_asset(path, blob)
                entry.update({k: info[k] for k in ("width", "height") if k in info})
            except (ValueError, struct.error) as exc:
                entry["problem"] = str(exc)
                warnings.append(f"{path}: {exc}")
            if not entry["referenced"]:
                entry["note"] = "Not referenced by the .c5m: kept as a declared export file."
            rows.append(entry)
        text, encoding, _ = decode(data)
        return {"project": slug, "file": f"mod/{slug}/{slug}.c5m", "sha256": sha(data), "bytes": len(data), "encoding": encoding,
                "newlines": "CRLF" if b"\r\n" in data else "LF", "objects": len(parsed["objects"]), "lines": len(text.splitlines()),
                "assets": rows, "missing_assets": sorted(refs - set(files)), "warnings": warnings,
                "note": "Creates a new project; existing projects are never overwritten. Static checks follow in Validation."}

    def preview_import_upload(self, slug: str, source: dict, assets: list | None = None, name: str | None = None,
                              target_version: str | None = None):
        data, files = self._upload_payload(slug, source, assets)
        if contained(self.workspace, slug).exists():
            raise KenoError("dest_exists", "A project with this folder name already exists; nothing was written.", field="slug")
        return {**self._upload_review(slug, source, data, files), "written": False}

    def import_upload(self, slug: str, source: dict, assets: list | None = None, name: str | None = None,
                      target_version: str | None = None):
        data, files = self._upload_payload(slug, source, assets)
        review = self._upload_review(slug, source, data, files)
        self.create_project(slug, name=name or None, target_version=target_version or None)
        root, meta = self._project(slug)
        with project_lock(root):
            mod = contained(root, f"mod/{slug}")
            if "banner.tga" not in files:
                contained(mod, "banner.tga").unlink()  # The placeholder must not satisfy an imported reference.
            atomic_write_bytes(contained(mod, f"{slug}.c5m"), data)
            for path, blob in files.items():
                target = contained(mod, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_bytes(target, blob)
            refs = {n for n, _, _ in asset_refs(parse(data))}
            meta["declared_assets"] = sorted(set(files) - refs)
            atomic_write_bytes(contained(root, "project.json"), json_bytes(meta))
        return {**review, "written": True, "revision": self._snapshot(slug)["revision"]}

    # ----- exports, files and catalog pages for the browser -----
    EXPORT_ID = re.compile(r"^\d{10,22}-[0-9a-f]{8}$")

    def list_exports(self, project: str):
        root, _ = self._project(project)
        folder = contained(root, "exports")
        out = []
        if folder.is_dir():
            for manifest in sorted(folder.glob("*.manifest.json"), reverse=True):
                export_id = manifest.name[:-len(".manifest.json")]
                if not self.EXPORT_ID.fullmatch(export_id) or is_link(manifest):
                    continue
                entry = {"export_id": export_id, "created_ns": int(export_id.split("-")[0]),
                         "manifest_path": f"exports/{manifest.name}"}
                try:
                    receipt = read_json(manifest)
                    archive = contained(root, f"exports/{export_id}.zip")
                    entry.update(revision=receipt.get("revision"), source_sha256=receipt.get("source_sha256"),
                                 archive_sha256=receipt.get("archive_sha256"), files=receipt.get("files", []),
                                 counts=(receipt.get("validation") or {}).get("counts"),
                                 target_version=receipt.get("target_version"),
                                 format="zip" if archive.is_file() else "folder",
                                 path=f"exports/{export_id}.zip" if archive.is_file() else f"exports/{export_id}/")
                except (OSError, KenoError, ValueError) as exc:
                    entry["error"] = str(exc)
                out.append(entry)
        return {"exports": sorted(out, key=lambda e: e["created_ns"], reverse=True)}

    def export_artifact(self, project: str, export_id: str, kind: str):
        root, _ = self._project(project)
        if not isinstance(export_id, str) or not self.EXPORT_ID.fullmatch(export_id) or kind not in ("archive", "manifest"):
            raise KenoError("not_found", "Unknown export.")
        name = f"{export_id}.zip" if kind == "archive" else f"{export_id}.manifest.json"
        path = contained(root, f"exports/{name}")
        if not path.is_file() or is_link(path):
            raise KenoError("not_found", "That export has no file of this kind.")
        data = read_file(path)
        if kind == "manifest":
            # Sanitize historical downloads without rewriting their private on-disk receipts or changing archive hashes.
            try:
                receipt = json.loads(data)
                receipt["catalog"] = self._distribution_catalog(receipt.get("catalog") or {})
                receipt["validation"] = self._distribution_validation(receipt["validation"])
                receipt["manifest_scope"] = "distribution"
                data = json_bytes(receipt)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise KenoError("bad_manifest", "The export manifest could not be prepared for distribution.") from exc
        return data, f"{project}-{name}"

    # ----- CoE5 Workshop staging: a private local ZIP from an existing export (see workshop.py); never uploads -----
    def preview_workshop_stage(self, project: str, expected_revision: str, export_id: str, banner: dict,
                               visibility: str = "private"):
        """Review the exact bundle (export payload + banner.png + coe5ws.txt) for an export of the saved revision; writes nothing."""
        from .workshop import plan_stage, public_plan
        snapshot = self._snapshot(project)
        self._check_revision(snapshot, expected_revision)
        return public_plan(plan_stage(self, snapshot, export_id, banner, visibility))

    def stage_workshop_bundle(self, project: str, expected_revision: str, export_id: str, banner: dict,
                              visibility: str = "private"):
        """Save the reviewed bundle as a NEW private stage with its receipt; the mod source and revision are unchanged."""
        from .workshop import plan_stage, public_plan, write_stage
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            plan = plan_stage(self, snapshot, export_id, banner, visibility)
            self._check_revision(self._snapshot(project), expected_revision)
            receipt = write_stage(root, plan)
            try:
                self._check_revision(self._snapshot(project), expected_revision)
            except BaseException:
                for name in (receipt["bundle"], f"{receipt['stage_id']}.receipt.json"):
                    with contextlib.suppress(OSError):
                        contained(root, f".kenogenesis/workshop-stages/{name}").unlink()
                raise
        result = public_plan(plan, written=True)
        result.update(stage_id=receipt["stage_id"], bundle_sha256=receipt["bundle_sha256"], bundle_bytes=receipt["bundle_bytes"],
                      file=f".kenogenesis/workshop-stages/{receipt['bundle']}", revision=snapshot["revision"])
        return result

    def list_workshop_stages(self, project: str):
        """Read-only stage history with each bundle's hash re-checked; never creates folders or files."""
        from .workshop import list_stages
        snapshot = self._snapshot(project)
        return list_stages(snapshot["root"], snapshot["revision"])

    def workshop_artifact(self, project: str, stage_id: str, kind: str):
        from .workshop import stage_artifact
        root, _ = self._project(project)
        return stage_artifact(root, project, stage_id, kind)

    def mod_file(self, project: str, path: str):
        """Bytes of one file inside the project's mod folder (exact case, no links, no traversal)."""
        root, _ = self._project(project)
        if not isinstance(path, str) or mod_relpath_problems(path) or path == f"{project}.c5m":
            raise KenoError("bad_asset_path", "Asset path fails the containment policy.")
        mod = contained(root, f"mod/{project}")
        return read_file(safe_asset(mod, path))

    def catalog_page(self, project: str, query: str = "", kind: str = "", sort: str = "name", order: str = "asc",
                     page: int = 1, per: int = 40, conditions: list | None = None):
        """One bounded, read-only page of the project's local catalog (at most 100 rows) with up to eight
        {"field","op","value"} conditions; the same view as the browser catalog. Nothing is extracted or written."""
        snapshot = self._snapshot(project)
        info = self._catalog_info(snapshot)
        catalog = snapshot["catalog"]
        if catalog is None:
            return {"catalog": info, "rows": [], "total": 0, "kinds": [], "page": 1, "per": per, "pages": 1}
        rows = list(enumerate(catalog["rows"]))
        kinds = sorted({str(r.get("kind")) for _, r in rows})
        columns = sorted({str(k) for _, row in rows for k in row})
        conditions = conditions or []
        if not isinstance(conditions, list) or len(conditions) > 8:
            raise KenoError("bad_filter", "Use at most eight catalog conditions.")
        operators = {"eq", "ne", "contains", "gt", "ge", "lt", "le", "exists", "missing"}
        for rule in conditions:
            if not isinstance(rule, dict) or rule.get("field") not in columns or rule.get("op") not in operators or len(str(rule.get("value", ""))) > 120:
                raise KenoError("bad_filter", "Choose a catalog column, a supported condition and a value up to 120 characters.")

        def matches(row, rule):
            key, op, wanted = rule["field"], rule["op"], str(rule.get("value", ""))
            value = row.get(key)
            if op in ("exists", "missing"):
                present = key in row and value is not None
                return present if op == "exists" else not present
            if value is None:
                return False
            actual = str(value).casefold()
            if op == "contains":
                return wanted.casefold() in actual
            if op in ("eq", "ne"):
                equal = actual == wanted.casefold()
                return equal if op == "eq" else not equal
            try:
                left, right = float(value), float(wanted)
            except (TypeError, ValueError):
                return False
            return {"gt": left > right, "ge": left >= right, "lt": left < right, "le": left <= right}[op]
        q = (query or "").strip().casefold()[:60]
        hits = [(i, r) for i, r in rows if (not kind or r.get("kind") == kind) and
                (not q or q in str(r.get("name", "")).casefold() or q == str(r.get("id", "")).casefold()) and all(matches(r, rule) for rule in conditions)]
        key = {"name": lambda x: str(x[1].get("name", "")).casefold(), "id": lambda x: str(x[1].get("id", "")).zfill(12),
               "kind": lambda x: (str(x[1].get("kind")), str(x[1].get("name", "")).casefold())}.get(sort, lambda x: x[0])
        hits.sort(key=key, reverse=order == "desc")
        per = max(1, min(int(per), 100))
        pages = max(1, -(-len(hits) // per))
        page = max(1, min(int(page), pages))
        start = (page - 1) * per
        return {"catalog": info, "kinds": kinds, "columns": columns, "conditions": conditions, "total": len(hits), "page": page, "per": per, "pages": pages,
                "rows": [{"index": i, "kind": r.get("kind"), "name": r.get("name"), "id": r.get("id"), "fields": len(r),
                          **{k: r[k] for k in ("name_ordinal", "name_count", "source_file", "source_line") if k in r}}
                         for i, r in hits[start:start + per]],
                "unverified": catalog["game_version"] != snapshot["meta"].get("target_version")}

    def catalog_entry(self, project: str, index: int):
        """One catalog row as printed in the local catalog, with this project's lines that reference it; read-only."""
        snapshot = self._snapshot(project)
        catalog = snapshot["catalog"]
        if catalog is None or not isinstance(index, int) or not 0 <= index < len(catalog["rows"]):
            raise KenoError("not_found", "No such catalog row.")
        row = catalog["rows"][index]
        used = []
        for st in snapshot["mods"][-1]["parsed"]["statements"]:
            ref = REFERENCES.get(st["command"])
            if ref and ref[1] == row.get("kind") and len(st["args"]) > ref[0]:
                value = st["args"][ref[0]]["value"]
                if value == row.get("name") or (row.get("id") is not None and value == str(row.get("id"))):
                    used.append({"line": st["line"], "command": st["command"]})
        return {"catalog": self._catalog_info(snapshot), "index": index, "row": row, "used_in_project": used}

    def browser_projects(self):
        """Project cards for the sidebar, including unreadable folders (reported, never repaired)."""
        from .view import Model
        out = []
        for root in sorted(self.workspace.iterdir()):
            if not SLUG_RE.fullmatch(root.name) or not root.is_dir() or is_link(root) or not (root / "project.json").exists():
                continue
            try:
                snapshot = self._snapshot(root.name)
                report = self._validate(snapshot)
                model = Model(self, snapshot, report, [])
                model.assets()
                icon = next((st for st in snapshot["mods"][-1]["parsed"]["statements"]
                             if st["command"] == "icon" and st["object"] is None and st["args"]), None)
                out.append({"slug": root.name, "ok": True, "name": snapshot["meta"]["name"],
                            "target_version": snapshot["meta"].get("target_version"),
                            "banner": model.sprite(icon["args"][0]["value"], icon["line"], "icon") if icon else None,
                            "validation": {"static_ok": report["static_ok"], "counts": report["counts"]}})
            except (OSError, KenoError, ValueError, TypeError, UnicodeError) as exc:
                code = exc.code if isinstance(exc, KenoError) else "unreadable"
                out.append({"slug": root.name, "ok": False, "error": {"code": code, "message": str(exc)}})
        return {"projects": out, "workspace": str(self.workspace)}

    def browser_model(self, project: str):
        from .view import Model
        snapshot = self._snapshot(project)
        report = self._validate(snapshot)
        exports = self.list_exports(project)["exports"]
        return Model(self, snapshot, report, exports).build()

    def mod_source(self, project: str):
        """The saved .c5m bytes, read through the same containment checks as every other input."""
        root, _ = self._project(project)
        return read_file(contained(root, f"mod/{project}/{project}.c5m"))

    # ----- private project notes: read-only Markdown directly inside <project>/docs/ (never exported) -----
    PROJECT_DOC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.md$")
    # Names that suggest secrets, credentials or backups are refused even when they are Markdown (tool policy).
    PROJECT_DOC_DENY = re.compile(r"secret|credential|passw|token|api[_.-]?key|private[_.-]?key|\.env|backup|\.bak|\.orig|~", re.I)
    MAX_PROJECT_DOC = 256 * 1024
    MAX_PROJECT_DOCS = 200

    def _project_doc_problem(self, folder, name):
        if not self.PROJECT_DOC.fullmatch(name) or self.PROJECT_DOC_DENY.search(name):
            return "not an allowlisted Markdown name"
        path = folder / name
        if is_link(path):
            return "link or junction"
        if not path.is_file():
            return "not a file"
        if path.stat().st_size > self.MAX_PROJECT_DOC:
            return f"larger than {self.MAX_PROJECT_DOC // 1024} KiB"
        return None

    def list_project_docs(self, project: str):
        """List readable private notes in the project's docs/ folder; only top-level .md files are considered."""
        root, _ = self._project(project)
        folder = contained(root, "docs")
        docs, skipped = [], []
        if folder.is_dir() and not is_link(folder):
            for name in sorted(os.listdir(folder))[:self.MAX_PROJECT_DOCS]:
                if not name.lower().endswith(".md"):
                    continue
                problem = self._project_doc_problem(folder, name)
                if problem:
                    skipped.append({"name": name, "reason": problem})
                else:
                    docs.append({"name": name, "bytes": (folder / name).stat().st_size})
        return {"project": project, "folder": "docs/", "docs": docs, "skipped": skipped,
                "note": "Private project notes, read-only. Only .md files directly in the project's docs/ folder are listed; "
                        "they are never exported or edited here."}

    def read_project_doc(self, project: str, name: str):
        """One private note as text. Exact-case name, no links, no subfolders, bounded size, UTF-8 only."""
        root, _ = self._project(project)
        folder = contained(root, "docs")
        if not isinstance(name, str) or not folder.is_dir() or is_link(folder) or name not in os.listdir(folder) \
                or self._project_doc_problem(folder, name):
            raise KenoError("not_found", "No readable private note of that name in this project's docs/ folder.")
        data = read_file(contained(folder, name))
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KenoError("bad_doc", "This note is not UTF-8 text.") from exc
        return {"project": project, "name": name, "text": text, "bytes": len(data), "sha256": sha(data)}
