"""Targeted regressions for write/export boundaries and adapter parity."""

import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import zipfile

from kenogenesis.assets import inspect_asset
from kenogenesis.core import Kenogenesis, envelope, project_lock
from kenogenesis.errors import KenoError
from kenogenesis.parser import parse
from kenogenesis.webserver import make_server

SOURCE = b'icon "banner.tga"\r\ndescription "Safety fixture"\r\nnewmonster "Test Unit"\r\n  hp 6  # keep this comment\r\nfuturecommand 7\r\nnewclass\r\nsetclassname "Test Class"\r\nhometerr 1\r\nsetmaincom "Test Unit"\r\naddstartunits "Test Unit" 5\r\n'


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.core = Kenogenesis(str(self.workspace))
        self.core.create_project("sample", target_version="5.36")
        self.path = self.workspace / "sample/mod/sample/sample.c5m"
        self.path.write_bytes(SOURCE)

    def tearDown(self):
        self.temp.cleanup()

    def view(self):
        return self.core.project_view("sample")

    def test_hash_comment_and_coe_syntax(self):
        parsed = parse(SOURCE)
        self.assertEqual(parsed["objects"][0]["kind"], "monster")
        hp = next(s for s in parsed["statements"] if s["command"] == "hp")
        self.assertEqual([a["value"] for a in hp["args"]], ["6"])
        self.assertEqual(parse(b'#newmonster "Wrong game"\n')["objects"], [])

    def test_preview_is_read_only_apply_preserves_bytes_and_backups(self):
        rev = self.view()["revision"]
        args = dict(project="sample", expected_revision=rev, object_index=0, command="hp", arguments=[9])
        preview = self.core.preview_fields(**args)
        self.assertEqual(self.path.read_bytes(), SOURCE)
        self.assertIn("hp 9", preview["diff"])
        self.core.apply_fields(**args)
        self.assertEqual(self.path.read_bytes(), SOURCE.replace(b"hp 6", b"hp 9"))
        backups = list((self.workspace / "sample/.kenogenesis/backups").glob("*.c5m"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), SOURCE)
        with self.assertRaises(KenoError) as caught:
            self.core.apply_fields(**args)
        self.assertEqual(caught.exception.code, "stale_revision")

    def test_non_ascii_and_bom_untouched_outside_span(self):
        original = b'\xef\xbb\xbf' + SOURCE + '# Caf\u00e9\n'.encode()
        self.path.write_bytes(original)
        self.core.apply_fields("sample", self.view()["revision"], 0, "hp", [11])
        self.assertEqual(self.path.read_bytes(), original.replace(b"hp 6", b"hp 11"))

    def test_asset_revision_and_metadata_revision_invalidate_review(self):
        before = self.view()["revision"]
        asset = self.path.parent / "banner.tga"
        data = bytearray(asset.read_bytes()); data[-1] = 99; asset.write_bytes(data)
        with self.assertRaises(KenoError):
            self.core.apply_patch("sample", before, "hp 6", "hp 7")
        current = self.view()["revision"]
        meta = self.workspace / "sample/project.json"
        data = json.loads(meta.read_text()); data["name"] = "Renamed"; meta.write_text(json.dumps(data))
        self.assertNotEqual(current, self.view()["revision"])

    def test_lock_blocks_second_writer(self):
        with project_lock(self.workspace / "sample"):
            result = envelope(self.core.apply_patch, project="sample", expected_revision=self.view()["revision"], old="hp 6", new="hp 7")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "project_locked")
        self.assertEqual(self.path.read_bytes(), SOURCE)

    def test_two_writers_cannot_silently_overwrite_each_other(self):
        revision = self.view()["revision"]
        def write(value):
            return envelope(self.core.apply_patch, project="sample", expected_revision=revision, old="hp 6", new=f"hp {value}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, (8, 10)))
        self.assertEqual(sum(result["ok"] for result in results), 1)

    def test_forward_reference_and_class_requirements(self):
        self.path.write_bytes(b'icon "banner.tga"\ndescription "test"\nnewclass\nsetclassname "Test"\naddstartunits "Later Unit" 2\nnewmonster "Later Unit"\nhp 4\n')
        report = self.core.validate_mod("sample")
        codes = {d["code"] for d in report["diagnostics"]}
        self.assertTrue({"forward_reference", "class_home"} <= codes)
        with self.assertRaises(KenoError):
            self.core.export_mod("sample", self.view()["revision"])

    def test_unknown_commands_remain_unverified_and_preserved(self):
        result = self.view()
        self.assertTrue(result["validation"]["static_ok"])
        self.assertTrue(any(d["code"] == "unknown_command" for d in result["validation"]["diagnostics"]))
        self.assertIn("futurecommand 7", result["source"])

    def test_export_allowlist_map_and_hashes_no_private_files(self):
        (self.path.parent / "private-notes.txt").write_text("DO NOT EXPORT")
        (self.path.parent / "map.coem").write_bytes(b"Opaque test payload; not an engine-valid map")
        self.path.write_bytes(SOURCE + b'mapfile "map.coem"\r\n')
        revision = self.view()["revision"]
        result = self.core.export_mod("sample", revision)
        second = self.core.export_mod("sample", revision)
        self.assertNotEqual(result["path"], second["path"])
        with zipfile.ZipFile(result["path"]) as archive:
            self.assertEqual(set(archive.namelist()), {"sample/sample.c5m", "sample/banner.tga", "sample/map.coem"})
            self.assertEqual(archive.read("sample/sample.c5m"), self.path.read_bytes())
        receipt = json.loads(Path(result["manifest"]).read_text())
        self.assertFalse(receipt["validation"]["engine_verified"])
        self.assertTrue(any(d["code"] == "map_semantics" for d in receipt["validation"]["diagnostics"]))

    def test_paths_case_and_traversal_rejected(self):
        for reference in ("../secret.png", "C:/secret.png", "Banner.tga"):
            self.path.write_bytes(SOURCE.replace(b"banner.tga", reference.encode()))
            self.assertFalse(self.core.validate_mod("sample")["static_ok"])

    def test_dependency_and_catalog_invalidate_revision(self):
        self.core.create_project("donor")
        before = self.view()["revision"]
        self.core.configure_project("sample", before, dependencies=["donor"], preview=False)
        before = self.view()["revision"]
        dependency = self.workspace / "donor/mod/donor/donor.c5m"
        dependency.write_bytes(dependency.read_bytes() + b"# external edit\n")
        self.assertNotEqual(before, self.view()["revision"])
        catalog = self.workspace / "catalog.json"
        catalog.write_text(json.dumps({"game_version": "5.35", "provenance": "test fixture only", "rows": [{"kind": "monster", "name": "Fixture"}]}))
        self.core.configure_project("sample", self.view()["revision"], catalog="catalog.json", preview=False)
        result = self.core.search_game_data("sample", "fixture")
        self.assertEqual(len(result["rows"]), 1)
        self.assertTrue(result["unverified"])
        before = self.view()["revision"]
        catalog.write_text(catalog.read_text() + "\n")
        self.assertNotEqual(before, self.view()["revision"])
        catalog.unlink()
        view = self.view()
        self.assertIn("Test Unit", view["source"])
        self.assertFalse(view["catalog"]["available"])
        self.assertTrue(any(d["code"] == "catalog_unavailable" for d in view["validation"]["diagnostics"]))
        self.core.configure_project("sample", view["revision"], catalog="", preview=False)

    def test_baseline_flags_definition_reordering(self):
        export = self.core.export_mod("sample", self.view()["revision"])
        baseline = str(Path(export["manifest"]).relative_to(self.workspace / "sample"))
        self.path.write_bytes(SOURCE.replace(b'newmonster "Test Unit"', b'newmonster "Inserted"\nhp 1\nnewmonster "Test Unit"'))
        report = self.core.compatibility("sample", baseline)
        self.assertIn("monster", report["change_review"]["definition_order_risks"])

    def test_corrupt_asset_rejected(self):
        for data in (b"not a png", b"\x89PNG\r\n\x1a\n", b"\x00" * 18):
            with self.assertRaises(ValueError):
                inspect_asset("bad.png", data)

    def test_invalid_settings_do_not_mutate_project(self):
        meta = self.workspace / "sample/project.json"
        original = meta.read_bytes()
        with self.assertRaises((KenoError, OSError)):
            self.core.configure_project("sample", self.view()["revision"], catalog="missing.json", preview=False)
        self.assertEqual(meta.read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), SOURCE)

    def test_documentation_version_gap_is_visible(self):
        self.core.configure_project("sample", self.view()["revision"], target_version="5.40", preview=False)
        self.assertTrue(any(d["code"] == "manual_version" for d in self.core.validate_mod("sample")["diagnostics"]))

    def test_empty_source_can_be_recovered_without_resetting_other_files(self):
        self.path.write_bytes(b"")
        self.core.apply_patch("sample", self.view()["revision"], "", SOURCE.decode())
        self.assertEqual(self.path.read_bytes(), SOURCE)

    def test_independent_example_is_exportable_and_never_overwrites(self):
        view = self.core.build_example("prototype", "5.40")
        self.assertTrue(view["validation"]["static_ok"])
        self.assertTrue({"terrain", "weapon", "school", "monster", "ritual", "class"} <= {o["kind"] for o in view["objects"]})
        self.core.export_mod("prototype", view["revision"])
        with self.assertRaises(KenoError):
            self.core.build_example("prototype", "5.40")

    def test_cli_and_http_parity_and_origin_checks(self):
        expected = self.view()
        result = subprocess.run([sys.executable, "-m", "kenogenesis", "--workspace", str(self.workspace), "project", "inspect", "sample"],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["result"], expected)
        server = make_server(self.core, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            query = urllib.parse.quote(json.dumps({"project": "sample"}))
            connection.request("GET", f"/api/project_view?args={query}")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["result"], expected)
            connection.request("POST", "/api/apply_patch", body="{}", headers={"Content-Type": "application/json"})
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
