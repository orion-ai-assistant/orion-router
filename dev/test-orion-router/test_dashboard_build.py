"""Offline regressions for dashboard caching and safe output replacement."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin import dashboard_build as build
import cli
from bin import update as cli_update
from core import updater


class DashboardBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dashboard = self.root / "dashboard"
        self.dashboard.mkdir()
        self.source = self.dashboard / "page.tsx"
        self.source.write_text("original", encoding="utf-8")
        (self.dashboard / "package.json").write_text('{"dependencies":{"next":"16.2.6"}}')
        (self.dashboard / "node_modules").mkdir()
        catalog = self.root / build.BUILD_INPUTS[0]
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{}')
        for name, value in (("ROOT", self.root), ("DASHBOARD", self.dashboard)):
            patcher = patch.object(build, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def mark_current(self):
        out = self.dashboard / "out"
        out.mkdir(exist_ok=True)
        (out / "index.html").write_text("old dashboard")
        (out / build.MANIFEST).write_text(json.dumps({
            "schema": build.SCHEMA, "source_hash": build.get_dashboard_hash(),
        }))

    def fake_build(self, command, cwd):
        self.assertEqual(command, "npm run build")
        # The live UI remains available during the entire build.
        if (self.dashboard / "out").exists():
            self.assertEqual((self.dashboard / "out/index.html").read_text(), "old dashboard")
        self.assertTrue((cwd / "node_modules").is_dir())
        (cwd / "out").mkdir()
        (cwd / "out/index.html").write_text("new dashboard")

    def test_first_build_and_manifest(self):
        with patch.object(build, "npm_needs_install", return_value=False), \
                patch.object(build, "_run_npm", side_effect=self.fake_build):
            build.ensure_dashboard()
        self.assertFalse(build.dashboard_needs_build())
        manifest = json.loads((self.dashboard / "out" / build.MANIFEST).read_text())
        self.assertEqual(manifest["next_version"], "16.2.6")
        self.assertIn("built_at", manifest)
        self.assertEqual(list(self.root.glob(".orion-dashboard-*")), [])

    def test_current_backend_update_and_port_changes_never_touch_npm(self):
        self.mark_current()
        (self.root / "backend.py").write_text("changed backend")
        with patch.dict(os.environ, {"ORION_ROUTER_TLS_PORT": "12345",
                                     "NEXT_PUBLIC_ROUTER_PORT": "12345"}), \
                patch.object(build, "npm_needs_install", side_effect=AssertionError("npm checked")), \
                patch.object(build.subprocess, "run", side_effect=AssertionError("process started")):
            build.ensure_dashboard()

    def test_edit_new_directory_rename_and_external_build_input(self):
        self.mark_current()
        original = build.get_dashboard_hash()
        self.source.write_text("edited")
        self.assertTrue(build.dashboard_needs_build())
        self.source.write_text("original")
        extra = self.dashboard / "new-folder/new.tsx"
        extra.parent.mkdir()
        extra.write_text("extra")
        self.assertNotEqual(build.get_dashboard_hash(), original)
        extra.unlink()
        renamed = self.source.with_name("renamed.tsx")
        self.source.rename(renamed)
        self.assertNotEqual(build.get_dashboard_hash(), original)
        renamed.rename(self.source)
        (self.root / build.BUILD_INPUTS[0]).write_text('{"changed":true}')
        self.assertTrue(build.dashboard_needs_build())

    def test_generated_files_are_ignored(self):
        self.mark_current()
        original = build.get_dashboard_hash()
        for folder in build.EXCLUDED_DIRS:
            path = self.dashboard / folder
            path.mkdir(exist_ok=True)
            (path / "generated.js").write_text("generated")
        for name in (*build.EXCLUDED_FILES, "debug.log", "tsconfig.tsbuildinfo"):
            (self.dashboard / name).write_text("generated")
        self.assertEqual(build.get_dashboard_hash(), original)

    def test_missing_and_invalid_output_or_manifest(self):
        self.assertTrue(build.dashboard_needs_build())
        self.mark_current()
        manifest = self.dashboard / "out" / build.MANIFEST
        for content in ("broken", "[]", "null", '{}', '{"schema":2}',
                        '{"schema":1}', '{"schema":1,"source_hash":"wrong"}'):
            with self.subTest(content=content):
                manifest.write_text(content)
                self.assertTrue(build.dashboard_needs_build())
        manifest.unlink()
        self.assertTrue(build.dashboard_needs_build())
        self.mark_current()
        (self.dashboard / "out/index.html").unlink()
        self.assertTrue(build.dashboard_needs_build())

    def test_force_rebuild(self):
        self.mark_current()
        with patch.object(build, "npm_needs_install", return_value=False), \
                patch.object(build, "_run_npm", side_effect=self.fake_build) as run:
            build.ensure_dashboard(force=True)
        run.assert_called_once()
        self.assertFalse(build.dashboard_needs_build())

    def test_failed_build_preserves_old_output_and_manifest(self):
        self.mark_current()
        manifest = (self.dashboard / "out" / build.MANIFEST).read_bytes()
        for effect in (RuntimeError("build failed"), lambda *args: None):
            with self.subTest(effect=effect), \
                    patch.object(build, "npm_needs_install", return_value=False), \
                    patch.object(build, "_run_npm", side_effect=effect):
                with self.assertRaises(RuntimeError):
                    build.ensure_dashboard(force=True)
            self.assertEqual((self.dashboard / "out/index.html").read_text(), "old dashboard")
            self.assertEqual((self.dashboard / "out" / build.MANIFEST).read_bytes(), manifest)
            self.assertTrue((self.dashboard / "node_modules").is_dir())

    def test_install_failure_aborts_before_build(self):
        with patch.object(build, "npm_needs_install", return_value=True), \
                patch.object(build, "_run_npm", side_effect=RuntimeError("install failed")), \
                patch.object(build, "build_dashboard") as compile_dashboard:
            with self.assertRaises(RuntimeError):
                build.ensure_dashboard()
        compile_dashboard.assert_not_called()

    def test_install_changes_are_included_in_manifest(self):
        def run(command, cwd):
            if command == "npm install":
                (self.dashboard / "package-lock.json").write_text('{"updated":true}')
            else:
                self.fake_build(command, cwd)
        with patch.object(build, "npm_needs_install", return_value=True), \
                patch.object(build, "_run_npm", side_effect=run):
            build.ensure_dashboard()
        self.assertFalse(build.dashboard_needs_build())

    def test_source_change_during_build_does_not_publish(self):
        self.mark_current()
        def run(command, cwd):
            self.fake_build(command, cwd)
            self.source.write_text("changed during build")
        with patch.object(build, "_run_npm", side_effect=run):
            with self.assertRaises(RuntimeError):
                build.build_dashboard()
        self.assertEqual((self.dashboard / "out/index.html").read_text(), "old dashboard")

    def test_failed_output_swap_restores_backup(self):
        self.mark_current()
        manifest = (self.dashboard / "out" / build.MANIFEST).read_bytes()
        rename = Path.rename
        def fail_publication(path, target):
            if path.name == "out" and path.parent.name.startswith(".orion-dashboard-"):
                raise OSError("output busy")
            return rename(path, target)
        with patch.object(build, "_run_npm", side_effect=self.fake_build), \
                patch.object(Path, "rename", fail_publication):
            with self.assertRaises(OSError):
                build.build_dashboard()
        self.assertEqual((self.dashboard / "out/index.html").read_text(), "old dashboard")
        self.assertEqual((self.dashboard / "out" / build.MANIFEST).read_bytes(), manifest)

    def test_cli_update_failure_is_nonzero(self):
        with patch.object(cli_update, "ROOT", self.root), \
                patch.object(cli_update, "check_for_updates", return_value={"update_available": True}), \
                patch.object(cli_update, "ensure_dashboard", side_effect=RuntimeError("build failed")):
            with self.assertRaises(SystemExit) as result:
                cli_update.main()
        self.assertEqual(result.exception.code, 1)

    def test_web_update_failure_does_not_restart_or_report_success(self):
        state = {"logs": [], "success": False, "is_updating": True, "error": None}
        with patch.object(updater, "ROOT", self.root), \
                patch.object(updater, "_UPDATE_STATE", state), \
                patch.object(build, "ensure_dashboard", side_effect=RuntimeError("build failed")), \
                patch.object(updater.logger, "error"):
            updater._perform_update_worker()
        self.assertFalse(state["success"])
        self.assertEqual(state["step"], "failed")
        self.assertIn("build failed", state["error"])
        self.assertFalse((self.root / ".restart_requested").exists())

    def test_web_backend_update_uses_fast_path(self):
        self.mark_current()
        state = {"logs": [], "success": False, "is_updating": True, "error": None}
        with patch.object(updater, "ROOT", self.root), \
                patch.object(updater, "_UPDATE_STATE", state), \
                patch.object(updater.threading, "Thread"), \
                patch.object(build, "npm_needs_install", side_effect=AssertionError("npm checked")):
            updater._perform_update_worker()
        self.assertTrue(state["success"])
        self.assertTrue(any("derleme atlandı" in line for line in state["logs"]))

    def test_cli_forwards_both_force_flags(self):
        for flag in ("--build", "--force-build"):
            with self.subTest(flag=flag), patch.object(sys, "argv", ["cli.py", "prod", flag]), \
                    patch.object(cli.subprocess, "run") as run:
                run.return_value.returncode = 0
                with self.assertRaises(SystemExit) as exit_result:
                    cli.main()
                self.assertEqual(exit_result.exception.code, 0)
                self.assertEqual(run.call_args.args[0][-1], flag)


if __name__ == "__main__":
    unittest.main()
