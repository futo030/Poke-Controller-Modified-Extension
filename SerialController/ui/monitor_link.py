#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
モニター(補助ツール。Monitor.py)と、このウィンドウをつなぐ

起動時に --monitor を付けたときだけ作る。窓口(services/monitor_server.py)を開き、
- 状態(実行中のコマンド、実行中・一時停止・待機)を、一定の間隔で調べて知らせる
- Output に書かれた内容を、そのまま知らせる
- カメラの映像を渡す
- 補助ツールからの操作(再生・一時停止・停止・前面に表示)を、画面のスレッドで実行する
"""
from __future__ import annotations

import atexit
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any

import Profile
import Theme
from Commands.CommandBase import Command
from services import command_service
from services.monitor_server import MonitorServer
from UiDispatcher import UiDispatcher

if TYPE_CHECKING:
    from Window import PokeControllerApp

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 状態を調べる間隔(ms)
STATE_INTERVAL_MS = 200
# 補助ツールに知らせる状態の名前
IDLE, RUNNING, PAUSED, STOPPING = "idle", "running", "paused", "stopping"


class MonitorLink:
    """
    このウィンドウの、モニターとのつなぎ役
    """

    def __init__(self, app: PokeControllerApp, profile: str):
        """app: メインウィンドウ。profile: プロファイルの名前"""
        self.app = app
        self.profile = profile
        self.server = MonitorServer(profile, self._frame, self._onAction)
        self._started = False

    def start(self) -> bool:
        """
        窓口を開く。開けたか。
        同じプロファイルの 2 つ目以降のウィンドウ(設定を保存しないもの)では、開かない(1 つ目の窓口と区別できないため)
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
        self.app.output_service.listeners.append(self._onOutput)
        atexit.register(self.stop)
        self.app.root.bind("<Destroy>", self._onDestroy, add="+")
        self._poll()
        return True

    def stop(self) -> None:
        """窓口を閉じる(何度呼んでもよい)"""
        if self._started:
            self._started = False
            self.server.stop()

    def _onDestroy(self, event: Any) -> None:
        """メインウィンドウが閉じられたとき: 窓口を閉じる"""
        if event.widget is self.app.root:
            self.stop()

    # ---------------------------------------------------------------- 知らせる

    def state(self) -> dict:
        """今の状態(画面のスレッドで呼ぶ)"""
        app = self.app
        service = app.command_service
        commandtype = "Mcu" if app.command_nb.index("current") == 1 else "Python"
        selected = app.getSelectedCommandName(commandtype)
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
            "selected": selected,
            "can_start": state == IDLE and str(app.start_button["state"]) != "disabled",
            "can_pause": state == RUNNING and bool(service.can_pause),
            "title": app.root.title(),
            # このウィンドウのテーマ(補助ツールは、このウィンドウの枠を、同じ配色で表示する)
            "theme": Theme.saved_theme_id(),
            # print の出力先の出力画面(1 / 2)。補助ツールは、初めは、こちらの Output を表示する
            "stdout_area": 2 if str(Command.stdout_destination) == "2" else 1,
        }

    def _poll(self) -> None:
        """一定の間隔で状態を調べて、変わっていれば知らせる"""
        if not self._started:
            return
        try:
            self.server.set_state(self.state())
        except Exception:
            _logger.exception("Failed to read the state for the monitor")
        self.app.root.after(STATE_INTERVAL_MS, self._poll)

    def _onOutput(self, area: int, mode: str, text: str) -> None:
        """Output に書かれたとき(書いたスレッドで呼ばれる): 内容を知らせる。mode: 'w' 上書き / 'a' 追記 / 'd' 削除"""
        self.server.push_output(area, mode in ("w", "d"), text if mode in ("w", "a") else "")

    def _frame(self) -> tuple[Any, int]:
        """カメラの最新の映像と、その通し番号(窓口の送信のスレッドから呼ばれる)"""
        camera = getattr(self.app, "camera", None)
        if camera is None:
            return None, 0
        # カメラの機器(VideoCapture)には触れず、読み取りのスレッドが置いた最新の画像を受け取るだけにする
        # (閉じているときは、画像が None になっている。isOpened は、機器に問い合わせ、ログも書くので、ここでは呼ばない)
        return camera.latestFrame()

    # ---------------------------------------------------------------- 操作

    def _onAction(self, name: str) -> None:
        """補助ツールからの操作の依頼(窓口のスレッドで呼ばれる): 画面のスレッドに渡す"""
        UiDispatcher.post(self.perform, name)

    def perform(self, name: str) -> None:
        """
        操作を実行する(画面のスレッドで呼ぶ)。今の状態でできない操作は、何もしない。
        name: "play"(待機中は、選んでいるコマンドを開始。一時停止中は、再開)/ "pause" / "stop" / "front"
        """
        app = self.app
        state = self.state()
        _logger.info(f"Monitor action: {name} (state: {state['state']})")
        if name == "play":
            if state["state"] == PAUSED:
                app.restartPlay()
            elif state["can_start"]:
                app.startPlay()
        elif name == "pause":
            if state["can_pause"]:
                app.pausePlay()
        elif name == "stop":
            if state["state"] in (RUNNING, PAUSED):
                app.stopPlay()
        elif name == "front":
            self.bringToFront()

    def bringToFront(self) -> None:
        """このウィンドウを、最前面に表示する(最小化していれば、元に戻す)"""
        root = self.app.root
        if str(root.state()) == "iconic":
            root.deiconify()
        root.lift()
        # いったん「常に手前」にして、ほかのウィンドウの上に出す(すぐに戻すので、手前に居座らない)
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
        root.focus_force()
