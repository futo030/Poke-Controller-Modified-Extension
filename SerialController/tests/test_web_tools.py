#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 版のツールの画面(タグの編集・新しい自動化スクリプトをつくる・Keyboard・モニター)のテスト

- 画面を持たない中身: services/tag_session.py、services/keyboard_session.py、services/monitor_relay.py
- 補助ツール(Monitor.py)とのつなぎ役: web/monitor_link.py
- サーバー(web/server.py)の操作: 実際に起動し、ブラウザの代わりにつないで確かめる
  (fastapi / uvicorn / websockets が無い環境では飛ばす)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Profile  # noqa: E402
import test_web  # noqa: E402
from CommandLoader import CommandLoader  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from Commands.PythonCommandBase import PythonCommand  # noqa: E402
from Commands.SwitchKeyboard import KEY  # noqa: E402
from services import command_service, monitor_relay, script_creator  # noqa: E402
from services import switch_keyboard_layout as layout  # noqa: E402
from services.keyboard_session import READY_MESSAGE, KeyboardSession  # noqa: E402
from services.monitor_client import MonitorConnection  # noqa: E402
from services.monitor_relay import MonitorRelay  # noqa: E402
from services.monitor_server import MonitorServer  # noqa: E402
from services.script_creator import ScriptSpec  # noqa: E402
from services.tag_session import TagEditorSession  # noqa: E402
from web.monitor_link import WebMonitorLink  # noqa: E402

COMMANDS = '''from Commands.PythonCommandBase import PythonCommand


class Mash(PythonCommand):
    NAME = "A連打"
    TAGS = ["連打", "基本"]

    def do(self):
        pass


class Computed(PythonCommand):
    NAME = "計算"
    TAGS = ["a"] + ["b"]

    def do(self):
        pass
'''


def wait_until(condition, timeout: float = 5.0) -> bool:
    """condition が真になるまで待つ(真になったか)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())


class CommandFolder(unittest.TestCase):
    """一時フォルダーに、コマンドのファイルを置く(Commands/PythonCommands/Sub/command.py)"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.folder = os.path.join(self.base, "Commands", "PythonCommands", "Sub")
        os.makedirs(self.folder)
        self.path = os.path.join(self.folder, "command.py")
        with open(self.path, "w", encoding="utf-8", newline="") as file:
            file.write(COMMANDS.replace("\n", "\r\n"))
        original = os.getcwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, original)
        self.loader = CommandLoader(os.path.join("Commands", "PythonCommands"), PythonCommand)
        self.entries = self.loader.load()
        self.reloads = 0

    def get_entries(self, command_type: str) -> list:
        return self.entries if command_type == "Python" else []

    def reload(self) -> None:
        self.reloads += 1
        self.entries = self.loader.reload()

    def read(self) -> str:
        with open(self.path, encoding="utf-8", newline="") as file:
            return file.read()


class TagSessionTest(CommandFolder):
    def setUp(self):
        super().setUp()
        self.session = TagEditorSession(self.get_entries, self.reload)

    def rows(self, state: dict) -> dict:
        return {row["name"]: row for row in state["commands"]["Python"]}

    def test_load_returns_tags_and_whether_they_can_be_edited(self):
        state = self.session.load()
        self.assertEqual(state["types"], ["Python", "Mcu"])
        self.assertEqual(state["commands"]["Mcu"], [])
        rows = self.rows(state)
        mash = rows["A連打 (Sub/command)"]
        self.assertEqual((mash["tags"], mash["folder_tags"], mash["editable"]), (["連打", "基本"], ["@Sub"], True))
        computed = rows["計算 (Sub/command)"]
        self.assertFalse(computed["editable"])
        self.assertIn("編集できません", computed["reason"])
        json.dumps(state)

    def test_save_rewrites_only_the_tags_and_reloads_the_list(self):
        self.session.load()
        result = self.session.save([{"command_type": "Python", "name": "A連打 (Sub/command)", "tags": ["基本", "新しい"]}])
        self.assertEqual((result["saved"], result["failures"], result["kept"]), (1, [], []))
        self.assertIn('TAGS = ["基本", "新しい"]\r\n', self.read())
        self.assertEqual(self.reloads, 1)
        self.assertEqual(self.rows(result["state"])["A連打 (Sub/command)"]["tags"], ["基本", "新しい"])
        # 変わっていないものは、書かない
        before = self.read()
        result = self.session.save([{"command_type": "Python", "name": "A連打 (Sub/command)", "tags": ["基本", "新しい"]}])
        self.assertEqual((result["saved"], self.read()), (0, before))

    def test_file_changed_after_loading_is_not_overwritten(self):
        self.session.load()
        with open(self.path, "a", encoding="utf-8", newline="") as file:
            file.write("# changed\r\n")
        before = self.read()
        result = self.session.save([{"command_type": "Python", "name": "A連打 (Sub/command)", "tags": ["x"]}])
        self.assertEqual((result["saved"], result["kept"]), (0, []))
        self.assertIn("書き換えられています", result["failures"][0])
        self.assertEqual(self.read(), before)
        # 読み直した後は、保存できる
        result = self.session.save([{"command_type": "Python", "name": "A連打 (Sub/command)", "tags": ["x"]}])
        self.assertEqual(result["saved"], 1)

    def test_locked_file_keeps_the_change(self):
        self.session.load()
        os.chmod(self.path, 0o444)
        self.addCleanup(os.chmod, self.path, 0o666)
        result = self.session.save([{"command_type": "Python", "name": "A連打 (Sub/command)", "tags": ["x"]}])
        self.assertEqual(result["saved"], 0)
        self.assertEqual(result["kept"], [["Python", "A連打 (Sub/command)"]])

    def test_bad_changes_are_refused(self):
        self.session.load()
        before = self.read()
        name = "A連打 (Sub/command)"
        for tags in (["@folder"], ["a", "a"], [" a"], [""], ["a\nb"], "a", [1], ["@Sub"]):
            result = self.session.save([{"command_type": "Python", "name": name, "tags": tags}])
            self.assertEqual((result["saved"], len(result["failures"])), (0, 1), tags)
        result = self.session.save([{"command_type": "Python", "name": "計算 (Sub/command)", "tags": ["x"]}])
        self.assertIn("編集できません", result["failures"][0])
        result = self.session.save([{"command_type": "Python", "name": "ない", "tags": ["x"]}, "bad", None])
        self.assertIn("見つかりません", result["failures"][0])
        self.assertEqual(self.session.save("bad")["saved"], 0)
        self.assertEqual(self.read(), before)


class PreviewLinesTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)
        os.makedirs(os.path.join(self.base, "Commands", "PythonCommands", "Old"))
        os.makedirs(os.path.join(self.base, "Template", "old"))

    def lines(self, **values) -> list:
        spec = ScriptSpec(**{"name": "テスト", "file_name": "my_script", **values}).normalized()
        return script_creator.preview_lines(spec, self.base)

    def test_shows_the_files_to_be_created(self):
        self.assertEqual(
            self.lines(folder="New", template_folder="my_script"),
            [
                "作るファイル: Commands/PythonCommands/New/my_script.py",
                "画像のフォルダー: Template/my_script(新しく作ります)",
                "一緒に作るファイル: README.md、License.txt(スクリプトと同じフォルダー)",
            ],
        )
        self.assertEqual(self.lines(template_folder="old")[1], "画像のフォルダー: Template/old")
        lines = self.lines(folder="Old", use_bridge=True, template_folder="img", template_location=script_creator.IN_SCRIPT_FOLDER)
        self.assertEqual(lines[1], "画像のフォルダー: Commands/PythonCommands/Old/img(新しく作ります)")
        for name in (script_creator.README_NAME, script_creator.LICENSE_NAME):
            open(os.path.join(self.base, "Commands", "PythonCommands", "Old", name), "w").close()
        self.assertEqual(self.lines(folder="Old")[-1], "README.md と License.txt は、すでにあるので、作りません")

    def test_nothing_while_the_input_is_not_valid(self):
        self.assertEqual(self.lines(file_name=""), [])
        self.assertEqual(self.lines(file_name="日本語"), [])
        self.assertEqual(self.lines(folder="a:b"), [])
        # 画像の保存先だけが正しくないときは、その行を出さない
        self.assertEqual(len(self.lines(template_folder="a:b")), 2)


class FakeTyper:
    """送信の処理の代役(頼まれたことを、記録するだけ)"""

    def __init__(self, reason: str = ""):
        self.reason = reason
        self.calls = []
        self.closed = False

    def unavailable_reason(self) -> str:
        return self.reason

    def type_text(self, text, label=None, mode=None):
        self.calls.append(("text", text, label, mode))
        return True

    def type_segments(self, segments, label):
        self.calls.append(("segments", segments, label))
        return True

    def set_mode(self, mode, label=None):
        self.calls.append(("mode", mode, label))
        return True

    def forget_mode(self):
        self.calls.append(("forget",))

    def type_key(self, key, label=None):
        self.calls.append(("key", int(key), label))
        return True

    def press_button(self):
        self.calls.append(("button",))
        return True

    def close(self):
        self.closed = True


class KeyboardSessionTest(unittest.TestCase):
    def setUp(self):
        self.typer = FakeTyper()
        self.messages = []
        self.session = KeyboardSession(None, on_message=lambda text, error: self.messages.append((text, error)), typer=self.typer)

    def test_layout_state(self):
        state = KeyboardSession.layout_state()
        self.assertEqual([page["id"] for page in state["pages"]], list(layout.PAGES))
        self.assertEqual([page["label"] for page in state["pages"]], ["あ", "ア", "a", "A", "1#※"])
        self.assertEqual([page["kana"] for page in state["pages"]], [True, True, False, False, False])
        for rows in list(state["rows"].values()) + list(state["small_rows"].values()):
            self.assertEqual([len(row) for row in rows], [layout.COLUMNS] * layout.ROWS)
        self.assertEqual(state["rows"]["hiragana"][0][0], {"c": "「", "ok": True})
        self.assertIsNone(state["rows"]["hiragana"][1][3])
        self.assertEqual(state["rows"]["symbol"][4][5], {"c": "※", "ok": False})
        self.assertEqual(sorted(state["small_rows"]), ["hiragana", "katakana"])
        json.dumps(state)

    def test_availability(self):
        self.assertEqual(self.session.availability(), (READY_MESSAGE, False))
        self.typer.reason = "未接続"
        self.assertEqual(self.session.availability(), ("未接続", True))

    def test_keys_are_typed_in_the_mode_of_the_page(self):
        self.assertTrue(self.session.press("hiragana", False, 0, 10, True))
        self.assertTrue(self.session.press("katakana", True, 0, 10, True))
        self.assertTrue(self.session.press("upper", False, 0, 0, True))
        self.assertTrue(self.session.press("symbol", False, 4, 4, True))
        self.assertTrue(self.session.press("hiragana", False, 0, 10, False))
        self.assertEqual(
            self.typer.calls,
            [
                ("text", "a", "あ (a)", layout.MODE_KANA),
                ("text", "ga", "ガ (ga)", layout.MODE_KATAKANA),
                ("text", "A", "A", layout.MODE_ALNUM),
                ("text", "/", "・ (/)", layout.MODE_KANA),
                ("text", "a", "あ (a)", None),
            ],
        )

    def test_keys_that_cannot_be_sent_are_refused(self):
        for args in (("hiragana", False, 1, 3), ("symbol", False, 4, 5), ("none", False, 0, 0), ("hiragana", False, 9, 0),
                     ("hiragana", False, None, 0), ("lower", True, 4, 0)):
            self.assertFalse(self.session.press(*args, True), args)
        self.assertEqual(self.typer.calls, [])

    def test_page_change_switches_the_mode_only_when_it_changes(self):
        self.session.show_page("hiragana", True)
        self.session.show_page("lower", True)
        self.session.show_page("lower", True)
        self.session.show_page("katakana", False)
        self.typer.reason = "未接続"
        self.session.show_page("upper", True)
        self.assertEqual(self.typer.calls, [("mode", layout.MODE_ALNUM, None)])
        with self.assertRaises(KeyError):
            self.session.show_page("none", True)

    def test_special_keys_ok_sync_and_forget(self):
        self.assertTrue(self.session.special("backspace"))
        self.assertTrue(self.session.special("enter"))
        self.assertFalse(self.session.special("none"))
        self.assertTrue(self.session.ok())
        self.assertTrue(self.session.sync("katakana"))
        self.session.forget()
        self.assertEqual(
            self.typer.calls,
            [
                ("key", int(KEY.BACKSPACE), "BackSpace"),
                ("key", int(KEY.ENTER), "改行 (Enter)"),
                ("button",),
                ("forget",),
                ("mode", layout.MODE_KATAKANA, "入力モードを合わせ直しました: カナ"),
                ("forget",),
            ],
        )

    def test_preview(self):
        self.assertEqual(KeyboardSession.preview("ポケモンGet!", True), "送る文字: [カナ] pokemonn  [英字] Get!")
        self.assertEqual(KeyboardSession.preview("ねこ", False), "送る文字: neko")
        self.assertEqual(KeyboardSession.preview("abc", False), "")
        self.assertEqual(KeyboardSession.preview("", True), "")
        self.assertEqual(KeyboardSession.preview("漢字a", True), "送れない文字があります: 漢 字")

    def test_send_text(self):
        self.assertTrue(self.session.send_text("ねこA", True, True))
        self.assertTrue(self.session.send_text("ねこ", False, False))
        self.assertEqual(
            self.typer.calls,
            [
                ("segments", [(layout.MODE_KANA, "neko"), (layout.MODE_ALNUM, "A")], "ねこA"),
                ("key", int(KEY.ENTER), "改行 (Enter)"),
                ("text", "neko", "ねこ (neko)", None),
            ],
        )
        del self.typer.calls[:]
        self.assertFalse(self.session.send_text("漢字", True, True))
        self.assertEqual(self.typer.calls, [])
        self.assertEqual(self.messages, [("送れない文字があるため、送っていません: 漢 字", True)])
        # 空のときは、改行だけを送れる(入力欄は、そのまま)
        self.assertFalse(self.session.send_text("", True, True))
        self.assertFalse(self.session.send_text("", True, False))
        self.assertEqual(self.typer.calls, [("key", int(KEY.ENTER), "改行 (Enter)")])

    def test_close(self):
        self.session.close()
        self.assertTrue(self.typer.closed)


class MonitorCase(unittest.TestCase):
    """窓口の情報のファイルを、一時フォルダーに置く"""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        patcher = mock.patch.object(Profile, "PROFILES_DIR", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)


class MonitorRelayTest(MonitorCase):
    def setUp(self):
        super().setUp()
        self.frame = None
        self.seq = 0
        self.actions = []
        self.server = MonitorServer("p1", lambda: (self.frame, self.seq), self.actions.append)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.sent = []
        self.relay = MonitorRelay(self.sent.append, lambda profile: MonitorConnection(profile, retry_interval=0.05), tick_seconds=0.01)
        self.addCleanup(self.relay.close)

    def last(self, kind: str, profile: str = "p1") -> dict | None:
        for message in reversed(list(self.sent)):
            if message["type"] == kind and message["profile"] == profile:
                return message
        return None

    def test_profile_names_include_running_ones(self):
        os.makedirs(os.path.join(self.folder, "default"))
        self.assertEqual(monitor_relay.profile_names(), ["default", "p1"])

    def test_state_and_output_are_relayed_when_they_change(self):
        self.server.set_state({"state": "idle", "selected": "c", "can_start": True})
        self.server.push_output(1, False, "one\n")
        self.relay.set_profiles(["p1", "absent", "", 3])
        self.assertEqual(sorted(self.relay.connections), ["absent", "p1"])
        self.assertTrue(wait_until(lambda: (self.last("monitor") or {}).get("state", {}).get("selected") == "c"))
        self.assertTrue(wait_until(lambda: (self.last("monitor") or {}).get("outputs", {}).get("1") == "one\n"))
        absent = self.last("monitor", "absent")
        self.assertEqual((absent["connected"], absent["state"]), (False, {}))
        # 変わった出力画面だけを送る
        count = len(self.sent)
        self.server.push_output(2, False, "two\n")
        self.assertTrue(wait_until(lambda: len(self.sent) > count))
        self.assertEqual(self.last("monitor")["outputs"], {"2": "two\n"})
        # 変わらなければ、送らない
        count = len(self.sent)
        time.sleep(0.2)
        self.assertEqual(len(self.sent), count)
        json.dumps(self.sent)
        # 開き直したときは、すべて送り直す
        self.relay.resend()
        self.assertTrue(wait_until(lambda: len(self.sent) > count))
        self.assertEqual(self.last("monitor")["outputs"], {"1": "one\n", "2": "two\n"})

    def test_frames_are_relayed_as_base64_jpeg(self):
        self.relay.set_video(10, 160)
        self.relay.set_profiles(["p1"])
        self.assertTrue(wait_until(lambda: self.relay.connections["p1"].connected))
        self.frame, self.seq = np.full((90, 160, 3), 128, np.uint8), 1
        self.assertTrue(wait_until(lambda: (self.last("monitor_frame") or {}).get("jpeg")))
        self.assertEqual(base64.b64decode(self.last("monitor_frame")["jpeg"])[:2], b"\xff\xd8")
        # 窓口が閉じたら、映像なしを知らせる
        self.server.stop()
        self.assertTrue(wait_until(lambda: self.last("monitor_frame")["jpeg"] is None))
        self.assertFalse(self.last("monitor")["connected"])

    def test_actions(self):
        self.relay.set_profiles(["p1"])
        self.assertFalse(self.relay.action("other", "play"))
        self.assertTrue(wait_until(lambda: self.relay.connections["p1"].connected))
        self.assertTrue(self.relay.action("p1", "pause"))
        self.assertTrue(wait_until(lambda: self.actions == ["pause"]))
        # まとめての操作は、今も対象の状態のものにだけ頼む
        self.server.set_state({"state": "idle", "can_start": False})
        self.assertTrue(wait_until(lambda: self.relay.connections["p1"].state.get("state") == "idle"))
        self.assertEqual(self.relay.action_all("play", ["p1", "p1", "other"]), 0)
        self.assertEqual(self.relay.action_all("stop", ["p1"]), 0)
        self.assertEqual(self.relay.action_all("front", ["p1"]), 0)
        self.server.set_state({"state": "paused"})
        self.assertTrue(wait_until(lambda: self.relay.connections["p1"].state.get("state") == "paused"))
        self.assertEqual(self.relay.action_all("play", ["p1", "p1"]), 1)
        self.assertEqual(self.relay.action_all("stop", ["p1"]), 1)
        self.assertTrue(wait_until(lambda: self.actions == ["pause", "play", "stop"]))

    def test_profiles_that_are_no_longer_shown_are_closed(self):
        self.relay.set_profiles(["p1"])
        connection = self.relay.connections["p1"]
        self.assertTrue(wait_until(lambda: connection.connected))
        self.relay.set_profiles([])
        self.assertEqual(self.relay.connections, {})
        self.assertTrue(wait_until(lambda: not connection.connected))
        self.relay.close()
        self.relay.set_profiles(["p1"])
        self.assertEqual(self.relay.connections, {})

    def test_shows_at_most_twelve_profiles(self):
        made = []

        def factory(profile):
            made.append(profile)
            return SimpleNamespace(
                set_video=lambda *args: None, close=lambda: None, connected=False, state={}, state_seq=0,
                output_seq={1: 0, 2: 0}, frame_seq=0, output=lambda area: "", frame=lambda: None,
            )

        relay = MonitorRelay(lambda message: None, factory, tick_seconds=0.01)
        self.addCleanup(relay.close)
        relay.set_profiles([f"p{index}" for index in range(20)])
        self.assertEqual(len(made), monitor_relay.MAX_COUNT)


class FakeCommands:
    """コマンドの管理の代役"""

    def __init__(self):
        self.state = command_service.IDLE
        self.current = None
        self.can_pause = True
        self.commands = {"Python": [SimpleNamespace(name="A"), SimpleNamespace(name="B")], "Mcu": [SimpleNamespace(name="M")]}


class LinkCore:
    """アプリ本体の代役(つなぎ役が使う分だけ)"""

    def __init__(self):
        self.calls = []
        self.commands = FakeCommands()
        self.output = SimpleNamespace(listeners=[])
        self.record = SimpleNamespace(is_recording=lambda: self.recording)
        self.recording = False
        self.camera = SimpleNamespace(latestFrame=lambda: ("frame", 7))

    def start_command(self, command_type, name):
        self.calls.append(("start", command_type, name))

    def resume_command(self):
        self.calls.append(("resume",))

    def pause_command(self):
        self.calls.append(("pause",))

    def stop_command(self):
        self.calls.append(("stop",))


class WebMonitorLinkTest(MonitorCase):
    def setUp(self):
        super().setUp()
        self.core = LinkCore()
        self.cancelled = []
        self.web_app = SimpleNamespace(
            core=self.core, selected_command=None, output_page=1,
            dialogues=SimpleNamespace(cancel_all=lambda: self.cancelled.append(True)),
        )
        self.link = WebMonitorLink(self.web_app, "p1")
        self.addCleanup(self.link.stop)
        self.original_pause = Command.isPause
        self.addCleanup(lambda: setattr(Command, "isPause", self.original_pause))
        Command.isPause = False

    def test_state_follows_the_selected_command(self):
        state = self.link.state()
        self.assertEqual((state["state"], state["selected"], state["can_start"], state["can_pause"]), ("idle", "", False, False))
        self.assertIn("(profile: p1) [Web]", state["title"])
        self.web_app.selected_command = ("Python", "B")
        self.assertEqual((self.link.state()["selected"], self.link.state()["can_start"]), ("B", True))
        # 一覧にないコマンド・操作の記録中は、開始できない
        self.web_app.selected_command = ("Python", "gone")
        self.assertEqual((self.link.state()["selected"], self.link.state()["can_start"]), ("", False))
        self.web_app.selected_command = ("Mcu", "M")
        self.core.recording = True
        self.assertEqual((self.link.state()["selected"], self.link.state()["can_start"]), ("M", False))
        json.dumps(self.link.state())

    def test_running_and_paused_states(self):
        self.core.commands.state = command_service.RUNNING
        self.core.commands.current = SimpleNamespace(NAME="Run")
        state = self.link.state()
        self.assertEqual((state["state"], state["command"], state["can_start"], state["can_pause"]), ("running", "Run", False, True))
        Command.isPause = True
        self.assertEqual((self.link.state()["state"], self.link.state()["can_pause"]), ("paused", False))
        self.core.commands.state = command_service.STOPPING
        self.assertEqual(self.link.state()["state"], "stopping")

    def test_actions_are_performed_only_when_possible(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            for name in ("play", "pause", "stop", "front"):
                self.link.perform(name)
            self.assertEqual(self.core.calls, [])
            self.assertIn("前面に表示できません", output.getvalue())
            self.web_app.selected_command = ("Python", "A")
            self.link.perform("play")
            self.core.commands.state = command_service.RUNNING
            self.link.perform("play")
            self.link.perform("pause")
            Command.isPause = True
            self.link.perform("pause")
            self.link.perform("play")
            self.link.perform("stop")
        self.assertEqual(self.core.calls, [("start", "Python", "A"), ("pause",), ("resume",), ("stop",)])
        self.assertEqual(self.cancelled, [True])

    def test_window_is_seen_and_operated_through_the_monitor(self):
        self.web_app.selected_command = ("Python", "A")
        with mock.patch.object(Profile, "is_read_only", return_value=False):
            self.assertTrue(self.link.start())
        connection = MonitorConnection("p1", retry_interval=0.05)
        self.addCleanup(connection.close)
        self.assertTrue(wait_until(lambda: connection.state.get("selected") == "A"))
        self.core.output.listeners[0](1, "a", "hello\n")
        self.core.output.listeners[0](2, "w", "over\n")
        self.assertTrue(wait_until(lambda: (connection.output(1), connection.output(2)) == ("hello\n", "over\n")))
        self.core.output.listeners[0](1, "d", "")
        self.assertTrue(wait_until(lambda: connection.output(1) == ""))
        self.assertEqual(self.link._frame(), ("frame", 7))
        self.assertTrue(connection.action("play"))
        self.assertTrue(wait_until(lambda: self.core.calls == [("start", "Python", "A")]))
        self.link.stop()
        self.assertTrue(wait_until(lambda: not connection.connected))

    def test_second_instance_of_a_profile_does_not_open(self):
        with mock.patch.object(Profile, "is_read_only", return_value=True), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(self.link.start())
        self.assertIn("--monitor は無効です", output.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.folder, "p1.monitor.json")))


class ToolsCore(test_web.FakeCore):
    """ツールの画面が使う分を足した、アプリ本体の代役"""

    def __init__(self, gui):
        super().__init__(gui)
        self.commands = SimpleNamespace(commands={"Python": [], "Mcu": []}, reload=lambda: None)
        self.refreshed = 0
        self.entries_after_refresh = None

    def refresh_command_list(self):
        self.refreshed += 1
        if self.entries_after_refresh is not None:
            self.commands.commands["Python"] = self.entries_after_refresh()
        self.notify()


@unittest.skipUnless(test_web.WEB_AVAILABLE, "fastapi / uvicorn / websockets are not installed")
class ToolsServerTest(MonitorCase):
    """サーバーを実際に起動し、ブラウザの代わりにつないで、ツールの画面の操作を確かめる"""

    def setUp(self):
        super().setUp()
        import uvicorn

        from web import server as web_server

        original_handler, original_stdout = Command.dialogue_handler, sys.stdout
        self.port = test_web.free_port()
        cores = []

        def factory(gui):
            cores.append(ToolsCore(gui))
            return cores[0]

        self.web_app = web_server.WebApp(factory, self.port)
        config = uvicorn.Config(self.web_app.app, host="127.0.0.1", port=self.port, log_level="error", access_log=False)
        self.server = uvicorn.Server(config)
        thread = threading.Thread(target=self.server.run, daemon=True)
        thread.start()

        def stop():
            self.server.should_exit = True
            thread.join(15)
            Command.dialogue_handler = original_handler
            sys.stdout = original_stdout

        self.addCleanup(stop)
        self.assertTrue(wait_until(lambda: self.server.started, 15))
        self.core = cores[0]
        from websockets.sync.client import connect

        self.ws = connect(f"ws://127.0.0.1:{self.port}/ws", origin=f"http://127.0.0.1:{self.port}")
        self.addCleanup(self.ws.close)
        self.assertEqual(json.loads(self.ws.recv(timeout=5))["role"], "operator")

    def send(self, action, **data):
        self.ws.send(json.dumps({"action": action, **data}))

    def wait_for(self, predicate, seconds=5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                message = json.loads(self.ws.recv(timeout=max(0.05, deadline - time.time())))
            except TimeoutError:
                break
            if predicate(message):
                return message
        self.fail("the expected message did not arrive")

    def test_page_has_the_tools(self):
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
        for text in ('id="menu-tools"', 'id="tag-editor"', 'id="script-creator"', 'id="switch-keyboard"', 'id="monitor"', "/static/tools.js"):
            self.assertIn(text, page)

    def test_selected_command_is_remembered(self):
        self.send("select", command_type="Python", name="A")
        self.assertTrue(wait_until(lambda: self.web_app.selected_command == ("Python", "A")))
        for data in ({"command_type": "History", "name": "A"}, {"command_type": "Mcu", "name": ""}, {}):
            self.send("select", command_type="Mcu", name="M")
            self.assertTrue(wait_until(lambda: self.web_app.selected_command == ("Mcu", "M")))
            self.send("select", **data)
            self.assertTrue(wait_until(lambda: self.web_app.selected_command is None), data)

    def test_tags_are_loaded_and_saved(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        folder = os.path.join(base, "Commands", "PythonCommands")
        os.makedirs(folder)
        path = os.path.join(folder, "command.py")
        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.write(COMMANDS)
        original = os.getcwd()
        os.chdir(base)
        self.addCleanup(os.chdir, original)
        loader = CommandLoader(os.path.join("Commands", "PythonCommands"), PythonCommand)
        loader.load()
        self.core.entries_after_refresh = loader.reload
        self.send("tags", op="load")
        loaded = self.wait_for(lambda m: m["type"] == "tags")
        rows = {row["name"]: row for row in loaded["state"]["commands"]["Python"]}
        self.assertEqual(rows["A連打 (command)"]["tags"], ["連打", "基本"])
        self.assertEqual(self.core.refreshed, 1)
        self.send("tags", op="save", changes=[{"command_type": "Python", "name": "A連打 (command)", "tags": ["web"]}])
        saved = self.wait_for(lambda m: m["type"] == "tags" and "saved" in m)
        self.assertEqual((saved["saved"], saved["failures"], saved["kept"]), (1, [], []))
        with open(path, encoding="utf-8") as file:
            self.assertIn('TAGS = ["web"]', file.read())
        self.assertEqual(self.core.refreshed, 2)

    def test_script_is_created_and_opened(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        os.makedirs(os.path.join(base, "Commands", "PythonCommands", "Mine"))
        os.makedirs(os.path.join(base, "Template", "old"))
        opened = []
        self.web_app.script_base_dir = base
        self.web_app.open_text_file = opened.append
        self.send("script", op="open")
        form = self.wait_for(lambda m: m["type"] == "script" and "form" in m)["form"]
        self.assertEqual(form, {"author": "", "folders": ["Mine"], "template_folders": ["old"]})
        spec = {"name": "テスト", "author": " 作者 ", "file_name": "web_made", "folder": "Mine", "template_folder": ""}
        self.send("script", op="preview", seq=3, **spec)
        preview = self.wait_for(lambda m: m["type"] == "script" and "preview" in m)
        self.assertEqual(preview["seq"], 3)
        self.assertTrue(preview["preview"].startswith("作るファイル: Commands/PythonCommands/Mine/web_made.py\n"))
        self.send("script", op="create", **{**spec, "file_name": "bad name"})
        error = self.wait_for(lambda m: m["type"] == "script" and "error" in m)
        self.assertIn("ファイル名", error["error"])
        self.assertEqual(opened, [])
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.send("script", op="create", **spec)
            created = self.wait_for(lambda m: m["type"] == "script" and "created" in m)
        self.assertEqual(created["created"]["command_name"], "テスト (Mine/web_made)")
        path = os.path.join(base, "Commands", "PythonCommands", "Mine", "web_made.py")
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(wait_until(lambda: opened == [path]))
        self.assertEqual(self.core.refreshed, 1)
        self.assertEqual(script_creator.load_author(base), "作者")
        # Output に、作ったものを知らせる(この代役では、標準出力に出る)
        self.assertIn("スクリプトを作成しました: " + os.path.join("Commands", "PythonCommands", "Mine", "web_made.py"), printed.getvalue())

    def test_keyboard_reports_why_it_cannot_send(self):
        self.send("switch_keyboard", op="open")
        opened = self.wait_for(lambda m: m["type"] == "switch_keyboard" and "layout" in m)
        self.assertEqual(len(opened["layout"]["pages"]), 5)
        self.assertEqual(opened["status"], {"text": "シリアルポートに接続していません。", "error": True})
        self.send("switch_keyboard", op="press", page="hiragana", small=False, row=0, column=10, auto=True)
        status = self.wait_for(lambda m: m["type"] == "switch_keyboard" and "status" in m)
        self.assertTrue(status["status"]["error"])
        self.send("switch_keyboard", op="preview", text="ねこ", auto=False)
        preview = self.wait_for(lambda m: m["type"] == "switch_keyboard" and "preview" in m)
        self.assertEqual((preview["preview"], preview["text"]), ("送る文字: neko", "ねこ"))
        self.send("switch_keyboard", op="text", text="漢字", auto=True, enter=False)
        sent = self.wait_for(lambda m: m["type"] == "switch_keyboard" and "sent" in m)
        self.assertFalse(sent["sent"])
        # 知らないページ・知らない操作でも、止まらない
        self.send("switch_keyboard", op="page", page="none")
        self.send("switch_keyboard", op="none")
        self.send("switch_keyboard", op="preview", text="a", auto=True)
        self.wait_for(lambda m: m["type"] == "switch_keyboard" and m.get("text") == "a")
        # 操作していたブラウザが閉じたら、送信をやめる
        session = self.web_app._keyboard
        self.ws.close()
        self.assertTrue(wait_until(lambda: self.web_app._keyboard is None and session.typer._closed))

    def test_monitor_shows_and_operates_another_window(self):
        actions = []
        server = MonitorServer("p1", lambda: (None, 0), actions.append)
        server.start()
        self.addCleanup(server.stop)
        server.set_state({"state": "paused", "command": "c"})
        server.push_output(1, False, "hello\n")
        self.send("monitor", op="open")
        info = self.wait_for(lambda m: m["type"] == "monitor_info")
        self.assertEqual((info["names"], info["max_count"]), (["p1"], 12))
        self.send("monitor", op="video", fps=5, width=320)
        self.send("monitor", op="profiles", names=["p1"])
        shown = self.wait_for(lambda m: m["type"] == "monitor" and m["connected"] and m["state"].get("state") == "paused")
        self.assertEqual(shown["profile"], "p1")
        self.assertTrue(wait_until(lambda: self.web_app._monitor.connections["p1"].output(1) == "hello\n"))
        self.send("monitor", op="action", profile="p1", name="pause")
        self.assertEqual(self.wait_for(lambda m: m["type"] == "monitor_result")["text"], "p1: pause")
        self.send("monitor", op="action", profile="other", name="pause")
        self.assertEqual(self.wait_for(lambda m: m["type"] == "monitor_result")["text"], "other: 送れませんでした")
        self.send("monitor", op="action_all", name="play", profiles=["p1"])
        result = self.wait_for(lambda m: m["type"] == "monitor_result" and m.get("all"))
        self.assertEqual(result["count"], 1)
        self.assertTrue(wait_until(lambda: actions == ["pause", "play"]))
        relay = self.web_app._monitor
        self.send("monitor", op="close")
        self.assertTrue(wait_until(lambda: self.web_app._monitor is None and relay.connections == {}))


if __name__ == "__main__":
    unittest.main()
