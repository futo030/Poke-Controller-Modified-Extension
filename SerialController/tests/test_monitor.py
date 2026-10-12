#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/monitor_server.py と services/monitor_client.py(モニターとのやり取り)のテスト
(画面を起動せずに実行できる。この PC の中だけで、実際につないで確かめる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Profile  # noqa: E402
from services import monitor_client, monitor_server  # noqa: E402
from services.monitor_client import MonitorConnection  # noqa: E402
from services.monitor_server import MonitorServer  # noqa: E402


def wait_until(condition, timeout: float = 5.0) -> bool:
    """condition が真になるまで待つ(真になったか)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())


class FrameSource:
    """映像の代役(next で、新しい 1 枚に進める)"""

    def __init__(self):
        self.frame = None
        self.seq = 0
        self.calls = 0

    def next(self, width: int = 640, height: int = 360) -> None:
        self.seq += 1
        frame = np.zeros((height, width, 3), np.uint8)
        frame[:, :, 1] = (self.seq * 40) % 256
        self.frame = frame

    def get(self):
        self.calls += 1
        return self.frame, self.seq


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        patcher = mock.patch.object(Profile, "PROFILES_DIR", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = FrameSource()
        self.actions = []
        self.server = MonitorServer("p1", self.source.get, self.actions.append, backlog_lines=5)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.connections = []

    def connect(self, profile: str = "p1") -> MonitorConnection:
        connection = MonitorConnection(profile, retry_interval=0.05)
        self.connections.append(connection)
        self.addCleanup(connection.close)
        return connection

    def connected(self, profile: str = "p1") -> MonitorConnection:
        connection = self.connect(profile)
        self.assertTrue(wait_until(lambda: connection.connected))
        return connection

    # ---- 見つけ方

    def test_info_file_is_written_and_removed(self):
        path = os.path.join(self.folder, "p1.monitor.json")
        with open(path, encoding="utf-8") as file:
            info = json.load(file)
        self.assertEqual((info["profile"], info["pid"], info["port"]), ("p1", os.getpid(), self.server.port))
        self.assertEqual(monitor_client.running_profiles(), ["p1"])
        self.assertEqual(monitor_client.read_info("p1")["token"], self.server.token)
        self.assertIsNone(monitor_client.read_info("none"))
        self.server.stop()
        self.assertFalse(os.path.exists(path))
        self.assertEqual(monitor_client.running_profiles(), [])
        self.server.stop()

    def test_stop_keeps_an_info_file_written_by_another_instance(self):
        path = os.path.join(self.folder, "p1.monitor.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"profile": "p1", "port": 1, "token": "other"}, file)
        self.server.stop()
        self.assertTrue(os.path.exists(path))

    def test_server_listens_on_this_computer_only(self):
        self.assertEqual(self.server._socket.getsockname()[0], "127.0.0.1")

    # ---- つなぐ

    def test_hello_state_and_backlog(self):
        self.server.set_state({"state": "running", "command": "c"})
        for index in range(8):
            self.server.push_output(1, False, f"line{index}\n")
        self.server.push_output(2, False, "second")
        connection = self.connected()
        self.assertEqual(connection.pid, os.getpid())
        self.assertTrue(wait_until(lambda: connection.state.get("command") == "c" and connection.output(2) == "second"))
        # 後からつないだ相手には、最後の 5 行だけ
        self.assertEqual(connection.output(1), "line3\nline4\nline5\nline6\nline7\n")

    def test_wrong_token_is_rejected(self):
        with open(os.path.join(self.folder, "p1.monitor.json"), "w", encoding="utf-8") as file:
            json.dump({"profile": "p1", "port": self.server.port, "token": "wrong"}, file)
        connection = self.connect()
        time.sleep(0.4)
        self.assertFalse(connection.connected)
        self.assertEqual(self.server.clients(), [])

    def test_data_before_hello_is_rejected(self):
        for data in (monitor_server.pack_json({"op": "action", "name": "stop"}), b"GET / HTTP/1.1\r\n\r\n"):
            with socket.create_connection(("127.0.0.1", self.server.port), timeout=2) as sock:
                sock.sendall(data)
                sock.settimeout(2)
                try:
                    received = sock.recv(10)
                except ConnectionError:
                    received = b""
                # 何も返さずに、切られる
                self.assertEqual(received, b"")
        self.assertEqual(self.actions, [])
        self.assertEqual(self.server.clients(), [])

    def test_profile_that_is_not_running(self):
        connection = self.connect("absent")
        time.sleep(0.2)
        self.assertFalse(connection.connected)
        self.assertFalse(connection.action("play"))

    def test_reconnects_when_the_window_starts_later(self):
        connection = self.connect("p2")
        time.sleep(0.15)
        self.assertFalse(connection.connected)
        second = MonitorServer("p2", self.source.get, self.actions.append)
        second.start()
        self.addCleanup(second.stop)
        self.assertTrue(wait_until(lambda: connection.connected))
        second.push_output(1, False, "kept")
        self.assertTrue(wait_until(lambda: connection.output(1) == "kept"))
        seq = connection.state_seq
        second.stop()
        self.assertTrue(wait_until(lambda: not connection.connected))
        self.assertGreater(connection.state_seq, seq)
        self.assertIsNone(connection.pid)
        # 切れても、Output は読み返せる
        self.assertEqual(connection.output(1), "kept")

    # ---- 状態と Output

    def test_state_is_sent_only_when_it_changes(self):
        connection = self.connected()
        self.server.set_state({"state": "idle", "selected": "a"})
        self.assertTrue(wait_until(lambda: connection.state == {"state": "idle", "selected": "a"}))
        seq = connection.state_seq
        self.server.set_state({"state": "idle", "selected": "a"})
        self.server.set_state({"state": "running", "command": "a"})
        self.assertTrue(wait_until(lambda: connection.state.get("state") == "running"))
        self.assertEqual(connection.state_seq, seq + 1)

    def test_output_append_and_clear(self):
        connection = self.connected()
        self.server.push_output(1, False, "a\n")
        self.server.push_output(1, False, "b\n")
        self.assertTrue(wait_until(lambda: connection.output(1) == "a\nb\n"))
        self.server.push_output(1, True, "new")
        self.assertTrue(wait_until(lambda: connection.output(1) == "new"))
        self.server.push_output(1, True, "")
        self.assertTrue(wait_until(lambda: connection.output(1) == ""))
        self.assertEqual(connection.output(2), "")
        # 知らない出力画面と、空の追記は、何も送らない
        seq = dict(connection.output_seq)
        self.server.push_output(3, False, "x")
        self.server.push_output(1, False, "")
        time.sleep(0.1)
        self.assertEqual(connection.output_seq, seq)

    def test_two_monitors_receive_the_same_output(self):
        first, second = self.connected(), self.connected()
        self.assertTrue(wait_until(lambda: len(self.server.clients()) == 2))
        self.server.push_output(1, False, "both")
        self.assertTrue(wait_until(lambda: first.output(1) == "both" and second.output(1) == "both"))
        first.close()
        self.assertTrue(wait_until(lambda: len(self.server.clients()) == 1))

    def test_flood_of_output_does_not_block_the_writer(self):
        # 受け取らない相手がいても、書き込む側(コマンドのスレッド)は待たされない。溜まりすぎた相手は切る
        with open(os.path.join(self.folder, "p1.monitor.json"), encoding="utf-8") as file:
            info = json.load(file)
        with socket.create_connection(("127.0.0.1", info["port"]), timeout=2) as stalled:
            stalled.sendall(monitor_server.pack_json({"op": "hello", "token": info["token"]}))
            self.assertTrue(wait_until(lambda: len(self.server.clients()) == 1))
            done = []

            def flood():
                text = "x" * 2000 + "\n"
                for _ in range(monitor_server.MAX_PENDING * 3):
                    self.server.push_output(1, False, text)
                done.append(True)

            import threading

            thread = threading.Thread(target=flood, daemon=True)
            started = time.time()
            thread.start()
            thread.join(20)
            self.assertEqual(done, [True], "push_output was blocked")
            self.assertLess(time.time() - started, 15)
            self.assertTrue(wait_until(lambda: self.server.clients() == []))
        # その後も、新しい相手は、つないで受け取れる
        connection = self.connected()
        self.server.push_output(2, False, "after")
        self.assertTrue(wait_until(lambda: connection.output(2) == "after"))

    # ---- 映像

    def test_frames_are_sent_only_when_new_and_resized(self):
        connection = self.connected()
        self.source.next()
        time.sleep(0.2)
        # 頼むまでは、送らない
        self.assertIsNone(connection.frame())
        connection.set_video(30, 320)
        self.assertTrue(wait_until(lambda: connection.frame() is not None))
        image = cv2.imdecode(np.frombuffer(connection.frame(), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape[:2], (180, 320))
        # 同じ映像のままなら、もう送らない(枚数を増やすための水増しはしない)
        seq = connection.frame_seq
        time.sleep(0.4)
        self.assertEqual(connection.frame_seq, seq)
        self.source.next()
        self.assertTrue(wait_until(lambda: connection.frame_seq == seq + 1))
        # 元より大きい幅を頼んでも、引き伸ばさない
        connection.set_video(30, 1280)
        self.assertTrue(wait_until(lambda: connection.frame_seq == seq + 2))
        image = cv2.imdecode(np.frombuffer(connection.frame(), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape[:2], (360, 640))

    def test_frame_rate_is_limited(self):
        connection = self.connected()
        self.source.next()
        connection.set_video(5, 160)
        self.assertTrue(wait_until(lambda: connection.frame() is not None))
        start_seq, started = connection.frame_seq, time.time()
        while time.time() - started < 1.0:
            self.source.next()
            time.sleep(0.005)
        sent = connection.frame_seq - start_seq
        self.assertTrue(3 <= sent <= 7, sent)

    def test_no_frame_when_the_camera_closes(self):
        connection = self.connected()
        self.source.next()
        connection.set_video(30, 160)
        self.assertTrue(wait_until(lambda: connection.frame() is not None))
        self.source.frame = None
        self.assertTrue(wait_until(lambda: connection.frame() is None))
        connection.set_video(0, 160)
        time.sleep(0.2)
        calls = self.source.calls
        self.source.next()
        time.sleep(0.3)
        # 止めた後は、映像を取りに行かない
        self.assertEqual(self.source.calls, calls)

    def test_video_request_is_kept_until_connected(self):
        connection = self.connect("p3")
        connection.set_video(30, 160)
        self.source.next()
        third = MonitorServer("p3", self.source.get, self.actions.append)
        third.start()
        self.addCleanup(third.stop)
        self.assertTrue(wait_until(lambda: connection.frame() is not None))

    # ---- 操作

    def test_actions(self):
        connection = self.connected()
        for name in ("play", "pause", "stop", "front"):
            self.assertTrue(connection.action(name))
        self.assertTrue(wait_until(lambda: len(self.actions) == 4))
        self.assertEqual(self.actions, ["play", "pause", "stop", "front"])
        # 知らない操作は、受け付けない
        connection.action("exit")
        connection.action("play")
        self.assertTrue(wait_until(lambda: len(self.actions) == 5))
        self.assertEqual(self.actions[-1], "play")

    def test_failing_action_does_not_break_the_connection(self):
        self.server.on_action = mock.Mock(side_effect=RuntimeError("boom"))
        connection = self.connected()
        connection.action("play")
        self.assertTrue(wait_until(lambda: self.server.on_action.call_count == 1))
        self.server.push_output(1, False, "alive")
        self.assertTrue(wait_until(lambda: connection.output(1) == "alive"))

    def test_clamp_and_encode(self):
        self.assertEqual(monitor_server.clamp("7", 2, 30, 0), 7)
        self.assertEqual(monitor_server.clamp(99, 2, 30, 0), 30)
        self.assertEqual(monitor_server.clamp(None, 2, 30, 5), 5)
        self.assertIsNone(monitor_server.encode_frame("not an image", 100))


if __name__ == "__main__":
    unittest.main()
