#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
モニター(複数起動をまとめて見る画面)の中身(画面を持たない版)

表示しているプロファイルの窓口(services/monitor_server.py)につなぎ(services/monitor_client.py)、届いた状態・Output・映像を、
変わったときだけ、画面に渡す形の知らせにして send に渡す。Web 版のブラウザの画面が使う。画面(tkinter)には触れない。

send に渡す知らせ:
    {"type": "monitor", "profile": 名前, "connected": つながっているか, "state": 状態,
     "outputs": {"1": 文字, "2": 文字}}     outputs は、変わった出力画面だけ(最後の OUTPUT_TAIL_LINES 行)
    {"type": "monitor_frame", "profile": 名前, "jpeg": JPEG を base64 にした文字(映像がなければ None)}
"""
from __future__ import annotations

import base64
import ctypes
import os
import threading
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

import Profile
from services.monitor_client import MAX_FPS, MIN_FPS, MonitorConnection, running_profiles
from services.monitor_server import clamp

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 一度に表示できるプロファイルの数の上限
MAX_COUNT = 12
DEFAULT_FPS = 5
# 画面に渡す Output の行数
OUTPUT_TAIL_LINES = 300
# 頼む映像の幅の範囲
MIN_VIDEO_WIDTH, MAX_VIDEO_WIDTH = 128, 1280
# 届いた内容を調べる間隔(秒)
TICK_SECONDS = 0.03
AREAS = (1, 2)
# まとめての操作で頼める操作
ALL_ACTIONS = ("play", "stop")


def tail_lines(text: str, count: int) -> str:
    """文字の、最後の count 行"""
    lines = text.split("\n")
    return text if len(lines) <= count + 1 else "\n".join(lines[-(count + 1):])


def profile_names() -> list:
    """選べるプロファイルの名前(今あるプロファイルと、窓口を開いているもの)"""
    names = Profile.list_profiles()
    return names + [name for name in running_profiles() if name not in names]


def is_target(state: dict, action: str) -> bool:
    """
    その状態のウィンドウが、まとめての操作の対象か。
    action: "play"(待機中で開始できるものと、一時停止中のもの)/ "stop"(実行中・一時停止中のもの)
    """
    if action == "play":
        return state.get("state") == "paused" or bool(state.get("can_start"))
    return state.get("state") in ("running", "paused")


class MonitorRelay:
    """
    表示しているプロファイルとのつながりを持ち、変わった内容を send に渡す。使い終わったら close
    """

    def __init__(
        self,
        send: Callable[[dict], None],
        connection_factory: Callable[[str], MonitorConnection] = MonitorConnection,
        tick_seconds: float = TICK_SECONDS,
    ):
        """
        send: 知らせを受け取る関数(裏のスレッドから呼ぶ)
        connection_factory: プロファイルの名前から、つながりを作る関数(テスト用に変えられる)
        tick_seconds: 届いた内容を調べる間隔(秒)
        """
        self._send = send
        self._factory = connection_factory
        self._tick = tick_seconds
        self._lock = threading.Lock()
        self.connections: dict[str, MonitorConnection] = {}
        # プロファイルごとの、前に知らせたときの通し番号
        self._seen: dict[str, tuple] = {}
        self._frame_seen: dict[str, int] = {}
        self._video = (DEFAULT_FPS, MIN_VIDEO_WIDTH)
        self._closed = threading.Event()
        threading.Thread(target=self._run, name="MonitorRelay", daemon=True).start()

    # ---------------------------------------------------------------- 画面の側から

    def close(self) -> None:
        """すべてのつながりを切って、知らせるのをやめる"""
        self._closed.set()
        with self._lock:
            connections, self.connections = self.connections, {}
        for connection in connections.values():
            connection.close()

    def set_profiles(self, names: list) -> None:
        """表示するプロファイルを決める(表示するものにだけ、つなぐ。表示をやめたものは、切る)"""
        shown = [str(name) for name in names if isinstance(name, str) and name][:MAX_COUNT]
        closing = []
        with self._lock:
            if self._closed.is_set():
                return
            for profile in list(self.connections):
                if profile not in shown:
                    closing.append(self.connections.pop(profile))
                    self._seen.pop(profile, None)
                    self._frame_seen.pop(profile, None)
            for profile in shown:
                if profile not in self.connections:
                    connection = self._factory(profile)
                    connection.set_video(*self._video)
                    self.connections[profile] = connection
        for connection in closing:
            connection.close()

    def set_video(self, fps: object, width: object) -> None:
        """映像の、毎秒の枚数と幅を、すべての相手に頼む(範囲の外の値は、範囲に収める)"""
        video = (clamp(fps, MIN_FPS, MAX_FPS, DEFAULT_FPS), clamp(width, MIN_VIDEO_WIDTH, MAX_VIDEO_WIDTH, MIN_VIDEO_WIDTH))
        with self._lock:
            self._video = video
            connections = list(self.connections.values())
        for connection in connections:
            connection.set_video(*video)

    def resend(self) -> None:
        """今の内容を、すべて知らせ直す(画面を開き直したとき)"""
        with self._lock:
            self._seen.clear()
            self._frame_seen.clear()

    def action(self, profile: str, name: str) -> bool:
        """操作("play" / "pause" / "stop" / "front")を、そのプロファイルのウィンドウに頼む。送れたか"""
        with self._lock:
            connection = self.connections.get(profile)
        if connection is None or not connection.connected:
            return False
        if name == "front" and os.name == "nt" and connection.pid:
            # ほかのアプリのウィンドウを前に出すには、今、前にいる側の許可が要る(このプロセスが前にいないときは、効かない)
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(int(connection.pid))
            except Exception:
                pass
        return connection.action(name)

    def action_all(self, name: str, profiles: list) -> int:
        """
        まとめての操作: profiles のうち、今も対象の状態のウィンドウに、操作("play" / "stop")を頼む。頼んだ数を返す
        (確認している間に状態が変わったものには、頼まない)
        """
        if name not in ALL_ACTIONS:
            return 0
        with self._lock:
            targets = [self.connections[profile] for profile in dict.fromkeys(profiles) if profile in self.connections]
        return sum(
            bool(connection.action(name))
            for connection in targets
            if connection.connected and is_target(connection.state, name)
        )

    # ---------------------------------------------------------------- 裏のスレッド

    def _run(self) -> None:
        """一定の間隔で、届いた内容を調べて、変わっていれば知らせる(スレッドの中身。close まで)"""
        while not self._closed.wait(self._tick):
            with self._lock:
                connections = list(self.connections.items())
            for profile, connection in connections:
                try:
                    self._check(profile, connection)
                except Exception:
                    _logger.exception("Failed to relay the monitor data")

    def _check(self, profile: str, connection: MonitorConnection) -> None:
        """1 つのつながりの内容を調べて、前に知らせたときから変わった所を知らせる"""
        connected = connection.connected
        seen = (connection, connected, connection.state_seq, connection.output_seq[1], connection.output_seq[2])
        frame_seq = connection.frame_seq
        with self._lock:
            if self.connections.get(profile) is not connection:
                return
            previous = self._seen.get(profile)
            previous_frame = self._frame_seen.get(profile)
            self._seen[profile] = seen
            self._frame_seen[profile] = frame_seq
        if seen != previous:
            outputs = {
                str(area): tail_lines(connection.output(area), OUTPUT_TAIL_LINES)
                for index, area in enumerate(AREAS)
                if previous is None or previous[:2] != seen[:2] or previous[3 + index] != seen[3 + index]
            }
            self._send(
                {"type": "monitor", "profile": profile, "connected": connected, "state": dict(connection.state), "outputs": outputs}
            )
        if frame_seq != previous_frame or (previous is not None and previous[:2] != seen[:2]):
            jpeg = connection.frame() if connected else None
            self._send(
                {
                    "type": "monitor_frame",
                    "profile": profile,
                    "jpeg": base64.b64encode(jpeg).decode("ascii") if jpeg else None,
                }
            )
