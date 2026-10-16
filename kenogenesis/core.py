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
from .commands import ASSET_ARGS, MANUAL, OPENERS, SCHEMAS, lookup
from .errors import KenoError
from .parser import check_arguments, decode, parse
from .paths import SLUG_RE, atomic_write_bytes, contained, exact_case_lookup, mod_relpath_problems, resolve_workspace

MAX_FILE = 16 * 1024 * 1024  # Tool policy, not a game limit.
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
        # An original flat test banner; no game assets or private artwork are copied.
        banner = bytearray(18)
        banner[2], banner[16], banner[17] = 2, 24, 32
        struct.pack_into("<HH", banner, 12, 256, 64)
        (mod / "banner.tga").write_bytes(banner + bytes((42, 24, 18)) * (256 * 64))
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

    def _snapshot(self, project, source_override=None, metadata_override=None):
        """Hash every declared input, including dependency assets and catalog, into a review revision."""
        root, meta = self._project(project)
        if metadata_override is not None:
            check_metadata(metadata_override, project)
            meta = metadata_override
        dependencies = meta.get("dependencies", [])
        if not isinstance(dependencies, list) or len(set(dependencies)) != len(dependencies) or project in dependencies or len(dependencies) > 32:
            raise KenoError("bad_dependencies", "Declare up to 32 unique direct dependency projects.")
        inputs, mods, catalog, captured = {}, [], None, {}
        catalog_issue = None
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
                raise KenoError("nested_dependencies", "List a flat dependency set; nested dependencies are not resolved.")
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
                proposed_catalog = json.loads(cat_data)
                if not isinstance(proposed_catalog, dict) or not isinstance(proposed_catalog.get("rows"), list) or not proposed_catalog.get("provenance") or not isinstance(proposed_catalog.get("game_version"), str):
                    raise KenoError("bad_catalog", "Catalog requires game_version, provenance and rows.")
                for row in proposed_catalog["rows"]:
                    if not isinstance(row, dict) or not isinstance(row.get("kind"), str) or not isinstance(row.get("name"), str):
                        raise KenoError("bad_catalog", "Each catalog row requires string kind and name fields.")
                catalog = proposed_catalog
            except (OSError, ValueError, KenoError) as exc:
                catalog_issue = f"Configured catalog is unavailable or invalid: {exc}"
        if any(sha(read_file(path)) != expected for path, expected in captured.items()):
            raise KenoError("inputs_changed", "Project inputs changed while reading; inspect again.")
        revision = sha(json.dumps(inputs, sort_keys=True).encode())
        return {"root": root, "meta": meta, "mods": mods, "catalog": catalog, "catalog_issue": catalog_issue,
                "revision": revision, "inputs": inputs}

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
        if catalog is None:
            return {"available": False, "note": snapshot["catalog_issue"] or "Vanilla references cannot be verified without a catalog."}
        return {"available": True, "game_version": catalog["game_version"],
                "provenance": catalog["provenance"], "sha256": snapshot["inputs"]["catalog"],
                "rows": len(catalog["rows"])}

    def lookup_command(self, command: str | None = None, context: str | None = None):
        return lookup(command, context)

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

    def _preview_result(self, project, snapshot, candidate):
        before = decode(snapshot["mods"][-1]["data"])[0]
        after = decode(candidate)[0]
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            fromfile=f"{project}.c5m", tofile=f"{project}.c5m"))
        return {"revision": snapshot["revision"], "candidate_sha256": sha(candidate), "diff": diff,
                "validation": self._validate(self._snapshot(project, candidate)), "written": False}

    def apply_patch(self, project: str, expected_revision: str, old: str, new: str):
        root, _ = self._project(project)
        with project_lock(root):
            snapshot = self._snapshot(project)
            self._check_revision(snapshot, expected_revision)
            candidate = self._candidate(snapshot, old, new)
            result = self._preview_result(project, snapshot, candidate)
            self._write_source(project, snapshot, candidate)
        result.update(written=True, revision=self._snapshot(project)["revision"])
        return result

    def _write_source(self, project, snapshot, candidate):
        self._check_revision(self._snapshot(project), snapshot["revision"])
        backups = contained(snapshot["root"], ".kenogenesis/backups")
        backups.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns()}-{secrets.token_hex(4)}.c5m"
        with contained(snapshot["root"], backups / name).open("xb") as stream:
            stream.write(snapshot["mods"][-1]["data"])
        atomic_write_bytes(contained(snapshot["root"], f"mod/{project}/{project}.c5m"), candidate)

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
            self._write_source(project, snapshot, candidate)
        result.update(written=True, revision=self._snapshot(project)["revision"])
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
                raise KenoError("bad_dependencies", "Use a flat list of up to 32 unique dependency slugs.")
            for dependency in meta["dependencies"]:
                self._project(dependency)
            if meta.get("catalog"):
                contained(self.workspace, meta["catalog"])
            if not isinstance(meta["declared_assets"], list) or not all(isinstance(name, str) for name in meta["declared_assets"]):
                raise KenoError("bad_assets", "declared_assets must be a list of relative filenames.")
            for name in meta["declared_assets"]:
                safe_asset(contained(root, f"mod/{project}"), name)
            candidate = self._snapshot(project, metadata_override=meta)
            if candidate["catalog_issue"]:
                raise KenoError("bad_catalog", candidate["catalog_issue"])
            self._check_revision(self._snapshot(project), expected_revision)
            diff = "".join(difflib.unified_diff(json_bytes(snapshot["meta"]).decode().splitlines(True),
                                                json_bytes(meta).decode().splitlines(True), fromfile="project.json", tofile="project.json"))
            if not preview:
                backup = contained(root, ".kenogenesis/backups")
                backup.mkdir(parents=True, exist_ok=True)
                (backup / f"{time.time_ns()}.json").write_bytes(json_bytes(snapshot["meta"]))
                atomic_write_bytes(contained(root, "project.json"), json_bytes(meta))
            return {"diff": diff, "written": not preview, "validation": self._validate(candidate),
                    "revision": snapshot["revision"] if preview else self._snapshot(project)["revision"]}

    def compatibility(self, project: str, baseline: str | None = None):
        snapshot = self._snapshot(project)
        report = self._validate(snapshot)
        priorities = []
        for mod in snapshot["mods"]:
            values = [st["args"][0]["value"] for st in mod["parsed"]["statements"] if st["command"] == "modprio" and st["args"]]
            priorities.append({"project": mod["slug"], "modprio": values[-1] if values else "5"})
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
            change_review = {"definition_order_risks": risks, "baseline_sha256": sha(read_file(baseline_path)),
                             "note": "Append-only comparison is a static warning, never proof of save compatibility."}
        return {"revision": snapshot["revision"], "declared_inputs": priorities,
                "diagnostics": [d for d in report["diagnostics"] if d["code"] in
                                ("overlapping_target", "ambiguous_name", "forward_reference", "reference", "ritual_school")],
                "change_review": change_review, "limitations": report["limitations"], "engine_verified": False}

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
                       "catalog": self._catalog_info(snapshot), "dependencies": snapshot["meta"]["dependencies"],
                       "files": [{"path": name, "sha256": sha(data), "bytes": len(data)} for name, data in sorted(payload.items())],
                       "archive_sha256": archive_sha, "validation": report,
                       "note": "Dependencies must be installed separately. Static checks only; not proof of game behavior."}
            manifest = contained(root, f"exports/{export_id}.manifest.json")
            with manifest.open("xb") as stream:
                stream.write(json_bytes(receipt))
            return {"export_id": export_id, "path": str(destination), "manifest": str(manifest),
                    "archive_sha256": archive_sha, "revision": snapshot["revision"],
                    "counts": report["counts"], "engine_verified": False}
