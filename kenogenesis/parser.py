"""Lossless line-indexed CoE5 inspection; edits use byte spans, not serialization."""

import re
from .commands import OPENERS, SCHEMAS

TOKEN = re.compile(r'"[^"\r\n]*"|[^\s"#]+')


def decode(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig", 3
    try:
        return data.decode("utf-8"), "utf-8", 0
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1", 0


def parse(data):
    """Retain original bytes, comments and offsets while inspecting supported contexts."""
    text, encoding, bom = decode(data)
    statements, objects, diagnostics = [], [], []
    active, offset = None, bom
    for number, raw in enumerate(text.splitlines(keepends=True), 1):
        line = raw.rstrip("\r\n")
        # A hash outside quotes begins a comment; quoted hash behavior needs engine confirmation.
        quoted = False
        comment = len(line)
        for i, char in enumerate(line):
            if char == '"':
                quoted = not quoted
            if char == "#" and not quoted:
                comment = i
                break
        code = line[:comment]
        tokens = list(TOKEN.finditer(code))
        if code.count('"') % 2:
            diagnostics.append({"severity": "error", "code": "quotes", "line": number,
                                "message": "Unclosed string; multiline syntax is not supported by this parser."})
        if tokens:
            command = tokens[0].group()
            args = [{"value": t.group()[1:-1] if t.group().startswith('"') else t.group(),
                     "quoted": t.group().startswith('"')} for t in tokens[1:]]
            if command in OPENERS:
                if active is not None:
                    active["end"] = offset
                active = {"index": len(objects), "kind": OPENERS[command], "opener": command,
                          "name": args[0]["value"] if args else "", "line": number,
                          "start": offset, "end": len(data), "statements": []}
                objects.append(active)
            context = active["kind"] if active else "global"
            spec = SCHEMAS.get(("global", command)) or SCHEMAS.get((context, command))
            st = {"command": command, "args": args, "line": number, "context": context,
                  "start": offset, "end": offset + len(raw.encode(encoding.replace("-sig", ""))),
                  "code_end": offset + len(code.rstrip().encode(encoding.replace("-sig", ""))),
                  "indent": len(code[:len(code) - len(code.lstrip())].encode(encoding.replace("-sig", ""))), "verified": spec is not None,
                  "object": active["index"] if active else None}
            statements.append(st)
            if active:
                active["statements"].append(st)
                if command == "setclassname" and context == "class" and args:
                    active["name"] = args[0]["value"]
            if command == "endevent":
                if active:
                    active["end"] = st["end"]
                active = None
        offset += len(raw.encode(encoding.replace("-sig", "")))
    return {"encoding": encoding, "source": text, "statements": statements,
            "objects": objects, "diagnostics": diagnostics}


def check_arguments(statement, spec):
    args, signatures = statement["args"], spec["args"]
    minimum = sum(not arg.endswith("?") for arg in signatures)
    if not minimum <= len(args) <= len(signatures):
        return f"Expected {minimum}..{len(signatures)} arguments, received {len(args)}."
    for arg, signature in zip(args, signatures):
        kind, *bounds = signature.rstrip("?").split(":")
        if kind == "s" and not arg["quoted"]:
            return "Expected a quoted string."
        if kind == "i" or (kind == "r" and not arg["quoted"]):
            if arg["quoted"] or not re.fullmatch(r"-?\d+", arg["value"]):
                return "Expected an integer."
            if bounds and not int(bounds[0]) <= int(arg["value"]) <= int(bounds[1]):
                return f"Value outside documented range {bounds[0]}..{bounds[1]}."
    return None
