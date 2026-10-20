"""Targeted regressions for write/export boundaries and adapter parity."""

import concurrent.futures
import base64
import hashlib
import http.client
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
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

    def test_block_review_preserves_unknown_bytes_and_refuses_changed_lines(self):
        revision = self.view()["revision"]
        args = {"project": "sample", "expected_revision": revision, "object_index": 0,
                "changes": [{"op": "replace", "line": 4, "was": "hp 6", "command": "hp", "arguments": [9]}]}
        preview = self.core.preview_block_edit(**args)
        self.assertTrue(preview["changed"])
        self.assertEqual(self.path.read_bytes(), SOURCE)
        wrong = {**args, "changes": [{**args["changes"][0], "was": "hp 99"}]}
        with self.assertRaises(KenoError) as failure:
            self.core.apply_block_edit(**wrong)
        self.assertEqual(failure.exception.code, "line_changed")
        receipt = self.core.apply_block_edit(**args)
        self.assertEqual(self.path.read_bytes(), SOURCE.replace(b"hp 6", b"hp 9"))
        self.assertEqual((self.workspace / "sample" / receipt["backup"]).read_bytes(), SOURCE)
        self.assertEqual(receipt["before_revision"], revision)

    @staticmethod
    def sprite(alpha=255, top=10, size=32):
        """A unit frame: a block of pixels with 2 free rows under it."""
        from kenogenesis.images import encode_png
        row = lambda y: b"".join(bytes((170, 136, 238, alpha)) if top <= y < size - 2 and 8 <= x < 24 else bytes(4) for x in range(size))
        return encode_png(size, size, b"".join(row(y) for y in range(size)))

    def test_art_review_exclusive_save_and_source_failure_rollback(self):
        png = self.sprite()
        args = {"project": "sample", "expected_revision": self.view()["revision"], "object_index": 0,
                "frame": "spr1", "asset_path": "units/test.png", "content": base64.b64encode(png).decode()}
        asset = self.path.parent / "units/test.png"
        self.core.preview_art_upload(**args)
        self.assertFalse(asset.exists())
        self.assertEqual(self.path.read_bytes(), SOURCE)
        with patch.object(self.core, "_write_source", side_effect=OSError("synthetic source failure")):
            with self.assertRaises(OSError):
                self.core.apply_art_upload(**args)
        self.assertFalse(asset.exists())
        self.assertEqual(self.path.read_bytes(), SOURCE)
        receipt = self.core.apply_art_upload(**args)
        self.assertEqual(asset.read_bytes(), png)
        self.assertIn(b'spr1 "units/test.png"', self.path.read_bytes())
        self.assertIn(b"futurecommand 7", self.path.read_bytes())
        self.assertEqual(receipt["before_revision"], args["expected_revision"])
        with self.assertRaises(KenoError):
            self.core.apply_art_upload(**{**args, "expected_revision": receipt["revision"]})

    def test_unit_frames_reject_bad_pixels_and_corrupt_streams(self):
        import struct
        import zlib
        from kenogenesis.images import unit_frame_facts
        chunk = lambda k, b: struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xffffffff)
        header = chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0))
        bad_filter = b"\x89PNG\r\n\x1a\n" + header + chunk(b"IDAT", zlib.compress(b"\x07" + bytes(128) + (b"\x00" + bytes(128)) * 31)) + chunk(b"IEND", b"")
        short_rows = b"\x89PNG\r\n\x1a\n" + header + chunk(b"IDAT", zlib.compress(bytes(129 * 31))) + chunk(b"IEND", b"")
        for name, data in (("filter", bad_filter), ("rows", short_rows), ("soft", self.sprite(alpha=128)),
                           ("empty", self.sprite(top=40)), ("canvas", self.sprite(size=48))):
            with self.subTest(name), self.assertRaises(ValueError):
                unit_frame_facts("unit.png", data)
        with self.assertRaises(ValueError):
            inspect_asset("banner.png", bad_filter)
        self.assertEqual(unit_frame_facts("unit.png", self.sprite())["margins"]["bottom"], 2)
        revision = self.view()["revision"]
        with self.assertRaises(KenoError) as caught:
            self.core.preview_art_upload("sample", revision, 0, "spr1", "units/soft.png", base64.b64encode(self.sprite(alpha=128)).decode())
        self.assertEqual(caught.exception.code, "bad_art")
        for path in ("../escape.png", "units/x.bmp", "banner.tga"):
            with self.assertRaises(KenoError):
                self.core.preview_art_upload("sample", revision, 0, "spr1", path, base64.b64encode(self.sprite()).decode())
        self.assertEqual(self.path.read_bytes(), SOURCE)

    def test_paired_art_saves_both_frames_once_in_order_or_nothing(self):
        source = SOURCE.replace(b"futurecommand 7\r\n", b"spr1 \"old.png\"\r\ncopystats \"Soldier\"\r\ncopyspr \"Soldier\"\r\nfuturecommand 7\r\n")
        self.path.write_bytes(source)
        b64 = lambda data: base64.b64encode(data).decode()
        revision = self.view()["revision"]
        with self.assertRaises(KenoError) as caught:
            self.core.preview_art_upload("sample", revision, 0, "spr1", "units/a1.png", b64(self.sprite()))
        self.assertEqual(caught.exception.code, "art_pair_required")
        args = {"project": "sample", "expected_revision": revision, "object_index": 0,
                "frames": [{"frame": "spr2", "asset_path": "units/a2.png", "content": b64(self.sprite(top=12))},
                           {"frame": "spr1", "asset_path": "units/a1.png", "content": b64(self.sprite())}]}
        review = self.core.preview_art_upload(**args)
        self.assertEqual(set(review["frames"]), {"spr1", "spr2"})
        files = [self.path.parent / "units/a1.png", self.path.parent / "units/a2.png"]
        real_open, opened = Path.open, []

        def fail_second(path, mode="r", *rest, **kw):
            if mode == "xb" and path.suffix == ".png":
                opened.append(path)
                if len(opened) == 2:
                    raise OSError("synthetic second-frame failure")
            return real_open(path, mode, *rest, **kw)
        with patch.object(Path, "open", fail_second), self.assertRaises(OSError):
            self.core.apply_art_upload(**args)
        self.assertEqual(len(opened), 2)
        self.assertFalse(any(f.exists() for f in files) or (self.path.parent / "units").exists())
        self.assertEqual(self.path.read_bytes(), source)
        self.path.write_bytes(source + b"\r\n")
        with self.assertRaises(KenoError) as caught:
            self.core.apply_art_upload(**args)
        self.assertEqual(caught.exception.code, "stale_revision")
        self.path.write_bytes(source)
        receipt = self.core.apply_art_upload(**args)
        saved = self.path.read_bytes()
        self.assertNotIn(b"copyspr", saved)
        self.assertNotIn(b"old.png", saved)
        self.assertIn(b"futurecommand 7", saved)
        self.assertLess(saved.index(b'copystats "Soldier"'), saved.index(b'spr1 "units/a1.png"'))
        self.assertLess(saved.index(b'spr1 "units/a1.png"'), saved.index(b'spr2 "units/a2.png"'))
        self.assertEqual(saved.count(b"spr1"), 1)
        idle_only = self.core.apply_art_upload("sample", receipt["revision"], 0, "spr1", "units/a1b.png", b64(self.sprite()))
        saved = self.path.read_bytes()
        self.assertLess(saved.index(b'spr1 "units/a1b.png"'), saved.index(b'spr2 "units/a2.png"'))
        self.assertTrue(all(f.exists() for f in files))
        with self.assertRaises(KenoError) as caught:
            self.core.preview_art_upload("sample", idle_only["revision"], 0, "spr2", "units/a1.png", b64(self.sprite()))
        self.assertEqual(caught.exception.code, "dest_exists")

    def test_reference_catalog_import_keeps_duplicates_and_invalidates_revision(self):
        # Synthetic reference text only; no game data is used in tests.
        ref = (b'newmonster "Twin"  # 4\nhp 3\ndescr "first\nsecond"\n\nnewmonster "Twin"  # 9\nhp 5\n'
               b'selectterr 2 # Marsh\nname "Marsh"\n')
        files = [{"filename": "Synthetic Data v1.0.c5m", "base64": base64.b64encode(ref).decode()}]
        args = {"project": "sample", "game_version": "1.0", "provenance": "synthetic test", "name": "synthetic", "files": files}
        before = self.view()["revision"]
        review = self.core.preview_catalog_import(expected_revision=before, **args)
        self.assertFalse((self.workspace / "catalogs").exists())
        self.assertTrue(any("1.0" in w and "5.36" in w for w in review["warnings"]))
        receipt = self.core.apply_catalog_import(expected_revision=before, **args)
        rows = json.loads((self.workspace / "catalogs/synthetic.json").read_bytes())["rows"]
        twins = [r for r in rows if r["name"] == "Twin"]
        self.assertEqual([(r["id"], r["hp"], r["name_ordinal"], r["name_count"]) for r in twins], [(4, "3", 0, 2), (9, "5", 1, 2)])
        self.assertEqual(twins[0]["statements"][1], 'descr "first\nsecond"')
        self.assertNotIn("descr", twins[0])
        self.assertEqual(ref[twins[1]["source_offset"]:twins[1]["source_end"]], b'newmonster "Twin"  # 9\nhp 5\n')
        self.assertEqual([(r["kind"], r["id"], r["name"]) for r in rows if r["opener"] == "selectterr"], [("terrain", 2, "Marsh")])
        self.assertNotEqual(receipt["revision"], before)
        self.assertEqual(self.path.read_bytes(), SOURCE)
        for revision, code in ((before, "stale_revision"), (receipt["revision"], "dest_exists")):
            with self.assertRaises(KenoError) as failure:
                self.core.apply_catalog_import(expected_revision=revision, **args)
            self.assertEqual(failure.exception.code, code)

    def test_linked_new_unit_and_class_row_are_one_guarded_change(self):
        revision = self.view()["revision"]
        args = {"project": "sample", "expected_revision": revision, "mode": "new", "changes": [{"op": "add", "command": "hp", "arguments": [4]}],
                "opener": {"command": "newmonster", "arguments": ["Scout"]},
                "linked": {"object_index": 1, "changes": [{"op": "add", "command": "addunitrec", "arguments": ["Scout", 50, 3, 10, 0, 0]}]}}
        preview = self.core.preview_block_edit(**args)
        self.assertEqual(self.path.read_bytes(), SOURCE)
        self.assertEqual(preview["validation"]["counts"]["error"], 0)
        bad = {**args, "linked": {"object_index": 1, "changes": [{"op": "replace", "line": 7, "was": "changed", "command": "hometerr", "arguments": [2]}]}}
        with self.assertRaises(KenoError):
            self.core.apply_block_edit(**bad)
        self.assertEqual(self.path.read_bytes(), SOURCE)
        self.core.apply_block_edit(**args)
        saved = self.path.read_bytes()
        self.assertLess(saved.index(b'newmonster "Scout"'), saved.index(b"newclass"))
        self.assertIn(b'addunitrec "Scout" 50 3 10 0 0\r\n', saved)
        self.assertIn(b"  hp 6  # keep this comment\r\nfuturecommand 7\r\n", saved)
        self.assertEqual(len(list((self.workspace / "sample/.kenogenesis/backups").glob("*.c5m"))), 1)
        with self.assertRaises(KenoError) as stale:
            self.core.apply_block_edit(**args)
        self.assertEqual(stale.exception.code, "stale_revision")

    def test_catalog_snapshot_is_guarded_private_and_used_offline(self):
        (self.workspace / "catalogs").mkdir()
        catalog = self.workspace / "catalogs/ref.json"
        catalog.write_text(json.dumps({"game_version": "5.36", "provenance": "synthetic private-note-7731", "rows": [{"kind": "monster", "name": "Ref"}]}))
        revision = self.core.configure_project("sample", self.view()["revision"], catalog="catalogs/ref.json", preview=False)["revision"]
        self.core.preview_catalog_snapshot("sample", revision)
        self.assertFalse((self.workspace / "sample/.kenogenesis/catalog-snapshots").exists())
        receipt = self.core.apply_catalog_snapshot("sample", revision)
        self.assertNotEqual(receipt["revision"], revision)
        snapshot = self.workspace / "sample" / receipt["snapshot_path"]
        self.assertEqual(snapshot.read_bytes(), catalog.read_bytes())
        self.assertEqual(self.view()["catalog"]["snapshot"]["status"], "current")
        catalog.unlink()
        view = self.view()
        self.assertEqual((view["catalog"]["source"], view["catalog"]["snapshot"]["status"]), ("snapshot", "offline"))
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        self.assertEqual(self.view()["catalog"]["snapshot"]["status"], "invalid")
        self.assertNotEqual(self.view()["revision"], view["revision"])
        snapshot.write_bytes(snapshot.read_bytes()[:-1])
        exported = self.core.export_mod("sample", self.view()["revision"])
        self.assertFalse(any("catalog" in name for name in zipfile.ZipFile(exported["path"]).namelist()))
        # The shareable manifest keeps a minimal catalog summary; private notes, paths and snapshot details stay out at any depth.
        text = Path(exported["manifest"]).read_text(encoding="utf-8")
        for private in ("private-note-7731", "catalogs/ref.json", "catalogs\\\\ref.json", "catalog-snapshots", "captured_at_revision",
                        str(self.workspace).replace("\\", "\\\\")):
            self.assertNotIn(private, text)
        manifest = json.loads(text)
        self.assertEqual({k: manifest["catalog"][k] for k in ("source", "snapshot_status", "rows", "game_version", "configured")},
                         {"source": "snapshot", "snapshot_status": "offline", "rows": 1, "game_version": "5.36", "configured": True})
        self.assertIn("catalog_unavailable", [d["code"] for d in manifest["validation"]["diagnostics"]])
        listed = self.core.list_exports("sample")["exports"][0]
        self.assertEqual((listed["revision"], listed["counts"]), (manifest["revision"], manifest["validation"]["counts"]))
        self.assertIsNotNone(self.core.compatibility("sample", exported["manifest_path"])["change_review"])
        # Historical downloads are sanitized too, while their on-disk receipt remains available for compatibility checks.
        legacy = dict(manifest, catalog={"available": True, "provenance": "private-note-7731", "snapshot": {"path": "catalog-snapshots/private.json"}})
        Path(exported["manifest"]).write_text(json.dumps(legacy), encoding="utf-8")
        before_download = Path(exported["manifest"]).read_bytes()
        downloaded, _ = self.core.export_artifact("sample", exported["export_id"], "manifest")
        self.assertNotIn(b"private-note-7731", downloaded)
        self.assertNotIn(b"catalog-snapshots", downloaded)
        self.assertEqual(Path(exported["manifest"]).read_bytes(), before_download)
        self.assertEqual(json.loads(downloaded)["files"], manifest["files"])
        self.assertIsNotNone(self.core.compatibility("sample", exported["manifest_path"])["change_review"])

    def test_evidence_records_are_bounded_private_and_never_verify(self):
        revision = self.view()["revision"]
        self.assertEqual(self.core.list_evidence("sample")["records"], [])
        self.core.record_evidence("sample", revision, "browser", "Units tab renders")
        self.assertFalse((self.workspace / "sample/.kenogenesis/evidence").exists())
        for category, summary in (("engine_verified", "x"), ("browser", "two\nlines"), ("browser", "")):
            with self.assertRaises(KenoError):
                self.core.record_evidence("sample", revision, category, summary, preview=False)
        with self.assertRaises(KenoError) as stale:
            self.core.record_evidence("sample", "old", "static", "x", preview=False)
        self.assertEqual(stale.exception.code, "stale_revision")
        self.core.record_evidence("sample", revision, "game_user_reported", "Class listed", details="a\nb", preview=False)
        records = self.core.list_evidence("sample")["records"]
        self.assertEqual([(r["category"], r["current"], r["engine_verified"]) for r in records], [("game_user_reported", True, False)])
        self.assertEqual(self.view()["revision"], revision)
        exported = self.core.export_mod("sample", revision)
        self.assertEqual(sorted(zipfile.ZipFile(exported["path"]).namelist()), ["sample/banner.tga", "sample/sample.c5m"])

    def test_inspection_respects_disabled_forms_and_cleared_donor_attacks(self):
        self.path.write_bytes(b'icon "banner.tga"\ndescription "Order fixture"\nnewweapon "Claw"\ndmg 3\n'
                              b'newmonster "Donor"\nmeleeweapon 3 "Claw"\nclearweapons\nfirstshape 1\nfirstshape 0\n'
                              b'newmonster "Copy"\ncopystats "Donor"\n')
        units = [o for o in self.core.project_model("sample")["objects"] if o["kind"] == "monster"]
        self.assertEqual(units[0]["view"]["forms"], [])
        self.assertEqual(units[0]["view"]["weapons"], [])
        self.assertEqual(units[1]["view"]["inherited_weapons"]["weapons"], [])

    def test_comparison_does_not_restore_catalog_values_overwritten_by_copy(self):
        catalog = self.workspace / "catalog.json"
        catalog.write_text(json.dumps({"game_version": "5.36", "provenance": "synthetic", "rows": [{
            "kind": "monster", "name": "Reference", "hp": "99",
            "statements": ['hp 99', 'copystats "Unknown"', 'meleeweapon 3 "Claw"', 'clearweapons']}]}))
        self.core.configure_project("sample", self.view()["revision"], catalog="catalog.json", preview=False)
        result = self.core.compare_units("sample", 0, [{"catalog_index": 0}])["columns"][1]
        self.assertIsNone(result["stats"]["hp"]["value"])
        self.assertEqual(result["attacks"], [])

    def test_home_citadel_evidence_and_relative_power_schools(self):
        classes = "".join(f'newclass\nsetclassname "{n}"\nhometerr {t}\n' for n, t in
                          (("A", 7), ("B", 8), ("C", 500), ("D", 9), ("E", 10), ("F", 11)))
        self.path.write_bytes(('newritpow\nnewritpow\nnewmonster "Caster"\npower 0\npower -1\npower -2\npower 3\n'
                               'newritual "Rite"\nritpow 0\nselectterr 7\ngold 1\nselectterr 8\ncitadel\nclearspec\n'
                               'selectterr 500\nname "Keep"\ncitadel\n' + classes).encode())
        evidence = lambda: {c["name"]: next(k for k in c["checks"] if k["key"] == "home") for c in self.core.design_report("sample")["classes"]}
        offline = evidence()
        self.assertEqual({n: (k["ok"], k["evidence"]) for n, k in offline.items()},
                         {"A": (False, "unresolved"), "B": (False, "cleared"), "C": (True, "local"), "D": (False, "unresolved"),
                          "E": (False, "unresolved"), "F": (False, "unresolved")})
        row = lambda i, *sts: {"kind": "terrain", "name": f"T{i}", "id": i, "source_file": "terrain.c5m", "source_line": i, "statements": list(sts)}
        (self.workspace / "catalog.json").write_text(json.dumps({"game_version": "5.35", "provenance": "synthetic", "rows": [
            row(7, "citadel"), row(8, "citadel"), row(9, "citadel"), row(9, "gold 2"), row(10, "citadel", "clearfort")]}))
        self.core.configure_project("sample", self.view()["revision"], catalog="catalog.json", preview=False)
        online = evidence()
        self.assertEqual({n: (k["ok"], k["evidence"]) for n, k in online.items()},
                         {"A": (True, "catalog"), "B": (False, "cleared"), "C": (True, "local"), "D": (False, "ambiguous"),
                          "E": (False, "unresolved"), "F": (False, "unresolved")})
        self.assertEqual((online["A"]["game_version"], online["A"]["version_mismatch"], online["C"]["line"]), ("5.35", True, 17))
        self.assertIn("still verify in game", online["A"]["detail"])
        objs = self.core.project_model("sample")["objects"]
        cleared = next(o for o in objs if o["kind"] == "class" and o["view"]["setclassname"]["value"] == "B")
        self.assertIsNone(cleared["view"]["hometerr"]["target"]["citadel"])
        powers = next(o for o in objs if o["kind"] == "monster")["view"]["powers"]
        self.assertEqual([(p["status"], p.get("name")) for p in powers[:3]],
                         [("local", "New ritual school 2"), ("local", "New ritual school 1"), ("unresolved", None)])
        self.assertEqual(powers[3]["status"], "vanilla")
        self.assertEqual(next(o for o in objs if o["kind"] == "ritual")["view"]["school"]["status"], "unresolved")
        from kenogenesis.view import form_specs
        specs = form_specs()
        power = next(c for g in specs["monster"]["rows"] for c in g["commands"] if c["command"] == "power")
        self.assertEqual((power["relative"]["arg"], power["relative"]["page"]), (0, 17))
        self.assertTrue(all(int(x["value"]) > 0 for x in power["choices"][0]))
        self.assertFalse(any("relative" in c for g in specs["ritual"]["rows"] for c in g["commands"]))

    def test_project_model_parity_across_cli_and_http(self):
        expected = self.core.project_model("sample")
        result = subprocess.run([sys.executable, "-m", "kenogenesis", "--workspace", str(self.workspace), "run", "project_model",
                                 "--args", json.dumps({"project": "sample"})], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["result"], expected)
        server = make_server(self.core, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            for url in (f"/api/project_model?args={urllib.parse.quote(json.dumps({'project': 'sample'}))}", "/api/projects/sample"):
                connection.request("GET", url)
                response = connection.getresponse()
                self.assertEqual(json.loads(response.read())["result"], expected)
            connection.request("POST", "/api/record_evidence", body="{}", headers={"Content-Type": "application/json"})
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


    def _workshop_banner(self, width=256, height=256):
        from kenogenesis.images import encode_png
        return {"filename": "banner.png", "base64": base64.b64encode(encode_png(width, height, b"\x20\x30\x40\xff" * (width * height))).decode()}

    def _tree(self):
        root = self.workspace / "sample"
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_workshop_preview_is_pure_guarded_and_bundle_is_private(self):
        rev = self.view()["revision"]
        export = self.core.export_mod("sample", rev)
        args = dict(project="sample", expected_revision=rev, export_id=export["export_id"], banner=self._workshop_banner())
        before = self._tree()
        preview = self.core.preview_workshop_stage(**args)
        self.assertEqual(self._tree(), before)
        self.assertFalse(preview["written"]); self.assertFalse(preview["uploaded"])
        self.assertEqual(preview["coe5ws_txt"], 'Visibility="private"\n')
        with self.assertRaises(KenoError) as caught:
            self.core.preview_workshop_stage(**{**args, "expected_revision": "0" * 64})
        self.assertEqual(caught.exception.code, "stale_revision")
        staged = self.core.stage_workshop_bundle(**{**args, "visibility": "friends"})
        self.assertEqual(staged["revision"], rev); self.assertEqual(self.view()["revision"], rev)
        with zipfile.ZipFile(self.workspace / "sample" / staged["file"]) as archive:
            self.assertEqual(set(archive.namelist()), {"sample/sample.c5m", "sample/banner.tga", "sample/banner.png", "sample/coe5ws.txt"})
            self.assertEqual(archive.read("sample/coe5ws.txt"), b'Visibility="friends"\n')
            self.assertEqual(archive.read("sample/sample.c5m"), self.path.read_bytes())
        self.assertEqual(len(self.core.list_exports("sample")["exports"]), 1)
        stages = self.core.list_workshop_stages("sample")["stages"]
        self.assertEqual([(s["bundle_status"], s["current"]) for s in stages], [("ok", True)])
        data, _ = self.core.workshop_artifact("sample", staged["stage_id"], "archive")
        self.assertEqual(hashlib.sha256(data).hexdigest(), staged["bundle_sha256"])
        self.core.apply_fields("sample", rev, 0, "hp", [9])
        with self.assertRaises(KenoError) as caught:
            self.core.preview_workshop_stage(**{**args, "expected_revision": self.view()["revision"]})
        self.assertEqual(caught.exception.code, "export_stale")

    def test_workshop_final_recheck_failure_removes_its_stage(self):
        revision = self.view()["revision"]
        export = self.core.export_mod("sample", revision)
        stage_dir = self.workspace / "sample/.kenogenesis/workshop-stages"
        read_snapshot = self.core._snapshot

        def fail_when_stage_exists(project):
            if stage_dir.exists() and list(stage_dir.glob("*.receipt.json")):
                raise OSError("source became unreadable after staging")
            return read_snapshot(project)

        with patch.object(self.core, "_snapshot", side_effect=fail_when_stage_exists):
            with self.assertRaises(OSError):
                self.core.stage_workshop_bundle("sample", revision, export["export_id"], self._workshop_banner())
        self.assertEqual(list(stage_dir.iterdir()), [])

    def test_workshop_rejects_corrupt_exports_collisions_and_leaves_no_partial_stage(self):
        rev = self.view()["revision"]
        export = self.core.export_mod("sample", rev)
        args = dict(project="sample", expected_revision=rev, export_id=export["export_id"], banner=self._workshop_banner())
        for bad, code in (({"export_id": "../exports/x"}, "not_found"), ({"banner": self._workshop_banner(256, 64)}, "bad_banner"),
                          ({"visibility": "everyone"}, "bad_visibility")):
            with self.assertRaises(KenoError) as caught:
                self.core.preview_workshop_stage(**{**args, **bad})
            self.assertEqual(caught.exception.code, code)
        with patch("kenogenesis.workshop._json_bytes", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.core.stage_workshop_bundle(**args)
        stage_dir = self.workspace / "sample/.kenogenesis/workshop-stages"
        self.assertEqual(list(stage_dir.iterdir()) if stage_dir.exists() else [], [])
        # A consistently edited manifest and ZIP are still compared with the saved bytes, and extra entries are refused.
        zip_path, manifest_path = Path(export["path"]), Path(export["manifest"])
        for extra in ({"sample/sample.c5m": b"hp 999\n"}, {"../escape.txt": b"x"}):
            with zipfile.ZipFile(zip_path, "w") as archive:
                for name, data in {"sample/sample.c5m": self.path.read_bytes(), "sample/banner.tga": (self.path.parent / "banner.tga").read_bytes(), **extra}.items():
                    archive.writestr(name, data)
            manifest = json.loads(manifest_path.read_text())
            manifest["archive_sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(KenoError) as caught:
                self.core.preview_workshop_stage(**args)
            self.assertEqual(caught.exception.code, "export_mismatch")
        (self.path.parent / "COE5WS.txt").write_bytes(b"user file")
        rev = self.core.configure_project("sample", rev, declared_assets=["COE5WS.txt"], preview=False)["revision"]
        export = self.core.export_mod("sample", rev)
        with self.assertRaises(KenoError) as caught:
            self.core.preview_workshop_stage(**{**args, "expected_revision": rev, "export_id": export["export_id"]})
        self.assertEqual(caught.exception.code, "workshop_collision")
        self.assertIn("sample/COE5WS.txt", caught.exception.message)
        self.assertEqual((self.path.parent / "COE5WS.txt").read_bytes(), b"user file")

    def test_settings_preview_reports_compatibility_impact_without_writing(self):
        self.core.create_project("donor")
        (self.workspace / "donor/mod/donor/donor.c5m").write_bytes(b'icon "banner.tga"\nnewmonster "Donor Unit"\nhp 3\nselectmonster "Shared"\nhp 2\n')
        self.path.write_bytes(SOURCE + b'newmonster "Copy"\r\ncopystats "Donor Unit"\r\nselectmonster "Shared"\r\nhp 4\r\n')
        meta = self.workspace / "sample/project.json"
        before, revision = meta.read_bytes(), self.view()["revision"]
        impact = self.core.configure_project("sample", revision, dependencies=["donor"], preview=True)["compatibility_impact"]
        self.assertEqual((meta.read_bytes(), self.view()["revision"]), (before, revision))
        self.assertFalse((self.workspace / "sample/.kenogenesis/backups").exists())
        self.assertEqual([d["code"] for d in impact["added"]], ["overlapping_target"])
        self.assertTrue(any(d["code"] == "reference" and "Donor Unit" in d["message"] for d in impact["removed"]))
        self.assertEqual([x["project"] for x in impact["declared_order"]["after"]], ["donor", "sample"])
        self.assertFalse(impact["engine_verified"])

    def test_private_project_docs_are_bounded_read_only_and_not_exported(self):
        docs = self.workspace / "sample/docs"
        docs.mkdir()
        (docs / "plan.md").write_bytes(b"# Plan\n[x](other.md)\n")
        (docs / "api-token.md").write_text("secret", encoding="utf-8")
        (docs / "big.md").write_bytes(b"x" * (256 * 1024 + 1))
        (docs / "nested").mkdir(); (docs / "nested/inner.md").write_text("inner")
        (self.workspace / "sample/notes.md").write_text("outside docs")
        listing = self.core.list_project_docs("sample")
        self.assertEqual([d["name"] for d in listing["docs"]], ["plan.md"])
        self.assertEqual({s["name"] for s in listing["skipped"]}, {"api-token.md", "big.md"})
        self.assertEqual(self.core.read_project_doc("sample", "plan.md")["text"], "# Plan\n[x](other.md)\n")
        for name in ("api-token.md", "big.md", "../notes.md", "nested/inner.md", "../project.json", "PLAN.md", "sample.c5m"):
            with self.assertRaises(KenoError) as caught:
                self.core.read_project_doc("sample", name)
            self.assertEqual(caught.exception.code, "not_found")
        export = self.core.export_mod("sample", self.view()["revision"])
        names = sorted(zipfile.ZipFile(export["path"]).namelist())
        self.assertEqual(names, ["sample/banner.tga", "sample/sample.c5m"])
        self.assertEqual((export["format"], sorted(f["path"] for f in export["files"])), ("zip", names))
        server = make_server(self.core, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            for url, status, code in (("/api/projects/sample/docs/plan.md", 200, None), ("/api/projects/sample/docs/..%2Fproject.json", 404, "not_found"),
                                      ("/api/projects/sample/catalog?conditions=%7Bbroken", 400, "bad_filter")):
                connection.request("GET", url)
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, status, url)
                self.assertEqual(body.get("error", {}).get("code"), code)
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_user_reported_observation_fields_are_optional_validated_and_private(self):
        revision = self.view()["revision"]
        self.core.record_evidence("sample", revision, "static", "legacy record without observation", preview=False)
        bad = ({"category": "browser", "observation": {"map": "Small"}}, {"observation": {"reference_sha256": "abc"}},
               {"observation": {"turns": -1}}, {"observation": {"turns": True}}, {"observation": {"seed": "1"}}, {"observation": {"tester": "a\nb"}})
        for extra in bad:
            with self.assertRaises(KenoError):
                self.core.record_evidence(**{"project": "sample", "expected_revision": revision, "category": "game_user_reported",
                                             "summary": "Recruited", "preview": False, **extra})
        digest = "AB" * 32
        preview = self.core.record_evidence("sample", revision, "game_user_reported", "Recruited", preview=True,
                                            observation={"game_version": "5.36", "map": "Small", "turns": 12, "reference_sha256": digest, "tester": ""})
        self.assertEqual(len(self.core.list_evidence("sample")["records"]), 1)
        obs = preview["record"]["observation"]
        self.assertEqual((obs["turns"], obs["reference_sha256"], obs["reported_by"], "tester" in obs), (12, digest.lower(), "user", False))
        self.core.record_evidence("sample", revision, "game_user_reported", "Recruited", preview=False, observation={"turns": 12})
        records = self.core.list_evidence("sample")["records"]
        self.assertEqual([("observation" in r, r["engine_verified"]) for r in records], [(True, False), (False, False)])
        self.assertEqual(self.view()["revision"], revision)

    def test_unit_and_class_comparisons_keep_unknowns_unknown(self):
        self.path.write_bytes(SOURCE + b'addunitrec "Test Unit" 40 2 10 5 1\r\nrecxcost 3 2\r\n')
        catalog = self.workspace / "catalog.json"
        catalog.write_text(json.dumps({"game_version": "5.35", "provenance": "synthetic", "rows": [
            {"kind": "monster", "name": "Militia", "statements": ["hp 10"]},
            {"kind": "class", "name": "Vanilla", "statements": ['addunitrec "Militia" 100 4 6 0 0']}]}))
        revision = self.core.configure_project("sample", self.view()["revision"], catalog="catalog.json", preview=False)["revision"]
        units = self.core.compare_units("sample", 0, [{"catalog_index": 0}])["columns"]
        self.assertEqual([(r["cls"], r["gold"], r["extra_costs"][0]["amount"]) for r in units[0]["recruitment"]["rows"]], [("Test Class", "10", "2")])
        self.assertEqual([(r["cls"], r["gold"], r["source"]) for r in units[1]["recruitment"]["rows"]], [("Vanilla", "6", "catalog")])
        self.assertIsNone(units[1]["sprites"])
        classes = self.core.compare_classes("sample", 1, [{"catalog_index": 1}])
        cells = {row["key"]: [c["value"] for c in row["cells"]] for row in classes["rows"]}
        self.assertEqual(cells["gold"], ["Test Unit 10", "Militia 6"])
        self.assertEqual(cells["goldbonus"], [None, None])
        self.assertEqual(cells["rituals"][1], None)
        for refs in ([], [{"catalog_index": 0}], [{"object_index": 0}]):
            with self.assertRaises(KenoError):
                self.core.compare_classes("sample", 1, refs)
        # The dashboard repeats the same figures: unknown stats are counted apart, never drawn as zero.
        dash = classes["dashboard"]["columns"]
        self.assertEqual([(c["marker"], c["roster"]["troops"], c["costs"]["gold"]["min"]) for c in dash], [("A", 1, 10), ("B", 1, 6)])
        self.assertEqual(dash[0]["stats"]["hp"], {"min": 6, "max": 6, "known": 1, "unknown": 0})
        self.assertEqual((dash[1]["units"][0]["stats_from"], dash[1]["stats"]["str"]["unknown"]), ("catalog row", 1))
        self.assertIsNone(dash[1]["rituals"]["resources"])
        self.assertFalse(dash[1]["recruitment_complete"])
        self.assertEqual(dash[0]["units"][0]["stats"]["hp"]["line"], 4)
        self.assertNotIn("_dash", classes["columns"][0])
        self.assertFalse(envelope(self.core.compare_classes, project="sample", class_index=1)["ok"])
        self.assertEqual(self.view()["revision"], revision)

    def test_lookup_exposes_full_manual_without_claiming_validation(self):
        documented = self.core.lookup_command("sndvol")
        self.assertEqual([(e["context"], e["status"], e["validated"]) for e in documented["entries"]], [("weapon", "documented", False)])
        self.assertEqual(documented["entries"][0]["arguments"], [{"name": "dvol", "type": "i", "optional": False}])
        curated = self.core.lookup_command("hp", "monster")["entries"][0]
        self.assertEqual((curated["args"], curated["page"], curated["validated"], curated["manual_page"]), (["i"], 14, True, 14))
        self.assertEqual(self.core.lookup_command("newmonster", "monster")["entries"][0]["matched_via"], "global")
        everything = self.core.lookup_command(limit=1000)
        self.assertEqual((everything["total"], everything["truncated"], everything["counts"]["announced"]), (897, False, 6))
        self.assertEqual(len({e["command"] for e in everything["entries"] if e["status"] != "announced"}), 845)
        self.assertEqual(self.core.lookup_command("futurecommand")["status"], "unknown")
        self.assertEqual(self.core.lookup_command(context="map")["status"], "unknown_context")
        self.assertTrue(all(e["status"] == "curated" for e in self.core.lookup_command(context="class", status="curated")["entries"]))
        result = subprocess.run([sys.executable, "-m", "kenogenesis", "--workspace", str(self.workspace), "commands", "sndvol"],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["result"]["entries"][0]["status"], "documented")
        page = subprocess.run([sys.executable, "-m", "kenogenesis", "--workspace", str(self.workspace), "run", "catalog_page",
                               "--args", json.dumps({"project": "sample"})], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(page.stdout)["result"]["rows"], [])

    def test_coe5_541_overlay_versions_announced_commands_and_custom_terrain(self):
        from kenogenesis.commands import game_profile
        statuses = {v: game_profile(v)["status"] for v in (None, "", "5.4", "v5.41", "5.36", "5.40", "5.41", " 5.41 ", "5.50", "6.00")}
        self.assertEqual(statuses, {None: "unset", "": "unset", "5.4": "unrecognized", "v5.41": "unrecognized", "5.36": "before_5.41",
                                    "5.40": "before_5.41", "5.41": "5.41_or_later", " 5.41 ": "5.41_or_later", "5.50": "5.41_or_later",
                                    "6.00": "5.41_or_later"})
        self.assertEqual({v: game_profile(v)["custom_terrain"]["last"] for v in (None, "5.4", "5.40", "5.41")},
                         {None: 999, "5.4": 999, "5.40": 999, "5.41": 1999})
        brigand = self.core.lookup_command("brigand")
        self.assertEqual([(e["status"], e["context"], e["validated"], e["signature"], e["minimum_version"]) for e in brigand["entries"]],
                         [("announced", None, False, None, "5.41")])
        self.assertEqual(self.core.lookup_command("brigand", "monster")["entries"][0]["matched_via"], "context_not_announced")
        self.assertEqual(self.core.lookup_command("+minunitshere", "event")["entries"][0]["context"], "event")
        self.assertEqual(self.core.lookup_command("+minunitshere", "monster")["status"], "unknown")
        self.assertNotIn("brigand", [e["command"] for e in self.core.lookup_command(context="monster", limit=1000)["entries"]])
        self.assertEqual(self.core.lookup_command(status="announced")["total"], 6)
        recs = "".join('addunitrec "Test Unit" 10 1 0 0 0\n' for _ in range(129))
        source = ('icon "banner.tga"\ndescription "Overlay"\nnewmonster "Test Unit"\nhp 6\nbrigand 3\nselectterr 1200\nname "High Keep"\n'
                  'citadel\nspr "keep.png"\nnewclass\nsetclassname "Test Class"\nhometerr 1200\nsetmaincom "Test Unit"\n' + recs +
                  'playerevent\n+minunitshere 2\nendevent\n').encode()
        self.path.write_bytes(source)

        def state(version):
            self.core.configure_project("sample", self.view()["revision"], target_version=version, preview=False)
            report = self.core.validate_mod("sample")
            model = self.core.project_model("sample")
            terrain = next(o for o in model["objects"] if o["kind"] == "terrain")
            home = next(o for o in model["objects"] if o["kind"] == "class")["view"]["hometerr"]["target"]
            return {d["code"]: d for d in report["diagnostics"]}, report, terrain, home, model
        for version in (None, "5.36"):
            codes, _, terrain, home, model = state(version)
            self.assertEqual((terrain["new"], home["new"], codes["recruitment_limit"]["severity"]), (False, False, "error"))
            self.assertIn("Needs CoE5 5.41", codes["announced_command"]["message"])
            self.assertIn("existing terrain", codes["terrain_range"]["message"])
            self.assertEqual(model["game_profile"]["custom_terrain"]["last"], 999)
        codes, report, terrain, home, model = state("5.41")
        self.assertEqual((terrain["new"], home["status"], home["new"], codes["recruitment_limit"]["severity"]), (True, "local", True, "unverified"))
        self.assertEqual({d["message"].split(":")[0] for d in report["diagnostics"] if d["code"] == "announced_command"}, {"brigand", "+minunitshere"})
        self.assertNotIn("Needs CoE5", codes["announced_command"]["message"])
        self.assertIn("inferred", codes["terrain_range"]["message"])
        self.assertNotIn("reference", codes)
        self.assertEqual((model["game_profile"]["release_notes"][0]["version"], len(model["game_profile"]["announced_limits"])), ("5.41", 8))
        self.assertEqual(self.path.read_bytes(), source)
        result = subprocess.run([sys.executable, "-m", "kenogenesis", "--workspace", str(self.workspace), "commands", "--status", "announced"],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["result"], self.core.lookup_command(status="announced"))
        server = make_server(self.core, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", "/api/meta")
            meta = json.loads(connection.getresponse().read())["result"]
            self.assertEqual(meta["release_notes"][0]["version"], "5.41")
            self.assertEqual({e["command"] for e in meta["registry"] if e["status"] == "announced"},
                             {"brigand", "pickupbrigands", "adventurer", "pickupadvent", "partyleader", "+minunitshere"})
            connection.request("GET", f"/api/lookup_command?args={urllib.parse.quote(json.dumps({'command': 'partyleader'}))}")
            self.assertEqual(json.loads(connection.getresponse().read())["result"], self.core.lookup_command("partyleader"))
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_typed_evidence_references_are_bounded_and_legacy_compatible(self):
        revision = self.view()["revision"]
        digest = "CD" * 32
        record = self.core.record_evidence("sample", revision, "browser", "Dashboard renders", reference="legacy.png",
                                           references=[{"kind": "screenshot", "label": "units.png", "sha256": digest},
                                                       {"kind": "log", "label": "", "sha256": ""}], preview=False)["record"]
        self.assertEqual(record["references"], [{"kind": "screenshot", "kind_label": "Screenshot", "label": "units.png", "sha256": digest.lower()}])
        self.assertEqual((record["reference"], record["engine_verified"]), ("legacy.png", False))
        bad = ([{"kind": "screenshot", "label": "x"}] * 9, [{"kind": "video", "label": "x"}], [{"kind": "log", "label": "", "sha256": digest}],
               [{"kind": "log", "label": "x", "sha256": "abc"}], [{"kind": "log", "label": "a\x7fb"}], [{"kind": "log", "label": "x", "path": "C:/"}])
        fields = []
        for refs in bad:
            with self.assertRaises(KenoError) as caught:
                self.core.record_evidence("sample", revision, "static", "x", references=refs, preview=False)
            fields.append(caught.exception.details.get("field"))
        self.assertEqual(fields, ["references", "references.0.kind", "references.0.label", "references.0.sha256", "references.0.label", "references.0"])
        listed = self.core.list_evidence("sample")
        self.assertEqual((len(listed["records"]), listed["max_references"]), (1, 8))
        exported = self.core.export_mod("sample", revision)
        self.assertEqual(sorted(zipfile.ZipFile(exported["path"]).namelist()), ["sample/banner.tga", "sample/sample.c5m"])

    def test_meta_reports_runtime_and_settings_errors_name_their_field(self):
        server = make_server(self.core, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", "/api/meta")
            runtime = json.loads(connection.getresponse().read())["result"]["runtime"]
            self.assertEqual((runtime["python_executable"], runtime["platform"]), (sys.executable, sys.platform))
            connection.request("GET", "/api/meta", headers={"Host": f"localhost:{server.server_port}"})
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()
        revision = self.view()["revision"]
        for kwargs, field in (({"dependencies": ["missing_mod"]}, "dependencies"), ({"dependencies": ["sample"]}, "dependencies"),
                              ({"declared_assets": ["../x.png"]}, "declared_assets")):
            with self.assertRaises(KenoError) as caught:
                self.core.configure_project("sample", revision, **kwargs)
            self.assertEqual(caught.exception.details.get("field"), field)
        self.core.create_project("nested")
        self.core.configure_project("nested", self.core.project_view("nested")["revision"], dependencies=["sample"], preview=False)
        with self.assertRaises(KenoError) as caught:
            self.core.configure_project("sample", revision, dependencies=["nested"])
        self.assertEqual((caught.exception.code, caught.exception.details["field"], caught.exception.details["dependency"]),
                         ("nested_dependencies", "dependencies", "nested"))

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "Windows PowerShell launcher")
    def test_launcher_refuses_a_bad_interpreter_before_starting(self):
        script = Path(__file__).resolve().parent.parent / "start.ps1"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                                 "-Workspace", str(self.workspace / "launcher ws"), "-Python", str(self.workspace / "no such python.exe")],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn("-Python was not found", result.stdout + result.stderr)
        self.assertFalse((self.workspace / "launcher ws").exists())


if __name__ == "__main__":
    unittest.main()
