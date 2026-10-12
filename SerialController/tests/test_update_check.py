#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/update_check.py(更新の確認)と、起動前の PokeConUpdateChecker.py のテスト(画面を起動せず、通信もしない)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constant  # noqa: E402
from services import update_check  # noqa: E402
from services.update_check import Release  # noqa: E402


def opener(data=None, error=None):
    """GitHub の API の代役(data を JSON で返す。error があれば、それを送出する)"""

    def open_url(request, timeout=None):
        open_url.requests.append((request.full_url, timeout))
        if error is not None:
            raise error
        return contextlib.closing(io.BytesIO(json.dumps(data).encode("utf-8")))

    open_url.requests = []
    return open_url


def not_found():
    return urllib.error.HTTPError(update_check.LATEST_RELEASE_API, 404, "Not Found", None, None)


class VersionTest(unittest.TestCase):
    def test_tags_are_compared_as_numbers(self):
        self.assertEqual(update_check.parse_version("v0.2.1"), (0, 2, 1))
        self.assertEqual(update_check.parse_version("0.10.0"), (0, 10, 0))
        self.assertLess(update_check.parse_version("v0.2.9"), update_check.parse_version("v0.10.0"))
        # upstream 由来のタグのような、形の違う名前は、版として扱わない
        for text in ("", "v1.0-alpha", "version3.0.2.8", "latest"):
            self.assertEqual(update_check.parse_version(text), (), text)

    def test_current_tag_is_made_from_the_application_version(self):
        self.assertEqual(update_check.current_tag(), f"v{Constant.VERSION}")
        self.assertEqual(update_check.zip_url("v0.2.1"), f"https://github.com/{update_check.REPOSITORY}/archive/refs/tags/v0.2.1.zip")


class FindUpdateTest(unittest.TestCase):
    def find(self, tag, current="0.2.0"):
        api = opener({"tag_name": tag, "html_url": "https://example.invalid/release"})
        with mock.patch.object(Constant, "VERSION", current):
            return update_check.find_update(api), api

    def test_a_newer_release_is_an_update(self):
        release, api = self.find("v0.2.1")
        self.assertEqual(release, Release("v0.2.1", (0, 2, 1), "https://example.invalid/release"))
        self.assertTrue(release.zip_url.endswith("/v0.2.1.zip"))
        self.assertEqual(api.requests, [(update_check.LATEST_RELEASE_API, update_check.TIMEOUT)])

    def test_the_same_or_an_older_release_is_not_an_update(self):
        # 以前は、手元の方が進んでいても「更新あり」になった
        self.assertIsNone(self.find("v0.2.0")[0])
        self.assertIsNone(self.find("v0.1.9")[0])
        self.assertIsNone(self.find("v0.2.1", current="0.3.0")[0])

    def test_no_release_yet_is_not_an_error(self):
        self.assertIsNone(update_check.find_update(opener(error=not_found())))

    def test_failures_are_reported(self):
        for error in (
            urllib.error.HTTPError(update_check.LATEST_RELEASE_API, 403, "rate limit", None, None),
            urllib.error.URLError("certificate verify failed"),
            TimeoutError("timed out"),
        ):
            with self.assertRaises(update_check.UpdateCheckError):
                update_check.find_update(opener(error=error))
        for data in ({"tag_name": "nightly"}, {}, ["unexpected"]):
            with self.assertRaises(update_check.UpdateCheckError):
                update_check.find_update(opener(data))


class CheckTest(unittest.TestCase):
    def check(self, result):
        printed = io.StringIO()
        with mock.patch.object(update_check, "find_update", side_effect=result), contextlib.redirect_stdout(printed):
            return update_check.check("ignored"), printed.getvalue()

    def test_results_keep_the_values_used_by_the_screens(self):
        self.assertEqual(self.check([None])[0], "0")
        status, text = self.check([Release("v9.0.0", (9, 0, 0), "url")])
        self.assertEqual(status, "1")
        self.assertIn("v9.0.0", text)

    def test_the_reason_of_a_failure_is_logged(self):
        with self.assertLogs("services.update_check", level="WARNING") as logs:
            self.assertEqual(self.check(update_check.UpdateCheckError("no network"))[0], "-1")
        self.assertIn("no network", logs.output[0])


class UpdateCheckerScriptTest(unittest.TestCase):
    """起動前に実行する PokeConUpdateChecker.py"""

    def load(self):
        sys.modules.pop("PokeConUpdateChecker", None)
        self.addCleanup(sys.modules.pop, "PokeConUpdateChecker", None)
        with contextlib.redirect_stdout(io.StringIO()):
            module = importlib.import_module("PokeConUpdateChecker")
            return module, module.PokeConUpdateCheck()

    def test_it_works_without_git(self):
        # 以前は、先頭で GitPython を読み込んでいたので、git がないと、これを読み込むメニューバーごと起動できなかった
        with mock.patch.dict(sys.modules, {"git": None}):
            module, checker = self.load()
            self.assertFalse(checker.uses_git())
            with mock.patch.object(update_check, "find_update", return_value=None), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(checker.check_repository_updates(), "0")

    def test_a_folder_without_dot_git_is_updated_with_the_zip(self):
        module, checker = self.load()
        checker.pokecon_path = os.path.dirname(os.path.abspath(__file__))  # .git のないフォルダー
        self.assertFalse(checker.uses_git())
        release = Release("v9.0.0", (9, 0, 0), "url")
        with mock.patch.object(module.release_update, "update", return_value="result") as update:
            self.assertEqual(checker.update_with_zip(release), "result")
        self.assertEqual(update.call_args.args, (checker.pokecon_path, update_check.zip_url(update_check.current_tag()), release.zip_url))

    def test_a_failed_pull_is_not_reported_as_success(self):
        # 以前は、手元の変更以外の理由で pull が失敗しても、「更新が完了しました。」と表示された
        class GitCommandError(Exception):
            stderr = "fatal: unable to access the repository"

        class Repo:
            def __init__(self, path):
                self.git = mock.Mock()
                self.git.pull.side_effect = GitCommandError()

        git = mock.Mock(Repo=Repo, GitCommandError=GitCommandError)
        module, checker = self.load()
        with mock.patch.dict(sys.modules, {"git": git}), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(GitCommandError):
                checker.update_with_git()
            with self.assertRaises(GitCommandError):
                checker.git_pull()

    def test_files_changed_by_the_user_are_listed_from_the_git_message(self):
        class GitCommandError(Exception):
            stderr = (
                "error: Your local changes to the following files would be overwritten by merge:\n"
                "\tSerialController/Window.py\n\tREADME.md\n"
                "Please commit your changes or stash them before you merge.\nAborting\n"
            )

        class Repo:
            def __init__(self, path):
                self.git = mock.Mock()
                self.git.pull.side_effect = GitCommandError()

        module, checker = self.load()
        with mock.patch.dict(sys.modules, {"git": mock.Mock(Repo=Repo, GitCommandError=GitCommandError)}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(checker.get_conflicting_files(), ["SerialController/Window.py", "README.md"])

    def test_uv_is_required_from_the_next_minor_version(self):
        module, _ = self.load()
        self.assertEqual(module.UV_REQUIRED_FROM, (0, 3, 0))
        self.assertLess(update_check.current_version(), module.UV_REQUIRED_FROM)
        self.assertFalse(module.uv_environment_ready(os.path.dirname(os.path.abspath(__file__))))


if __name__ == "__main__":
    unittest.main()
