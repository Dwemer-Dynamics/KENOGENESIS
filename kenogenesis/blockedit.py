"""Exact-span block edits: typed line changes become byte splices of the saved source.

Nothing here serializes a mod. Every change names one statement (by line and its current text) or
an insertion point; untouched bytes, comments, unknown commands, encoding and newlines are kept.
The caller (core.Kenogenesis) owns revision checks, locking, backups and the write itself.
"""

import json
import re

from .commands import KNOWN_COMMANDS, OPENERS, SCHEMAS, manual_entry
from .errors import KenoError
from .parser import check_arguments, parse

NAME_RE = re.compile(r"^[+-]?[a-z][a-z0-9_]{0,47}$")
FIELD_LOCKED = {"copystats", "copyspr", "copyritual", "clearweapons", "clearspec", "clearmove", "clearrec",
                "clearstartunits", "clearstartterr", "clearritspec", "clearfort", "clearwspec"}
MAX_CHANGES = 200


def format_line(command, arguments):
    if not isinstance(command, str) or not NAME_RE.fullmatch(command):
        raise KenoError("bad_command", "Commands are lowercase words (letters, digits, underscore).", field="command")
    if not isinstance(arguments, list) or len(arguments) > 12:
        raise KenoError("bad_arguments", "Arguments must be a list of at most 12 values.")
    parts = [command]
    for value in arguments:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise KenoError("bad_arguments", "Arguments must be strings or integers.")
        if isinstance(value, str):
            if len(value) > 4000 or any(c in value for c in ('"', "\\", "#")) or any(ord(c) < 32 for c in value):
                raise KenoError("bad_arguments", "Text must contain no quotes, backslashes, hash signs or line breaks.")
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts)


def _code(data, st, codec):
    return data[st["start"] + st["indent"]:st["code_end"]].decode(codec)


def _check(line, context, codec):
    """Curated commands get their documented argument check; others only the syntax checks above."""
    st = parse(line.encode(codec))["statements"][0]
    spec = SCHEMAS.get(("global", st["command"])) or SCHEMAS.get((context, st["command"]))
    if spec:
        error = check_arguments(st, spec)
        if error:
            raise KenoError("bad_arguments", f"{st['command']}: {error}", field=st["command"])
    return spec


def _allowed_in(context, command):
    if command in OPENERS or command == "endevent":
        raise KenoError("structure_change", f"{command} starts or ends a block; use New block or Remove block.", field=command)
    entry = manual_entry(context, command)
    is_global = ("global", command) in SCHEMAS or (entry or {}).get("context") == "global"
    if context != "global" and is_global:
        raise KenoError("wrong_context", f"{command} is a mod-wide command, not a {context} command.", field=command)
    if context == "global" and not is_global and command in KNOWN_COMMANDS:
        raise KenoError("wrong_context", f"{command} belongs inside a block, not in the mod-wide commands.", field=command)


def candidate(parsed, data, object_index, changes, mode="edit", opener=None, before=None):
    """Return (candidate bytes, change summary, new object index or None).

    A new block is appended, or inserted before block ``before`` so that it precedes the definitions that use it.
    """
    codec = parsed["encoding"].replace("-sig", "")
    if parsed["diagnostics"]:
        raise KenoError("source_edit_required", "Fix parser errors in the source before using block edits.")
    if not isinstance(changes, list) or len(changes) > MAX_CHANGES:
        raise KenoError("bad_changes", f"Send a list of at most {MAX_CHANGES} changes.")
    newline = "\r\n" if b"\r\n" in data else "\n"
    summary = []
    if mode == "new":
        return _new_block(parsed, data, codec, newline, changes, opener, before)
    if before is not None:
        raise KenoError("bad_changes", "insert_before applies to new blocks only.")
    if object_index == -1:
        obj = {"kind": "global", "opener": None, "statements": [s for s in parsed["statements"] if s["object"] is None],
               "line": 0}
        context = "global"
    else:
        if not isinstance(object_index, int) or isinstance(object_index, bool) or not 0 <= object_index < len(parsed["objects"]):
            raise KenoError("bad_object", "Choose a block from the current project view.")
        obj = parsed["objects"][object_index]
        context = obj["kind"]
    statements = obj["statements"]
    by_line = {st["line"]: st for st in statements}
    if mode == "delete":
        if changes:
            raise KenoError("bad_changes", "Removing a block takes no line changes.")
        if object_index == -1:
            raise KenoError("bad_object", "Mod-wide commands are not a removable block.")
        first, last = statements[0], statements[-1]
        cut = data[:first["start"]] + data[last["end"]:]
        return cut, [{"op": "remove_block", "command": obj["opener"], "line": obj["line"],
                      "before": _code(data, first, codec), "after": None}], None
    if mode != "edit":
        raise KenoError("bad_mode", "Mode is edit, new or delete.")
    splices, touched = [], set()
    body = [st for st in statements if st["command"] not in OPENERS]
    indent = data[body[-1]["start"]:body[-1]["start"] + body[-1]["indent"]].decode(codec) if body else ""
    if statements:
        tail = statements[-1]
        insert_at = tail["end"]
        lead = "" if data[:insert_at].endswith(b"\n") or insert_at == 0 else newline
    else:
        # Mod-wide commands with none present yet: insert at the top of the file, after a BOM.
        insert_at, lead = (3 if data.startswith(b"\xef\xbb\xbf") else 0), ""
    after_opener = statements[0]["end"] if statements and statements[0]["command"] in OPENERS else insert_at

    def insert(position, line, prefix=""):
        splices.append((position, position, (prefix + indent + line + newline).encode(codec), len(splices)))

    for raw in changes:
        if not isinstance(raw, dict):
            raise KenoError("bad_changes", "Each change is an object.")
        op = raw.get("op")
        if op in ("set", "unset"):
            command = raw.get("command")
            spec = SCHEMAS.get((context, command)) or (SCHEMAS.get(("global", command)) if context == "global" else None)
            if spec is None or spec["repeat"] or command in OPENERS or command in FIELD_LOCKED:
                raise KenoError("source_edit_required", f"{command}: use a line change for this command.", field=command)
            matches = [st for st in statements if st["command"] == command]
            if len(matches) > 1:
                raise KenoError("ambiguous_field", f"{command} appears {len(matches)} times; resolve it in the line editor.", field=command)
            if matches and any(st["command"] in ("copystats", "copyspr", "copyritual") for st in statements[statements.index(matches[0]) + 1:]):
                raise KenoError("reset_after_field", f"A later copy command overwrites {command}; edit the source instead.", field=command)
            if op == "unset":
                if matches:
                    st = matches[0]
                    if st["line"] in touched:
                        raise KenoError("bad_changes", f"Line {st['line']} is changed twice.")
                    touched.add(st["line"])
                    splices.append((st["start"], st["end"], b"", len(splices)))
                    summary.append({"op": "remove", "command": command, "line": st["line"], "before": _code(data, st, codec), "after": None})
                continue
            line = format_line(command, raw.get("arguments", []))
            _check(line, context, codec)
            if matches:
                st = matches[0]
                before = _code(data, st, codec)
                if before == line:
                    continue
                if st["line"] in touched:
                    raise KenoError("bad_changes", f"Line {st['line']} is changed twice.")
                touched.add(st["line"])
                splices.append((st["start"] + st["indent"], st["code_end"], line.encode(codec), len(splices)))
                summary.append({"op": "change", "command": command, "line": st["line"], "before": before, "after": line})
            else:
                position = after_opener if command == "setclassname" and obj["opener"] == "newclass" else insert_at
                insert(position, line, lead if position == insert_at else "")
                summary.append({"op": "add", "command": command, "line": None, "before": None, "after": line})
        elif op == "add":
            command = raw.get("command")
            _allowed_in(context, command)
            line = format_line(command, raw.get("arguments", []))
            _check(line, context, codec)
            insert(insert_at, line, lead)
            summary.append({"op": "add", "command": command, "line": None, "before": None, "after": line})
        elif op in ("replace", "remove"):
            st = by_line.get(raw.get("line"))
            if st is None:
                raise KenoError("line_changed", f"Line {raw.get('line')} is not a command in this block any more.", line=raw.get("line"))
            before = _code(data, st, codec)
            if raw.get("was") != before:
                raise KenoError("line_changed", f"Line {st['line']} changed after this change was drafted; review it again.",
                                line=st["line"], actual=before)
            if st["command"] in OPENERS:
                raise KenoError("structure_change", "The opening line selects the block; remove the whole block instead.")
            if st["line"] in touched:
                raise KenoError("bad_changes", f"Line {st['line']} is changed twice.")
            touched.add(st["line"])
            if op == "remove":
                splices.append((st["start"], st["end"], b"", len(splices)))
                summary.append({"op": "remove", "command": st["command"], "line": st["line"], "before": before, "after": None})
            else:
                command = raw.get("command") or st["command"]
                _allowed_in(context, command)
                line = format_line(command, raw.get("arguments", []))
                _check(line, context, codec)
                if line == before:
                    continue
                splices.append((st["start"] + st["indent"], st["code_end"], line.encode(codec), len(splices)))
                summary.append({"op": "change", "command": command, "line": st["line"], "before": before, "after": line})
        else:
            raise KenoError("bad_changes", "Change op is set, unset, add, replace or remove.")
    out = data
    # Apply from the end so earlier offsets stay valid; equal insertion points keep request order.
    for start, end, text, _ in sorted(splices, key=lambda x: (x[0], x[3]), reverse=True):
        out = out[:start] + text + out[end:]
    return out, summary, object_index


def _new_block(parsed, data, codec, newline, changes, opener, before=None):
    if not isinstance(opener, dict) or opener.get("command") not in OPENERS:
        raise KenoError("bad_opener", "Choose how the new block opens (newmonster, newclass, selectterr ...).", field="opener")
    command = opener["command"]
    context = OPENERS[command]
    lines = [format_line(command, opener.get("arguments", []))]
    _check(lines[0], "global", codec)
    summary = [{"op": "add", "command": command, "line": None, "before": None, "after": lines[0]}]
    ordered = sorted(changes, key=lambda c: 0 if isinstance(c, dict) and c.get("command") == "setclassname" else 1)
    for raw in ordered:
        if not isinstance(raw, dict) or raw.get("op") not in ("add", "set"):
            raise KenoError("bad_changes", "A new block takes add or set changes only.")
        cmd = raw.get("command")
        _allowed_in(context, cmd)
        line = format_line(cmd, raw.get("arguments", []))
        _check(line, context, codec)
        lines.append(line)
        summary.append({"op": "add", "command": cmd, "line": None, "before": None, "after": line})
    if context == "event":
        lines.append("endevent")
    if before is not None:
        if not isinstance(before, int) or isinstance(before, bool) or not 0 <= before < len(parsed["objects"]):
            raise KenoError("bad_object", "insert_before must name a block from the current project view.", field="insert_before")
        position = parsed["objects"][before]["start"]
        # Keep a comment written directly above the target block attached to it.
        while position > 0:
            prev_start = data.rfind(b"\n", 0, position - 1) + 1
            line = data[prev_start:position].decode(codec).strip()
            if not line.startswith("#"):
                break
            position = prev_start
        if position < 3 and data.startswith(b"\xef\xbb\xbf"):
            position = 3
        head = data[:position]
        lead = "" if position <= 3 or head.endswith((b"\n\n", b"\n\r\n")) else newline
        block = (lead + newline.join(lines) + newline + newline).encode(codec)
        return data[:position] + block + data[position:], summary, before
    text = data.decode(codec) if data else ""
    prefix = "" if not text or text.endswith(newline) else newline
    if text.strip():
        prefix += newline
    block = (prefix + newline.join(lines) + newline).encode(codec)
    return data + block, summary, len(parsed["objects"])
