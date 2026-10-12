#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web ブラウザ版の Serial タブ・Log タブに送る内容(web/server.py)のテスト(サーバーもブラウザも起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import log_buffer, note_store  # noqa: E402
from services.settings_store import AppSettings  # noqa: E402
from services.log_buffer import LogBuffer  # noqa: E402
from services.serial_monitor import SerialMonitor  # noqa: E402
from web import server as web_server  # noqa: E402


class LineBacklogTest(unittest.TestCase):
    def test_entries_are_kept_in_order(self):
        backlog = web_server.LineBacklog(max_lines=10)
        backlog.add("debug", "a\nb\n")
        backlog.add("error", "c\n")
        self.assertEqual(backlog.entries(), [["debug", "a\nb\n"], ["error", "c\n"]])

    def test_old_entries_are_dropped_over_the_limit(self):
        backlog = web_server.LineBacklog(max_lines=3)
        for i in range(6):
            backlog.add("", f"line {i}\n")
        self.assertEqual([text for _, text in backlog.entries()], ["line 3\n", "line 4\n", "line 5\n"])

    def test_one_long_entry_is_kept(self):
        backlog = web_server.LineBacklog(max_lines=2)
        backlog.add("", "a\nb\nc\nd\n")
        self.assertEqual(len(backlog.entries()), 1)

    def test_clear_and_copies(self):
        backlog = web_server.LineBacklog()
        backlog.add("", "a\n")
        backlog.entries()[0][1] = "changed"
        self.assertEqual(backlog.entries(), [["", "a\n"]])
        backlog.clear()
        self.assertEqual(backlog.entries(), [])


class ViewMessagesTest(unittest.TestCase):
    def setUp(self):
        self.buffer = LogBuffer(max_lines=100, drain_limit=100)
        patcher = mock.patch.object(log_buffer, "buffer", self.buffer)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.logger = logging.Logger("test.web_views", logging.DEBUG)
        self.logger.addHandler(self.buffer)
        self.app = web_server.WebApp(lambda gui: None, 0)
        self.monitor = SerialMonitor()
        self.app.core = SimpleNamespace(sender=SimpleNamespace(monitor=self.monitor))
        self.posted = []
        self.app.hub.post = self.posted.append
        self.app.hub.clients = [object()]
        # Note は、一時フォルダーのファイルに読み書きする(本物のプロファイルのファイルには、触れない)
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        patcher = mock.patch.object(AppSettings, "SETTING_PATH", os.path.join(self.folder, "profile", "settings.ini"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nothing_is_sent_when_nothing_happened(self):
        self.assertEqual(self.app._view_messages(), [])

    def test_serial_and_log_are_sent_and_kept_for_later_browsers(self):
        self.monitor.add("Default", "0x0004 8")
        self.logger.debug("d1")
        self.logger.debug("d2")
        self.logger.error("e1")
        messages = self.app._view_messages()
        self.assertEqual([m["type"] for m in messages], ["serial", "log"])
        self.assertTrue(messages[0]["text"].endswith("[Default] 0x0004 8\n"))
        self.assertIs(messages[0]["clear"], False)
        self.assertEqual([group for group, _ in messages[1]["segments"]], ["debug", "error"])
        self.assertEqual(messages[1]["segments"][0][1].count("\n"), 2)
        # 2 回目は、新しい分だけ
        self.assertEqual(self.app._view_messages(), [])
        # あとから開いたブラウザには、それまでの内容を、消してから書く形で送る
        backlog = self.app._view_backlog_messages()
        self.assertEqual([(m["type"], m.get("clear")) for m in backlog], [("serial", True), ("log", True), ("note", None)])
        self.assertEqual(backlog[0]["text"], messages[0]["text"])
        self.assertEqual(backlog[1]["segments"], messages[1]["segments"])

    def test_nothing_is_drained_while_no_browser_is_open(self):
        self.app.hub.clients = []
        self.monitor.add("Default", "x")
        self.logger.info("kept")
        self.assertEqual(self.app._view_messages(), [])
        self.assertEqual(len(self.buffer), 1)
        # ブラウザが開くと、溜まっていた分が届く
        self.app.hub.clients = [object()]
        self.assertEqual([m["type"] for m in self.app._view_messages()], ["serial", "log"])

    def test_core_without_a_serial_monitor(self):
        self.app.core = SimpleNamespace(sender=SimpleNamespace())
        self.logger.info("log only")
        self.assertEqual([m["type"] for m in self.app._view_messages()], ["log"])
        self.app._clear_view("serial")
        self.assertEqual(self.posted, [{"type": "serial", "clear": True, "text": ""}])

    def test_clear_serial(self):
        self.monitor.add("Default", "old")
        self.app._view_messages()
        self.monitor.add("Default", "not sent yet")
        self.app._clear_view("serial")
        self.assertEqual(self.posted, [{"type": "serial", "clear": True, "text": ""}])
        self.assertEqual(self.app._view_backlog_messages()[0]["text"], "")
        self.assertEqual(self.app._view_messages(), [])

    def test_clear_log(self):
        self.logger.info("old")
        self.app._view_messages()
        self.logger.info("not sent yet")
        self.app._clear_view("log")
        self.assertEqual(self.posted, [{"type": "log", "clear": True, "segments": []}])
        self.assertEqual(self.app._view_backlog_messages()[1]["segments"], [])
        self.assertEqual(self.app._view_messages(), [])

    def test_note_is_loaded_saved_and_sent_to_the_browsers(self):
        self.assertEqual(self.app._view_backlog_messages()[2], {"type": "note", "text": "", "saved": False})
        self.app._handle_action({"action": "note_save", "text": "色違い 3 匹目\nメモ"}, lambda data: None)
        self.assertEqual(self.posted, [{"type": "note", "text": "色違い 3 匹目\nメモ", "saved": True}])
        self.assertEqual(note_store.load(), "色違い 3 匹目\nメモ")
        self.assertTrue(note_store.note_path().startswith(self.folder))
        # あとから開いたブラウザにも、保存した内容が届く。起動し直した場合は、ファイルから読む
        self.assertEqual(self.app._view_backlog_messages()[2]["text"], "色違い 3 匹目\nメモ")
        self.app.note_text = None
        self.assertEqual(self.app._view_backlog_messages()[2]["text"], "色違い 3 匹目\nメモ")

    def test_note_that_is_not_text_or_too_long_is_not_saved(self):
        for text in (None, 123, ["a"], "x" * (web_server.NOTE_MAX_LENGTH + 1)):
            self.app._handle_action({"action": "note_save", "text": text}, lambda data: None)
        self.assertEqual(self.posted, [])
        self.assertFalse(os.path.exists(note_store.note_path()))

    def test_note_is_not_saved_by_a_read_only_instance(self):
        with mock.patch.object(web_server.Profile, "is_read_only", lambda: True):
            self.app._handle_action({"action": "note_save", "text": "x"}, lambda data: None)
        self.assertFalse(os.path.exists(note_store.note_path()))
        self.assertEqual(self.posted, [{"type": "note", "text": "x", "saved": True}])

    def test_release_all_action(self):
        calls = []
        self.app.core.release_all_inputs = lambda: calls.append("released")
        self.app._handle_action({"action": "release_all"}, lambda data: None)
        self.assertEqual(calls, ["released"])

    def test_unknown_view_is_ignored(self):
        self.app._clear_view("pages")
        self.app._clear_view(None)
        self.assertEqual(self.posted, [])

    def test_clear_view_action(self):
        self.logger.info("x")
        self.app._view_messages()
        self.app._handle_action({"action": "clear_view", "view": "log"}, lambda data: None)
        self.assertEqual(self.posted, [{"type": "log", "clear": True, "segments": []}])

    def test_messages_can_be_sent_as_json(self):
        import json

        self.monitor.add("NX", b"\x01\x02")
        self.logger.warning("警告 %s", "あ")
        json.dumps(self.app._view_messages() + self.app._view_backlog_messages(), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
