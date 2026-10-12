#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コントローラーのプロファイル(ボタンの割り当て)をGUIで作る

Switchのボタン・十字キー・スティックを1つずつ表示し、対応するコントローラーの入力を押してもらって割り当てる。
- JoystickMonitor: 別スレッドでコントローラーの状態を読み続ける(pygameの初期化に1秒ほどかかるため)
- SetupSession: 入力の検出と割り当ての管理(Tkに依存しない)
- ControllerSetupWindow: 設定用のウィンドウ
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

from Commands.ControllerProfile import (
    ControllerProfile,
    ControllerProfileError,
    save_profile,
)

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 入力の検出と割り当ての管理(画面に依存しない部分)は、Commands/ControllerSetupSession.py にある
from Commands.ControllerSetupSession import (  # noqa: E402,F401
    POLL_INTERVAL_MS,
    SETUP_STEPS,
    HatAssign,
    JoystickMonitor,
    JoystickSnapshot,
    SetupSession,
    SetupStep,
    describe,
    describe_key,
)


class ControllerSetupWindow:
    """
    コントローラーの割り当てを1つずつ設定し、プロファイルのJSONファイルに保存するウィンドウ
    """

    def __init__(
        self,
        root: tk.Misc,
        device: str,
        joystick_name: str,
        base: ControllerProfile | None,
        path: str,
        exists: bool,
        on_close: Callable[[], None] | None = None,
    ):
        """
        root: 親のウィンドウ(メインウィンドウ)
        device: コントローラーの選択(Controller の一覧に表示している「番号: 名前」)
        joystick_name: コントローラーの名前
        base: 元にするプロファイル(割り当てを引き継ぐ。無ければ None)
        path: 保存先のJSONファイルのパス
        exists: 保存先のファイルが既にあるか(ある場合は、保存するときに更新するかを確認する)
        on_close: ウィンドウを閉じたときに呼ぶ関数
        """
        self.path = path
        self.exists = exists
        self.on_close = on_close
        # 既存のJSONファイルなら名前と照合文字列を引き継ぎ、新規ならコントローラーの名前を使う
        if base is not None and base.path is not None:
            name, match = base.name, base.match
        else:
            name, match = joystick_name, [joystick_name]
        self.session = SetupSession(name, match, base)
        self.monitor = JoystickMonitor(device, joystick_name)
        self._after_id = None

        self.window = tk.Toplevel(root)
        self.window.title("コントローラーの設定")
        self.window.resizable(False, False)
        self.window.transient(root)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"コントローラー: {device}").grid(row=0, column=0, columnspan=4, sticky="w")
        state = "既存のファイルを更新" if exists else "新規作成"
        ttk.Label(frame, text=f"保存先: {os.path.basename(path)} ({state})").grid(
            row=1, column=0, columnspan=4, sticky="w"
        )
        self.progress_label = ttk.Label(frame)
        self.progress_label.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.instruction_label = ttk.Label(frame, font=("", 12, "bold"), wraplength=440)
        self.instruction_label.grid(row=3, column=0, columnspan=4, sticky="w", pady=5)
        self.current_label = ttk.Label(frame)
        self.current_label.grid(row=4, column=0, columnspan=4, sticky="w")
        self.input_label = ttk.Label(frame, foreground="gray")
        self.input_label.grid(row=5, column=0, columnspan=4, sticky="w", pady=(0, 5))

        # 最後に表示する割り当ての一覧
        self.summary_frame = ttk.Frame(frame)
        self.summary = ttk.Treeview(self.summary_frame, columns=("value",), height=12, selectmode="none")
        summary_scroll = ttk.Scrollbar(self.summary_frame, orient="vertical", command=self.summary.yview)
        self.summary.configure(yscrollcommand=summary_scroll.set)
        self.summary.pack(side="left", fill="both", expand=True)
        summary_scroll.pack(side="right", fill="y")
        self.summary.heading("#0", text="Switch")
        self.summary.heading("value", text="コントローラー")
        self.summary.column("#0", width=200)
        self.summary.column("value", width=240)
        self.summary_note = ttk.Label(frame, foreground="#c00000", wraplength=440)

        self.back_button = ttk.Button(frame, text="戻る", command=self.back)
        self.skip_button = ttk.Button(frame, text="スキップ", command=self.skip)
        self.clear_button = ttk.Button(frame, text="割り当てなし", command=self.clear)
        self.cancel_button = ttk.Button(frame, text="中止", command=self.cancel)
        self.save_button = ttk.Button(frame, text="保存", command=self.save)
        self.back_button.grid(row=8, column=0, padx=2, pady=(5, 0), sticky="ew")
        self.skip_button.grid(row=8, column=1, padx=2, pady=(5, 0), sticky="ew")
        self.clear_button.grid(row=8, column=2, padx=2, pady=(5, 0), sticky="ew")
        self.cancel_button.grid(row=8, column=3, padx=2, pady=(5, 0), sticky="ew")
        for col in range(4):
            frame.columnconfigure(col, weight=1, minsize=110)
        self.frame = frame

        self.window.grab_set()
        self.monitor.start()
        self.update_view()
        self._after_id = self.window.after(POLL_INTERVAL_MS, self.poll)

    # --- 状態の更新
    def poll(self) -> None:
        """
        コントローラーの最新の状態を調べ、割り当てや手順が変わっていれば表示を更新する
        (after() で POLL_INTERVAL_MS ごとに自分を呼び直す。コントローラーを読めなくなった場合は、エラーを表示して閉じる)
        """
        self._after_id = None
        if self.monitor.error is not None:
            tkmsg.showerror("コントローラーの設定", self.monitor.error, parent=self.window)
            self.close()
            return
        snapshot = self.monitor.latest
        if snapshot is not None:
            if self.session.feed(snapshot):
                self.update_view()
            if self.session.baseline is not None:
                active = self.session.active_inputs(snapshot)
                self.input_label["text"] = "入力中: " + (", ".join(active) if active else "なし")
        self._after_id = self.window.after(POLL_INTERVAL_MS, self.poll)

    def update_view(self) -> None:
        """今の手順(準備中 / 割り当て中 / 割り当ての一覧)に合わせて、表示とボタンの状態を更新する"""
        session = self.session
        if session.baseline is None:
            self.progress_label["text"] = ""
            self.instruction_label["text"] = "コントローラーを準備しています。触れずにお待ちください…"
            self.current_label["text"] = ""
            self._set_step_buttons("disabled")
            return
        if session.done:
            self._show_summary()
            return
        self._hide_summary()
        step = session.current
        self.progress_label["text"] = f"{session.index + 1} / {len(session.steps)}  {step.label}"
        if session.waiting_release:
            self.instruction_label["text"] = "入力を離してください"
        else:
            self.instruction_label["text"] = step.instruction
        mark = "" if session.is_assigned(step) else " (変更なし)"
        self.current_label["text"] = f"現在の割り当て: {describe(session.value(step))}{mark}"
        self._set_step_buttons("normal")
        self.back_button["state"] = "normal" if session.history else "disabled"

    def _set_step_buttons(self, state: str) -> None:
        """戻る・スキップ・割り当てなし のボタンを、押せる("normal")/ 押せない("disabled")にする"""
        for button in (self.back_button, self.skip_button, self.clear_button):
            button["state"] = state

    def _show_summary(self) -> None:
        """すべての手順が終わったとき: 割り当ての一覧と保存ボタンを表示する(同じ入力を複数に割り当てている場合は、注意も表示する)"""
        session = self.session
        self.progress_label["text"] = "設定が終わりました"
        self.instruction_label["text"] = "割り当てを確認して保存してください"
        self.current_label["text"] = ""
        self.summary.delete(*self.summary.get_children())
        for step in session.steps:
            mark = "" if session.is_assigned(step) else " (変更なし)"
            self.summary.insert("", "end", text=step.label, values=(describe(session.value(step)) + mark,))
        self.summary_frame.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=5)
        duplicates = session.duplicates()
        self.summary_note["text"] = ("同じ入力が複数に割り当てられています: " + " / ".join(duplicates)) if duplicates else ""
        self.summary_note.grid(row=7, column=0, columnspan=4, sticky="w")
        self.skip_button.grid_remove()
        self.clear_button.grid_remove()
        self.save_button.grid(row=8, column=1, columnspan=2, padx=2, pady=(5, 0), sticky="ew")
        self.back_button["state"] = "normal"

    def _hide_summary(self) -> None:
        """割り当ての一覧と保存ボタンを隠し、スキップ・割り当てなし のボタンを表示する(割り当て中の表示に戻す)"""
        self.summary_frame.grid_remove()
        self.summary_note.grid_remove()
        self.save_button.grid_remove()
        self.skip_button.grid()
        self.clear_button.grid()

    # --- ボタン
    def back(self) -> None:
        """戻る ボタン: 1つ前の手順に戻る"""
        self.session.back()
        self.update_view()

    def skip(self) -> None:
        """スキップ ボタン: 今の割り当てを変えずに、次の手順へ進む"""
        self.session.skip()
        self.update_view()

    def clear(self) -> None:
        """割り当てなし ボタン: 今の手順を割り当てなしにして、次の手順へ進む"""
        self.session.clear()
        self.update_view()

    def save(self) -> None:
        """
        保存 ボタン: 割り当てをプロファイルのJSONファイルに保存して、ウィンドウを閉じる
        (保存先が既にある場合は、更新するかを確認する。保存できなかった場合は、閉じない)
        """
        filename = os.path.basename(self.path)
        if self.exists:
            answer = tkmsg.askyesnocancel(
                "設定ファイルの更新",
                f"{filename} は既にあります。設定ファイルを更新しますか？\n\n"
                "はい: 更新して終了\nいいえ: 更新せずに終了\nキャンセル: 設定画面に戻る",
                parent=self.window,
            )
            if answer is None:
                return
            if not answer:
                print(f"コントローラーの設定を保存せずに終了しました ({filename})")
                self.close()
                return
        try:
            save_profile(self.session.build_profile(self.path), self.path)
        except (OSError, ControllerProfileError) as e:
            tkmsg.showerror("コントローラーの設定", f"保存できませんでした: {e}", parent=self.window)
            return
        _logger.info(f"Controller profile is saved: {self.path}")
        print(f"コントローラーの設定を保存しました: {self.path}")
        self.close()

    def cancel(self) -> None:
        """中止 ボタン、またはウィンドウの × ボタン: 変更がある場合は確認してから、保存せずに閉じる"""
        if self.session.changed and not tkmsg.askyesno(
            "コントローラーの設定", "設定を保存せずに終了しますか？", parent=self.window
        ):
            return
        self.close()

    def close(self) -> None:
        """コントローラーの読み取りを止めてウィンドウを閉じ、on_close を呼ぶ"""
        if self._after_id is not None:
            self.window.after_cancel(self._after_id)
            self._after_id = None
        self.monitor.stop()
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        if self.on_close is not None:
            self.on_close()

    def focus(self) -> None:
        """ウィンドウにフォーカスを移す(すでに開いているときに、もう一度開こうとした場合)"""
        self.window.focus_force()
