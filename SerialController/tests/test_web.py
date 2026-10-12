#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web ブラウザ版の画面(web/)のテスト。カメラもシリアルも開かず、アプリ本体は代役を使う。
fastapi / uvicorn / websockets が無い環境では、サーバーのテストは飛ばす

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands.CommandBase import Command  # noqa: E402
from services.output_service import OutputService  # noqa: E402
from web import dialogue as web_dialogue  # noqa: E402
from web import preview as web_preview  # noqa: E402
from web.dialogue import DialogueBroker  # noqa: E402

try:
    import uvicorn
    from websockets.sync.client import connect

    from web import server as web_server

    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

WIDGETS = [
    ["Check", "check", True],
    ["Combo", "combo", ["a", "b"], "b"],
    ["Entry", "entry", "text"],
    ["Next"],
    ["Radio", "radio", ["x", "y"], "y"],
    ["Scale", "int scale", 0, 10, 3, 0],
    ["Scale", "float scale", 0, 1, 0.25, 2],
    ["Spin", "spin", ["1", "2"], "2"],
]


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class DialogueFieldsTest(unittest.TestCase):
    def test_entry_dialogue(self):
        fields = web_dialogue.build_fields(["first", 2], 0)
        self.assertEqual([(f["kind"], f["key"], f["name"], f["value"]) for f in fields], [("entry", "first", "first", ""), ("entry", 2, "2", "")])
        self.assertEqual(web_dialogue.build_fields("only", 0)[0]["key"], "only")
        self.assertEqual(web_dialogue.build_result(fields, ["a", "b"], list), ["a", "b"])
        # 辞書のキーは、項目名そのもの(文字列でない場合もそのまま)
        self.assertEqual(web_dialogue.build_result(fields, ["a", "b"], dict), {"first": "a", 2: "b"})

    def test_widget_dialogue_fields(self):
        fields = web_dialogue.build_fields(WIDGETS, 1)
        self.assertEqual([f["kind"] for f in fields], ["check", "combo", "entry", "next", "radio", "scale", "scale", "spin"])
        self.assertEqual(len(web_dialogue.input_fields(fields)), 7)
        self.assertEqual(fields[1]["options"], ["a", "b"])
        self.assertEqual((fields[6]["min"], fields[6]["max"], fields[6]["value"], fields[6]["digits"]), (0, 1, 0.25, 2))
        json.dumps([{k: v for k, v in f.items() if k != "key"} for f in fields])

    def test_values_have_the_same_types_as_the_tkinter_dialogue(self):
        fields = web_dialogue.build_fields(WIDGETS, 1)
        values = [False, "a", "typed", "x", 7.0, 0.61803, "3"]
        self.assertEqual(web_dialogue.build_result(fields, values, list), [False, "a", "typed", "x", 7, 0.62, "3"])
        result = web_dialogue.build_result(fields, values, dict)
        self.assertEqual(result["int scale"], 7)
        self.assertIsInstance(result["int scale"], int)
        self.assertEqual(list(result), ["check", "combo", "entry", "radio", "int scale", "float scale", "spin"])

    def test_bad_values_fall_back(self):
        fields = web_dialogue.build_fields(WIDGETS, 1)
        values = [1, "not an option", 5, "q", "abc", 99, None]
        self.assertEqual(web_dialogue.build_result(fields, values, list), [True, "b", "5", "y", 3, 1.0, "None"])
        # 値が足りない場合は、初期値で補う
        self.assertEqual(web_dialogue.build_result(fields, [False], list), [False, "b", "text", "y", 3, 0.25, "2"])

    def test_other_need_returns_a_list(self):
        fields = web_dialogue.build_fields(["a"], 0)
        with quiet():
            self.assertEqual(web_dialogue.build_result(fields, ["x"], str), ["x"])


class DialogueBrokerTest(unittest.TestCase):
    def setUp(self):
        self.shown = []
        self.hidden = []
        self.broker = DialogueBroker(self.shown.append, self.hidden.append)

    def open_in_thread(self, *args, **kwargs):
        result = {}
        thread = threading.Thread(target=lambda: result.update(value=self.broker.open(None, *args, **kwargs)))
        thread.start()
        deadline = time.time() + 3
        while not self.shown and time.time() < deadline:
            time.sleep(0.01)
        return thread, result

    def test_answer(self):
        thread, result = self.open_in_thread("Title", WIDGETS, desc="note", need=dict, mode=1, pos=3)
        request = self.shown[0]
        self.assertEqual((request["title"], request["desc"], request["pos"]), ("Title", "note", 3))
        self.assertNotIn("key", request["fields"][0])
        self.assertEqual(self.broker.pending_requests(), [request])
        self.assertTrue(self.broker.answer(request["id"], True, [False, "a", "t", "x", 1, 0.5, "1"]))
        thread.join(3)
        self.assertEqual(result["value"]["combo"], "a")
        self.assertEqual(self.hidden, [request["id"]])
        self.assertEqual(self.broker.pending_requests(), [])
        self.assertFalse(self.broker.answer(request["id"], True, []))  # もう待っていない

    def test_cancel(self):
        thread, result = self.open_in_thread("Title", ["a"])
        self.assertTrue(self.broker.answer(self.shown[0]["id"], False))
        thread.join(3)
        self.assertIs(result["value"], False)

    def test_cancel_all(self):
        thread, result = self.open_in_thread("Title", ["a"])
        self.broker.cancel_all()
        thread.join(3)
        self.assertIs(result["value"], False)
        self.assertEqual(self.hidden, [self.shown[0]["id"]])


class FakeCamera:
    def __init__(self, frame=None, capture_size=(1280, 720)):
        self.frame = frame
        self.capture_size = capture_size

    @property
    def image_bgr(self):
        return self.frame

    def readFrame(self, timeout=1.0):
        time.sleep(0.01)
        return None if self.frame is None else self.frame.copy()


def fake_core_for_preview(frame, capture_size=(1280, 720)):
    settings = SimpleNamespace(is_show_mask=True, preview_gain=100, preview_gamma=1.0)
    return SimpleNamespace(camera=FakeCamera(frame, capture_size), settings=settings, masks=[])


class PreviewTest(unittest.TestCase):
    def test_scaled_size(self):
        self.assertEqual(web_preview.scaled_size(1920, 1080), (960, 540))
        self.assertEqual(web_preview.scaled_size(1280, 720), (960, 540))
        self.assertEqual(web_preview.scaled_size(256, 384), (256, 384))
        self.assertEqual(web_preview.scaled_size(1920, 1080, 1280), (1280, 720))
        self.assertEqual(web_preview.scaled_size(1920, 1080, 0), (1920, 1080))  # 0 は、縮めない

    def test_brightness_table(self):
        self.assertIsNone(web_preview.brightness_table(100, 1.0))
        table = web_preview.brightness_table(50, 1.0)
        self.assertEqual((int(table[0]), int(table[200]), int(table[255])), (0, 100, 128))
        self.assertEqual(int(web_preview.brightness_table(300, 1.0)[255]), 255)

    def decode(self, jpeg):
        import cv2

        return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)

    def test_encode_scales_large_frames(self):
        frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
        jpeg = web_preview.FrameEncoder(fake_core_for_preview(frame)).encode(frame)
        self.assertEqual(jpeg[:2], b"\xff\xd8")
        image = self.decode(jpeg)
        self.assertEqual(image.shape[:2], (540, 960))
        self.assertTrue(abs(int(image[10, 10, 0]) - 200) <= 3)

    def test_encode_applies_brightness_and_masks(self):
        from Mask import Mask

        frame = np.full((360, 640, 3), 200, dtype=np.uint8)
        core = fake_core_for_preview(frame, (640, 360))
        core.settings.preview_gain = 50
        core.masks = [Mask("Rectangle", 0, 0, 100, 100, "#000000", True)]
        image = self.decode(web_preview.FrameEncoder(core).encode(frame))
        self.assertTrue(int(image[50, 50, 0]) <= 5)  # 目隠しの中
        self.assertTrue(abs(int(image[200, 400, 0]) - 100) <= 3)  # 明るさ 50%
        self.assertEqual(int(frame[50, 50, 0]), 200)  # 元の画像は変えない
        core.settings.is_show_mask = False
        self.assertTrue(abs(int(self.decode(web_preview.FrameEncoder(core).encode(frame))[50, 50, 0]) - 100) <= 3)

    def test_encode_uses_the_chosen_maximum_width(self):
        frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
        encoder = web_preview.FrameEncoder(fake_core_for_preview(frame))
        encoder.max_width = 640
        self.assertEqual(self.decode(encoder.encode(frame)).shape[:2], (360, 640))
        encoder.max_width = 0
        self.assertEqual(self.decode(encoder.encode(frame)).shape[:2], (720, 1280))

    def test_no_image(self):
        core = fake_core_for_preview(None)
        image = self.decode(web_preview.FrameEncoder(core).encode(None))
        self.assertEqual(image.shape[:2], (540, 960))

    def test_encoder_runs_only_while_viewed(self):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        frames = []
        encoder = web_preview.FrameEncoder(fake_core_for_preview(frame, (160, 90)), lambda: frames.append(1))
        self.assertEqual(encoder.latest(), (None, 0))
        encoder.add_viewer()
        deadline = time.time() + 3
        while not frames and time.time() < deadline:
            time.sleep(0.01)
        encoder.remove_viewer()
        jpeg, seq = encoder.latest()
        self.assertEqual(jpeg[:2], b"\xff\xd8")
        self.assertGreaterEqual(seq, 1)
        time.sleep(0.2)
        count = len(frames)
        time.sleep(0.2)
        self.assertEqual(len(frames), count)  # 見ているブラウザが無くなったら、作るのを止める

    def test_overlay_messages(self):
        sent = []
        gui = web_preview.WebPreview(FakeCamera(), sent.append)
        gui.ImgRect(10, 20, 30, 40, "red", "tag1", 2000)
        gui.ImgRect(1, 2, 3, 4, "blue", "tag1", 2000, False)
        gui.ImgText(5, 6, "text", "tag2", 500, ("font", 20), "yellow")
        gui.deleteImageRect("tag1")
        json.dumps(sent)
        self.assertEqual(sent[0], {"type": "overlay", "kind": "rect", "tag": "tag1", "ms": 2000, "capture": [1280, 720], "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0, "color": "red"})
        self.assertIsNone(sent[1]["ms"])
        self.assertEqual((sent[2]["kind"], sent[2]["text"], sent[2]["size"], sent[2]["color"]), ("text", "text", 20, "yellow"))
        self.assertEqual(sent[3], {"type": "overlay", "kind": "delete", "tag": "tag1"})


class FakeSettingsControl:
    def __init__(self):
        self.calls = []

    def apply(self, name, value):
        self.calls.append(("apply", name, value))
        if name == "bad":
            from services.settings_control import SettingError

            raise SettingError("refused bad")

    def scan(self):
        self.calls.append(("scan",))

    def scan_ports(self):
        self.ports = ["A (COM3)"]
        self.calls.append(("scan_ports",))


class FakeSoftcon:
    def __init__(self):
        self.calls = []

    def press(self, tag):
        if tag == "unknown":
            from services.software_controller import SoftwareControllerError

            raise SoftwareControllerError("unknown part")
        self.calls.append(("press", tag))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name,) + args)


class FakeEditor:
    def __init__(self):
        self.calls = []

    def set_shortcut(self, num, command_type, name):
        from services.editor_service import EditError

        if name == "bad":
            raise EditError("no such command")
        self.calls.append(("set_shortcut", num, command_type, name))

    def discord_state(self, name=None):
        return {"names": ["DISCORD_WEBHOOK"], "selected": name, "values": {"webhook_url": "secret-url"}}

    def keymaps(self):
        return {"consoles": ["Switch"]}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name,) + args)


class FakeSetup:
    def __init__(self):
        self.calls = []
        self.on_change = None

    def start(self, on_change=None):
        self.on_change = on_change
        self.calls.append("start")
        return {"active": True, "phase": "preparing"}

    def skip(self):
        from services.controller_setup_service import SetupError

        raise SetupError("not started")

    def state(self):
        return {"active": False}

    def cancel(self):
        self.calls.append("cancel")
        return {"active": False}

    def close(self):
        self.calls.append("close")


class FakeTools:
    def __init__(self):
        self.calls = []

    def diagnostics_texts(self):
        return "diagnostics text", "masked text"

    def save_capture(self, area, name):
        from services.tools_service import ToolError

        if name == "bad":
            raise ToolError("cannot save")
        self.calls.append(("save_capture", area, name))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self.calls.append((name,) + args)


class FakeCore:
    """Web の画面が呼ぶ分だけを持つ、アプリ本体の代役"""

    def __init__(self, gui):
        self.gui = gui
        self.calls = []
        self.listeners = []
        self.output = OutputService()
        self.camera = FakeCamera(np.full((90, 160, 3), 128, dtype=np.uint8), (160, 90))
        self.settings = SimpleNamespace(is_show_mask=False, preview_gain=100, preview_gamma=1.0, is_use_keyboard=False)
        self.masks = []
        self.sender = SimpleNamespace(isOpened=lambda: False)
        self.record = SimpleNamespace(is_recording=lambda: False)
        self.has_touchscreen = False
        self.command_state = "idle"
        self.keyboard_active = False
        self.settings_control = FakeSettingsControl()
        self.softcon = FakeSoftcon()
        self.simulator = FakeSoftcon()
        self.editor = FakeEditor()
        self.tools = FakeTools()
        self.controller_setup = FakeSetup()
        self.audio = SimpleNamespace(meter=lambda: self.meter_value)
        self.meter_value = None

    def add_listener(self, listener):
        self.listeners.append(listener)

    def notify(self):
        for listener in self.listeners:
            listener("command")

    def start(self):
        self.calls.append(("core start",))

    def close(self):
        self.calls.append(("core close",))

    def state(self):
        return {"app": "test", "profile": "test", "command": {"state": self.command_state}}

    def start_command(self, command_type, name):
        self.calls.append(("start", command_type, name))
        self.command_state = "running"
        self.output.enqueue(1, "a", f"started {name}\n")
        self.notify()

    def stop_command(self):
        self.calls.append(("stop",))
        self.command_state = "idle"
        self.notify()

    def set_keyboard_active(self, active):
        self.keyboard_active = active
        return active

    def __getattr__(self, name):
        # そのほかの操作は、呼ばれたことだけを記録する
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name,) + args)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(WEB_AVAILABLE, "fastapi / uvicorn / websockets are not installed")
class ServerHelpersTest(unittest.TestCase):
    def test_allowed_hosts(self):
        self.assertEqual(web_server.allowed_hosts(8765), {"127.0.0.1:8765", "localhost:8765"})

    def test_is_inside(self):
        root = os.path.realpath("Captures")
        self.assertTrue(web_server.is_inside(root, os.path.join(root, "a.png")))
        self.assertTrue(web_server.is_inside(root, os.path.join(root, "sub", "a.png")))
        self.assertFalse(web_server.is_inside(root, os.path.realpath("Window.py")))
        self.assertFalse(web_server.is_inside(root, root + "2"))

    def test_split_output(self):
        import OutputLinks

        self.assertEqual(web_server.split_output("plain\n"), [{"text": "plain\n", "link": None}])
        text = "a " + OutputLinks.link("label", lambda: None) + " b\n"
        parts = web_server.split_output(text)
        self.assertEqual([part["text"] for part in parts], ["a ", "label", " b\n"])
        self.assertIsInstance(parts[1]["link"], int)
        self.assertIsNone(parts[0]["link"])

    def test_backlog_keeps_the_latest_lines(self):
        backlog = web_server.Backlog(max_lines=3)
        for i in range(6):
            backlog.apply(1, False, [{"text": f"line {i}\n", "link": None}])
        backlog.apply(2, False, [{"text": "old\n", "link": None}])
        backlog.apply(2, True, [{"text": "new\n", "link": None}])
        first, second = backlog.messages()
        self.assertEqual("".join(part["text"] for part in first["parts"]), "line 3\nline 4\nline 5\n")
        self.assertEqual((first["area"], first["clear"]), (1, True))
        self.assertEqual("".join(part["text"] for part in second["parts"]), "new\n")


@unittest.skipUnless(WEB_AVAILABLE, "fastapi / uvicorn / websockets are not installed")
class ServerTest(unittest.TestCase):
    """サーバーを実際に起動し、ブラウザの代わりにつないで確かめる"""

    @classmethod
    def setUpClass(cls):
        cls.original_handler = Command.dialogue_handler
        cls.original_stdout = sys.stdout
        cls.port = free_port()
        cls.cores = []

        def factory(gui):
            core = FakeCore(gui)
            cls.cores.append(core)
            return core

        cls.web_app = web_server.WebApp(factory, cls.port)
        config = uvicorn.Config(cls.web_app.app, host="127.0.0.1", port=cls.port, log_level="error", access_log=False)
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 15
        while not cls.server.started and time.time() < deadline:
            time.sleep(0.05)
        assert cls.server.started, "the server did not start"
        cls.core = cls.cores[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(15)
        Command.dialogue_handler = cls.original_handler
        sys.stdout = cls.original_stdout

    def base(self):
        return f"127.0.0.1:{self.port}"

    def get(self, path, headers=None):
        request = urllib.request.Request(f"http://{self.base()}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers.get("content-type", ""), response.read(100000)
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("content-type", ""), b""

    def open_ws(self):
        ws = connect(f"ws://{self.base()}/ws", origin=f"http://{self.base()}")
        self.addCleanup(ws.close)
        hello = json.loads(ws.recv(timeout=5))
        return ws, hello

    def wait_for(self, ws, predicate, seconds=5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                message = json.loads(ws.recv(timeout=max(0.05, deadline - time.time())))
            except TimeoutError:
                break
            if predicate(message):
                return message
        self.fail("the expected message did not arrive")

    def test_pages(self):
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"/static/app.js", body)
        self.assertEqual(self.get("/static/app.js")[0], 200)
        self.assertEqual(self.get("/static/style.css")[0], 200)
        status, _, body = self.get("/api/state")
        self.assertEqual(json.loads(body)["profile"], "test")

    def test_other_host_names_are_refused(self):
        self.assertEqual(self.get("/api/state", {"Host": f"evil.example:{self.port}"})[0], 403)
        self.assertEqual(self.get("/", {"Host": "evil.example"})[0], 403)

    def test_capture_serves_only_images_in_the_capture_folder(self):
        # このアプリのフォルダの外は断り、中でも画像でないファイルは出さない
        self.assertEqual(self.get("/api/capture?path=..%2Frequirements.txt")[0], 403)
        self.assertEqual(self.get("/api/capture?path=C%3A%5CWindows%5Cwin.ini")[0], 403)
        self.assertEqual(self.get("/api/capture?path=Window.py")[0], 404)
        self.assertEqual(self.get("/api/capture?path=.%2FCaptures%2F..%2FWindow.py")[0], 404)
        self.assertEqual(self.get("/api/capture?path=profiles%2Fdefault%2Fsettings.ini")[0], 404)
        self.assertEqual(self.get("/api/capture?path=.%2FCaptures%2Fno_such_file.png")[0], 404)

    def test_guide_assets_are_served(self):
        status, _, body = self.get("/assets/manual/manual.md")
        self.assertEqual(status, 200)
        self.assertIn("# ".encode("utf-8"), body)
        self.assertEqual(self.get("/assets/..%2FWindow.py")[0], 404)

    def test_output_pages_tools_and_meter(self):
        operator, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        self.assertEqual((hello["state"]["output_page"], hello["state"]["output_pages"]), (0, 3))
        tools = self.core.tools
        start = len(tools.calls)

        def send(action, **data):
            operator.send(json.dumps({"action": action, **data}))

        # 表示しているページを変えると、画面の操作での出力はそのページに出る
        send("output_page", page=2)
        self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["output_page"] == 2)
        self.assertEqual(self.core._get_output_page(), 2)
        send("clear", area=1)
        cleared = self.wait_for(operator, lambda m: m["type"] == "output" and m["clear"])
        self.assertEqual((cleared["area"], cleared["page"]), (1, 2))
        send("output_page", page=9)  # 無いページは無視する
        send("output_page", page=0)
        self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["output_page"] == 0)

        send("tool", op="capture", area=[1, 2, 3, 4], name="x")
        send("tool", op="pixel", x=10, y=20)
        send("tool", op="history_clear")
        send("tool", op="notify_windows")
        send("tool", op="introduction_hidden", hidden=True)
        send("tool", op="diagnostics")
        result = self.wait_for(operator, lambda m: m["type"] == "tool_result")
        self.assertEqual((result["op"], result["title"], result["text"]), ("diagnostics", "環境の診断", "diagnostics text"))
        self.assertEqual(result["masked"], "masked text")
        self.assertEqual(
            tools.calls[start:],
            [("save_capture", [1, 2, 3, 4], "x"), ("pixel_info", 10, 20), ("clear_history",), ("send_windows_notification",),
             ("set_introduction_hidden", True)],
        )
        send("tool", op="capture", name="bad")
        send("tool", op="no such op")
        with quiet():
            errors = [self.wait_for(operator, lambda m: m["type"] == "tool_error") for _ in range(2)]
        self.assertEqual([(e["op"], e["message"]) for e in errors][0], ("capture", "cannot save"))

        # 送る映像の大きさ(画質)は、選べる値だけを受け付ける
        self.assertEqual(hello["state"]["preview_max_width"], 960)
        send("preview_quality", width=1280)
        self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["preview_max_width"] == 1280)
        send("preview_quality", width=12345)
        send("preview_quality", width=0)
        changed = self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["preview_max_width"] != 1280)
        self.assertEqual(changed["state"]["preview_max_width"], 0)
        send("preview_quality", width=960)
        self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["preview_max_width"] == 960)

        # 音声を取り込んでいる間だけ、音量メーターが届く
        self.core.meter_value = {"percent": 50.0, "text": "-30 dB"}
        meter = self.wait_for(operator, lambda m: m["type"] == "meter")
        self.assertEqual(meter["meter"], {"percent": 50.0, "text": "-30 dB"})
        self.core.meter_value = None
        self.wait_for(operator, lambda m: m["type"] == "meter" and m["meter"] is None)

    def test_stream_sends_jpeg_frames(self):
        request = urllib.request.Request(f"http://{self.base()}/stream.mjpg")
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertIn("multipart/x-mixed-replace", response.headers.get("content-type"))
            head = response.read(300)
        self.assertTrue(head.startswith(b"--frame\r\nContent-Type: image/jpeg"))
        self.assertIn(b"\xff\xd8", head)

    def test_websocket_from_another_site_is_refused(self):
        with self.assertRaises(Exception):
            with connect(f"ws://{self.base()}/ws", origin="http://evil.example") as ws:
                ws.recv(timeout=2)

    def test_operator_and_viewer(self):
        operator, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        self.assertEqual(hello["state"]["profile"], "test")
        viewer, viewer_hello = self.open_ws()
        self.assertEqual(viewer_hello["role"], "viewer")

        # 閲覧のみのブラウザからの操作は行わない
        before = len(self.core.calls)
        viewer.send(json.dumps({"action": "start", "command_type": "Python", "name": "X"}))
        viewer.send("not json")
        time.sleep(0.3)
        self.assertEqual(len(self.core.calls), before)

        # 操作できるブラウザからの操作は行い、状態と出力は両方に届く
        operator.send(json.dumps({"action": "start", "command_type": "Python", "name": "A"}))
        for ws in (operator, viewer):
            self.wait_for(ws, lambda m: m["type"] == "state" and m["state"]["command"]["state"] == "running")
        output = self.wait_for(viewer, lambda m: m["type"] == "output" and m["parts"])
        self.assertEqual((output["area"], output["parts"][0]["text"]), (1, "started A\n"))
        self.assertIn(("start", "Python", "A"), self.core.calls)

        operator.send(json.dumps({"action": "stick", "side": "left", "angle": 90, "magnitude": 0.5}))
        operator.send(json.dumps({"action": "stop"}))
        self.wait_for(operator, lambda m: m["type"] == "state" and m["state"]["command"]["state"] == "idle")
        self.assertIn(("move_stick", "left", 90.0, 0.5), self.core.calls)
        self.assertIn(("stop",), self.core.calls)

        # Software-Controller の操作(そのレイアウトに無い部品は無視する)
        pad_start = len(self.core.softcon.calls)
        for pad in (
            {"op": "press", "tag": "btn_a"}, {"op": "press", "tag": "unknown"}, {"op": "hold", "tag": "btn_a"},
            {"op": "tilt", "tag": "stick_left", "angle": 45, "magnitude": 0.5}, {"op": "touch", "x": 10, "y": 20},
            {"op": "touch_end"}, {"op": "center", "tag": "stick_left"}, {"op": "hold_end", "tag": "btn_a"},
        ):
            operator.send(json.dumps({"action": "pad", **pad}))
        deadline = time.time() + 3
        while len(self.core.softcon.calls) < pad_start + 7 and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(
            self.core.softcon.calls[pad_start:],
            [("press", "btn_a"), ("hold", "btn_a"), ("tilt", "stick_left", 45.0, 0.5), ("touch", 10.0, 20.0),
             ("touch_end",), ("center", "stick_left"), ("hold_end", "btn_a")],
        )

        # Controller Simulator の操作は、別のコントローラーに届く
        simulator_start = len(self.core.simulator.calls)
        operator.send(json.dumps({"action": "pad2", "op": "press", "tag": "btn_b"}))
        operator.send(json.dumps({"action": "pad2", "op": "release_all"}))
        deadline = time.time() + 3
        while len(self.core.simulator.calls) < simulator_start + 2 and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.core.simulator.calls[simulator_start:], [("press", "btn_b"), ("release_all",)])
        self.assertNotIn(("press", "btn_b"), self.core.softcon.calls)

        # 設定の変更と、一覧の取得し直し
        operator.send(json.dumps({"action": "setting", "name": "fps", "value": "30"}))
        operator.send(json.dumps({"action": "setting", "name": "bad", "value": 1}))
        operator.send(json.dumps({"action": "scan"}))
        operator.send(json.dumps({"action": "scan_ports"}))
        deadline = time.time() + 3
        with quiet():
            while len(self.core.settings_control.calls) < 4 and time.time() < deadline:
                time.sleep(0.02)
        self.assertEqual(
            self.core.settings_control.calls, [("apply", "fps", "30"), ("apply", "bad", 1), ("scan",), ("scan_ports",)]
        )

        # あとから開いたブラウザには、それまでの出力が届く
        late, _ = self.open_ws()
        backlog = self.wait_for(late, lambda m: m["type"] == "output" and m["area"] == 1)
        self.assertIn("started A\n", "".join(part["text"] for part in backlog["parts"]))

        # 操作していたブラウザが閉じたら、押したままの入力を離し、次のブラウザが操作できるようになる
        before = len(self.core.calls)
        operator.send(json.dumps({"action": "stick", "side": "right", "angle": 0, "magnitude": 1}))
        operator.send(json.dumps({"action": "ping"}))
        time.sleep(0.3)
        operator.close()
        self.assertEqual(self.wait_for(viewer, lambda m: m["type"] == "role")["role"], "operator")
        deadline = time.time() + 3
        while len([call for call in self.core.calls[before:] if call[0].startswith("release")]) < 2 and time.time() < deadline:
            time.sleep(0.02)
        released = [call for call in self.core.calls[before:] if call[0].startswith("release")]
        # 左スティック(上で倒したまま)と右スティックだけを離す。押していないタッチは離さない
        self.assertEqual(sorted(released), [("release_stick", "left"), ("release_stick", "right")])
        self.assertEqual(self.core.softcon.calls[-1], ("release_all",))
        self.assertEqual(self.core.simulator.calls[-1], ("release_all",))

    def test_dialogue_and_overlay(self):
        ws, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(value=Command.dialogue_handler(None, "Title", ["a", "b"], need=dict))
        )
        thread.start()
        request = self.wait_for(ws, lambda m: m["type"] == "dialogue")["dialogue"]
        self.assertEqual((request["title"], [f["name"] for f in request["fields"]]), ("Title", ["a", "b"]))
        ws.send(json.dumps({"action": "dialogue", "id": request["id"], "ok": True, "values": ["1", "2"]}))
        thread.join(5)
        self.assertEqual(result["value"], {"a": "1", "b": "2"})
        self.assertEqual(self.wait_for(ws, lambda m: m["type"] == "dialogue_close")["id"], request["id"])

        self.core.gui.ImgRect(1, 2, 3, 4, "red", "tag", 100)
        overlay = self.wait_for(ws, lambda m: m["type"] == "overlay")
        self.assertEqual((overlay["kind"], overlay["capture"], overlay["color"]), ("rect", [160, 90], "red"))

    def test_editing(self):
        operator, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        viewer, _ = self.open_ws()
        editor = self.core.editor
        start = len(editor.calls)

        def send(action, **data):
            operator.send(json.dumps({"action": action, **data}))

        send("shortcut", op="set", num=2, command_type="Python", name="A")
        send("shortcut", op="start", num=2)
        send("mask", op="add", shape="Rectangle", x1=1, y1=2, x2=30, y2=40)
        send("mask", op="update", index=0, values={"enabled": False})
        send("mask", op="options", show=True)
        send("touchscreen", area=[1, 2, 3, 4])
        send("colors", controller="GameCube", colors={"body": "#000000"})
        send("line", token="dummy")
        self.assertEqual(self.wait_for(operator, lambda m: m["type"] == "line_saved")["type"], "line_saved")
        self.assertEqual(
            editor.calls[start:],
            [
                ("set_shortcut", 2, "Python", "A"), ("start_shortcut", 2), ("add_mask", "Rectangle", 1, 2, 30, 40),
                ("update_mask", 0, {"enabled": False}), ("set_mask_options", True, None), ("set_touchscreen_area", 1, 2, 3, 4),
                ("set_controller_colors", "GameCube", {"body": "#000000"}), ("save_line_token", "dummy"),
            ],
        )

        # できない変更は、理由を操作した画面に返す
        send("shortcut", op="set", num=1, command_type="Python", name="bad")
        with quiet():
            error = self.wait_for(operator, lambda m: m["type"] == "edit_error")
        self.assertEqual((error["action"], error["message"]), ("shortcut", "no such command"))
        send("touchscreen", area="bad")
        with quiet():
            self.assertIn("Touch Screen", self.wait_for(operator, lambda m: m["type"] == "edit_error")["message"])

        # Webhook URL を含む返事は、操作した画面にだけ届く(閲覧のみの画面には届かない)
        send("discord", op="get", name="DISCORD_WEBHOOK")
        send("keymap", op="get")
        discord = self.wait_for(operator, lambda m: m["type"] == "discord")["discord"]
        self.assertEqual(discord["values"]["webhook_url"], "secret-url")
        self.assertEqual(self.wait_for(operator, lambda m: m["type"] == "keymap")["keymap"], {"consoles": ["Switch"]})
        viewer.send(json.dumps({"action": "discord", "op": "get"}))
        time.sleep(0.5)
        received = []
        while True:
            try:
                received.append(json.loads(viewer.recv(timeout=0.2)))
            except TimeoutError:
                break
        self.assertFalse([m for m in received if m["type"] in ("discord", "keymap", "edit_error", "line_saved")])
        self.assertNotIn("secret-url", json.dumps(received))

    def test_controller_setup(self):
        operator, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        viewer, _ = self.open_ws()
        setup = self.core.controller_setup
        start = len(setup.calls)
        operator.send(json.dumps({"action": "controller_setup", "op": "start"}))
        message = self.wait_for(operator, lambda m: m["type"] == "controller_setup")
        self.assertEqual(message["setup"], {"active": True, "phase": "preparing"})
        # 手順が進んだ知らせは、設定を始めた画面にだけ届く
        setup.on_change({"active": True, "phase": "step", "index": 0})
        self.assertEqual(self.wait_for(operator, lambda m: m["type"] == "controller_setup")["setup"]["phase"], "step")
        # できない操作は、理由を付けて今の状態を返す
        operator.send(json.dumps({"action": "controller_setup", "op": "skip"}))
        with quiet():
            message = self.wait_for(operator, lambda m: m["type"] == "controller_setup" and "error" in m["setup"])
        self.assertEqual(message["setup"], {"active": False, "error": "not started"})
        operator.send(json.dumps({"action": "controller_setup", "op": "cancel"}))
        self.wait_for(operator, lambda m: m["type"] == "controller_setup" and m["setup"] == {"active": False})
        self.assertEqual(setup.calls[start:], ["start", "cancel"])
        received = []
        while True:
            try:
                received.append(json.loads(viewer.recv(timeout=0.2)))
            except TimeoutError:
                break
        self.assertFalse([m for m in received if m["type"] == "controller_setup"])
        # 操作していた画面が閉じたら、設定をやめる
        operator.close()
        deadline = time.time() + 3
        while setup.calls[-1] != "close" and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(setup.calls[-1], "close")

    def test_exit_is_requested_only_by_the_operator(self):
        requested = []
        self.web_app.on_exit = lambda: requested.append(True)
        self.addCleanup(lambda: setattr(self.web_app, "on_exit", None))
        operator, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        viewer, _ = self.open_ws()
        viewer.send(json.dumps({"action": "exit"}))
        time.sleep(0.4)
        self.assertEqual(requested, [])
        operator.send(json.dumps({"action": "exit"}))
        # 終了することは、開いている全員に知らせる
        self.assertEqual(self.wait_for(viewer, lambda m: m["type"] == "exit")["type"], "exit")
        self.assertEqual(self.wait_for(operator, lambda m: m["type"] == "exit")["type"], "exit")
        deadline = time.time() + 3
        while not requested and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(requested, [True])

    def test_keyboard_follows_the_focus_of_the_operator(self):
        ws, hello = self.open_ws()
        self.assertEqual(hello["role"], "operator")
        ws.send(json.dumps({"action": "keyboard", "enabled": True}))
        ws.send(json.dumps({"action": "focus", "focused": True}))
        self.wait_for(ws, lambda m: m["type"] == "state")
        deadline = time.time() + 3
        while not self.core.keyboard_active and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.core.keyboard_active)
        ws.send(json.dumps({"action": "focus", "focused": False}))
        deadline = time.time() + 3
        while self.core.keyboard_active and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.core.keyboard_active)
        # 前面にある間に閉じた場合も、受け付けを止める
        ws.send(json.dumps({"action": "focus", "focused": True}))
        time.sleep(0.3)
        ws.close()
        deadline = time.time() + 3
        while self.core.keyboard_active and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.core.keyboard_active)


class PortTest(unittest.TestCase):
    """ポート番号を指定しない場合は、空いている番号を使う(複数のプロファイルを同時に起動できる)"""

    def test_free_port_skips_the_ones_in_use(self):
        import socket

        from web import main

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as first:
            first.bind((main.HOST, 0))
            first.listen(1)
            used = first.getsockname()[1]
            self.assertFalse(main.is_port_free(used))
            found = main.find_free_port(used, 20)
            self.assertIsNotNone(found)
            self.assertGreater(found, used)
            self.assertTrue(main.is_port_free(found))
            self.assertIsNone(main.find_free_port(used, 1))
        self.assertTrue(main.is_port_free(used))

    def test_run_refuses_a_port_in_use(self):
        import io as io_module
        import socket
        from unittest import mock

        from web import main

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as first:
            first.bind((main.HOST, 0))
            first.listen(1)
            used = first.getsockname()[1]
            out = io_module.StringIO()
            # プロファイルを選ぶ前に、番号が使えないことを知らせて終わる
            with mock.patch.object(main.sys, "__stdout__", out), mock.patch.object(
                main, "select_profile", side_effect=AssertionError("must not be reached")
            ):
                self.assertEqual(main.run(port=used, open_browser=False), 1)
                self.assertIn(str(used), out.getvalue())
                with mock.patch.object(main, "find_free_port", lambda: None):
                    self.assertEqual(main.run(open_browser=False), 1)


if __name__ == "__main__":
    unittest.main()
