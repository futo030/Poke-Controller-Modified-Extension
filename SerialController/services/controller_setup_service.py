#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接続したコントローラーのボタンの割り当ての設定(手順の進行と、プロファイルの保存)

画面(tkinter)には触れない。入力の検出と割り当ての管理は Commands/ControllerSetupSession.py が行う。
画面は、状態(state)を表示し、戻る・スキップ・割り当てなし・保存・中止を頼む。
"""
from __future__ import annotations

import os
import threading
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

from Commands.ControllerProfile import (
    ControllerProfileError,
    device_label,
    list_joystick_names,
    load_profiles,
    profile_file_for,
    save_profile,
    select_device,
)
from Commands.ControllerSetupSession import POLL_INTERVAL_MS, JoystickMonitor, SetupSession, describe

if TYPE_CHECKING:
    from services.app_core import AppCore

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True


class SetupError(Exception):
    """設定を始められない・保存できない(メッセージは、そのまま表示できる文)"""


class ControllerSetupService:
    """接続したコントローラーの、ボタンの割り当ての設定の手順を進め、プロファイルに保存する"""

    def __init__(self, core: AppCore, monitor_class: type[JoystickMonitor] = JoystickMonitor):
        """
        core: アプリ本体(AppCore)
        monitor_class: コントローラーの状態を読むクラス(テストで代役に差し替える)
        """
        self.core = core
        self._monitor_class = monitor_class
        self._lock = threading.RLock()
        self.session = None
        self.monitor = None
        self.device = ""
        self.path = ""
        self.exists = False
        self._inputs = []
        self._on_change = None
        self._thread = None
        self._stop = None

    @property
    def active(self) -> bool:
        """設定の途中か"""
        return self.session is not None

    # ---------------------------------------------------------------- 開始と終了

    def start(self, on_change: Callable[[dict], None] | None = None) -> dict:
        """
        選択中のコントローラーの割り当ての設定を始める。状態を返す。
        on_change: 状態が変わるたびに呼ぶ関数(引数は状態。別のスレッドから呼ぶ)
        すでに設定の途中の場合は、on_change だけを入れ替える。始められない場合は SetupError
        """
        core = self.core
        if self.active:
            self._on_change = on_change
            return self.state()
        if core.commands.is_running:
            raise SetupError("コマンド実行中は、コントローラーの設定を始められません。")
        # コントローラーでの操作中は、同時にコントローラーを開けないので止める
        core.stop_controller()
        profiles, errors = load_profiles()
        for error in errors:
            print(f"コントローラーのプロファイルを読み込めませんでした: {error}")
        try:
            names = list_joystick_names()
            core.settings_control.controller_names = names
            index, _, _ = select_device(names, profiles, core.settings.controller_device)
        except ControllerProfileError as e:
            raise SetupError(f"{e}\nコントローラーを接続し、接続中のコントローラーを調べ直してから、もう一度お試しください。")
        except Exception as e:
            _logger.error(f"Failed to list controllers: {e}")
            raise SetupError(f"接続中のコントローラーを取得できませんでした: {e}")
        joystick_name = names[index]
        path, base, exists = profile_file_for(joystick_name, profiles)
        # 既存のJSONファイルなら名前と照合文字列を引き継ぎ、新規ならコントローラーの名前を使う
        if base is not None and base.path is not None:
            name, match = base.name, base.match
        else:
            name, match = joystick_name, [joystick_name]
        with self._lock:
            self.device = device_label(index, joystick_name)
            self.path = path
            self.exists = exists
            self.session = SetupSession(name, match, base)
            self.monitor = self._monitor_class(self.device, joystick_name)
            self._inputs = []
            self._on_change = on_change
            self._stop = threading.Event()
            self.monitor.start()
            self._thread = threading.Thread(target=self._poll, args=(self._stop,), name="ControllerSetupPoll", daemon=True)
            self._thread.start()
        return self.state()

    def close(self) -> None:
        """
        設定をやめる(保存しない)
        """
        with self._lock:
            if self.session is None:
                return
            self._stop.set()
            self.monitor.stop()
            self.session = None
            self.monitor = None
            self._on_change = None

    def _poll(self, stop: threading.Event) -> None:
        """
        コントローラーの状態を手順に渡し、変化があれば知らせる(スレッドの中身。stop が立つまで繰り返す)
        """
        while not stop.wait(POLL_INTERVAL_MS / 1000):
            with self._lock:
                session, monitor = self.session, self.monitor
                if session is None or stop.is_set():
                    return
                if monitor.error is not None:
                    # コントローラーが外れた等: 理由を知らせて終了する
                    state = self.state()
                    state.update({"active": False, "error": monitor.error})
                    callback = self._on_change
                    self.close()
                    if callback is not None:
                        callback(state)
                    return
                snapshot = monitor.latest
                if snapshot is None:
                    continue
                changed = session.feed(snapshot)
                inputs = session.active_inputs(snapshot) if session.baseline is not None else []
                if inputs != self._inputs:
                    self._inputs = inputs
                    changed = True
                callback = self._on_change if changed else None
                state = self.state() if changed else None
            if callback is not None:
                callback(state)

    # ---------------------------------------------------------------- 手順の操作

    def _session(self) -> SetupSession:
        """進行中の手順を返す(始まっていない場合は SetupError)"""
        if self.session is None:
            raise SetupError("コントローラーの設定は始まっていません。")
        return self.session

    def back(self) -> dict:
        """1 つ前の項目に戻る。状態を返す"""
        with self._lock:
            self._session().back()
            return self.state()

    def skip(self) -> dict:
        """今の項目を、変えずに次へ進む。状態を返す"""
        with self._lock:
            self._session().skip()
            return self.state()

    def clear(self) -> dict:
        """今の項目を「割り当てなし」にして次へ進む。状態を返す"""
        with self._lock:
            self._session().clear()
            return self.state()

    def save(self) -> dict:
        """
        割り当てをプロファイルのファイルに保存して終了する。状態を返す
        設定が終わっていない場合と、保存できない場合は SetupError
        """
        with self._lock:
            session = self._session()
            if not session.done:
                raise SetupError("設定が終わっていません。")
            try:
                save_profile(session.build_profile(self.path), self.path)
            except (OSError, ControllerProfileError) as e:
                raise SetupError(f"保存できませんでした: {e}")
            _logger.info(f"Controller profile is saved: {self.path}")
            print(f"コントローラーの設定を保存しました: {self.path}")
            self.close()
            return self.state()

    def cancel(self) -> dict:
        """
        保存せずに終了する。状態を返す
        """
        with self._lock:
            if self.session is not None and self.session.done and self.exists:
                print(f"コントローラーの設定を保存せずに終了しました ({os.path.basename(self.path)})")
            self.close()
            return self.state()

    # ---------------------------------------------------------------- 状態

    def state(self) -> dict:
        """
        画面に表示する状態(JSON にできる値だけ)
        """
        with self._lock:
            session = self.session
            if session is None:
                return {"active": False}
            state = {
                "active": True,
                "device": self.device,
                "file": os.path.basename(self.path),
                "exists": self.exists,
                "total": len(session.steps),
                "changed": session.changed,
                "can_back": bool(session.history),
                "inputs": list(self._inputs),
            }
            if session.baseline is None:
                state.update({"phase": "preparing", "instruction": "コントローラーを準備しています。触れずにお待ちください…"})
            elif session.done:
                state.update(
                    {
                        "phase": "done",
                        "instruction": "割り当てを確認して保存してください",
                        "summary": [
                            {"label": step.label, "value": describe(session.value(step)), "changed": session.is_assigned(step)}
                            for step in session.steps
                        ],
                        "duplicates": session.duplicates(),
                    }
                )
            else:
                step = session.current
                state.update(
                    {
                        "phase": "release" if session.waiting_release else "step",
                        "index": session.index,
                        "label": step.label,
                        "instruction": "入力を離してください" if session.waiting_release else step.instruction,
                        "current": describe(session.value(step)),
                        "current_changed": session.is_assigned(step),
                    }
                )
            return state
