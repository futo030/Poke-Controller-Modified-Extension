#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
モニター(Monitor.py)が、起動中の Poke-Controller の窓口(services/monitor_server.py)につなぐ部分

1 つのプロファイルにつき、MonitorConnection を 1 つ作る。裏のスレッドが、窓口の情報のファイルを読んでつなぎ、
届いた状態・Output・映像を覚える。切れたときや、まだ起動していないときは、少し待って、つなぎ直す。
画面(tkinter)には触れない。画面の側は、覚えてある内容を、通し番号が変わったときに読んで表示する。
"""
from __future__ import annotations

import json
import os
import socket
import threading
from logging import getLogger, DEBUG, NullHandler

import Profile
from services.monitor_server import (
    HOST,
    INFO_SUFFIX,
    MAX_FPS,
    MIN_FPS,
    PROTOCOL_VERSION,
    TYPE_FRAME,
    TYPE_JSON,
    clamp,
    info_path,
    pack_json,
    receive,
)

__all__ = ["MonitorConnection", "running_profiles", "read_info", "INFO_SUFFIX", "MIN_FPS", "MAX_FPS"]

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# つなぐときに待つ時間と、つなぎ直すまでの間隔(秒)
CONNECT_TIMEOUT = 1.0
RETRY_INTERVAL = 1.0
# 覚えておく Output の行数の上限(出力画面ごと)
MAX_OUTPUT_LINES = 2000


def read_info(profile: str) -> dict | None:
    """そのプロファイルの窓口の情報を読む(ファイルがない・読めない・形が違うときは None)"""
    try:
        with open(info_path(profile), encoding="utf-8") as file:
            info = json.load(file)
        if isinstance(info, dict) and isinstance(info.get("port"), int) and isinstance(info.get("token"), str):
            return info
    except (OSError, ValueError):
        pass
    return None


def running_profiles() -> list[str]:
    """窓口の情報のファイルがあるプロファイルの名前(実際につながるかは、つないでみるまで分からない)"""
    try:
        names = os.listdir(Profile.PROFILES_DIR)
    except OSError:
        return []
    return sorted((name[: -len(INFO_SUFFIX)] for name in names if name.endswith(INFO_SUFFIX)), key=str.lower)


class MonitorConnection:
    """
    1 つのプロファイルの窓口とのつながり。作るとすぐに、裏でつなぎ始める。使い終わったら close

    読んでよい内容(裏のスレッドが書き換える。読むときは snapshot か、それぞれの関数を使う):
        connected: つながっているか
        state: 届いた状態(まだ届いていなければ、空)
        pid: 相手のプロセスの番号(つながっていなければ None)
    """

    def __init__(self, profile: str, retry_interval: float = RETRY_INTERVAL):
        """profile: プロファイルの名前。retry_interval: つなぎ直すまでの間隔(秒)"""
        self.profile = profile
        self.connected = False
        self.state: dict = {}
        self.pid = None
        self._retry_interval = retry_interval
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._socket = None
        self._video = (0, 0)
        self._outputs = {1: "", 2: ""}
        # 画面の側が「前に読んだときから変わったか」を見るための通し番号
        self.state_seq = 0
        self.output_seq = {1: 0, 2: 0}
        self._frame = None
        self.frame_seq = 0
        threading.Thread(target=self._run, name=f"MonitorConnection-{profile}", daemon=True).start()

    # ---------------------------------------------------------------- 画面の側から

    def close(self) -> None:
        """つながりを切って、つなぎ直しもやめる"""
        self._closed.set()
        self._disconnect()

    def set_video(self, fps: int, width: int) -> None:
        """映像の、毎秒の枚数(0 で止める)と幅を頼む(つながっていなければ、つながったときに頼む)"""
        video = (clamp(fps, 0, MAX_FPS, 0), int(width))
        if video != self._video:
            self._video = video
            self._send({"op": "video", "fps": video[0], "width": video[1]})

    def action(self, name: str) -> bool:
        """操作("play" / "pause" / "stop" / "front")を頼む。送れたか(つながっていなければ False)"""
        return self._send({"op": "action", "name": name})

    def output(self, area: int) -> str:
        """その出力画面(1 / 2)の、覚えてある Output"""
        with self._lock:
            return self._outputs[area]

    def frame(self) -> bytes | None:
        """最新の映像(JPEG。なければ None)"""
        with self._lock:
            return self._frame

    # ---------------------------------------------------------------- 裏のスレッド

    def _send(self, message: dict) -> bool:
        """知らせを送る。送れたか"""
        with self._lock:
            sock = self._socket
            if sock is None:
                return False
            try:
                sock.sendall(pack_json(message))
                return True
            except OSError:
                return False

    def _disconnect(self) -> None:
        """切って、映像と状態を「つながっていない」ときの形に戻す(Output は、読み返せるように残す)"""
        with self._lock:
            sock, self._socket = self._socket, None
            was_connected = self.connected
            self.connected = False
            self.pid = None
            self.state = {}
            self._frame = None
            if was_connected:
                self.state_seq += 1
                self.frame_seq += 1
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        """つないで、受け取り続ける。切れたら、少し待って、つなぎ直す(スレッドの中身。close まで)"""
        while not self._closed.is_set():
            info = read_info(self.profile)
            if info is not None:
                try:
                    self._session(info)
                except (OSError, ValueError) as e:
                    _logger.debug(f"Monitor connection to '{self.profile}' ended: {e}")
                self._disconnect()
            self._closed.wait(self._retry_interval)

    def _session(self, info: dict) -> None:
        """1 回のつながり: つないで合言葉を送り、切れるまで受け取る"""
        sock = socket.create_connection((HOST, info["port"]), timeout=CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.sendall(pack_json({"op": "hello", "token": info["token"]}))
        received = receive(sock)
        if received is None or received[0] != TYPE_JSON:
            sock.close()
            return
        hello = json.loads(received[1].decode("utf-8"))
        if hello.get("op") != "hello" or hello.get("version") != PROTOCOL_VERSION or hello.get("profile") != self.profile:
            sock.close()
            return
        sock.settimeout(None)
        with self._lock:
            if self._closed.is_set():
                sock.close()
                return
            self._socket = sock
            self.pid = hello.get("pid")
            self.connected = True
            self.state_seq += 1
            video = self._video
        if video[0] > 0:
            self._send({"op": "video", "fps": video[0], "width": video[1]})
        while not self._closed.is_set():
            received = receive(sock)
            if received is None:
                return
            kind, payload = received
            if kind == TYPE_FRAME:
                with self._lock:
                    self._frame = payload
                    self.frame_seq += 1
            elif kind == TYPE_JSON:
                self._handle(json.loads(payload.decode("utf-8")))

    def _handle(self, message: dict) -> None:
        """届いた知らせを 1 つ、覚える"""
        op = message.get("op")
        with self._lock:
            if op == "state":
                self.state = {key: value for key, value in message.items() if key != "op"}
                self.state_seq += 1
            elif op == "output" and message.get("area") in self._outputs:
                area = message["area"]
                text = str(message.get("text", ""))
                text = text if message.get("clear") else self._outputs[area] + text
                lines = text.split("\n")
                if len(lines) > MAX_OUTPUT_LINES + 1:
                    text = "\n".join(lines[-(MAX_OUTPUT_LINES + 1):])
                self._outputs[area] = text
                self.output_seq[area] += 1
            elif op == "no_frame":
                self._frame = None
                self.frame_seq += 1
