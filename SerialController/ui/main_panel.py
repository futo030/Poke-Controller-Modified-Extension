#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Panel(プレビューの上のボタン): 画像の保存・スクリーンショット・通知の送信
"""
from __future__ import annotations

import tkinter as tk
import sys
import os
import platform
import subprocess
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING
import tkinter.ttk as ttk
from PIL import Image
import Constant
from Camera import CAPTURE_DIR
from LineNotify import Line_Notify
from DiscordNotify import Discord_Notify
import WindowCapture
from services import notification_image
from ui.constants import (
    notification,
    flag_import_plyer,
    PANEL_BUTTON_TEXTS,
    WINDOW_CORNER_RADIUS,
    SCREENSHOT_REDRAW_WAIT_S,
    CAPTURE_LINK_PREFIX,
)

if TYPE_CHECKING:
    import numpy as np


class MainPanelMixin:
    """
    Main Panel(プレビューの上のボタン): 画像の保存・スクリーンショット・通知の送信
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildMainPanel(self, master: tk.Misc) -> None:
        """
        Main Panel(プレビューと、その上のボタン)を作る(起動時に1回だけ呼ぶ)
        master: 部品を置く親(メインウィンドウ)
        """
        # build ui
        self.main_frame = ttk.Frame(master)
        self.camera_lf = ttk.Labelframe(self.main_frame)
        self.top_command_f = ttk.Frame(self.camera_lf)
        self.start_top_button = ttk.Button(self.top_command_f)
        # Start/Controller/Capture/Discordは幅を詰めて、Screenshotボタンを置いてもMain Panelの幅が変わらないようにする
        # 幅は、スクリプトの読み込み中の表示(Loading...)が収まる文字数
        self.start_top_button.configure(text="Start", width="9")
        self.start_top_button.grid(column="0", padx="5", pady="5", row="0", sticky="ew")
        self.start_top_button.configure(command=self.startPlay)
        self.simplecon_top_button = ttk.Button(self.top_command_f)
        self.simplecon_top_button.configure(text="Controller", width="9")
        self.simplecon_top_button.grid(
            column="1", padx="5", pady="5", row="0", sticky="ew"
        )
        self.simplecon_top_button.configure(command=self.createControllerWindow)
        self.clear_top_button = ttk.Button(self.top_command_f)
        self.clear_top_button.configure(text="Clear Outputs")
        self.clear_top_button.grid(column="2", padx="5", pady="5", row="0")
        self.clear_top_button.configure(command=self.clearOutputs)
        self.capture_button = ttk.Button(self.top_command_f)
        self.capture_button.configure(text="Capture", width="7")
        self.capture_button.grid(column="3", padx="5", pady="5", row="0", sticky="ew")
        self.capture_button.configure(command=self.saveCapture)
        # アプリケーションのウィンドウ全体のスクリーンショットを、Capturesフォルダに保存する
        self.screenshot_button = ttk.Button(self.top_command_f)
        self.screenshot_button.configure(text="Screenshot", width="10", command=self.saveWindowScreenshot)
        self.screenshot_button.grid(column="4", padx="5", pady="5", row="0", sticky="ew")
        self.open_capture_button = ttk.Button(self.top_command_f)
        self.open_folder_img = tk.PhotoImage(
            file="./assets/icons8-OpenDir-16.png"
        )  # modified
        self.open_capture_button.configure(image=self.open_folder_img)  # modified
        self.open_capture_button.grid(column="5", pady="5", row="0")
        self.open_capture_button.configure(command=self.OpenCaptureDir)
        # self.line_button = ttk.Button(self.top_command_f)
        # self.line_button.configure(text='Line')
        # self.line_button.grid(column='5', padx='5', pady='5', row='0', sticky='ew')
        # self.line_button.configure(command=self.sendLineImage)
        self.discord_button = ttk.Button(self.top_command_f)
        self.discord_button.configure(text="Discord", width="7")
        self.discord_button.grid(column="6", padx="5", pady="5", row="0", sticky="ew")
        self.discord_button.configure(command=self.sendDiscordImage)
        # 右側のパネル(Output・Software-Controller)の表示・非表示を切り替える
        # (隠すとウィンドウの幅が狭くなり、複数のウィンドウを並べやすくなる)
        # 右側のパネルの位置(通常の画面 / ミニ画面)。PANEL_POSITIONS のどれか
        self.panel_position = "right"
        self.mini_panel_position = "bottom"
        self.side_panel_button = ttk.Button(self.top_command_f)
        self.side_panel_button.configure(text=PANEL_BUTTON_TEXTS["right"], width="8", command=self.toggleSidePanel)
        self.side_panel_button.grid(column="7", padx="5", pady="5", row="0", sticky="ew")
        # ミニ画面(プレビューを最小にし、コマンドの選択・実行に必要な部品だけを縦に並べた画面)との切り替え
        self.is_mini = False
        self.mini_button = ttk.Button(self.top_command_f)
        self.mini_button.configure(text="Mini", width="6", command=self.toggleMiniMode)
        self.mini_button.grid(column="8", padx="5", pady="5", row="0", sticky="ew")
        # ミニ画面でのみ上段に表示するPause/Reloadボタン
        # (Commandsタブのボタンを代わりに押す。表示と有効・無効はCommandsタブのボタンに合わせる)
        self.mini_pause_button = ttk.Button(self.top_command_f)
        self.mini_pause_button.configure(text="Pause", width="7", command=lambda: self.pause_button.invoke())
        self.mini_reload_button = ttk.Button(self.top_command_f)
        self.mini_reload_button.configure(
            text="Reload", width="7", command=lambda: self.reload_command_button.invoke()
        )
        self.mini_button_sync_after = None
        self.top_command_f.grid(column="0", row="0", sticky="w")
        self.top_command_f.grid_anchor("center")
        self.canvas_frame = ttk.Frame(self.camera_lf)
        self.canvas_frame.configure(height="360", relief="groove", width="640")
        self.canvas_frame.grid(column="0", columnspan="7", row="1")
        self.camera_lf.configure(text="Main Panel")  # modfied
        # Main Panel は、仕切り線の枠(left_pw)に置く(buildPanes)
        self.camera_lf.rowconfigure("0", uniform="0")

    def saveCapture(self) -> None:
        """Captureボタン: キャプチャ画面の今の画像を、Capturesフォルダに保存する"""
        self.camera.saveCapture()

    def saveWindowScreenshot(self) -> None:
        """
        Screenshotボタン: アプリケーションのウィンドウ全体(タイトルバーを含む)の画像を、Capturesフォルダに保存する
        """
        try:
            from PIL import ImageDraw, ImageGrab
        except ImportError:
            print("Screenshot: この環境では画面の取り込みが使えません。")
            return
        # 他のウィンドウに隠れていると、その内容が写るので、手前に出してから取り込む
        self.root.lift()
        self.root.update()
        x1, y1 = self.root.winfo_rootx(), self.root.winfo_rooty()
        x2, y2 = x1 + self.root.winfo_width(), y1 + self.root.winfo_height()
        framed = False
        if platform.system() == "Windows":
            # タイトルバーと枠を含めたウィンドウの範囲(影は含まない)
            try:
                import ctypes
                from ctypes import wintypes

                rect = wintypes.RECT()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                # DWMWA_EXTENDED_FRAME_BOUNDS = 9
                if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
                    x1, y1, x2, y2 = rect.left, rect.top, rect.right, rect.bottom
                    framed = True
            except (OSError, AttributeError):
                pass
        save_path = os.path.join(CAPTURE_DIR, datetime.now().strftime("Window_%Y-%m-%d_%H-%M-%S") + ".png")
        # プレビューの明るさを変えている場合は、撮る間だけ、明るさを変える前の画像で表示する
        raw_display = self.camera.isDisplayAdjusted()
        if raw_display:
            self._setRawDisplay(True)
            self.root.update()
            # 画面に描かれるのを待つ
            time.sleep(SCREENSHOT_REDRAW_WAIT_S)
        try:
            os.makedirs(CAPTURE_DIR, exist_ok=True)
            image = ImageGrab.grab((x1, y1, x2, y2), all_screens=True)
            if framed and self.root.state() != "zoomed":
                # ウィンドウの枠(1px)は半透明で、後ろにあるものが透けて写るので削る
                image = image.crop((1, 1, image.width - 1, image.height - 1))
                if sys.getwindowsversion().build >= 22000:
                    # Windows 11は四隅が丸く、その外側に後ろにあるものが写るので、四隅を透明にする
                    radius = round(WINDOW_CORNER_RADIUS * self.root.winfo_fpixels("1i") / 96)
                    mask = Image.new("L", image.size, 0)
                    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius, fill=255)
                    image.putalpha(mask)
            image.save(save_path)
        except Exception as e:
            self._logger.error(f"Screenshot Failed: {e}")
            print("Screenshot Failed")
            return
        finally:
            if raw_display:
                self._setRawDisplay(False)
        self._logger.debug(f"Screenshot succeeded: {save_path}")
        print(CAPTURE_LINK_PREFIX + save_path)

    def OpenCaptureDir(self) -> None:
        """フォルダのボタン、または メニューの「Captures フォルダを開く」: Capturesフォルダを開く(Windows / macOS のみ)"""
        # 画像を保存する場所(CAPTURE_DIR)と同じフォルダーを開く(まだ無ければ作る)
        directory = os.path.abspath(CAPTURE_DIR)
        os.makedirs(directory, exist_ok=True)
        self._logger.debug(f"Open folder: '{directory}'")
        if platform.system() == "Windows":
            subprocess.call(f'explorer "{directory}"')
        elif platform.system() == "Darwin":
            command = f'open "{directory}"'
            subprocess.run(command, shell=True)

    def sendWinNotfication(self) -> None:
        """Notification タブの Test ボタン、または メニューの「Windows の通知をテスト」: テスト用の通知を出す"""
        global flag_import_plyer
        if flag_import_plyer:
            notification.notify(
                title=f"{Constant.NAME} ver.{Constant.VERSION} (profile:{self.profile})",
                message="Notification Test",
                timeout=5,
            )
        else:
            print('"plyer" is not installed.')

    def sendLineImage(self) -> None:
        """Notification タブ(Line)の Test ボタン: キャプチャ画面の今の画像を、別スレッドで LINE に送る"""

        def sendMessage(src: np.ndarray | None) -> None:
            """画像を付けて通知を送る(失敗しても何もしない)。src: 送る画像(取得できていない場合は None)"""
            try:
                Line = Line_Notify()
                Line.send_message("---Manual---", src, "token")
            except Exception:
                pass

        src = self.camera.readFrame()
        thread = threading.Thread(target=sendMessage, args=(src,))
        thread.start()

    def _mainWindowHandle(self) -> int | None:
        """このアプリケーションのウィンドウ(タイトルバーを含む)のハンドル。Windows 以外では None(画面のスレッドから呼ぶ)"""
        if platform.system() != "Windows":
            return None
        try:
            import ctypes

            return ctypes.windll.user32.GetParent(self.root.winfo_id()) or None
        except (OSError, AttributeError, tk.TclError):
            return None

    def discordNotificationImage(self, kind: str | None = None) -> np.ndarray | None:
        """
        Discord の通知に付ける画像を取り出す(取り出せなければ None)。
        kind: 画像の種類(notification_image.CAMERA / WINDOW)。省くと、Notification タブで選んでいるもの。
        コマンドのスレッドからも呼ぶので、tkinter には触れない(ウィンドウのハンドルと設定は、覚えてある値を使う)
        """
        handle = getattr(self, "_main_window_handle", None)
        return notification_image.pick(
            getattr(self, "_discord_image_kind", notification_image.DEFAULT) if kind is None else kind,
            self.camera.readFrame,
            lambda: WindowCapture.capture_whole_window(handle),
        )

    def _sendDiscordManual(self, src: np.ndarray | None) -> None:
        """画像を付けた通知を、別スレッドで Discord に送る。src: 送る画像(取得できていない場合は None)"""

        def sendMessage() -> None:
            Discord = Discord_Notify()
            Discord.send_message(notification_message="---Manual---", image=src)

        threading.Thread(target=sendMessage).start()

    def sendDiscordImage(self) -> None:
        """
        Discordボタン、または Notification タブ(Discord)の Test ボタン: Notification タブで選んでいる画像
        (画面 = キャプチャ画面の今の画像 / ウィンドウ全体)を、別スレッドで Discord に送る
        """
        self._sendDiscordManual(self.discordNotificationImage())

    def sendDiscordWindowImage(self) -> None:
        """メニューの「Discord にウィンドウ全体を送信」: このウィンドウ全体の画像を、別スレッドで Discord に送る(設定に関係なく)"""
        src = WindowCapture.capture_whole_window(self._mainWindowHandle())
        if src is None:
            print("ウィンドウを取り込めませんでした(最小化している間と、Windows 以外では、取り込めません)。")
            return
        self._sendDiscordManual(src)
