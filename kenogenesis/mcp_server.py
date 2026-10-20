"""Optional official-SDK stdio adapter; no protocol data is printed outside the SDK."""

import argparse
import functools
import sys
import shlex
from .core import Kenogenesis, envelope
from .cli import OPERATIONS

READ_ONLY = {"list_projects", "project_view", "lookup_command", "search_game_data",
             "preview_patch", "preview_fields", "validate_mod", "compatibility",
             "preview_block_edit", "preview_import_upload", "list_exports", "preview_art_upload",
             "preview_catalog_import", "project_model", "compare_units", "design_report",
             "list_evidence", "preview_catalog_snapshot", "preview_workshop_stage", "list_workshop_stages",
             "compare_classes", "list_project_docs", "read_project_doc", "catalog_page", "catalog_entry"}


def missing_sdk_message():
    """A stderr diagnostic naming the interpreter that lacks the optional SDK; nothing is installed automatically."""
    executable = "'" + sys.executable.replace("'", "''") + "'" if sys.platform == "win32" else shlex.quote(sys.executable)
    install = ("& " if sys.platform == "win32" else "") + executable + " -m pip install '.[mcp]'"
    return "\n".join([
        "KENOGENESIS MCP needs the optional 'mcp' package (mcp>=1.20,<2), which this Python does not have:",
        f"  {sys.executable}",
        "Install the optional extra into that interpreter from the KENOGENESIS folder, for example:",
        f"  {install}",
        "The browser and command line work without it."])


def wrapped(operation):
    """Retain each core method's signature so MCP exposes the same typed argument names."""
    @functools.wraps(operation)
    def call(**arguments):
        return envelope(operation, **arguments)
    return call


def build_server(core):
    # ImportError propagates so each entry point reports missing_sdk_message() on stderr, never on the protocol stream.
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    server = FastMCP("KENOGENESIS", instructions=(
        "Local CoE5 authoring. Inspect project_view, research lookup_command, preview, then apply with "
        "the same expected_revision. Preserve unknown source. Validate and export the reviewed revision. "
        "Unknown references are unverified, not necessarily missing. Static success is not in-game proof. "
        "Do not publish private projects, assets or catalogs. Use stderr for diagnostics."))
    for name in OPERATIONS:
        operation = getattr(core, name)
        server.tool(name=name, annotations=ToolAnnotations(readOnlyHint=name in READ_ONLY,
                    destructiveHint=False, openWorldHint=False))(wrapped(operation))
    return server


def main():
    parser = argparse.ArgumentParser(description="KENOGENESIS MCP stdio server")
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        server = build_server(Kenogenesis(args.workspace))
    except ImportError:
        print(missing_sdk_message(), file=sys.stderr)
        raise SystemExit(3)
    server.run(transport="stdio")
