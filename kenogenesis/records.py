"""Private evidence records: bounded plain-text observations linked to one project revision.

Records live in the project's private ``.kenogenesis/evidence`` folder, one new file per record, and
are never exported. A record states who observed what; it never marks a mod as engine verified.
"""

import json
import os
import re
import secrets
import time

from . import __version__
from .errors import KenoError
from .paths import contained, is_link

EVIDENCE_DIR = ".kenogenesis/evidence"
CATEGORIES = {"static": "Static checks", "browser": "Browser check", "packaging": "Packaging check",
              "game_user_reported": "Game observation (user reported)"}
RECORD_NAME = re.compile(r"^\d{10,22}-[0-9a-f]{8}\.json$")
MAX_RECORDS = 1000
LIMITS = {"summary": 200, "details": 4000, "reference": 200}
# Optional structured fields of a user-reported game observation (all plain text unless noted).
OBSERVATION = {"game_version": 40, "tester": 80, "class_played": 120, "opponents": 200, "map": 120, "outcome": 200}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Optional typed references: private plain-text labels (a filename, log name or note) with an optional SHA-256.
# Nothing is attached, opened or dereferenced; the label is the user's own description.
REFERENCE_KINDS = {"screenshot": "Screenshot", "log": "Log", "save": "Saved game", "report": "Report or notes",
                   "package": "Package or archive", "other": "Other"}
MAX_REFERENCES = 8


def _text(name, value, multiline, limit=None):
    limit = limit or LIMITS[name]
    if not isinstance(value, str):
        raise KenoError("bad_evidence", f"{name} must be text.", field=name)
    value = value.strip()
    if len(value) > limit:
        raise KenoError("bad_evidence", f"{name} is limited to {limit} characters.", field=name)
    allowed = "\n\t" if multiline else ""
    if any((ord(c) < 32 and c not in allowed) or ord(c) == 127 for c in value):
        raise KenoError("bad_evidence", f"{name} must be plain text{' without line breaks' if not multiline else ''}.", field=name)
    return value


def _observation(category, observation):
    """Validate optional structured fields of a user-reported game check; other categories take none.
    Empty fields are dropped, so an all-empty observation leaves the record in its original shape."""
    if observation is None:
        return None
    if not isinstance(observation, dict) or set(observation) - set(OBSERVATION) - {"turns", "reference_sha256"}:
        raise KenoError("bad_evidence", f"observation fields are: {', '.join([*OBSERVATION, 'turns', 'reference_sha256'])}.",
                        field="observation")
    out = {k: _text(k, observation[k], False, limit) for k, limit in OBSERVATION.items() if observation.get(k) not in (None, "")}
    out = {k: v for k, v in out.items() if v}
    turns = observation.get("turns")
    if turns not in (None, ""):
        if isinstance(turns, bool) or not isinstance(turns, int) or not 0 <= turns <= 100000:
            raise KenoError("bad_evidence", "turns is a whole number from 0 to 100000.", field="turns")
        out["turns"] = turns
    digest = observation.get("reference_sha256")
    if digest not in (None, ""):
        if not isinstance(digest, str) or not SHA256.fullmatch(digest.strip().lower()):
            raise KenoError("bad_evidence", "reference_sha256 is 64 hexadecimal characters.", field="reference_sha256")
        out["reference_sha256"] = digest.strip().lower()
    if out and category != "game_user_reported":
        raise KenoError("bad_evidence", "Structured game fields belong to user-reported game observations only.", field="observation")
    return out or None


def _references(references):
    """Validate up to MAX_REFERENCES typed references; empty rows are dropped, a hash without a label is refused."""
    if references is None:
        return []
    if not isinstance(references, list) or len(references) > MAX_REFERENCES:
        raise KenoError("bad_evidence", f"references is a list of at most {MAX_REFERENCES} entries.", field="references")
    out = []
    for i, ref in enumerate(references):
        if not isinstance(ref, dict) or set(ref) - {"kind", "label", "sha256"}:
            raise KenoError("bad_evidence", "Each reference has kind, label and an optional sha256.", field=f"references.{i}")
        try:
            label = _text("reference", ref.get("label", ""), False)
        except KenoError as exc:
            raise KenoError("bad_evidence", f"Reference {i + 1}: {exc.message}", field=f"references.{i}.label") from exc
        digest = ref.get("sha256")
        digest = "" if digest in (None, "") else digest
        if not label and not digest:
            continue
        if ref.get("kind") not in REFERENCE_KINDS:
            raise KenoError("bad_evidence", f"Reference kind is one of: {', '.join(REFERENCE_KINDS)}.", field=f"references.{i}.kind")
        if not label:
            raise KenoError("bad_evidence", "Describe the reference (a filename or short label).", field=f"references.{i}.label")
        entry = {"kind": ref["kind"], "kind_label": REFERENCE_KINDS[ref["kind"]], "label": label}
        if digest:
            if not isinstance(digest, str) or not SHA256.fullmatch(digest.strip().lower()):
                raise KenoError("bad_evidence", "A reference SHA-256 is 64 hexadecimal characters.", field=f"references.{i}.sha256")
            entry["sha256"] = digest.strip().lower()
        out.append(entry)
    return out


def build_record(project, revision, source_sha256, category, summary, details="", reference="", observation=None, references=None):
    if category not in CATEGORIES:
        raise KenoError("bad_evidence", f"Category is one of: {', '.join(CATEGORIES)}.", field="category")
    summary = _text("summary", summary, False)
    if not summary:
        raise KenoError("bad_evidence", "Give a short summary of what was observed.", field="summary")
    record = {"schema": 1, "project": project, "revision": revision, "source_sha256": source_sha256,
              "category": category, "category_label": CATEGORIES[category], "summary": summary,
              "details": _text("details", details, True), "reference": _text("reference", reference, False),
              "engine_verified": False, "tool_version": __version__,
              "note": "Recorded observation only. It is linked to this revision and does not verify game behavior."}
    typed = _references(references)
    if typed:
        record["references"] = typed
    fields = _observation(category, observation)
    if fields:
        record["observation"] = {**fields, "reported_by": "user",
                                 "note": "Reported by the user from their own play; KENOGENESIS did not run or observe the game."}
    return record


def write_record(root, record):
    """Create one new record file (exclusive create); existing records are never changed."""
    folder = contained(root, EVIDENCE_DIR)
    if folder.is_dir() and sum(1 for _ in folder.glob("*.json")) >= MAX_RECORDS:
        raise KenoError("evidence_limit", f"This project already holds {MAX_RECORDS} evidence records (tool policy).")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
    target = contained(root, f"{EVIDENCE_DIR}/{name}")
    record = {**record, "id": name[:-5], "recorded_ns": int(name.split("-")[0])}
    with target.open("xb") as stream:
        stream.write((json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return f"{EVIDENCE_DIR}/{name}"


def list_records(root, current_revision):
    folder = contained(root, EVIDENCE_DIR)
    out, skipped = [], []
    if folder.is_dir() and not is_link(folder):
        for path in sorted(folder.iterdir(), reverse=True)[:MAX_RECORDS]:
            if not RECORD_NAME.fullmatch(path.name) or is_link(path) or not path.is_file():
                skipped.append(path.name)
                continue
            try:
                if path.stat().st_size > 64 * 1024:
                    raise ValueError("record is larger than 64 KiB")
                record = json.loads(path.read_bytes().decode("utf-8"))
                if not isinstance(record, dict) or record.get("category") not in CATEGORIES:
                    raise ValueError("unrecognised record")
                record["engine_verified"] = False
                record["current"] = record.get("revision") == current_revision
                out.append(record)
            except (OSError, UnicodeError, ValueError) as exc:
                skipped.append(f"{path.name}: {exc}")
    return {"revision": current_revision, "records": out, "skipped": skipped, "categories": CATEGORIES,
            "reference_kinds": REFERENCE_KINDS, "max_references": MAX_REFERENCES,
            "note": "Evidence is private project metadata, excluded from exports. Records about older revisions "
                    "describe that revision only. No record marks a mod as engine verified."}
