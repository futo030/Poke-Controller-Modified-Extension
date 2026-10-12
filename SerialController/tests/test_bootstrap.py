#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap(uv を探す、環境をそろえる、.venv の Python で起動し直す、移行の判断)のテスト
(uv は実行しない。何もダウンロードしない。画面も出さない)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPOSITORY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPOSITORY_DIR)

from bootstrap import __main__ as bootstrap_main  # noqa: E402
from bootstrap import added_libraries, environment, library_list, migrate, relaunch, uv_tool  # noqa: E402
from bootstrap.added_libraries import Candidate  # noqa: E402

BOOTSTRAP_DIR = os.path.join(REPOSITORY_DIR, "bootstrap")


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def touch(self, *parts, text=""):
        path = os.path.join(self.folder, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
        return path


@unittest.skipUnless(os.name == "nt", "Windows の置き場所で確かめる")
class FindUvTest(Folder):
    def environ(self, path=()):
        return {
            "LOCALAPPDATA": os.path.join(self.folder, "local"),
            "USERPROFILE": os.path.join(self.folder, "home"),
            "PATH": os.pathsep.join(path),
        }

    def test_the_place_in_the_receipt_comes_first(self):
        official = self.touch("tools", "uv.exe")
        self.touch("local", "uv", "uv-receipt.json", text=json.dumps({"install_prefix": os.path.dirname(official)}))
        other = self.touch("other", "uv.exe")
        environ = self.environ([os.path.dirname(other)])
        self.assertEqual(uv_tool.find_uv(environ), official)
        self.assertTrue(uv_tool.is_official(official, environ))
        self.assertFalse(uv_tool.is_official(other, environ))

    def test_the_default_place_is_used_without_a_receipt(self):
        official = self.touch("home", ".local", "bin", "uv.exe")
        self.assertEqual(uv_tool.find_uv(self.environ()), official)

    def test_a_broken_receipt_is_ignored(self):
        self.touch("local", "uv", "uv-receipt.json", text="{broken")
        self.assertIsNone(uv_tool.find_uv(self.environ()))

    def test_uv_installed_by_another_tool_is_found_on_path(self):
        # winget や scoop で入れた uv(pip に結び付いていない)は、使う
        other = self.touch("WinGet", "Links", "uv.exe")
        self.assertEqual(uv_tool.find_uv(self.environ([os.path.join(self.folder, "empty"), os.path.dirname(other)])), other)

    def test_uv_installed_by_pip_is_skipped(self):
        beside_python = self.touch("Python312", "Scripts", "uv.exe")
        self.touch("Python312", "python.exe")
        in_venv = self.touch("venv", "Scripts", "uv.exe")
        self.touch("venv", "pyvenv.cfg")
        user_site = self.touch("Roaming", "Python", "Python312", "Scripts", "uv.exe")
        self.touch("Roaming", "Python", "Python312", "site-packages", "uv-0.12.9.dist-info", "METADATA")
        for path in (beside_python, in_venv, user_site):
            self.assertTrue(uv_tool.is_pip_installed(path), path)
        good = self.touch("scoop", "shims", "uv.exe")
        self.assertFalse(uv_tool.is_pip_installed(good))
        path = [os.path.dirname(item) for item in (beside_python, in_venv, user_site, good)]
        self.assertEqual(uv_tool.find_uv(self.environ(path)), good)
        self.assertIsNone(uv_tool.find_uv(self.environ(path[:3])))


class UvVersionTest(Folder):
    def test_versions_are_read_from_the_output(self):
        self.assertEqual(uv_tool.parse_version("uv 0.13.0 (4ecd0eff2 2026-10-09 x86_64-pc-windows-msvc)"), (0, 13, 0))
        self.assertEqual(uv_tool.parse_version(""), ())
        self.assertLess(uv_tool.parse_version("uv 0.12.9"), uv_tool.parse_version("0.12.22"))

    def test_required_version_of_this_repository(self):
        self.assertEqual(uv_tool.required_version(REPOSITORY_DIR), (0, 12, 22))
        self.assertEqual(uv_tool.required_version(self.folder), ())

    def test_system_certificates_are_used_unless_the_user_set_it(self):
        self.assertEqual(uv_tool.uv_environment({})["UV_SYSTEM_CERTS"], "1")
        self.assertEqual(uv_tool.uv_environment({"UV_SYSTEM_CERTS": "0"})["UV_SYSTEM_CERTS"], "0")

    def ensure(self, found, versions, official=True, confirm=True, update_ok=True):
        versions = iter(versions)
        calls = []

        def run(uv, arguments, **options):
            calls.append(list(arguments))
            return mock.Mock(returncode=0 if update_ok else 1)

        with mock.patch.object(uv_tool, "find_uv", return_value=found), mock.patch.object(
            uv_tool, "version", side_effect=lambda uv: next(versions)
        ), mock.patch.object(uv_tool, "is_official", return_value=official), mock.patch.object(
            uv_tool, "run", side_effect=run
        ), mock.patch.object(uv_tool, "install", return_value="installed-uv") as install:
            result = uv_tool.ensure(REPOSITORY_DIR, lambda message: confirm, log=lambda text: None)
        return result, calls, install

    def test_a_new_enough_uv_is_used_as_it_is(self):
        result, calls, install = self.ensure("uv", [(0, 13, 0)])
        self.assertEqual((result, calls), ("uv", []))
        install.assert_not_called()

    def test_missing_uv_is_installed_only_after_asking(self):
        result, _, install = self.ensure(None, [(0, 13, 0)])
        self.assertEqual(result, "installed-uv")
        install.assert_called_once()
        with self.assertRaises(uv_tool.UvError):
            self.ensure(None, [(0, 13, 0)], confirm=False)

    def test_an_old_official_uv_updates_itself(self):
        result, calls, _ = self.ensure("uv", [(0, 12, 9), (0, 13, 0)])
        self.assertEqual((result, calls), ("uv", [["self", "update"]]))

    def test_an_old_uv_from_another_tool_is_left_to_the_user(self):
        with self.assertRaises(uv_tool.UvError) as raised:
            self.ensure("uv", [(0, 12, 9)], official=False)
        self.assertIn("0.12.22 以上", str(raised.exception))

    def test_a_failed_update_is_reported(self):
        with self.assertRaises(uv_tool.UvError):
            self.ensure("uv", [(0, 12, 9), (0, 12, 9)])


class EnvironmentTest(Folder):
    def make_venv(self):
        python = environment.venv_python(self.folder)
        os.makedirs(os.path.dirname(python))
        open(python, "w").close()

    def write_stamp(self):
        with open(os.path.join(self.folder, environment.VENV, environment.STAMP), "w", encoding="utf-8") as file:
            file.write(environment.sync_state(self.folder))

    def test_sync_is_needed_until_the_environment_is_made(self):
        self.assertTrue(environment.needs_sync(self.folder))
        self.make_venv()
        self.assertTrue(environment.needs_sync(self.folder))
        self.write_stamp()
        self.assertFalse(environment.needs_sync(self.folder))

    def test_sync_is_needed_when_a_setting_file_changes(self):
        self.touch("uv.lock", text="a\n")
        self.make_venv()
        self.write_stamp()
        self.touch("requirements-user.txt", text="numba\n")
        self.assertTrue(environment.needs_sync(self.folder))
        self.write_stamp()
        self.touch("uv.lock", text="b\n")
        self.assertTrue(environment.needs_sync(self.folder))

    def test_line_endings_do_not_matter(self):
        with open(os.path.join(self.folder, "uv.lock"), "wb") as file:
            file.write(b"a\nb\n")
        before = environment.sync_state(self.folder)
        with open(os.path.join(self.folder, "uv.lock"), "wb") as file:
            file.write(b"a\r\nb\r\n")
        self.assertEqual(environment.sync_state(self.folder), before)

    def test_user_requirements_skip_comments(self):
        self.touch("requirements-user.txt", text="# comment\n\nnumba\n  pyocr  \n")
        self.assertEqual(environment.user_requirements(self.folder), ["numba", "pyocr"])
        os.remove(os.path.join(self.folder, "requirements-user.txt"))
        self.assertEqual(environment.user_requirements(self.folder), [])

    def test_python_request_of_this_repository(self):
        self.assertEqual(environment.python_request(REPOSITORY_DIR), "3.13")

    def run_sync(self, fail=()):
        calls = []

        def run(uv, arguments, cwd=None, capture=False):
            calls.append(list(arguments))
            if arguments[0] == "sync":
                self.make_venv()
            failed = arguments[0] == "pip" and arguments[-1] in fail
            return mock.Mock(returncode=1 if failed else 0, stderr="error: no matching version\n", stdout="")

        with mock.patch.object(uv_tool, "run", side_effect=run):
            return environment.sync(self.folder, "uv", log=lambda text: None), calls

    def test_sync_keeps_user_libraries_and_the_locked_versions(self):
        self.touch(".python-version", text="3.13\n")
        self.touch("requirements-user.txt", text="numba\nbroken\n")
        failed, calls = self.run_sync(fail=("broken",))
        self.assertEqual(calls[0], ["python", "upgrade", "3.13"])
        # 利用者が足したライブラリを消さない
        self.assertEqual(calls[1], ["sync", "--inexact"])
        self.assertEqual(calls[2][:3], ["export", "--frozen", "--no-hashes"])
        installs = [call for call in calls if call[0] == "pip"]
        self.assertEqual([call[-1] for call in installs], ["numba", "broken"])
        # 本体のライブラリの版を変えない(合わないライブラリは、入れずに知らせる)
        self.assertTrue(all("--constraints" in call for call in installs))
        self.assertEqual(failed, [("broken", "error: no matching version")])
        self.assertIn("broken", environment.describe_failures(failed))
        self.assertFalse(environment.needs_sync(self.folder))

    def test_sync_fails_when_the_environment_is_not_made(self):
        with mock.patch.object(uv_tool, "run", return_value=mock.Mock(returncode=1, stderr="", stdout="")):
            with self.assertRaises(uv_tool.UvError):
                environment.sync(self.folder, "uv", log=lambda text: None)
        self.assertTrue(environment.needs_sync(self.folder))

    def test_ensure_does_nothing_when_up_to_date(self):
        self.make_venv()
        self.write_stamp()
        with mock.patch.object(uv_tool, "ensure", side_effect=AssertionError("uv は探さない")):
            self.assertEqual(environment.ensure(self.folder, lambda message: True), [])


class RelaunchTest(Folder):
    def test_relaunch_only_outside_an_existing_venv(self):
        self.assertFalse(relaunch.should_relaunch(self.folder, {}))
        python = environment.venv_python(self.folder)
        os.makedirs(os.path.dirname(python))
        open(python, "w").close()
        self.assertTrue(relaunch.should_relaunch(self.folder, {}))
        # 起動し直した先では、もう一度起動し直さない
        self.assertFalse(relaunch.should_relaunch(self.folder, {relaunch.RELAUNCHED: "1"}))
        with mock.patch.object(sys, "prefix", os.path.join(self.folder, environment.VENV)):
            self.assertFalse(relaunch.should_relaunch(self.folder, {}))

    def test_the_same_script_and_arguments_run_in_the_venv(self):
        with mock.patch.object(relaunch, "should_relaunch", return_value=True), mock.patch.object(
            relaunch.subprocess, "call", return_value=3
        ) as call, mock.patch.object(sys, "argv", ["Window.py", "--profile", "a"]):
            with self.assertRaises(SystemExit) as raised:
                relaunch.run_in_venv()
        self.assertEqual(raised.exception.code, 3)
        command = call.call_args.args[0]
        self.assertEqual(command[1:], ["Window.py", "--profile", "a"])
        self.assertEqual(command[0], environment.venv_python(environment.repository_dir()))
        self.assertEqual(call.call_args.kwargs["env"][relaunch.RELAUNCHED], "1")

    def test_nothing_happens_without_a_venv_or_when_it_cannot_start(self):
        with mock.patch.object(relaunch, "should_relaunch", return_value=False), mock.patch.object(
            relaunch.subprocess, "call", side_effect=AssertionError("起動しない")
        ):
            relaunch.run_in_venv()
        with mock.patch.object(relaunch, "should_relaunch", return_value=True), mock.patch.object(
            relaunch.subprocess, "call", side_effect=OSError("cannot start")
        ):
            relaunch.run_in_venv()


class MigrationTest(Folder):
    def test_offer_until_migrated_or_declined(self):
        self.assertFalse(migrate.should_offer(self.folder))  # pyproject.toml がない(古い版のフォルダー)
        self.touch("pyproject.toml")
        self.assertTrue(migrate.should_offer(self.folder))
        migrate.write_state(self.folder, {"migration_declined": True})
        self.assertFalse(migrate.should_offer(self.folder))
        migrate.write_state(self.folder, {})
        python = environment.venv_python(self.folder)
        os.makedirs(os.path.dirname(python))
        open(python, "w").close()
        self.assertFalse(migrate.should_offer(self.folder))

    def test_a_broken_state_file_is_ignored(self):
        self.touch(migrate.STATE_FILE, text="[1, 2")
        self.assertEqual(migrate.read_state(self.folder), {})

    def test_dedicated_python_is_next_to_the_repository(self):
        root = os.path.join(self.folder, "install", "Poke-Controller-Modified-Extension")
        self.assertTrue(migrate.is_dedicated_python(root, os.path.join(self.folder, "install", "python")))
        self.assertFalse(migrate.is_dedicated_python(root, os.path.join(self.folder, "Program Files", "Python312")))

    def test_only_libraries_used_by_scripts_are_selected_at_first(self):
        candidates = [Candidate("numba", ["Mine"]), Candidate("jupyter")]
        self.assertEqual(migrate.initial_selection(candidates, dedicated=False), [True, False])
        self.assertEqual(migrate.initial_selection(candidates, dedicated=True), [True, True])


class LibraryListTest(unittest.TestCase):
    installed = {
        "numpy": ("numpy", "2.5.4"),
        "pillow": ("Pillow", "12.3.0"),
        "numba": ("numba", "0.70.0"),
        "llvmlite": ("llvmlite", "0.50.0"),
        "tzdata": ("tzdata", "2026.5"),
    }

    def test_libraries_are_grouped(self):
        parts = library_list.sections(["numpy", "pillow", "opencv-python"], ["numba", "pyocr", "numpy", "numba"], self.installed)
        self.assertEqual([title.split("(")[0] for title, _ in parts], ["本体が使うライブラリ", "自分で足したライブラリ", "そのほか"])
        # 本体の分は、pyproject.toml の順。入っていないものは、版が None
        self.assertEqual(parts[0][1], [("numpy", "2.5.4"), ("Pillow", "12.3.0"), ("opencv-python", None)])
        # 足した分に、本体の分と同じ名前や、同じ名前の重複があっても、1 回だけ
        self.assertEqual(parts[1][1], [("numba", "0.70.0"), ("pyocr", None)])
        self.assertEqual(parts[2][1], [("llvmlite", "0.50.0"), ("tzdata", "2026.5")])

    def test_report_shows_versions_and_missing_libraries(self):
        parts = library_list.sections(["numpy"], ["pyocr"], self.installed)
        text = library_list.format_report("3.13.16", "C:/tool/.venv", parts)
        self.assertIn("Python 3.13.16", text)
        self.assertIn("環境: C:/tool/.venv", text)
        self.assertIn("■ 本体が使うライブラリ: 1 個", text)
        self.assertRegex(text, r"numpy +2\.5\.4")
        self.assertRegex(text, r"pyocr +\(入っていません\)")
        self.assertIn("PokeConExtension_AddLibrary.bat", text)

    def test_an_empty_group_says_so(self):
        text = library_list.format_report("3.13.16", "x", library_list.sections(["numpy"], [], {"numpy": ("numpy", "2.5.4")}))
        self.assertIn("■ 自分で足したライブラリ(requirements-user.txt): 0 個\n  (ありません)", text)

    def test_report_runs_on_this_repository(self):
        text = library_list.report(REPOSITORY_DIR)
        self.assertEqual(library_list.project_requirements(REPOSITORY_DIR)[0], "opencv-python")
        self.assertIn("■ 本体が使うライブラリ: 18 個", text)


class AddAndRemoveLibraryTest(Folder):
    def setUp(self):
        super().setUp()
        self.said = []
        for target, name, value in (
            (uv_tool, "ensure", lambda root, confirm, log=None: "uv"),
            (uv_tool, "say", self.said.append),
            (environment, "mark_synced", lambda root: self.marked.append(root)),
        ):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.marked = []

    def listed(self):
        return environment.user_requirements(self.folder)

    def add(self, names, failed=(), error=None):
        def sync(root, uv, log=None):
            if error is not None:
                raise error
            return [(name, "error: not found") for name in self.listed() if name in failed]

        with mock.patch.object(environment, "sync", side_effect=sync), mock.patch("builtins.print"):
            return bootstrap_main.add_library(self.folder, list(names))

    def test_a_library_that_cannot_be_installed_is_not_kept_in_the_list(self):
        # 以前は、名前を間違えたライブラリが一覧に残り、そろえ直すたびに、もう一度試して知らされた
        self.assertEqual(self.add(["numba", "win32gui"], failed=("win32gui",)), 1)
        self.assertEqual(self.listed(), ["numba"])
        self.assertTrue(any("win32gui" in text and "残していません" in text for text in self.said))
        self.assertTrue(any(text == "追加しました: numba" for text in self.said))
        # 一覧を書き直した後の内容で、そろえ終えたことを覚える(次の起動で、そろえ直さない)
        self.assertEqual(self.marked, [self.folder])

    def test_a_library_that_was_already_in_the_list_stays(self):
        # 移行のときに引き継いだものなどは、今は入らなくても、一覧に残す(後で、合う版が出ることがある)
        self.touch("requirements-user.txt", text="oldlib\n")
        self.assertEqual(self.add(["numba"], failed=("oldlib",)), 0)
        self.assertEqual(self.listed(), ["oldlib", "numba"])

    def test_nothing_is_kept_when_the_environment_cannot_be_prepared(self):
        self.touch("requirements-user.txt", text="oldlib\n")
        self.assertEqual(self.add(["numba"], error=uv_tool.UvError("no network")), 1)
        self.assertEqual(self.listed(), ["oldlib"])

    def remove(self, names, uninstall_fails=()):
        calls = []

        def uninstall(root, uv, targets):
            calls.append(list(targets))
            return [(name, "error") for name in targets if name in uninstall_fails]

        with mock.patch.object(environment, "uninstall", side_effect=uninstall), mock.patch.object(
            library_list, "project_requirements", return_value=["numpy"]
        ), mock.patch("builtins.print") as printed:
            code = bootstrap_main.remove_library(self.folder, list(names))
        return code, calls, " ".join(str(call.args[0]) for call in printed.call_args_list if call.args)

    def test_remove_takes_the_library_out_of_the_list_and_the_environment(self):
        self.touch("requirements-user.txt", text="# comment\nnumba\nwin32gui\nNumPy\n")
        code, calls, printed = self.remove(["win32gui", "numpy", "typo"])
        self.assertEqual(code, 0)
        self.assertEqual(self.listed(), ["numba"])
        # 本体が使うライブラリは、一覧からは外すが、.venv からは外さない
        self.assertEqual(calls, [["win32gui"]])
        self.assertIn("typo", printed)
        self.assertEqual(self.marked, [self.folder])

    def test_remove_reports_names_that_are_not_in_the_list(self):
        self.touch("requirements-user.txt", text="numba\n")
        code, calls, printed = self.remove(["other"])
        self.assertEqual((code, calls, self.listed()), (1, [], ["numba"]))
        self.assertIn("一覧にない名前", printed)

    def test_remove_says_so_when_nothing_was_added(self):
        code, calls, printed = self.remove(["numba"])
        self.assertEqual((code, calls), (0, []))
        self.assertIn("ありません", printed)

    def test_remove_user_requirements_keeps_comments_and_other_lines(self):
        self.touch("requirements-user.txt", text="# 自分で足したライブラリ\nnumba\nPy_OCR>=0.8\n")
        self.assertEqual(added_libraries.remove_user_requirements(self.folder, ["py-ocr"]), ["py-ocr"])
        with open(os.path.join(self.folder, "requirements-user.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "# 自分で足したライブラリ\nnumba\n")
        self.assertEqual(added_libraries.remove_user_requirements(self.folder, ["missing"]), [])


class FilesTest(unittest.TestCase):
    def test_bootstrap_uses_only_the_standard_library(self):
        # 本体のコードも、追加のライブラリも読み込まない(uv の環境ができる前の Python から呼ぶため)
        for name in sorted(os.listdir(BOOTSTRAP_DIR)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(BOOTSTRAP_DIR, name), encoding="utf-8") as file:
                tree = ast.parse(file.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    tops = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    tops = [(node.module or "").split(".")[0]]
                else:
                    continue
                for top in tops:
                    self.assertTrue(top in sys.stdlib_module_names or top == "bootstrap", f"{name}: {top}")

    def test_setup_script_can_be_read_by_windows_powershell(self):
        with open(os.path.join(BOOTSTRAP_DIR, "setup.ps1"), "rb") as file:
            data = file.read()
        # BOM がないと、Windows PowerShell 5.1 は日本語を読み違える
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"uv-receipt.json", data)

    def test_installer_is_a_batch_file_followed_by_powershell(self):
        with open(os.path.join(REPOSITORY_DIR, "PokeConExtension_Install.bat"), "rb") as file:
            data = file.read()
        # BOM があると、cmd が 1 行目を読み違える。LF だけの行があると、bat として正しく動かない
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        marker = b"\r\n#PS1-BEGIN\r\n"
        self.assertEqual(data.count(b"#PS1-BEGIN"), 1)
        batch, script = data.split(marker)
        # cmd が読む部分は ASCII だけ。目印より後ろは、UTF-8 の PowerShell
        batch.decode("ascii")
        self.assertTrue(batch.decode("ascii").splitlines()[-1].endswith("exit /b"))
        self.assertIn("'#PS' + '1-BEGIN'", batch.decode("ascii"))
        self.assertIn("releases/latest", script.decode("utf-8"))

    def test_batch_files_are_ascii_and_finish_on_one_line(self):
        names = ("PokeConExtension.bat", "PokeConExtension_Monitor.bat", "PokeConExtension_AddLibrary.bat", "PokeConExtension_ListLibraries.bat",
                 "PokeConExtension_RemoveLibrary.bat")  # fmt: skip
        for name in names:
            with open(os.path.join(REPOSITORY_DIR, name), "rb") as file:
                data = file.read()
            data.decode("ascii")
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)
            # 実行中に更新でファイルが入れ替わっても続きを読まないように、起動から終了までを 1 行に書く
            last = data.decode("ascii").strip().splitlines()[-1]
            self.assertIn("-m bootstrap", last)
            self.assertTrue(last.endswith("& pause & exit /b"), name)


if __name__ == "__main__":
    unittest.main()
