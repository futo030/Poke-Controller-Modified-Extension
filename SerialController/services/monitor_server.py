#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
モニター(複数起動をまとめて見る補助ツール。Monitor.py)のための窓口

起動時に --monitor を付けたときだけ使う。この PC の中(127.0.0.1)からの接続だけを受け付け、つないできた補助ツールに、
状態・Output・カメラの映像を送り、操作(再生・一時停止・停止・ウィンドウを前面に表示)の依頼を受け取る。
画面(tkinter)には触れない。状態の中身と、依頼の実行は、作る側(ui/monitor_link.py)が受け持つ。

見つけ方: 窓口を開くと、profiles/<プロファイル名>.monitor.json に、ポート番号と合言葉を書く(閉じるときに消す)。
          補助ツールは、このファイルを読んでつなぎ、初めに合言葉を送る。合言葉が違う相手は、切る。

やり取りの形: [種類 1 バイト][長さ 4 バイト(ビッグエンディアン)][中身]
    種類 "J": 中身は JSON(UTF-8)。種類 "F": 中身は JPEG の画像(映像の 1 枚)
  補助ツール → 窓口:
    {"op": "hello", "token": 合言葉}
    {"op": "video", "fps": 毎秒の枚数(0 で止める), "width": 幅}
    {"op": "action", "name": "play" / "pause" / "stop" / "front"}
  窓口 → 補助ツール:
    {"op": "hello", "version": 版, "profile": 名前, "pid": プロセスの番号}
    {"op": "state", ...}                         状態(変わるたび。中身は、作る側が決める)
    {"op": "output", "area": 1 か 2, "clear": 消してから書くか, "text": 足す文字}
    {"op": "no_frame"}                           映像がなくなった(カメラを閉じた)
"""
from __future__ import annotations

import json
import os
import queue
import secrets
import socket
import struct
import threading
import time
from logging import getLogger, DEBUG, NullHandler
from typing import Any, Callable

import cv2

import Profile

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

PROTOCOL_VERSION = 1
HOST = "127.0.0.1"
INFO_SUFFIX = ".monitor.json"
TYPE_JSON = b"J"
TYPE_FRAME = b"F"
_HEADER = struct.Struct(">cI")
# 1 つの中身の大きさの上限(これより大きいものを送ってくる相手は、切る)
MAX_PAYLOAD = 16 * 1024 * 1024
# 映像の、毎秒の枚数と幅の範囲
MIN_FPS, MAX_FPS = 2, 30
MIN_WIDTH, MAX_WIDTH = 96, 1920
JPEG_QUALITY = 70
# 後からつないだ補助ツールに送る、Output の行数の上限(出力画面ごと)
BACKLOG_LINES = 500
# 合言葉を待つ時間(秒)
HELLO_TIMEOUT = 5.0
# 送る順番を待つ知らせの数の上限(これを超えたら、受け取りが止まっていると見なして切る)
MAX_PENDING = 2000
ACTIONS = ("play", "pause", "stop", "front")


def info_path(profile: str) -> str:
    """そのプロファイルの窓口の情報(ポート番号と合言葉)を書くファイルの場所"""
    return os.path.join(Profile.PROFILES_DIR, profile + INFO_SUFFIX)


def pack(kind: bytes, payload: bytes) -> bytes:
    """種類と中身を、送る形にする"""
    return _HEADER.pack(kind, len(payload)) + payload


def pack_json(message: dict) -> bytes:
    """JSON の知らせを、送る形にする"""
    return pack(TYPE_JSON, json.dumps(message, ensure_ascii=False).encode("utf-8"))


def receive(sock: socket.socket) -> tuple[bytes, bytes] | None:
    """1 つ受け取って、(種類, 中身)を返す。相手が切ったときは None。形が違うときは ValueError"""
    header = _receive_exact(sock, _HEADER.size)
    if header is None:
        return None
    kind, length = _HEADER.unpack(header)
    if kind not in (TYPE_JSON, TYPE_FRAME) or length > MAX_PAYLOAD:
        raise ValueError("unexpected data")
    payload = _receive_exact(sock, length)
    return None if payload is None else (kind, payload)


def _receive_exact(sock: socket.socket, length: int) -> bytes | None:
    """ちょうど length バイトを受け取る(途中で相手が切ったときは None)"""
    chunks = []
    while length > 0:
        chunk = sock.recv(min(length, 65536))
        if not chunk:
            return None
        chunks.append(chunk)
        length -= len(chunk)
    return b"".join(chunks)


def clamp(value: Any, low: int, high: int, default: int) -> int:
    """value を整数にして、low〜high に収める(整数にできなければ default)"""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def encode_frame(frame: Any, width: int) -> bytes | None:
    """映像の 1 枚(BGR の配列)を、幅 width 以下に縮めて JPEG にする(できなければ None)"""
    try:
        height, original_width = frame.shape[:2]
        if original_width > width:
            frame = cv2.resize(frame, (width, max(1, round(height * width / original_width))), interpolation=cv2.INTER_AREA)
        ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return data.tobytes() if ok else None
    except Exception:
        return None


class _Client:
    """つないできた補助ツール 1 つ分。受け取りと送信を、それぞれのスレッドで行う"""

    def __init__(self, server: MonitorServer, sock: socket.socket):
        """server: 窓口。sock: つながった相手"""
        self.server = server
        self.sock = sock
        self.alive = True
        self.ready = False
        self._pending = queue.Queue()
        self._video = (0, 0)
        self._last_seq = None
        self._had_frame = False
        threading.Thread(target=self._read_loop, name="MonitorClientReader", daemon=True).start()

    def post(self, data: bytes) -> None:
        """送る知らせを、順番待ちに入れる(どのスレッドから呼んでも、待たされない)"""
        if not self.alive:
            return
        if self._pending.qsize() > MAX_PENDING:
            self.close()
            return
        self._pending.put(data)

    def close(self) -> None:
        """切る"""
        if self.alive:
            self.alive = False
            try:
                self.sock.close()
            except OSError:
                pass
            self._pending.put(None)
            self.server._remove(self)

    def _read_loop(self) -> None:
        """合言葉を確かめてから、依頼を受け取り続ける(スレッドの中身)"""
        try:
            self.sock.settimeout(HELLO_TIMEOUT)
            message = self._receive_json()
            if message is None or message.get("op") != "hello" or not secrets.compare_digest(
                str(message.get("token", "")), self.server.token
            ):
                return
            # 受け取りは待ち続ける。送信が止まった相手は、順番待ちが溜まった所で切る(post)
            self.sock.settimeout(None)
            self.server._welcome(self)
            self.ready = True
            threading.Thread(target=self._send_loop, name="MonitorClientSender", daemon=True).start()
            while self.alive:
                message = self._receive_json()
                if message is None:
                    return
                self._handle(message)
        except (OSError, ValueError):
            pass
        finally:
            self.close()

    def _receive_json(self) -> dict | None:
        """JSON の知らせを 1 つ受け取る(相手が切ったときは None。JSON でないものは ValueError)"""
        received = receive(self.sock)
        if received is None:
            return None
        kind, payload = received
        if kind != TYPE_JSON:
            raise ValueError("unexpected data")
        message = json.loads(payload.decode("utf-8"))
        if not isinstance(message, dict):
            raise ValueError("unexpected data")
        return message

    def _handle(self, message: dict) -> None:
        """依頼を 1 つ処理する"""
        op = message.get("op")
        if op == "video":
            fps = clamp(message.get("fps"), 0, MAX_FPS, 0)
            self._video = (0 if fps <= 0 else max(MIN_FPS, fps), clamp(message.get("width"), MIN_WIDTH, MAX_WIDTH, 320))
            self._last_seq = None
            self._pending.put(b"")  # 送信のスレッドを起こして、新しい設定で送り始める
        elif op == "action" and message.get("name") in ACTIONS:
            try:
                self.server.on_action(message["name"])
            except Exception:
                _logger.exception("Monitor action failed")

    def _send_loop(self) -> None:
        """順番待ちの知らせと、映像を送り続ける(スレッドの中身)"""
        next_frame = time.perf_counter()
        try:
            while self.alive:
                fps, width = self._video
                timeout = 0.5 if fps <= 0 else max(next_frame - time.perf_counter(), 0.0)
                try:
                    data = self._pending.get(timeout=timeout) if timeout > 0 else self._pending.get_nowait()
                except queue.Empty:
                    data = b""
                if data is None:
                    return
                if data:
                    self.sock.sendall(data)
                    continue
                fps, width = self._video
                if fps <= 0:
                    continue
                now = time.perf_counter()
                if now < next_frame:
                    continue
                next_frame = max(next_frame + 1.0 / fps, now)
                self._send_frame(width)
        except OSError:
            pass
        finally:
            self.close()

    def _send_frame(self, width: int) -> None:
        """新しい映像があれば、1 枚送る(前に送ったものと同じなら、送らない)"""
        frame, seq = self.server.get_frame()
        if frame is None:
            if self._had_frame:
                self._had_frame = False
                self.sock.sendall(pack_json({"op": "no_frame"}))
            self._last_seq = None
            return
        if seq == self._last_seq:
            return
        self._last_seq = seq
        data = encode_frame(frame, width)
        if data is not None:
            self._had_frame = True
            self.sock.sendall(pack(TYPE_FRAME, data))


class MonitorServer:
    """
    モニターのための窓口。start で開き、stop で閉じる
    """

    def __init__(
        self,
        profile: str,
        get_frame: Callable[[], tuple[Any, int]],
        on_action: Callable[[str], None],
        backlog_lines: int = BACKLOG_LINES,
    ):
        """
        profile: プロファイルの名前(情報のファイルの名前になる)
        get_frame: (最新の映像(BGR の配列。なければ None), 映像の通し番号)を返す関数。送信のスレッドから呼ぶ
        on_action: 操作の依頼("play" / "pause" / "stop" / "front")を受け取る関数。受け取りのスレッドから呼ぶ
        backlog_lines: 後からつないだ補助ツールに送る、Output の行数の上限
        """
        self.profile = profile
        self.get_frame = get_frame
        self.on_action = on_action
        self.token = secrets.token_hex(16)
        self.port = 0
        self._backlog_lines = backlog_lines
        # 送る途中で相手を切ることがあり(順番待ちが溜まったとき)、そのときに同じスレッドでもう一度使うので、RLock にする
        self._lock = threading.RLock()
        self._clients: list[_Client] = []
        self._state: dict | None = None
        # これまでの Output(出力画面ごと)。書き込みのたびに全体を作り直さないように、足された文字を並べて持ち、
        # 行数が上限の 2 倍を超えたときだけ、上限まで切り詰める
        self._backlog = {1: [], 2: []}
        self._backlog_newlines = {1: 0, 2: 0}
        self._socket = None
        self._info_path = info_path(profile)

    # ---------------------------------------------------------------- 開く・閉じる

    def start(self) -> None:
        """窓口を開き、情報のファイルを書く(開けないときは OSError)"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((HOST, 0))
        server.listen(8)
        self._socket = server
        self.port = server.getsockname()[1]
        info = {"version": PROTOCOL_VERSION, "profile": self.profile, "pid": os.getpid(), "port": self.port, "token": self.token}
        temporary = self._info_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(info, file)
        os.replace(temporary, self._info_path)
        threading.Thread(target=self._accept_loop, args=(server,), name="MonitorServer", daemon=True).start()
        _logger.info(f"Monitor server started (port {self.port})")

    def stop(self) -> None:
        """窓口を閉じ、つないでいる相手を切り、情報のファイルを消す(何度呼んでもよい)"""
        server, self._socket = self._socket, None
        if server is None:
            return
        try:
            server.close()
        except OSError:
            pass
        for client in self.clients():
            client.close()
        try:
            # ほかの起動が書き直したものは、消さない
            with open(self._info_path, encoding="utf-8") as file:
                token = json.load(file).get("token")
            if token == self.token:
                os.remove(self._info_path)
        except (OSError, ValueError):
            pass
        _logger.info("Monitor server stopped")

    def _accept_loop(self, server: socket.socket) -> None:
        """つないでくる相手を受け付け続ける(スレッドの中身。窓口を閉じるまで)"""
        while True:
            try:
                sock, _ = server.accept()
            except OSError:
                return
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            _Client(self, sock)

    # ---------------------------------------------------------------- 相手

    def clients(self) -> list:
        """合言葉を確かめ終えた相手の一覧"""
        with self._lock:
            return list(self._clients)

    def _welcome(self, client: _Client) -> None:
        """合言葉が合った相手に、今の状態と、これまでの Output を送って、一覧に入れる"""
        with self._lock:
            client.post(pack_json({"op": "hello", "version": PROTOCOL_VERSION, "profile": self.profile, "pid": os.getpid()}))
            if self._state is not None:
                client.post(pack_json({"op": "state", **self._state}))
            for area in self._backlog:
                client.post(pack_json({"op": "output", "area": area, "clear": True, "text": self._trim_backlog(area)}))
            self._clients.append(client)

    def _remove(self, client: _Client) -> None:
        """切れた相手を、一覧から外す"""
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def _trim_backlog(self, area: int) -> str:
        """その出力画面の、これまでの Output を、行数の上限まで切り詰めて、その文字を返す(_lock を持って呼ぶ)"""
        backlog = "".join(self._backlog[area])
        lines = backlog.split("\n")
        if len(lines) > self._backlog_lines + 1:
            backlog = "\n".join(lines[-(self._backlog_lines + 1):])
        self._backlog[area] = [backlog] if backlog else []
        self._backlog_newlines[area] = backlog.count("\n")
        return backlog

    # ---------------------------------------------------------------- 送る

    def set_state(self, state: dict) -> None:
        """状態を知らせる(前に知らせたものと同じなら、何も送らない)"""
        with self._lock:
            if state == self._state:
                return
            self._state = dict(state)
            data = pack_json({"op": "state", **self._state})
            for client in list(self._clients):
                client.post(data)

    def push_output(self, area: int, clear: bool, text: str) -> None:
        """Output に書かれた内容を知らせる(どのスレッドから呼んでもよく、待たされない)"""
        if area not in self._backlog or (not clear and not text):
            return
        with self._lock:
            if clear:
                self._backlog[area] = []
                self._backlog_newlines[area] = 0
            if text:
                self._backlog[area].append(text)
                self._backlog_newlines[area] += text.count("\n")
                if self._backlog_newlines[area] > self._backlog_lines * 2:
                    self._trim_backlog(area)
            if not self._clients:
                return
            data = pack_json({"op": "output", "area": area, "clear": bool(clear), "text": text})
            # 送る途中で切れた相手は、一覧から外れるので、一覧の写しを回す
            for client in list(self._clients):
                client.post(data)
