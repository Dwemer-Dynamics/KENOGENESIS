"""Thin CLI adapter; all authoring behavior lives in the shared core."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import Kenogenesis, envelope

OPERATIONS = ("list_projects", "create_project", "import_project", "build_example", "project_view", "lookup_command",
              "search_game_data", "preview_patch", "apply_patch", "preview_fields", "apply_fields",
              "configure_project", "validate_mod", "compatibility", "export_mod",
              "preview_block_edit", "apply_block_edit", "preview_import_upload", "import_upload", "list_exports",
              "preview_art_upload", "apply_art_upload", "preview_catalog_import", "apply_catalog_import",
              "project_model", "compare_units", "design_report", "list_evidence", "record_evidence",
              "preview_catalog_snapshot", "apply_catalog_snapshot", "preview_workshop_stage", "stage_workshop_bundle",
              "list_workshop_stages", "compare_classes", "list_project_docs", "read_project_doc", "catalog_page", "catalog_entry")


def main(argv=None):
    parser = argparse.ArgumentParser(description="KENOGENESIS — local CoE5 mod authoring")
    parser.add_argument("--version", action="version", version=f"KENOGENESIS {__version__}")
    parser.add_argument("--workspace", required=True, help="Existing directory for private local projects")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON (also the default for operations)")
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run", help="Call a core operation using JSON arguments")
    run.add_argument("operation", choices=OPERATIONS)
    run.add_argument("--args", default="{}", help="JSON object; use --args-file for multiline requests")
    run.add_argument("--args-file", help="Read UTF-8 JSON arguments from a local file")
    project = subs.add_parser("project")
    project.add_argument("action", choices=("create", "inspect", "list", "import"))
    project.add_argument("slug", nargs="?")
    project.add_argument("--source")
    project.add_argument("--target-version")
    example = subs.add_parser("example", help="Create an independent small class prototype in a fresh project")
    example.add_argument("--slug", default="proving_ground")
    example.add_argument("--target-version")
    for command in ("validate", "compatibility", "export"):
        child = subs.add_parser(command)
        child.add_argument("project")
        if command == "export":
            child.add_argument("--revision", required=True)
            child.add_argument("--format", choices=("zip", "folder"), default="zip")
        if command == "compatibility":
            child.add_argument("--baseline")
    catalog = subs.add_parser("catalog", help="Review or save a private catalog built from local reference .c5m files")
    catalog.add_argument("action", choices=("import",))
    catalog.add_argument("project")
    catalog.add_argument("--revision", required=True)
    catalog.add_argument("--name", required=True, help="Catalog file stem under <workspace>/catalogs/")
    catalog.add_argument("--game-version", required=True, help="Game version the reference files describe")
    catalog.add_argument("--provenance", required=True, help="Source, revision and license of the reference files")
    catalog.add_argument("--source", action="append", required=True, help="A local reference .c5m (repeatable)")
    catalog.add_argument("--apply", action="store_true", help="Save after review; the default only previews")
    workshop = subs.add_parser("workshop", help="Review or save a private CoE5 Workshop staging ZIP from an existing export (never uploads)")
    workshop.add_argument("action", choices=("preview", "stage", "list"))
    workshop.add_argument("project")
    workshop.add_argument("--revision")
    workshop.add_argument("--export", help="Export id of the saved revision")
    workshop.add_argument("--banner", help="A local square PNG copied unchanged as banner.png")
    workshop.add_argument("--visibility", choices=("private", "friends", "public"), default="private")
    commands = subs.add_parser("commands")
    commands.add_argument("name", nargs="?")
    commands.add_argument("--context")
    commands.add_argument("--query", help="Match command names or manual summaries")
    commands.add_argument("--status", choices=("curated", "documented"), help="curated entries have argument checks")
    commands.add_argument("--limit", type=int, default=200)
    serve = subs.add_parser("serve")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--open-browser", action="store_true", help="Open the loopback address after the server binds")
    subs.add_parser("mcp")
    args = parser.parse_args(argv)
    try:
        core = Kenogenesis(args.workspace)
        if args.command == "serve":
            from .webserver import serve
            serve(core, args.port, open_browser=args.open_browser)
            return 0
        if args.command == "mcp":
            from .mcp_server import build_server, missing_sdk_message
            try:
                server = build_server(core)
            except ImportError:
                # stdout belongs to the MCP protocol; the diagnostic goes to stderr only.
                print(missing_sdk_message(), file=sys.stderr)
                return 3
            server.run(transport="stdio")
            return 0
        if args.command == "run":
            params = json.loads(Path(args.args_file).read_text("utf-8-sig") if args.args_file else args.args)
            if not isinstance(params, dict):
                parser.error("Arguments must be a JSON object")
            result = envelope(getattr(core, args.operation), **params)
        elif args.command == "project":
            if args.action == "list":
                result = envelope(core.list_projects)
            elif args.action == "create":
                result = envelope(core.create_project, slug=args.slug, target_version=args.target_version)
            elif args.action == "import":
                result = envelope(core.import_project, slug=args.slug, source=args.source, target_version=args.target_version)
            else:
                result = envelope(core.project_view, project=args.slug)
        elif args.command == "example":
            result = envelope(core.build_example, slug=args.slug, target_version=args.target_version)
        elif args.command == "catalog":
            operation = core.apply_catalog_import if args.apply else core.preview_catalog_import
            result = envelope(operation, project=args.project, expected_revision=args.revision, game_version=args.game_version,
                              provenance=args.provenance, name=args.name, paths=args.source)
        elif args.command == "workshop":
            if args.action == "list":
                result = envelope(core.list_workshop_stages, project=args.project)
            else:
                import base64
                if not (args.revision and args.export and args.banner):
                    parser.error("workshop preview/stage requires --revision, --export and --banner")
                banner = {"filename": Path(args.banner).name, "base64": base64.b64encode(Path(args.banner).read_bytes()).decode("ascii")}
                operation = core.stage_workshop_bundle if args.action == "stage" else core.preview_workshop_stage
                result = envelope(operation, project=args.project, expected_revision=args.revision, export_id=args.export,
                                  banner=banner, visibility=args.visibility)
        elif args.command == "commands":
            result = envelope(core.lookup_command, command=args.name, context=args.context, query=args.query,
                              status=args.status, limit=args.limit)
        elif args.command == "export":
            result = envelope(core.export_mod, project=args.project, expected_revision=args.revision, format=args.format)
        elif args.command == "compatibility":
            result = envelope(core.compatibility, project=args.project, baseline=args.baseline)
        else:
            result = envelope(core.validate_mod, project=args.project)
    except (OSError, ValueError, TypeError) as exc:
        result = {"ok": False, "error": {"code": "cli_input", "message": str(exc)}}
    except Exception as exc:
        from .errors import KenoError
        if not isinstance(exc, KenoError):
            raise
        result = {"ok": False, "error": exc.to_dict()}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if not result["ok"]:
        return 1
    if args.command == "validate" and not result["result"]["static_ok"]:
        return 2
    return 0
