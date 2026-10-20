"""Build a private reference catalog from local vanilla-reference .c5m files, with exact provenance.

Rows hold only what the files print: opener names, printed index comments, explicit commands and
their source location. Commented lines (such as untranslated "# fx" notes) are not imported, game
defaults are not modelled and duplicate names are kept as separate rows with their file order.
"""

import hashlib
import re

from . import __version__
from .errors import KenoError
from .parser import parse

RESERVED = {"kind", "name", "id", "opener", "printed_label", "id_source", "name_source", "name_ordinal",
            "name_count", "source_file", "source_line", "source_offset", "source_end", "statements", "multiline_commands"}
PRINTED_INDEX = re.compile(r"-?\d+")
FILE_VERSION = re.compile(r"v(\d+(?:\.\d+)+)", re.IGNORECASE)
MAX_SOURCES = 12


def _comment(data, codec, st):
    """Text of the comment that follows an opener on its own line, without the hash."""
    tail = data[st["code_end"]:st["end"]].decode(codec).strip()
    return tail[1:].strip() if tail.startswith("#") else None


def _string_spans(data, parsed):
    """Map each line that opens a string left unclosed to (closing line, end byte of that line).

    The parser reports every line with an odd quote count; pairing them in order recovers strings
    that continue over raw line breaks. The engine's handling of raw breaks is not verified here.
    """
    starts, offset = [], 3 if data.startswith(b"\xef\xbb\xbf") else 0
    codec = parsed["encoding"].replace("-sig", "")
    for raw in parsed["source"].splitlines(keepends=True):
        starts.append(offset)
        offset += len(raw.encode(codec))
    starts.append(offset)
    odd = [d["line"] for d in parsed["diagnostics"] if d["code"] == "quotes"]
    spans = {}
    for first, last in zip(odd[0::2], odd[1::2]):
        end = starts[last]
        while end > starts[last - 1] and data[end - 1:end] in (b"\n", b"\r"):
            end -= 1
        spans[first] = (last, end)
    return spans, len(odd) % 2 == 1


def _row(data, codec, filename, obj, spans):
    opener_st = obj["statements"][0]
    label = _comment(data, codec, opener_st)
    opener = obj["opener"]
    row = {"kind": obj["kind"], "name": obj["name"], "opener": opener}
    if opener.startswith("new"):
        if label is not None and PRINTED_INDEX.fullmatch(label):
            row["id"], row["id_source"] = int(label), "printed_comment"
        elif label:
            row["printed_label"] = label
    else:
        # select* openers name an existing entity by number; the printed comment is its label.
        if opener_st["args"] and PRINTED_INDEX.fullmatch(opener_st["args"][0]["value"]) and not opener_st["args"][0]["quoted"]:
            row["id"], row["id_source"] = int(opener_st["args"][0]["value"]), "argument"
        if label:
            row["printed_label"] = label
        if opener != "selectterr":
            # Selecting an existing class or ritual modifies it; keep it apart from definitions.
            row["kind"] = f"{obj['kind']}_selection"
        if row.get("id_source") == "argument" and label:
            row["name"], row["name_source"] = label, "printed_comment"
    row.update(source_file=filename, source_line=obj["line"], source_offset=obj["start"], source_end=obj["end"])
    statements, texts, multiline, until = [], [], [], 0
    for st in obj["statements"][1:]:
        if st["line"] <= until:
            continue  # Text inside a string that continues over lines, not a command.
        start = st["start"] + st["indent"]
        if st["line"] in spans:
            until, end = spans[st["line"]]
            texts.append(data[start:end].decode(codec))
            multiline.append(st["command"])
            continue
        statements.append(st)
        texts.append(data[start:st["code_end"]].decode(codec))
    counts = {}
    for command in [st["command"] for st in statements] + multiline:
        counts[command] = counts.get(command, 0) + 1
    names = [st for st in statements if st["command"] == "name" and len(st["args"]) == 1 and st["args"][0]["quoted"]]
    if opener == "selectterr" and len(names) == 1 and counts["name"] == 1:
        row["name"], row["name_source"] = names[0]["args"][0]["value"], "name_command"
    if not row["name"]:
        row["name"] = label or ""
    for st in statements:
        if counts[st["command"]] == 1 and len(st["args"]) == 1 and st["command"] not in RESERVED:
            row[st["command"]] = st["args"][0]["value"]
    if multiline:
        row["multiline_commands"] = multiline
    row["statements"] = texts
    return row


def build_catalog(sources, game_version, provenance):
    """Return (catalog, review) for [(filename, bytes)] without touching disk."""
    if not isinstance(game_version, str) or not re.fullmatch(r"\d+(?:\.\d+)+", game_version.strip()):
        raise KenoError("bad_catalog", "Give the game version the reference files describe, such as 5.22.", field="game_version")
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 2000:
        raise KenoError("bad_catalog", "Describe where the files came from (source, revision, license) in up to 2000 characters.", field="provenance")
    if not sources or len(sources) > MAX_SOURCES:
        raise KenoError("bad_catalog", f"Choose 1 to {MAX_SOURCES} reference .c5m files.", field="sources")
    game_version = game_version.strip()
    names = [name for name, _ in sources]
    if len({n.casefold() for n in names}) != len(names):
        raise KenoError("bad_catalog", "Each reference file must have a different name.", field="sources")
    rows, files, warnings = [], [], []
    for filename, data in sources:
        if not filename.lower().endswith(".c5m"):
            raise KenoError("bad_catalog", f"{filename}: reference files must be .c5m.", field="sources")
        parsed = parse(data)
        codec = parsed["encoding"].replace("-sig", "")
        spans, unpaired = _string_spans(data, parsed)
        file_rows = [_row(data, codec, filename, obj, spans) for obj in parsed["objects"] if obj["statements"]]
        kinds = {}
        for row in file_rows:
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        versions = sorted(set(FILE_VERSION.findall(filename)))
        if versions and versions != [game_version]:
            warnings.append(f"{filename} is labelled v{', v'.join(versions)} but the catalog is declared as game {game_version}.")
        if b"\x00" in data:
            warnings.append(f"{filename} contains NUL bytes; it may not be a text reference file.")
        if spans:
            lines = ", ".join(f"{a}-{b}" for a, (b, _) in list(spans.items())[:8])
            warnings.append(f"{filename}: {len(spans)} strings continue over raw line breaks (lines {lines}"
                            f"{', ...' if len(spans) > 8 else ''}); their text is kept verbatim in statements, not as fields. "
                            "The engine's reading of raw line breaks is not verified.")
        if unpaired:
            warnings.append(f"{filename}: a string is never closed; rows after it may contain description text as commands.")
        other = [d for d in parsed["diagnostics"] if d["code"] != "quotes"]
        for d in other[:20]:
            warnings.append(f"{filename} line {d['line']}: {d['message']}")
        if not file_rows:
            warnings.append(f"{filename} contains no recognised definitions.")
        files.append({"file": filename, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "encoding": parsed["encoding"], "rows": len(file_rows), "kinds": dict(sorted(kinds.items())),
                      "printed_versions": versions})
        rows.extend(file_rows)
    groups = {}
    for row in rows:
        groups.setdefault((row["kind"], row["name"]), []).append(row)
    duplicates = 0
    for group in groups.values():
        for ordinal, row in enumerate(group):
            row["name_ordinal"], row["name_count"] = ordinal, len(group)
        duplicates += len(group) > 1
    catalog = {"game_version": game_version, "provenance": provenance.strip(), "format": "kenogenesis.reference-catalog/1",
               "importer": {"tool": "KENOGENESIS", "version": __version__},
               "notes": ["Rows hold explicit commands printed in the reference files only; commented lines, defaults and "
                         "copied values are not resolved. name_ordinal is file order among rows of the same kind and name; "
                         "it is not proof of the engine's selection offset."],
               "sources": files, "rows": rows}
    review = {"game_version": game_version, "sources": files, "rows": len(rows), "duplicate_names": duplicates,
              "warnings": warnings}
    return catalog, review


def catalog_bytes(catalog):
    """Stable, line-per-row JSON so private catalogs stay diffable without a large indented file."""
    import json
    head = {k: v for k, v in catalog.items() if k != "rows"}
    lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in catalog["rows"]]
    text = json.dumps(head, ensure_ascii=False, indent=2)[:-2] + ',\n  "rows": [\n    ' + ",\n    ".join(lines) + "\n  ]\n}\n"
    return text.encode("utf-8")
