#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web ブラウザ版の画面のサーバー

- アプリ本体(services/app_core.py の AppCore)を、ブラウザから操作する
- 映像は MJPEG(画像の連続送信)、操作と状態の知らせは WebSocket で送る
- 接続は、このアプリを動かしている PC のブラウザからだけ受け付ける
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import Constant
import OutputLinks
import Profile
import Utility as util
from Commands.CommandBase import Command
from services import log_buffer, monitor_relay, note_store, script_creator
from services.controller_setup_service import SetupError
from services.editor_service import EditError
from services.keyboard_session import KeyboardSession
from services.monitor_relay import MonitorRelay
from services.script_creator import ScriptCreateError, ScriptSpec
from services.settings_control import SettingError
from services.tag_session import TagEditorSession
from services.tools_service import QUESTION_NOTE, SERIAL_CONTROLLER_DIR, ToolError
from services.software_controller import SoftwareControllerError
from web.dialogue import DialogueBroker
from web.preview import MAX_WIDTH_CHOICES, FrameEncoder, WebPreview

if TYPE_CHECKING:
    from fastapi import Response

    from services.app_core import AppCore
    from services.software_controller import SoftwareController

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
# ガイド(Instruction Manual・機能紹介)の文章と画像
ASSETS_DIR = os.path.join(SERIAL_CONTROLLER_DIR, "assets")
# 出力画面のページ数
OUTPUT_PAGES = 3
# 音量メーターを送る間隔(出力画面を送る回数で数える。約0.1秒)
METER_TICKS = 2
# 出力画面の内容をブラウザへ送る間隔(秒)
OUTPUT_INTERVAL = 0.05
# カメラの映像の有無を確かめる間隔(出力画面を送る回数で数える。約1秒)
CAMERA_CHECK_TICKS = 20
# あとから開いたブラウザに見せるために覚えておく、出力画面の行数の上限
BACKLOG_MAX_LINES = 2000
# Note タブに保存できる文字数の上限
NOTE_MAX_LENGTH = 1_000_000
# 画像の連続送信の、区切りの文字列
MJPEG_BOUNDARY = "frame"
# 新しい画像を待つ時間の上限(秒)。過ぎたら、同じ画像をもう一度送って接続を保つ
FRAME_WAIT_TIMEOUT = 2.0
# ブラウザで開ける画像の拡張子(キャプチャーのリンク)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")
# 設定の編集の操作
EDIT_ACTIONS = ("shortcut", "mask", "touchscreen", "keymap", "colors", "discord", "line")
OPERATOR = "operator"
VIEWER = "viewer"
# 閲覧のみのブラウザからも受け付ける操作
VIEWER_ACTIONS = ("ping",)
# 一覧で選べるコマンドの種類(モニターからの再生で、始めるコマンドの種類)
COMMAND_TYPES = ("Python", "Mcu")


def allowed_hosts(port: int) -> set:
    """
    受け付ける宛先(Host)。ほかの名前で届いた要求は、別のサイトからの呼び出しの可能性があるので断る
    """
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def ignore_closed_connections(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """
    イベントループの、例外の受け取り口(loop.set_exception_handler に渡す)。
    ブラウザ側が接続を閉じた(映像の受信をやめた、ページを閉じた)ときのエラーは、記録しない
    """
    if isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return
    loop.default_exception_handler(context)


def is_inside(root: str, target: str) -> bool:
    """
    target が、フォルダ root の中にあるか(どちらも絶対パス)
    """
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:
        # ドライブが違う場合など
        return False


def split_output(text: str) -> list:
    """
    出力画面の文字を、ブラウザに渡す形にする: [{"text": 文字, "link": リンクの番号(無ければ None)}, ...]
    """
    if not OutputLinks.has_link(text):
        return [{"text": text, "link": None}]
    return [{"text": part, "link": link_id} for part, link_id in OutputLinks.split(text)]


class Backlog:
    """
    出力画面の内容の控え(あとから開いたブラウザに、それまでの出力を見せる)
    """

    def __init__(self, max_lines: int = BACKLOG_MAX_LINES):
        """max_lines: 出力画面・ページごとに覚えておく行数の上限"""
        self._max_lines = max_lines
        # (出力画面の番号, ページ) -> 文字の並び
        self._parts = {}

    def apply(self, area: int, clear: bool, parts: list, page: int = 0) -> None:
        """
        ブラウザへ送った出力を、控えにも反映する。
        area: 出力画面の番号(1 / 2)、clear: 足す前に消すか、parts: 足す文字(split_output の形)、page: ページ
        """
        stored = self._parts.setdefault((area, page), [])
        if clear:
            stored.clear()
        stored.extend(parts)
        # 行数が上限を超えたら、古い方から捨てる
        lines = sum(part["text"].count("\n") for part in stored)
        while lines > self._max_lines and len(stored) > 1:
            lines -= stored.pop(0)["text"].count("\n")

    def messages(self) -> list:
        """控えの内容を、あとから開いたブラウザへ送る形(出力画面・ページごとの辞書)にする"""
        return [
            {"type": "output", "area": area, "page": page, "clear": True, "parts": list(parts)}
            for (area, page), parts in self._parts.items()
        ]


class LineBacklog:
    """
    Serial タブ・Log タブの内容の控え(あとから開いたブラウザに、それまでの内容を見せる)
    """

    def __init__(self, max_lines: int = BACKLOG_MAX_LINES):
        """max_lines: 覚えておく行数の上限"""
        self._max_lines = max_lines
        # [レベルの分け方(Serial は空文字), 文字] の並び
        self._entries = []
        self._lines = 0

    def add(self, group: str, text: str) -> None:
        """足す。行数が上限を超えたら、古い方から捨てる"""
        self._entries.append([group, text])
        self._lines += text.count("\n")
        while self._lines > self._max_lines and len(self._entries) > 1:
            self._lines -= self._entries.pop(0)[1].count("\n")

    def clear(self) -> None:
        """すべて捨てる"""
        self._entries = []
        self._lines = 0

    def entries(self) -> list:
        """控えの内容([[レベルの分け方, 文字], ...])"""
        return [list(entry) for entry in self._entries]


class Hub:
    """
    開いているブラウザの管理と、ブラウザへの知らせ。
    操作できるのは1つのブラウザだけ(最初に開いたもの)で、ほかは閲覧のみ
    """

    def __init__(self):
        """loop(サーバーのイベントループ)は、サーバーの起動時に入れる"""
        self.loop = None
        self.clients = []
        self.operator = None

    def role_of(self, websocket: WebSocket) -> str:
        """そのブラウザの役割(OPERATOR: 操作できる / VIEWER: 閲覧のみ)"""
        return OPERATOR if websocket is self.operator else VIEWER

    async def add(self, websocket: WebSocket) -> None:
        """開いたブラウザを足す(操作できるブラウザがいなければ、操作できるブラウザにする)"""
        self.clients.append(websocket)
        if self.operator is None:
            self.operator = websocket

    async def remove(self, websocket: WebSocket) -> bool:
        """閉じたブラウザを除く。操作できるブラウザだったかを返す"""
        if websocket in self.clients:
            self.clients.remove(websocket)
        if websocket is self.operator:
            # 操作していたブラウザが閉じたら、次に古いブラウザが操作できるようにする
            self.operator = self.clients[0] if self.clients else None
            if self.operator is not None:
                await self.send(self.operator, {"type": "role", "role": OPERATOR})
            return True
        return False

    async def send(self, websocket: WebSocket, message: dict) -> None:
        """1 つのブラウザへ、JSON にして送る(送れなくても例外にしない)"""
        try:
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            # 閉じたブラウザへの送信は無視する(切断の処理は、受信側で行う)
            pass

    async def broadcast(self, message: dict) -> None:
        """すべてのブラウザへ送る(イベントループの中から呼ぶ)"""
        for websocket in list(self.clients):
            await self.send(websocket, message)

    def post(self, message: dict) -> None:
        """
        すべてのブラウザへ送る(任意のスレッドから呼べる)
        """
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except RuntimeError:
            pass


class WebApp:
    """
    アプリ本体と、Web の画面をつなぐ
    """

    def __init__(self, core_factory: Callable[[WebPreview], AppCore], port: int, monitor_profile: str | None = None):
        """
        core_factory: gui(認識した位置の表示先)を受け取って、アプリ本体(AppCore)を作る関数
        port: 待ち受けるポート番号(受け付ける宛先の確認に使う)
        monitor_profile: 補助ツール(Monitor.py)から見えるようにする場合の、プロファイルの名前(--monitor。None なら、しない)
        """
        self.port = port
        self.monitor_profile = monitor_profile
        self.monitor_link = None
        # 操作できるブラウザが、一覧で選んでいるコマンド (種類, 名前)。補助ツールからの再生で、始めるコマンドになる
        self.selected_command = None
        # ツールの画面の中身(使うときに作る): タグの編集 / Keyboard / モニター
        self._tags = None
        self._keyboard = None
        self._monitor = None
        # ひな形を作る場所(SerialController フォルダー)と、作ったファイルをエディタで開く関数(テスト用に変えられる)
        self.script_base_dir = script_creator.BASE_DIR
        self.open_text_file = util.open_text_file
        self.hub = Hub()
        self.backlog = Backlog()
        # Serial タブ(機器へ送ったデータ)と Log タブ(ログ)の控え
        self.serial_backlog = LineBacklog()
        self.log_backlog = LineBacklog()
        # Note タブの内容(初めて要るときに、今のプロファイルのファイルから読む)
        self.note_text = None
        self.dialogues = DialogueBroker(self._show_dialogue, self._hide_dialogue)
        self._core_factory = core_factory
        self.core = None
        self.encoder = None
        self._frame_event = None
        self._focused = False
        # 操作できるブラウザが表示している、出力画面のページ(コマンドを開始したときの出力先になる)
        self.output_page = 0
        self._meter_shown = False
        # 操作できるブラウザが、マウスで押したままにしている入力("left" / "right" / "touch")
        self._held = set()
        self._original_stdout = sys.stdout
        # アプリを終了する関数(サーバーを止める。起動する側が入れる)
        self.on_exit = None
        self.app = self._create_app()

    # ---------------------------------------------------------------- 起動と終了

    def startup(self) -> None:
        """
        アプリ本体を作って起動する(サーバーの起動時に、1回だけ呼ぶ)
        """
        preview = WebPreview(None, self.hub.post)
        self.core = self._core_factory(preview)
        preview.camera = self.core.camera
        self.encoder = FrameEncoder(self.core, self._on_frame)
        Command.dialogue_handler = self.dialogues.open
        self.core.add_listener(self._on_core_changed)
        # Log タブに表示するために、ログを溜め始める
        log_buffer.install()
        self.core._get_output_page = lambda: self.output_page
        self.core.start()
        if self.monitor_profile is not None:
            from web.monitor_link import WebMonitorLink

            self.monitor_link = WebMonitorLink(self, self.monitor_profile)
            self.monitor_link.start()

    def shutdown(self) -> None:
        """終了の処理(サーバーが止まるときに呼ぶ): ダイアログを閉じ、映像を止め、アプリ本体を閉じ、標準出力を戻す"""
        self.dialogues.cancel_all()
        if self.monitor_link is not None:
            self.monitor_link.stop()
        self._close_tools()
        if self.encoder is not None:
            self.encoder.stop()
        if self.core is not None:
            self.core.close()
        sys.stdout = self._original_stdout

    def _state(self) -> dict:
        """ブラウザへ送る状態(アプリ本体の状態に、出力画面のページと、映像の幅の上限を足したもの)"""
        state = self.core.state()
        state["output_page"] = self.output_page
        state["output_pages"] = OUTPUT_PAGES
        state["preview_max_width"] = self.encoder.max_width if self.encoder is not None else None
        state["preview_max_width_choices"] = list(MAX_WIDTH_CHOICES)
        return state

    def _on_core_changed(self, topic: str) -> None:
        """アプリ本体の状態が変わったときに、すべてのブラウザへ状態を送る(topic は使わない)"""
        self.hub.post({"type": "state", "state": self._state()})

    def _on_frame(self) -> None:
        """新しい画像ができたことを、映像を送る処理に知らせる(画像を作るスレッドから呼ばれる)"""
        loop, event = self.hub.loop, self._frame_event
        if loop is not None and event is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass

    def _show_dialogue(self, request: dict) -> None:
        """ダイアログの表示を、ブラウザに頼む"""
        self.hub.post({"type": "dialogue", "dialogue": request})

    def _hide_dialogue(self, dialogue_id: int) -> None:
        """ダイアログを閉じるよう、ブラウザに頼む"""
        self.hub.post({"type": "dialogue_close", "id": dialogue_id})

    # ---------------------------------------------------------------- 出力画面

    async def _pump_output(self) -> None:
        """
        出力画面に溜まった文字を、まとめてブラウザへ送る。
        カメラの映像が届き始めた / 途切れたときは、状態を知らせる(カメラからは知らせが来ないため)
        """
        camera_opened = None
        ticks = 0
        while True:
            await asyncio.sleep(OUTPUT_INTERVAL)
            ticks += 1
            if ticks % CAMERA_CHECK_TICKS == 0:
                opened = self.core.camera.image_bgr is not None
                if opened != camera_opened:
                    camera_opened = opened
                    await self.hub.broadcast({"type": "state", "state": self._state()})
            if ticks % METER_TICKS == 0:
                await self._send_meter()
            try:
                updates = self.core.output.drain(lambda: self.output_page)
            except Exception:
                _logger.exception("Failed to read the output.")
                continue
            for update in updates:
                parts = split_output(update.text) if update.text else []
                page = update.page if 0 <= update.page < OUTPUT_PAGES else 0
                self.backlog.apply(update.area, update.clear, parts, page)
                await self.hub.broadcast(
                    {"type": "output", "area": update.area, "page": page, "clear": update.clear, "parts": parts}
                )
            try:
                messages = self._view_messages()
            except Exception:
                _logger.exception("Failed to read the serial monitor or the log.")
                continue
            for message in messages:
                await self.hub.broadcast(message)

    def _view_messages(self) -> list:
        """
        シリアルモニターとログに溜まった分を、ブラウザへ送る形にして返す(控えにも足す)。
        開いているブラウザがない間は、取り出さない(溜めたままにして、文字にする処理を行わない。
        溜まるのは、新しいものから 10000 件まで)
        """
        if not self.hub.clients:
            return []
        messages = []
        monitor = getattr(self.core.sender, "monitor", None)
        text = monitor.drain() if monitor is not None else ""
        if text:
            self.serial_backlog.add("", text)
            messages.append({"type": "serial", "clear": False, "text": text})
        segments = log_buffer.buffer.drain_segments()
        if segments:
            for group, segment in segments:
                self.log_backlog.add(group, segment)
            messages.append({"type": "log", "clear": False, "segments": [list(segment) for segment in segments]})
        return messages

    def _view_backlog_messages(self) -> list:
        """Serial タブ・Log タブの控えを、あとから開いたブラウザへ送る形にする"""
        if self.note_text is None:
            self.note_text = note_store.load()
        return [
            {"type": "serial", "clear": True, "text": "".join(text for _, text in self.serial_backlog.entries())},
            {"type": "log", "clear": True, "segments": self.log_backlog.entries()},
            {"type": "note", "text": self.note_text, "saved": False},
        ]

    def _save_note(self, text: object) -> None:
        """
        Note タブの内容を、今のプロファイルのファイルに保存し、ほかのブラウザ(閲覧のみ)の表示も合わせる。
        設定を保存しない起動(同じプロファイルの 2 つ目)では、保存しない
        """
        if not isinstance(text, str) or len(text) > NOTE_MAX_LENGTH:
            return
        if not Profile.is_read_only():
            note_store.save(text)
        self.note_text = text
        self.hub.post({"type": "note", "text": text, "saved": True})

    def _clear_view(self, view: object) -> None:
        """Serial タブ / Log タブの Clear: 溜まっている分と控えを消し、すべてのブラウザの表示を消す"""
        if view == "serial":
            monitor = getattr(self.core.sender, "monitor", None)
            if monitor is not None:
                monitor.clear()
            self.serial_backlog.clear()
            self.hub.post({"type": "serial", "clear": True, "text": ""})
        elif view == "log":
            log_buffer.buffer.clear()
            self.log_backlog.clear()
            self.hub.post({"type": "log", "clear": True, "segments": []})

    async def _send_meter(self) -> None:
        """
        音量メーターの値を送る(音声を取り込んでいる間だけ)
        """
        try:
            meter = self.core.audio.meter()
        except Exception:
            _logger.exception("Failed to read the audio level.")
            return
        if meter is None:
            if self._meter_shown:
                self._meter_shown = False
                await self.hub.broadcast({"type": "meter", "meter": None})
            return
        self._meter_shown = True
        await self.hub.broadcast({"type": "meter", "meter": meter})
        if meter.get("stopped"):
            # 取り込みが止まった(デバイスが外れた等): Use Audio の表示を合わせる
            await self.hub.broadcast({"type": "state", "state": self._state()})

    # ---------------------------------------------------------------- 手動操作

    def _update_keyboard(self) -> None:
        """
        キーボードでの手動操作は、操作できるブラウザの画面が前面にあり、入力欄を使っていない間だけ受け付ける
        """
        core = self.core
        active = bool(core.settings.is_use_keyboard and self._focused and self.hub.operator is not None)
        # (シリアルに接続していない場合は、受け付けを始められない)
        core.set_keyboard_active(active)

    def _handle(self, message: dict, reply: Callable[[dict], None] | None = None) -> None:
        """
        操作できるブラウザからの操作を行う(時間のかかる処理があるので、別のスレッドで呼ぶ)
        message: ブラウザから届いた辞書("action" が操作の名前)
        reply: 操作したブラウザにだけ返事を送る関数(引数は、送る辞書。None なら返事を送らない)
        """
        reply = reply if reply is not None else (lambda data: None)
        # 画面の操作での出力は、表示しているページに出す(実行中のコマンドのページではなく)
        with Command.output_to_page(self.output_page):
            self._handle_action(message, reply)

    def _handle_action(self, message: dict, reply: Callable[[dict], None]) -> None:
        """message の "action" に応じた操作を行う(知らない操作は、ログに残すだけ)"""
        core = self.core
        action = message.get("action")
        if action == "start":
            core.start_command(message.get("command_type"), str(message.get("name", "")))
        elif action == "stop":
            # 先に停止を頼んでから、入力を待っているダイアログを閉じる
            # (ダイアログを先に閉じると、コマンドが自分で終了を始め、停止の依頼と重なる)
            core.stop_command()
            self.dialogues.cancel_all()
        elif action == "pause":
            core.pause_command()
        elif action == "resume":
            core.resume_command()
        elif action == "reload":
            core.reload_commands()
        elif action == "clear":
            for area in (1, 2) if message.get("area") is None else (int(message["area"]),):
                core.output.enqueue(area, "d")
        elif action == "clear_view":
            self._clear_view(message.get("view"))
        elif action == "release_all":
            core.release_all_inputs()
        elif action == "note_save":
            self._save_note(message.get("text"))
        elif action == "link":
            OutputLinks.run(int(message["id"]))
        elif action == "dialogue":
            self.dialogues.answer(int(message["id"]), bool(message.get("ok")), message.get("values"))
        elif action == "focus":
            self._focused = bool(message.get("focused"))
            self._update_keyboard()
        elif action == "keyboard":
            core.settings.is_use_keyboard = bool(message.get("enabled"))
            self._update_keyboard()
            self._on_core_changed("input")
        elif action == "controller":
            if message.get("enabled"):
                core.start_controller()
            else:
                core.stop_controller()
        elif action == "record":
            if core.record.is_recording():
                core.stop_record()
            else:
                core.start_record()
        elif action == "stick":
            side = "left" if message.get("side") == "left" else "right"
            self._held.add(side)
            core.move_stick(side, float(message["angle"]), float(message["magnitude"]))
        elif action == "stick_release":
            side = "left" if message.get("side") == "left" else "right"
            self._held.discard(side)
            core.release_stick(side)
        elif action == "touch":
            if core.touch(float(message["x"]), float(message["y"])):
                self._held.add("touch")
        elif action == "touch_release":
            self._held.discard("touch")
            core.release_touch()
        elif action == "pad":
            self._handle_pad(message, self.core.softcon)
        elif action == "pad2":
            self._handle_pad(message, self.core.simulator)
        elif action == "exit":
            # 画面の「終了」: 全員に知らせてから、サーバーを止める(設定の保存などの終了の処理は、止まるときに行う)
            _logger.debug("Exit is requested from the browser.")
            self.hub.post({"type": "exit"})
            if self.on_exit is not None:
                self.on_exit()
        elif action == "preview_quality":
            # 送る映像の幅の上限(大きいほどくっきりするが、負荷と通信量が増える)
            width = int(message.get("width", 0))
            if width in MAX_WIDTH_CHOICES and self.encoder is not None:
                self.encoder.max_width = width
                self._on_core_changed("preview")
        elif action == "controller_setup":
            self._handle_controller_setup(str(message.get("op")), reply)
        elif action == "output_page":
            page = int(message.get("page", 0))
            if 0 <= page < OUTPUT_PAGES:
                self.output_page = page
                self._on_core_changed("output")
        elif action == "tool":
            try:
                self._handle_tool(str(message.get("op")), message, reply)
            except ToolError as e:
                reply({"type": "tool_error", "op": message.get("op"), "message": str(e)})
                print(e)
        elif action in EDIT_ACTIONS:
            try:
                self._handle_edit(action, message, reply)
            except EditError as e:
                # 理由を、操作した画面と出力画面の両方に知らせる
                reply({"type": "edit_error", "action": action, "message": str(e)})
                print(e)
                self._on_core_changed("settings")
        elif action == "serial":
            if message.get("connect"):
                core.settings_control.scan_ports()
                core.connect_serial()
                core.settings.save()
            else:
                core.disconnect_serial()
        elif action == "camera":
            core.open_camera()
        elif action == "setting":
            try:
                core.settings_control.apply(str(message.get("name")), message.get("value"))
            except (SettingError, TypeError, ValueError) as e:
                print(e if isinstance(e, SettingError) else f"設定を変更できませんでした: {e}")
                # 画面の表示を、変更前の値に戻す
                self._on_core_changed("settings")
        elif action == "scan":
            core.settings_control.scan()
            self._on_core_changed("settings")
        elif action == "scan_ports":
            core.settings_control.scan_ports()
            print(f"Scan Device: シリアルポート {len(core.settings_control.ports)} 個")
            self._on_core_changed("settings")
        elif action == "scan_controllers":
            core.settings_control.scan_controllers()
            self._on_core_changed("settings")
        elif action == "select":
            # 一覧で選んでいるコマンドが変わった(補助ツールからの再生で、始めるコマンド)
            command_type, name = message.get("command_type"), message.get("name")
            valid = command_type in COMMAND_TYPES and isinstance(name, str) and name
            self.selected_command = (command_type, name) if valid else None
        elif action == "tags":
            self._handle_tags(str(message.get("op")), message, reply)
        elif action == "script":
            self._handle_script(str(message.get("op")), message, reply)
        elif action == "switch_keyboard":
            self._handle_switch_keyboard(str(message.get("op")), message, reply)
        elif action == "monitor":
            self._handle_monitor(str(message.get("op")), message, reply)
        else:
            _logger.warning(f"Unknown action: {action}")

    # ---------------------------------------------------------------- ツールの画面

    def _post_to_operator(self, message: dict) -> None:
        """操作できるブラウザにだけ送る(任意のスレッドから呼べる。操作できるブラウザがいなければ、送らない)"""
        loop, operator = self.hub.loop, self.hub.operator
        if operator is None or loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.hub.send(operator, message), loop)
        except RuntimeError:
            pass

    def _close_tools(self) -> None:
        """Keyboard の送信と、モニターのつながりを止める(操作していたブラウザが閉じたとき、終了するとき)"""
        keyboard, self._keyboard = self._keyboard, None
        if keyboard is not None:
            keyboard.close()
        monitor, self._monitor = self._monitor, None
        if monitor is not None:
            monitor.close()

    def _handle_tags(self, op: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        タグの編集画面(op: load = 一覧とタグを読む / save = 変更を保存する)。保存していない変更は、ブラウザが持つ
        """
        core = self.core
        if self._tags is None:
            self._tags = TagEditorSession(
                lambda command_type: core.commands.commands.get(command_type, []), core.refresh_command_list
            )
        if op == "load":
            # ファイルの今の内容で編集を始められるように、開く前に、コマンドの一覧を読み直す
            core.refresh_command_list()
            reply({"type": "tags", "state": self._tags.load()})
        elif op == "save":
            reply({"type": "tags", **self._tags.save(message.get("changes"))})

    def _script_spec(self, message: dict) -> ScriptSpec:
        """ブラウザから届いた入力を、作るスクリプトの内容にする"""
        return ScriptSpec(
            name=str(message.get("name", "")),
            author=str(message.get("author", "")),
            file_name=str(message.get("file_name", "")),
            folder=str(message.get("folder", "")),
            use_bridge=bool(message.get("use_bridge")),
            template_folder=str(message.get("template_folder", "")),
            template_location=str(message.get("template_location", script_creator.IN_TEMPLATE)),
        ).normalized()

    def _handle_script(self, op: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        新しいスクリプトのひな形を作る画面(op: open = 候補を読む / preview = 作るファイルの場所 / create = 作る)
        """
        base = self.script_base_dir
        if op == "open":
            form = {
                "author": script_creator.load_author(base),
                "folders": script_creator.script_folders(base),
                "template_folders": script_creator.template_folders(base),
            }
            reply({"type": "script", "form": form})
        elif op == "preview":
            lines = script_creator.preview_lines(self._script_spec(message), base)
            reply({"type": "script", "preview": "\n".join(lines), "seq": message.get("seq")})
        elif op == "create":
            spec = self._script_spec(message)
            try:
                result = script_creator.create_script(spec, base, app_version=Constant.VERSION)
            except ScriptCreateError as e:
                reply({"type": "script", "error": str(e)})
                return
            script_creator.save_author(spec.author, base)
            print(f"スクリプトを作成しました: {os.path.relpath(result.path, base)}")
            for folder in result.created_folders:
                print(f"フォルダーを作成しました: {os.path.relpath(folder, base)}")
            for path in result.created_files:
                print(f"ひな形を作成しました: {os.path.relpath(path, base)}(要約や使い方を、書き足してください)")
            for path in result.skipped_files:
                print(f"すでにあるため、作成していません: {os.path.relpath(path, base)}")
            _logger.info(f"Script created: {result.path}")
            # 一覧を読み直してから知らせる(ブラウザは、作ったコマンドを選んだ状態にする)
            self.core.refresh_command_list()
            reply({"type": "script", "created": {"command_name": result.command_name}})
            try:
                self.open_text_file(result.path)
            except OSError as e:
                _logger.error(f"Failed to open the file: {e}")
                print(f"Open file: ファイルを開けませんでした。({result.path})")

    def _handle_switch_keyboard(self, op: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        Keyboard(Switch のキーボード画面に、画面上のキーボードから文字を打つ)
        op: open / page / press / special / ok / sync / forget / preview / text
        """

        def status(text: str, is_error: bool = False) -> None:
            """知らせを、操作できるブラウザに送る(送信のスレッドからも呼ばれる)"""
            self._post_to_operator({"type": "switch_keyboard", "status": {"text": text, "error": bool(is_error)}})

        if self._keyboard is None:
            self._keyboard = KeyboardSession(self.core.sender, on_message=status)
        session = self._keyboard
        auto_mode = bool(message.get("auto", True))
        page = str(message.get("page", ""))
        try:
            if op == "open":
                text, is_error = session.availability()
                reply({"type": "switch_keyboard", "layout": session.layout_state(), "status": {"text": text, "error": is_error}})
            elif op == "page":
                session.show_page(page, auto_mode)
            elif op == "press":
                session.press(page, bool(message.get("small")), message.get("row"), message.get("column"), auto_mode)
            elif op == "special":
                session.special(str(message.get("name")))
            elif op == "ok":
                session.ok()
            elif op == "sync":
                session.sync(page)
            elif op == "forget":
                session.forget()
            elif op == "preview":
                text = str(message.get("text", ""))
                reply({"type": "switch_keyboard", "preview": session.preview(text, auto_mode), "text": text})
            elif op == "text":
                sent = session.send_text(str(message.get("text", "")), auto_mode, bool(message.get("enter")))
                reply({"type": "switch_keyboard", "sent": sent})
        except KeyError:
            # 知らないページの名前(ブラウザの画面からは、届かない)
            _logger.warning(f"Keyboard: unknown page: {page}")

    def _handle_monitor(self, op: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        モニター(--monitor を付けて起動した、ほかのウィンドウを、まとめて見る)
        op: open / names / profiles / video / action / action_all / close
        """
        if op == "close":
            monitor, self._monitor = self._monitor, None
            if monitor is not None:
                monitor.close()
            return
        if self._monitor is None:
            self._monitor = MonitorRelay(self._post_to_operator)
        relay = self._monitor
        if op in ("open", "names"):
            if op == "open":
                relay.resend()
            reply({"type": "monitor_info", "names": monitor_relay.profile_names(), "max_count": monitor_relay.MAX_COUNT})
        elif op == "profiles":
            names = message.get("names")
            relay.set_profiles(names if isinstance(names, list) else [])
        elif op == "video":
            relay.set_video(message.get("fps"), message.get("width"))
        elif op == "action":
            profile, name = str(message.get("profile", "")), str(message.get("name", ""))
            sent = relay.action(profile, name)
            reply({"type": "monitor_result", "text": f"{profile}: {name}" if sent else f"{profile}: 送れませんでした"})
        elif op == "action_all":
            names = message.get("profiles")
            count = relay.action_all(str(message.get("name", "")), names if isinstance(names, list) else [])
            reply({"type": "monitor_result", "all": True, "count": count})

    def _handle_controller_setup(self, op: str, reply: Callable[[dict], None]) -> None:
        """
        接続したコントローラーの、ボタンの割り当ての設定(op: start / back / skip / clear / save / cancel)
        """
        setup = self.core.controller_setup

        def push(state: dict) -> None:
            """設定の状態を、操作したブラウザへ送る"""
            reply({"type": "controller_setup", "setup": state})

        try:
            if op == "start":
                state = setup.start(push)
            elif op == "back":
                state = setup.back()
            elif op == "skip":
                state = setup.skip()
            elif op == "clear":
                state = setup.clear()
            elif op == "save":
                state = setup.save()
                state["saved"] = True
            else:
                state = setup.cancel()
        except SetupError as e:
            state = setup.state()
            state["error"] = str(e)
            print(e)
        push(state)
        if op in ("start", "save", "cancel"):
            # 一覧(接続中のコントローラー)と、コントローラーでの操作の状態を合わせる
            self._on_core_changed("input")

    def _handle_tool(self, op: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        こまごました操作(スクリーンショット、ファイルを開く、通知の確認、履歴の削除、プロファイル、ヘルプ)
        できない場合は ToolError(知らない op も)
        """
        tools = self.core.tools
        if op == "capture":
            tools.save_capture(message.get("area"), message.get("name"))
        elif op == "pixel":
            tools.pixel_info(message.get("x"), message.get("y"))
        elif op == "open_captures":
            tools.open_capture_folder()
        elif op == "send_image":
            tools.send_image(str(message.get("target")))
        elif op == "open_image":
            if message.get("how") == "folder":
                tools.open_image_folder(message.get("path", ""))
            else:
                tools.open_image(message.get("path", ""), choose_app=message.get("how") == "with")
        elif op == "open_command":
            tools.open_command_file(message.get("command_type"), str(message.get("name", "")), str(message.get("how", "file")))
        elif op == "command_path":
            reply({"type": "tool_result", "op": op, "text": tools.command_file(message.get("command_type"), str(message.get("name", "")))})
        elif op == "history_delete":
            tools.delete_history(message.get("command_type"), str(message.get("name", "")))
        elif op == "history_clear":
            tools.clear_history()
        elif op == "notify_windows":
            tools.send_windows_notification()
        elif op == "introduction_hidden":
            tools.set_introduction_hidden(bool(message.get("hidden")))
        elif op == "check_line":
            tools.check_line()
        elif op == "check_discord":
            tools.check_discord()
        elif op == "color_preset":
            tools.save_color_preset(str(message.get("controller")), message.get("name", ""))
            reply({"type": "tool_result", "op": op, "text": "書き出しました。"})
        elif op == "profile_add":
            text = tools.add_profile(message.get("name", ""), bool(message.get("copy", True)), message.get("bat") or None)
            reply({"type": "tool_result", "op": op, "text": text})
        elif op == "diagnostics":
            text, masked = tools.diagnostics_texts()
            reply({"type": "tool_result", "op": op, "title": "環境の診断", "text": text, "masked": masked})
        elif op == "changelog":
            reply({"type": "tool_result", "op": op, "title": "更新履歴", "text": tools.changelog_text()})
        elif op == "license":
            reply({"type": "tool_result", "op": op, "title": "LICENSE", "text": tools.license_text()})
        elif op == "question_defaults":
            reply({"type": "tool_result", "op": op, "defaults": tools.question_defaults()})
        elif op == "question":
            text = tools.question_text(*(message.get(name, "") for name in ("program", "developer", "question", "tried")))
            reply({"type": "tool_result", "op": op, "title": "質問テンプレート", "text": text, "note": QUESTION_NOTE})
        elif op == "update":
            reply({"type": "tool_result", "op": op, "result": tools.check_update()})
        else:
            raise ToolError(f"その操作はできません: {op}")

    def _handle_edit(self, action: str, message: dict, reply: Callable[[dict], None]) -> None:
        """
        設定の編集(ショートカット・目隠し・タッチスクリーンの範囲・キーコンフィグ・本体の色・通知先)
        action: EDIT_ACTIONS のどれか。変更できない場合は EditError
        """
        editor = self.core.editor
        op = message.get("op")
        if action == "shortcut":
            if op == "set":
                editor.set_shortcut(message.get("num"), message.get("command_type"), str(message.get("name", "")))
            elif op == "clear":
                editor.clear_shortcut(message.get("num"))
            elif op == "start":
                editor.start_shortcut(message.get("num"))
        elif action == "mask":
            if op == "add":
                editor.add_mask(str(message.get("shape")), *(message.get(name) for name in ("x1", "y1", "x2", "y2")))
            elif op == "update":
                values = message.get("values")
                editor.update_mask(message.get("index"), values if isinstance(values, dict) else {})
            elif op == "delete":
                editor.delete_mask(message.get("index"))
            elif op == "options":
                editor.set_mask_options(message.get("show"), message.get("apply_to_capture"))
            elif op == "save":
                editor.save_mask_file(message.get("name", ""))
            elif op == "load":
                editor.load_mask_file(message.get("name", ""), bool(message.get("replace")))
        elif action == "touchscreen":
            area = message.get("area")
            if not isinstance(area, list) or len(area) != 4:
                raise EditError("Touch Screen: 範囲の指定が正しくありません。")
            editor.set_touchscreen_area(*area)
        elif action == "keymap":
            if op == "get":
                reply({"type": "keymap", "keymap": editor.keymaps()})
            elif op == "save":
                editor.save_keymaps(message.get("keymaps"))
                reply({"type": "keymap", "keymap": editor.keymaps(), "saved": True})
            elif op == "capture":
                field = message.get("field")
                if message.get("start"):
                    editor.start_key_capture(lambda key: reply({"type": "key_captured", "field": field, "key": key}))
                else:
                    editor.stop_key_capture()
        elif action == "colors":
            editor.set_controller_colors(str(message.get("controller")), message.get("colors"))
        elif action == "discord":
            if op == "save":
                state = editor.save_discord(message.get("name", ""), message.get("values"))
                state["saved"] = True
            elif op == "delete":
                state = editor.delete_discord(message.get("name", ""))
                state["saved"] = True
            else:
                state = editor.discord_state(message.get("name"))
            # Webhook URL を含むので、操作したブラウザにだけ返す
            reply({"type": "discord", "discord": state})
        elif action == "line":
            editor.save_line_token(message.get("token", ""))
            reply({"type": "line_saved"})
            self._on_core_changed("settings")

    def _handle_pad(self, message: dict, softcon: SoftwareController) -> None:
        """
        Software-Controller / Controller Simulator の操作
        (op: press / release / hold / hold_end / tilt / center / touch / touch_end / release_all)
        """
        op = message.get("op")
        tag = str(message.get("tag", ""))
        try:
            if op == "press":
                softcon.press(tag)
            elif op == "release":
                softcon.release(tag)
            elif op == "hold":
                softcon.hold(tag)
            elif op == "hold_end":
                softcon.hold_end(tag)
            elif op == "tilt":
                softcon.tilt(tag, float(message["angle"]), float(message["magnitude"]))
            elif op == "center":
                softcon.center(tag)
            elif op == "touch":
                softcon.touch(float(message["x"]), float(message["y"]))
            elif op == "touch_end":
                softcon.touch_end()
            elif op == "release_all":
                softcon.release_all()
        except SoftwareControllerError as e:
            # レイアウトを切り替えた直後に、前のレイアウトの部品が届いた場合など
            _logger.warning(f"Software-Controller: {e}")

    async def _handle_safely(self, message: dict, websocket: WebSocket | None = None) -> None:
        """
        操作を、別のスレッドで行う(終わるまで待つ)。失敗した場合は、理由を出力画面に表示する
        websocket: 操作したブラウザ(None なら、返事を送らない)
        """

        def reply(data: dict) -> None:
            """操作したブラウザにだけ送る"""
            # 別のスレッドから、そのブラウザにだけ送る
            if websocket is not None and self.hub.loop is not None and not self.hub.loop.is_closed():
                asyncio.run_coroutine_threadsafe(self.hub.send(websocket, data), self.hub.loop)

        try:
            await asyncio.to_thread(self._handle, message, reply)
        except Exception as e:
            _logger.exception("Failed to handle a message.")
            self.core.output.enqueue(1 if Command.stdout_destination == "1" else 2, "a", f"操作を実行できませんでした: {e}\n")

    # ---------------------------------------------------------------- サーバー

    def _create_app(self) -> FastAPI:
        """
        FastAPI のアプリを作る(経路: 画面、状態、画像、映像、WebSocket、静的なファイル)。
        経路の関数の戻り値には、型ヒントを付けない(FastAPI が、応答の変換の指定として読むため)
        """
        hosts = allowed_hosts(self.port)
        origins = {f"http://{host}" for host in hosts}

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            """サーバーの起動時にアプリ本体を起動し、止まるときに終了の処理をする"""
            self.hub.loop = asyncio.get_running_loop()
            self.hub.loop.set_exception_handler(ignore_closed_connections)
            self._frame_event = asyncio.Event()
            await asyncio.to_thread(self.startup)
            pump = asyncio.create_task(self._pump_output())
            try:
                yield
            finally:
                pump.cancel()
                await asyncio.to_thread(self.shutdown)

        app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

        @app.middleware("http")
        async def check_host(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            """宛先(Host)が違う要求を断り、応答をブラウザに保存させないようにする"""
            # 別のサイトのページから、名前を偽ってこのサーバーを呼ぶ方法(DNS リバインディング)を防ぐ
            if request.headers.get("host") not in hosts:
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.get("/")
        async def index():
            """画面(index.html)を返す"""
            return FileResponse(os.path.join(STATIC_DIR, "index.html"))

        @app.get("/api/state")
        async def state():
            """今の状態を、JSON で返す"""
            return self._state()

        @app.get("/api/capture")
        async def capture(path: str):
            """保存した画像を返す(path: 画像のファイルのパス。フォルダーの外は 403、画像でない・無い場合は 404)"""
            # 開けるのは、このアプリのフォルダの中にある画像だけ(キャプチャー、テンプレート画像など)
            root = os.path.realpath(SERIAL_CONTROLLER_DIR)
            target = os.path.realpath(path)
            if not is_inside(root, target):
                raise HTTPException(status_code=403, detail="Forbidden")
            if not target.lower().endswith(IMAGE_EXTENSIONS) or not os.path.isfile(target):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(target)

        @app.get("/stream.mjpg")
        async def stream():
            """映像を、画像の連続送信(MJPEG)で返す"""
            return StreamingResponse(
                self._frames(), media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"
            )

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """ブラウザとの WebSocket: 状態と出力を送り、操作できるブラウザからの操作を、届いた順に行う"""
            # ほかのサイトのページからの接続は断る(Origin が無いのは、ブラウザ以外からの接続)
            origin = websocket.headers.get("origin")
            if websocket.headers.get("host") not in hosts or (origin is not None and origin not in origins):
                await websocket.close(code=1008)
                return
            await websocket.accept()
            await self.hub.add(websocket)
            try:
                await self.hub.send(
                    websocket, {"type": "hello", "role": self.hub.role_of(websocket), "state": self._state()}
                )
                for message in self.backlog.messages() + self._view_backlog_messages():
                    await self.hub.send(websocket, message)
                if self.hub.role_of(websocket) == OPERATOR:
                    for request in self.dialogues.pending_requests():
                        await self.hub.send(websocket, {"type": "dialogue", "dialogue": request})
                while True:
                    try:
                        message = json.loads(await websocket.receive_text())
                    except ValueError:
                        continue
                    if not isinstance(message, dict):
                        continue
                    if self.hub.role_of(websocket) != OPERATOR and message.get("action") not in VIEWER_ACTIONS:
                        continue
                    if message.get("action") == "ping":
                        continue
                    # 操作は届いた順に行う
                    await self._handle_safely(message, websocket)
            except WebSocketDisconnect:
                pass
            finally:
                was_operator = await self.hub.remove(websocket)
                if was_operator:
                    # 操作していたブラウザが閉じた: 押したままの入力を離し、キーボードの受け付けを止める
                    self._focused = False
                    await asyncio.to_thread(self._release_inputs)
                    for request in self.dialogues.pending_requests():
                        if self.hub.operator is not None:
                            await self.hub.send(self.hub.operator, {"type": "dialogue", "dialogue": request})

        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        if os.path.isdir(ASSETS_DIR):
            app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
        return app

    def _release_inputs(self) -> None:
        """操作していたブラウザが閉じたときに、押したままの入力を離し、キーの読み取りなどを止める"""
        try:
            self._update_keyboard()
            # キーコンフィグのキーの読み取りとコントローラーの設定を止め、押したままになっている入力だけを離す
            self.core.editor.stop_key_capture()
            self.core.controller_setup.close()
            self.core.softcon.release_all()
            self.core.simulator.release_all()
            self._close_tools()
            held, self._held = self._held, set()
            for name in held:
                if name == "touch":
                    self.core.release_touch()
                else:
                    self.core.release_stick(name)
        except Exception:
            _logger.exception("Failed to release the inputs.")

    async def _frames(self) -> AsyncIterator[bytes]:
        """
        画像の連続送信(MJPEG)。見ているブラウザがある間だけ、画像を作る
        """
        encoder = self.encoder
        encoder.add_viewer()
        last = -1
        try:
            while True:
                jpeg, seq = encoder.latest()
                if jpeg is not None and seq != last:
                    last = seq
                    yield (
                        f"--{MJPEG_BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                        + jpeg
                        + b"\r\n"
                    )
                    continue
                self._frame_event.clear()
                try:
                    await asyncio.wait_for(self._frame_event.wait(), FRAME_WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    # 画像が変わらない間も、同じ画像を送って接続を保つ
                    last = -1
        finally:
            encoder.remove_viewer()

