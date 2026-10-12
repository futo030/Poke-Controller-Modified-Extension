#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
モニター(補助ツール。Monitor.py)と、Web 版の画面のアプリ本体をつなぐ

起動時に --ui web --monitor を付けたときだけ作る(ウィンドウの画面では ui/monitor_link.py)。
窓口(services/monitor_server.py)を開き、
- 状態(実行中のコマンド、実行中・一時停止・待機)を、一定の間隔で調べて知らせる
- Output に書かれた内容を、そのまま知らせる
- カメラの映像を渡す
- 補助ツールからの操作(再生・一時停止・停止)を実行する

ウィンドウの画面との違い:
- 再生で始まるコマンドは、操作できるブラウザが、一覧で選んでいるコマンド(ブラウザが知らせてくる。閉じた後も、最後に選んでいたもの)
- 「前面に表示」は、できない(ブラウザのタブを、アプリの側から前に出せないため。Output に、その旨を表示する)
"""
from __future__ import annotations

import threading
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any

import Constant
import Profile
from Commands.CommandBase import Command
from services import command_service
from services.monitor_server import MonitorServer

if TYPE_CHECKING:
    from web.server import WebApp

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 状態を調べる間隔(秒)
STATE_INTERVAL = 0.2
# 補助ツールに知らせる状態の名前
IDLE, RUNNING, PAUSED, STOPPING = "idle", "running", "paused", "stopping"
# 補助ツールに知らせる、このウィンドウのテーマ(Web 版の配色は、ブラウザごとに決まるので、デフォルトとして扱う)
THEME = "default"


class WebMonitorLink:
    """
    Web 版の画面のアプリ本体の、モニターとのつなぎ役
    """

    def __init__(self, web_app: WebApp, profile: str):
        """web_app: Web の画面とアプリ本体をつなぐもの(アプリ本体を作った後に渡す)。profile: プロファイルの名前"""
        self.web_app = web_app
        self.profile = profile
        self.server = MonitorServer(profile, self._frame, self._on_action)
        self._stopped = threading.Event()
        self._started = False

    def start(self) -> bool:
        """
        窓口を開く。開けたか。
        同じプロファイルの 2 つ目以降(設定を保存しないもの)では、開かない(1 つ目の窓口と区別できないため)
        """
        if Profile.is_read_only():
            print("このプロファイルは、すでに起動されているため、--monitor は無効です。")
            return False
        try:
            self.server.start()
        except OSError as e:
            print(f"モニター用の窓口を開けませんでした: {e}")
            _logger.warning(f"Failed to start the monitor server: {e}")
            return False
        self._started = True
        self.web_app.core.output.listeners.append(self._on_output)
        threading.Thread(target=self._poll, name="WebMonitorLink", daemon=True).start()
        return True

    def stop(self) -> None:
        """窓口を閉じる(何度呼んでもよい)"""
        self._stopped.set()
        if self._started:
            self._started = False
            self.server.stop()

    # ---------------------------------------------------------------- 知らせる

    def selected(self) -> tuple[str, str] | None:
        """操作できるブラウザが選んでいるコマンド(種類, 名前)。選んでいない・一覧にない場合は None"""
        selected = self.web_app.selected_command
        if selected is None:
            return None
        command_type, name = selected
        entries = self.web_app.core.commands.commands.get(command_type, [])
        return selected if any(entry.name == name for entry in entries) else None

    def state(self) -> dict:
        """今の状態"""
        core = self.web_app.core
        service = core.commands
        selected = self.selected()
        if service.state == command_service.IDLE:
            state, command = IDLE, ""
        else:
            command = str(getattr(service.current, "NAME", "") or "")
            if service.state == command_service.STOPPING:
                state = STOPPING
            else:
                state = PAUSED if Command.isPause else RUNNING
        return {
            "state": state,
            # 実行中のコマンド(待機中は空)と、一覧で選んでいるコマンド(再生で始まるもの)
            "command": command,
            "selected": selected[1] if selected else "",
            "can_start": state == IDLE and selected is not None and not core.record.is_recording(),
            "can_pause": state == RUNNING and bool(service.can_pause),
            "title": f"{Constant.NAME} ver.{Constant.VERSION} (profile: {self.profile}) [Web]",
            "theme": THEME,
            # print の出力先の出力画面(1 / 2)。補助ツールは、初めは、こちらの Output を表示する
            "stdout_area": 2 if str(Command.stdout_destination) == "2" else 1,
        }

    def _poll(self) -> None:
        """一定の間隔で状態を調べて、変わっていれば知らせる(スレッドの中身。stop まで)"""
        while not self._stopped.wait(STATE_INTERVAL):
            try:
                self.server.set_state(self.state())
            except Exception:
                _logger.exception("Failed to read the state for the monitor")

    def _on_output(self, area: int, mode: str, text: str) -> None:
        """Output に書かれたとき(書いたスレッドで呼ばれる): 内容を知らせる。mode: 'w' 上書き / 'a' 追記 / 'd' 削除"""
        self.server.push_output(area, mode in ("w", "d"), text if mode in ("w", "a") else "")

    def _frame(self) -> tuple[Any, int]:
        """カメラの最新の映像と、その通し番号(窓口の送信のスレッドから呼ばれる)"""
        camera = getattr(self.web_app.core, "camera", None)
        if camera is None:
            return None, 0
        return camera.latestFrame()

    # ---------------------------------------------------------------- 操作

    def _on_action(self, name: str) -> None:
        """補助ツールからの操作の依頼(窓口のスレッドで呼ばれる): 別のスレッドで実行する(窓口を待たせない)"""
        threading.Thread(target=self._perform_safely, args=(name,), name="WebMonitorAction", daemon=True).start()

    def _perform_safely(self, name: str) -> None:
        """操作を実行する(失敗しても、スレッドの外に例外を出さない)"""
        try:
            # 操作での出力は、ブラウザが表示しているページに出す(ブラウザからの操作と同じ)
            with Command.output_to_page(self.web_app.output_page):
                self.perform(name)
        except Exception:
            _logger.exception("Failed to perform a monitor action")

    def perform(self, name: str) -> None:
        """
        操作を実行する。今の状態でできない操作は、何もしない。
        name: "play"(待機中は、選んでいるコマンドを開始。一時停止中は、再開)/ "pause" / "stop" / "front"
        """
        core = self.web_app.core
        state = self.state()
        _logger.info(f"Monitor action: {name} (state: {state['state']})")
        if name == "play":
            if state["state"] == PAUSED:
                core.resume_command()
            elif state["can_start"]:
                core.start_command(*self.selected())
        elif name == "pause":
            if state["can_pause"]:
                core.pause_command()
        elif name == "stop":
            if state["state"] in (RUNNING, PAUSED):
                # ブラウザからの停止と同じ順(先に停止を頼んでから、入力を待っているダイアログを閉じる)
                core.stop_command()
                self.web_app.dialogues.cancel_all()
        elif name == "front":
            print("モニター: Web 版の画面は、前面に表示できません(ブラウザのタブを選んでください)。")
