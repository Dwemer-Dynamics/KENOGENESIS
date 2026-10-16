"""Optional official-SDK stdio adapter; no protocol data is printed outside the SDK."""

import argparse
import functools
from .core import Kenogenesis, envelope
from .cli import OPERATIONS

READ_ONLY = {"list_projects", "project_view", "lookup_command", "search_game_data",
             "preview_patch", "preview_fields", "validate_mod", "compatibility"}


def wrapped(operation):
    """Retain each core method's signature so MCP exposes the same typed argument names."""
    @functools.wraps(operation)
    def call(**arguments):
        return envelope(operation, **arguments)
    return call


def build_server(core):
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        from .errors import KenoError
        raise KenoError("mcp_unavailable", "Install the optional MCP extra: pip install '.[mcp]'.") from exc
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
    build_server(Kenogenesis(args.workspace)).run(transport="stdio")
