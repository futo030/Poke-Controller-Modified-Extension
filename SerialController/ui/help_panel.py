#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
機能紹介とマニュアル(Instruction Manual)のウィンドウ
"""
from __future__ import annotations

import Constant
import PokeConLogger
import Profile
from ui.diagnostics_window import DiagnosticsWindow

import Introduction
import Manual


class HelpPanelMixin:
    """
    機能紹介とマニュアル(Instruction Manual)のウィンドウ
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def showIntroductionAtStartup(self) -> None:
        """起動時に、機能紹介を表示する設定であれば、機能紹介のウィンドウを開く(失敗しても起動は続ける)"""
        try:
            if Introduction.should_show_at_startup():
                self.openIntroduction()
        except Exception as e:
            # 機能紹介を表示できなくても、起動は続ける
            self._logger.error(f"Failed to show the introduction: {e}")

    def openIntroduction(self) -> None:
        """
        機能紹介のウィンドウを開く(起動時、または メニュー > ヘルプ > 機能紹介)
        """
        if self.introduction_window is not None:
            self.introduction_window.focus_force()
            return
        window = Introduction.IntroductionWindow(self.root)
        window.protocol("WM_DELETE_WINDOW", self.closingIntroduction)
        self.introduction_window = window

    def closingIntroduction(self) -> None:
        """機能紹介のウィンドウを閉じる(ウィンドウの × ボタン)"""
        if self.introduction_window is not None:
            self.introduction_window.destroy()
            self.introduction_window = None

    def openManual(self) -> None:
        """
        メニューバーの ヘルプ > Instruction Manual: マニュアルのウィンドウを開く
        """
        if self.manual_window is not None:
            self.manual_window.focus_force()
            return
        window = Manual.ManualWindow(self.root)
        window.protocol("WM_DELETE_WINDOW", self.closingManual)
        self.manual_window = window

    def closingManual(self) -> None:
        """マニュアルのウィンドウを閉じる(ウィンドウの × ボタン)"""
        if self.manual_window is not None:
            self.manual_window.destroy()
            self.manual_window = None

    def openDiagnostics(self) -> None:
        """
        メニューの ヘルプ > 環境の診断: 必要なライブラリ・フォルダー・機器の状態を調べて、結果を表示する
        (すでに開いている場合は、もう一度調べて、前面に出す)
        """
        window = getattr(self, "diagnostics_window", None)
        if window is not None and window.isOpen():
            window.run()
            window.lift()
            return
        self.diagnostics_window = DiagnosticsWindow(self.root, self.diagnosticsContext)

    def diagnosticsContext(self) -> dict:
        """環境の診断に渡す、今の状態(プロファイル、シリアル、カメラ、コマンドの数、ログのファイル)"""
        port = self.com_port_name.get() or (f"COM{self.com_port.get()}" if str(self.com_port.get()) else "")
        return {
            "app": f"{Constant.NAME} ver.{Constant.VERSION}",
            "profile": self.profile,
            "read_only": Profile.is_read_only(),
            "command_counts": {"Python": len(self.py_commands), "Mcu": len(self.mcu_commands)},
            "log_file": PokeConLogger.log_file_path(),
            "serial_connected": bool(self.ser.isOpened()),
            "serial_port": port,
            "data_format": self.serial_data_format_name.get(),
            "camera_opened": bool(self.camera.isOpened()),
            "camera_name": f"Camera ID {self.camera_id.get()}",
            "capture_size": self.capture_size.get(),
        }
