"""Local CoE5 Steam Workshop staging: an existing reviewed export plus banner.png and coe5ws.txt.

Official layout (https://www.illwinter.com/coe5/coe5modding.html, "Minimal Mod for Steam Workshop"):
<slug>/<slug>.c5m with its ordinary icon, a square banner.png (256x256 recommended) and coe5ws.txt
holding Visibility="private" | "friends" | "public". The game uploads from its Mods screen
(right-click the mod, Upload mod to Steam Workshop). KENOGENESIS only writes a private local ZIP; it
never installs, uploads or publishes anything.

Stages live in the project's private ``.kenogenesis/workshop-stages`` folder, apart from ``exports/``,
so a stage receipt is never listed or used as an ordinary export manifest. The chosen export is
re-checked byte for byte against the current saved revision; its manifest and ZIP are never trusted.
"""

import base64
import binascii
import contextlib
import hashlib
import io
import json
import os
import re
import secrets
import time
import zipfile

from . import __version__
from .assets import read_png
from .errors import KenoError
from .paths import contained, exact_case_lookup, is_link

STAGE_DIR = ".kenogenesis/workshop-stages"
STAGE_ID = re.compile(r"^\d{10,22}-[0-9a-f]{8}$")
EXPORT_ID = STAGE_ID
VISIBILITY = ("private", "friends", "public")
WORKSHOP_FILES = ("banner.png", "coe5ws.txt")
# Tool policy bounds, not engine limits.
MAX_BANNER = 4 * 1024 * 1024
MAX_BUNDLE = 64 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_STAGES = 200
MAX_RECEIPT = 256 * 1024
RECOMMENDED_BANNER = 256
SOURCE_URL = "https://www.illwinter.com/coe5/coe5modding.html"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def coe5ws_text(visibility):
    if visibility not in VISIBILITY:
        raise KenoError("bad_visibility", "Visibility is private, friends or public.", field="visibility")
    return f'Visibility="{visibility}"\n'.encode("ascii")


def _display_name(value):
    """The chosen file's name, kept only for the review and receipt; it never names an output file."""
    name = value if isinstance(value, str) else ""
    name = "".join(c for c in name.replace("\\", "/").split("/")[-1] if c.isprintable())[:120]
    return name or "banner.png"


def check_banner(banner):
    """Decode the chosen PNG bytes, check structure and squareness; the bytes are copied unchanged."""
    if not isinstance(banner, dict) or not isinstance(banner.get("base64"), str):
        raise KenoError("bad_banner", "Choose a square PNG file for banner.png.", field="banner")
    if len(banner["base64"]) > (MAX_BANNER * 4) // 3 + 8:
        raise KenoError("bad_banner", f"The banner exceeds the {MAX_BANNER // (1024 * 1024)} MiB tool limit.", field="banner")
    try:
        data = base64.b64decode(banner["base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KenoError("bad_banner", "The banner contents are not valid base64.", field="banner") from exc
    if not data or len(data) > MAX_BANNER:
        raise KenoError("bad_banner", f"The banner must be 1 byte to {MAX_BANNER // (1024 * 1024)} MiB.", field="banner")
    try:
        header, _ = read_png(data)
    except ValueError as exc:
        raise KenoError("bad_banner", f"banner.png must be a valid PNG: {exc}", field="banner") from exc
    width, height = header["width"], header["height"]
    if width != height:
        raise KenoError("bad_banner", f"The Workshop banner must be square; this PNG is {width}x{height}.", field="banner")
    warnings = [] if width == RECOMMENDED_BANNER else [
        f"The CoE5 modding page suggests {RECOMMENDED_BANNER}x{RECOMMENDED_BANNER}; this banner is {width}x{height} "
        "and is staged unchanged (KENOGENESIS never resizes artwork)."]
    return data, {"filename": _display_name(banner.get("filename")), "bytes": len(data), "sha256": _sha(data),
                  "width": width, "height": height, "warnings": warnings}


def _export_files(root, export_id, kind, expected):
    """Read the export's payload (ZIP or folder) and require exactly the expected names and bytes."""
    found = {}
    if kind == "zip":
        path = contained(root, f"exports/{export_id}.zip")
        if is_link(path) or not path.is_file() or path.stat().st_size > MAX_BUNDLE:
            raise KenoError("export_unusable", "The chosen export ZIP is missing, linked or too large.")
        with path.open("rb") as stream:
            archive_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                names = [i.filename for i in infos]
                if len(infos) > MAX_ENTRIES or len(set(names)) != len(names) or set(names) != set(expected):
                    raise KenoError("export_mismatch", "The export ZIP's file list does not match the saved revision; export again.",
                                    unexpected=sorted(set(names) - set(expected))[:20], missing=sorted(set(expected) - set(names))[:20])
                for info in infos:
                    if info.is_dir() or info.file_size != len(expected[info.filename]):
                        raise KenoError("export_mismatch", f"{info.filename} differs from the saved revision; export again.")
                    found[info.filename] = archive.read(info)
        except zipfile.BadZipFile as exc:
            raise KenoError("export_mismatch", f"The export ZIP is unreadable: {exc}") from exc
        return found, archive_sha
    folder = contained(root, f"exports/{export_id}")
    if is_link(folder) or not folder.is_dir():
        raise KenoError("export_unusable", "The chosen export folder is missing or linked.")
    seen = []
    for current, dirs, files in os.walk(folder):
        for name in [*dirs, *files]:
            full = contained(folder, os.path.join(current, name))
            if is_link(full):
                raise KenoError("export_mismatch", "The export folder contains a link; export again.")
        seen.extend(os.path.relpath(os.path.join(current, f), folder).replace(os.sep, "/") for f in files)
        if len(seen) > MAX_ENTRIES:
            raise KenoError("export_mismatch", "The export folder holds too many files.")
    if set(seen) != set(expected):
        raise KenoError("export_mismatch", "The export folder's file list does not match the saved revision; export again.",
                        unexpected=sorted(set(seen) - set(expected))[:20], missing=sorted(set(expected) - set(seen))[:20])
    for name in seen:
        path, reason = exact_case_lookup(folder, name)
        if path is None or path.stat().st_size != len(expected[name]):
            raise KenoError("export_mismatch", f"{name} differs from the saved revision ({reason or 'size'}); export again.")
        found[name] = path.read_bytes()
    return found, None


def plan_stage(core, snapshot, export_id, banner, visibility="private"):
    """Pure review of one stage: verify the export against the saved revision, then list exact bundle bytes."""
    project, root = snapshot["meta"]["slug"], snapshot["root"]
    if not isinstance(export_id, str) or not EXPORT_ID.fullmatch(export_id):
        raise KenoError("not_found", "Choose an existing export of this project.", field="export_id")
    data = coe5ws_text(visibility)
    report = core._validate(snapshot)
    if not report["static_ok"]:
        raise KenoError("validation_failed", "Fix static errors, export again, then stage.", counts=report["counts"])
    mod = snapshot["mods"][-1]
    expected = {f"{project}/{project}.c5m": mod["data"], **{f"{project}/{name}": blob for name, blob in mod["assets"].items()}}
    if len(expected) > MAX_ENTRIES:
        raise KenoError("bundle_too_large", "The mod holds too many files to stage.")
    taken = {name.casefold(): name for name in expected}
    collisions = [{"file": f"{project}/{name}", "existing": taken[f"{project}/{name}".casefold()]}
                  for name in WORKSHOP_FILES if f"{project}/{name}".casefold() in taken]
    if collisions:
        raise KenoError("workshop_collision", "The mod payload already contains " + ", ".join(c["existing"] for c in collisions) +
                        ". KENOGENESIS will not overwrite it: rename that mod file (and its reference) and export again, or remove it "
                        "from declared export files.", collisions=collisions)
    manifest_path = contained(root, f"exports/{export_id}.manifest.json")
    if is_link(manifest_path) or not manifest_path.is_file():
        raise KenoError("not_found", "That export has no manifest; choose another export or export again.")
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise KenoError("export_unusable", "The export manifest is too large.")
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise KenoError("export_unusable", "The export manifest is not valid JSON.") from exc
    if not isinstance(manifest, dict) or manifest.get("tool") != "KENOGENESIS" or manifest.get("project") != project:
        raise KenoError("export_unusable", "Choose a KENOGENESIS export of this project.")
    if manifest.get("revision") != snapshot["revision"]:
        raise KenoError("export_stale", "That export is of an older revision. Export the saved revision first, then stage it.",
                        export_revision=manifest.get("revision"), actual_revision=snapshot["revision"])
    listed = [{"path": name, "sha256": _sha(blob), "bytes": len(blob)} for name, blob in sorted(expected.items())]
    if manifest.get("files") != listed or manifest.get("source_sha256") != _sha(mod["data"]):
        raise KenoError("export_mismatch", "The export manifest does not match the saved revision; export again.")
    archive = contained(root, f"exports/{export_id}.zip")
    kind = "zip" if archive.exists() else "folder"
    payload, archive_sha = _export_files(root, export_id, kind, expected)
    if manifest.get("archive_sha256") != archive_sha:
        raise KenoError("export_mismatch", "The export archive hash does not match its manifest; export again.")
    if any(_sha(payload[name]) != _sha(blob) for name, blob in expected.items()):
        raise KenoError("export_mismatch", "Export bytes differ from the saved revision; export again.")
    banner_bytes, banner_facts = check_banner(banner)
    files = {**expected, f"{project}/banner.png": banner_bytes, f"{project}/coe5ws.txt": data}
    if sum(len(b) for b in files.values()) > MAX_BUNDLE:
        raise KenoError("bundle_too_large", f"The staged bundle would exceed {MAX_BUNDLE // (1024 * 1024)} MiB (tool policy).")
    roles = {f"{project}/banner.png": "workshop banner (chosen file, unchanged)", f"{project}/coe5ws.txt": "workshop visibility"}
    return {"project": project, "revision": snapshot["revision"], "source_sha256": _sha(mod["data"]),
            "export": {"export_id": export_id, "format": kind, "archive_sha256": archive_sha,
                       "manifest_sha256": _sha(manifest_bytes), "created_ns": int(export_id.split("-")[0])},
            "visibility": visibility, "coe5ws_txt": data.decode("ascii"), "banner": banner_facts,
            "files": [{"path": name, "bytes": len(blob), "sha256": _sha(blob), "role": roles.get(name, "export payload")}
                      for name, blob in sorted(files.items())],
            "blobs": files, "validation_counts": report["counts"]}


NOTES = ["Staging writes a private local ZIP only. It does not upload, install or publish anything.",
         "To publish later (separately authorized), extract the bundle into the game's mods folder, then in CoE5 open Mods, "
         "right-click the mod and choose Upload mod to Steam Workshop.",
         "The bundle holds the reviewed export plus banner.png and coe5ws.txt. Private receipts, catalogs, snapshots, "
         "evidence and backups are never included.",
         "Static checks only; staging is not proof that the mod loads or plays."]


def public_plan(plan, written=False):
    out = {k: v for k, v in plan.items() if k != "blobs"}
    out.update(written=written, uploaded=False, engine_verified=False, source=SOURCE_URL, notes=NOTES,
               before_revision=plan["revision"], source_changed=False)
    return out


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, blob in sorted(files.items()):
            archive.writestr(name, blob)
    return buffer.getvalue()


def write_stage(root, plan):
    """Create one NEW bundle and receipt; any failure removes everything this call created."""
    folder = contained(root, STAGE_DIR)
    if folder.is_dir() and sum(1 for _ in folder.glob("*.receipt.json")) >= MAX_STAGES:
        raise KenoError("stage_limit", f"This project already holds {MAX_STAGES} Workshop stages (tool policy).")
    made, created = [], []
    try:
        for parent in (contained(root, ".kenogenesis"), folder):
            if not parent.exists():
                parent.mkdir()
                made.append(parent)
            elif is_link(parent) or not parent.is_dir():
                raise KenoError("symlink_rejected", "The private staging folder is not a plain folder.")
        stage_id = f"{time.time_ns()}-{secrets.token_hex(4)}"
        bundle = _zip_bytes(plan["blobs"])
        with zipfile.ZipFile(io.BytesIO(bundle)) as check:
            if {n: _sha(check.read(n)) for n in check.namelist()} != {n: _sha(b) for n, b in plan["blobs"].items()}:
                raise KenoError("stage_failed", "The staged ZIP did not read back as reviewed.")
        partial = contained(root, f"{STAGE_DIR}/.{stage_id}.zip.partial")
        final = contained(root, f"{STAGE_DIR}/{stage_id}.zip")
        receipt_path = contained(root, f"{STAGE_DIR}/{stage_id}.receipt.json")
        with partial.open("xb") as stream:
            created.append(partial)
            stream.write(bundle)
            stream.flush()
            os.fsync(stream.fileno())
        if final.exists() or receipt_path.exists():
            raise KenoError("dest_exists", "A stage with this id already exists; nothing was overwritten.")
        # Publish without replacement on every platform; rename can overwrite on POSIX.
        os.link(partial, final)
        created.append(final)
        partial.unlink()
        created.remove(partial)
        receipt = {"schema": 1, "kind": "coe5_workshop_stage", "tool": "KENOGENESIS", "tool_version": __version__,
                   "stage_id": stage_id, "created_ns": int(stage_id.split("-")[0]),
                   **{k: v for k, v in public_plan(plan, True).items() if k not in ("notes", "before_revision", "source_changed")},
                   "bundle": f"{stage_id}.zip", "bundle_sha256": _sha(bundle), "bundle_bytes": len(bundle),
                   "note": "Private staging receipt; not an export manifest and not part of the bundle. Nothing was uploaded."}
        with receipt_path.open("xb") as stream:
            created.append(receipt_path)
            stream.write(_json_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        return receipt
    except BaseException:
        for path in reversed(created):
            with contextlib.suppress(OSError):
                path.unlink()
        for parent in reversed(made):
            with contextlib.suppress(OSError):
                parent.rmdir()
        raise


def _receipt(root, stage_id):
    path = contained(root, f"{STAGE_DIR}/{stage_id}.receipt.json")
    if is_link(path) or not path.is_file():
        raise KenoError("not_found", "Unknown Workshop stage.")
    if path.stat().st_size > MAX_RECEIPT:
        raise ValueError("receipt is larger than 256 KiB")
    receipt = json.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(receipt, dict) or receipt.get("kind") != "coe5_workshop_stage" or receipt.get("stage_id") != stage_id:
        raise ValueError("unrecognised receipt")
    return receipt, path


def _bundle_state(root, stage_id, receipt):
    path = contained(root, f"{STAGE_DIR}/{stage_id}.zip")
    if is_link(path) or not path.is_file():
        return "missing", None
    if path.stat().st_size > MAX_BUNDLE + 1024 * 1024:
        return "modified", None
    data = path.read_bytes()
    return ("ok" if _sha(data) == receipt.get("bundle_sha256") else "modified"), data


def list_stages(root, current_revision):
    """Read stage receipts and check each bundle hash; never creates folders or files."""
    folder = contained(root, STAGE_DIR)
    out, skipped = [], []
    if folder.is_dir() and not is_link(folder):
        for path in sorted(folder.glob("*.receipt.json"), reverse=True)[:MAX_STAGES]:
            stage_id = path.name[:-len(".receipt.json")]
            if not STAGE_ID.fullmatch(stage_id):
                skipped.append(path.name)
                continue
            try:
                receipt, _ = _receipt(root, stage_id)
                status, _ = _bundle_state(root, stage_id, receipt)
                out.append({k: receipt.get(k) for k in ("stage_id", "created_ns", "revision", "source_sha256", "visibility",
                                                         "banner", "files", "export", "bundle_sha256", "bundle_bytes")}
                           | {"bundle_status": status, "current": receipt.get("revision") == current_revision,
                              "uploaded": False, "engine_verified": False})
            except (OSError, UnicodeError, ValueError, KenoError) as exc:
                skipped.append(f"{path.name}: {exc}")
    return {"revision": current_revision, "stages": sorted(out, key=lambda s: s.get("created_ns") or 0, reverse=True),
            "skipped": skipped, "visibility_options": list(VISIBILITY), "source": SOURCE_URL, "notes": NOTES}


def stage_artifact(root, project, stage_id, kind):
    """Bytes of a stage bundle (only while it still matches its receipt) or its receipt, for download."""
    if not isinstance(stage_id, str) or not STAGE_ID.fullmatch(stage_id) or kind not in ("archive", "receipt"):
        raise KenoError("not_found", "Unknown Workshop stage.")
    try:
        receipt, path = _receipt(root, stage_id)
    except (OSError, UnicodeError, ValueError) as exc:
        raise KenoError("not_found", f"The stage receipt is unreadable: {exc}") from exc
    if kind == "receipt":
        return path.read_bytes(), f"{project}-workshop-{stage_id}.receipt.json"
    status, data = _bundle_state(root, stage_id, receipt)
    if status != "ok":
        raise KenoError("not_found", f"The staged bundle is {status}; stage again from a fresh export.")
    return data, f"{project}-workshop-{stage_id}.zip"
