#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import importlib
import sys
import os
import json

if __name__ == "__main__":
    # uv の環境(.venv)があれば、その Python で起動し直す(以前からの起動用のファイルのため。0.3.0 で消す)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from bootstrap.relaunch import run_in_venv

        run_in_venv()
    except ImportError:
        pass
    finally:
        sys.path.pop(0)

import tkinter as tk
from os.path import dirname, abspath
import cv2
import platform
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import Constant
from logging import getLogger, DEBUG, NullHandler

from Camera import (
    DEFAULT_CAPTURE_SIZE,
    EXTRA_SOURCES,
    Camera,
)
import Settings
from GuiAssets import CaptureArea
from KeyConfig import PokeKeycon
from Menubar import PokeController_Menubar
import Theme
import PokeConLogger
from Commands import Sender
from Commands.Keys import KeyPress, InputSource
from Commands.transport import DEFAULT_NAME, get_transport
from Mask import Mask
import ControllerColors
from Commands.CommandBase import Command
import Profile

addpath = dirname(dirname(dirname(abspath(__file__))))  # SerialControllerフォルダのパス
sys.path.append(addpath)

# メイン画面で使う定数、独立した部品、タブ・機能ごとの処理(Mixin)
from services.serial_service import SerialService
from services.profile_paths import apply_profile, profile_file
from services.record_service import RecordService
from services import geometry, log_buffer
from ui.constants import *  # noqa: F401,F403
from ui.popups import TagFilterPopup, CommandFilterPopup  # noqa: F401
from ui.tooltip import ToolTip  # noqa: F401
from ui.dialogue import open_dialogue
from ui.output import OutputTextAreaProxy, OutputWriter, StdoutRedirector  # noqa: F401
from ui.profile_dialog import selectProfile, selectProfileAllRunning  # noqa: F401
from ui.main_panel import MainPanelMixin
from ui.camera_panel import CameraPanelMixin
from ui.status_panel import StatusPanelMixin
from ui.audio_panel import AudioPanelMixin
from ui.serial_panel import SerialPanelMixin
from ui.touch_panel import TouchPanelMixin
from ui.controller_panel import ControllerPanelMixin
from ui.command_panel import CommandPanelMixin
from ui.notification_panel import NotificationPanelMixin
from ui.mask_panel import MaskPanelMixin
from ui.output_panel import OutputPanelMixin
from ui.layout_panel import LayoutPanelMixin
from ui.help_panel import HelpPanelMixin
from ui.tooltips import ToolTipsMixin


class PokeControllerApp(
    MainPanelMixin,
    CameraPanelMixin,
    StatusPanelMixin,
    AudioPanelMixin,
    SerialPanelMixin,
    TouchPanelMixin,
    ControllerPanelMixin,
    CommandPanelMixin,
    NotificationPanelMixin,
    MaskPanelMixin,
    OutputPanelMixin,
    LayoutPanelMixin,
    HelpPanelMixin,
    ToolTipsMixin,
):
    """
    メイン画面。起動時の組み立て、設定の読み込みと保存、終了の処理を持つ。
    タブ・機能ごとの処理は ui フォルダの各ファイル(Mixin)に分けてあり、ここで1つのクラスにまとめる
    """

    def __init__(self, master: tk.Tk | None = None, profile: str = "default"):
        """
        メイン画面を組み立て、設定を読み込んで、カメラ・シリアルポートなどを使える状態にする
        master: メインウィンドウ(tk.Tk)
        profile: 使うプロファイルの名前(設定ファイルは profiles/プロファイル名 から読む)
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())

        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self._logger.debug(f"User Profile Name: '{profile}'")

        self.root = master
        # 前回の大きさに戻す(_initWindowLayout)までは、ウィンドウを見えなくしておく
        # (中身に合わせた大きさで一度表示されてから、大きさが変わるのを見せないため)
        self._hideWindowUntilLayout()
        self.root.title(
            f"{Constant.NAME} ver.{Constant.VERSION} (profile: {profile})"
            + (" [設定を保存しません]" if Profile.is_read_only() else "")
        )
        # テーマ(配色)。部品の大きさがテーマで変わるので、部品を作る前に当てる。
        # 設定ファイルの場所をプロファイルのものにする(apply_profile)のは後なので、プロファイルの設定ファイルを指定して読む
        Theme.init(self.root, Settings.GuiSettings.readTheme(profile_file(profile, "settings.ini")))
        # ミニ画面のタブ領域の、見出しを表示しないスタイル(ttk のスタイルはテーマごとに持つので、テーマを変えるたびに作る)
        Theme.add_style_hook(lambda style: style.layout("Mini.TNotebook.Tab", []))
        # self.root.resizable(0, 0)
        self.controller = None
        # コントローラー設定(本体の色)のウィンドウ
        self.controller_color_window = None
        # 機能紹介のウィンドウ
        self.introduction_window = None
        # マニュアル(Instruction Manual)のウィンドウ
        self.manual_window = None
        self.keyPress = None
        self.keyboard = None

        self.camera_dic = None
        # カメラの番号 -> デバイスパス(音声入力がどのカメラと同じ機器かを調べるために使う)
        self.camera_paths = {}
        # カメラの代わりに取り込むウィンドウの識別名(空ならカメラを使う)
        self.capture_window = ""
        # カメラの一覧に並べたウィンドウの番号 -> ウィンドウの識別名
        self.window_ids = {}
        self.Line = None
        self.Discord = None

        self.procon = None
        self.procon_thread = None
        # 接続中のコントローラー一覧を取得中か(取得に1秒ほどかかるので別スレッドで行う)
        self.controller_devices_refreshing = False
        # 最後に取得した接続中のコントローラーの名前(番号順)
        self.controller_device_names = []
        # コントローラーの設定ウィンドウ
        self.controller_setup = None

        self.pokeconname = Constant.NAME
        self.pokeconversion = Constant.VERSION

        self.profile = profile
        Command.app_name = f"{Constant.NAME} ver.{Constant.VERSION}"
        Command.profilename = profile

        """
        ここから
        """
        self._buildMainPanel(master)
        self.controller_nb = ttk.Notebook(self.main_frame)
        self._buildStatusTab()
        self._buildCameraTab()
        self._buildAudioTab()
        self._buildSerialTab()
        self._buildTouchScreenTab()
        self._buildManualControlTab()
        self._buildCommandsTab()
        self._buildNotificationTab()
        self._buildMaskTab()
        right_frame_widget_mode_list = self._buildOthersTab()
        if platform.system() == "Windows" or platform.system() == "Darwin":
            self.controller_nb.configure(height="150")
        else:
            self.controller_nb.configure(height="180")
        self._fitControllerNotebookHeight()
        self._buildOutputArea()
        self._buildSidePanel(right_frame_widget_mode_list)
        self._buildToolTips()
        # self.text_area_1_tooltip = ToolTip(self.text_area_1, "output(#1)")
        # self.text_area_2_tooltip = ToolTip(self.text_area_2, "output(#2)")

        # 仮置フレームを削除
        self.canvas_frame.destroy()

        # 標準出力をログにリダイレクト
        # sys.stdout = StdoutRedirector(self.text_area_1)
        # sys.stdout = StdoutRedirector(self.text_area_2)

        # ログ画面に自動化スクリプトからアクセスできるようにする。
        Command.text_area_1 = self.text_area_1
        Command.text_area_2 = self.text_area_2
        # コマンドから開くダイアログの表示方法
        Command.dialogue_handler = open_dialogue

        # 初期表示を出力
        # self.text_area_1.config(state='normal')
        # self.text_area_1.insert('1.0', '----------画面1----------\n')
        # self.text_area_1.config(state='disable')
        # self.text_area_2.config(state='normal')
        # self.text_area_2.insert('1.0', '----------画面2----------\n')
        # self.text_area_2.config(state='disable')

        # 引数設定時、使用するsetting.iniを変更
        print("User Profile Name:", Settings.GuiSettings.SETTING_PATH)
        # 設定ファイルの場所を、プロファイルのものにする(画面を使わない処理が読む設定ファイルも同じにする)
        setting_path = apply_profile(profile)
        if setting_path is not None:
            Settings.GuiSettings.SETTING_PATH = setting_path
            PokeKeycon.SETTING_PATH = setting_path

        # シリアルの送信と、接続の管理(接続と切断、送るデータの形式)。
        # 設定の反映の中でポートの一覧を作るので、その前に用意する
        self.ser = Sender.Sender(self.is_show_serial)
        # 送信の失敗が続いたら、実行中のコマンドを止める
        self.watchSendFailures()
        self.serial_service = SerialService(self.ser)
        self.record_service = RecordService(self.ser, self.isCommandRunning, CONTROLLER_LOG_DIR)
        # load settings file
        self.loadSettings()
        # コントローラーの本体の色(Software-Controllerを作る前に反映する)
        ControllerColors.load_settings(self.settings.controller_colors)
        # 各tk変数に設定値をセット(コピペ簡単のため)
        self.is_show_realtime.set(self.settings.is_show_realtime.get())
        self.is_show_value.set(self.settings.is_show_value.get())
        self.is_show_guide.set(self.settings.is_show_guide.get())
        self.is_show_serial.set(self.settings.is_show_serial.get())
        self.is_use_keyboard.set(self.settings.is_use_keyboard.get())
        self.fps.set(self.settings.fps.get())
        self.show_size.set(self.settings.show_size.get())
        self.capture_size.set(self.settings.capture_size.get())
        self.controller_device.set(self.settings.controller_device.get())
        self.software_controller_layout.set(self.settings.software_controller_layout.get())
        self.is_use_audio.set(self.settings.is_use_audio.get())
        self.is_use_mjpg.set(self.settings.is_use_mjpg.get())
        self.preview_gain.set(self.settings.preview_gain)
        self.preview_gamma.set(self.settings.preview_gamma)
        self.is_show_mask.set(self.settings.is_show_mask)
        self.is_mask_apply_to_capture.set(self.settings.is_mask_apply_to_capture)
        for text in self.settings.masks:
            try:
                self.masks.append(Mask.from_text(text))
            except ValueError as e:
                self._logger.warning(f"Invalid mask setting is ignored: {text} ({e})")
        self.audio_device.set(self.settings.audio_device.get())
        self.is_audio_playback.set(self.settings.is_audio_playback.get())
        self.audio_output_device.set(self.settings.audio_output_device.get() or AUDIO_OUTPUT_DEFAULT)
        self.audio_volume.set(min(max(self.settings.audio_volume.get(), 0), 100))
        self.audio_volume_scale.set(self.audio_volume.get())
        self.refreshControllerDevices()
        self.com_port.set(self.settings.com_port.get())
        self.com_port_name.set(self.settings.com_port_name.get())
        self.baud_rate.set(self.settings.baud_rate.get())
        self.camera_id.set(self.settings.camera_id.get())
        if platform.system() == "Windows":
            self.is_show_windows.set(self.settings.is_show_windows.get())
            saved_window = self.settings.capture_window.get()
            # ウィンドウの識別名は "実行ファイル名|ウィンドウクラス名"。それ以外は追加の映像ソースの識別名で、
            # その機能が有効でない場合は使わない(カメラに戻す)
            if saved_window in EXTRA_SOURCES or (self.is_show_windows.get() and "|" in saved_window):
                self.capture_window = saved_window
        self.serial_data_format_name.set(self.settings.serial_data_format_name.get())
        transport = get_transport(self.serial_data_format_name.get())
        if not transport.is_available():
            # 保存されている形式が、この環境では使えない(例: ftd2xx が無い)
            print(f"{transport.unavailable_message()}{DEFAULT_NAME} に変更します。")
            self.serial_data_format_name.set(DEFAULT_NAME)
        self.touchscreen_start_x = self.settings.touchscreen_start_x
        self.touchscreen_start_y = self.settings.touchscreen_start_y
        self.touchscreen_end_x = self.settings.touchscreen_end_x
        self.touchscreen_end_y = self.settings.touchscreen_end_y
        self.is_touchscreen_capture_size.set(self.settings.is_touchscreen_capture_size)
        self.shortcut_command_name = {
            num: self.settings.command_name_dict[str(num)].get()
            for num in range(1, Settings.GuiSettings.SHORTCUT_NUM + 1)
        }
        # ショートカットに設定されたスクリプトのclass(python/mcu)はtk変数ではない
        self.shortcut_command_class = {
            num: self.settings.command_class_dict[str(num)]
            for num in range(1, Settings.GuiSettings.SHORTCUT_NUM + 1)
        }
        self.is_win_notification_start.set(
            self.settings.is_win_notification_start.get()
        )
        self.is_win_notification_end.set(self.settings.is_win_notification_end.get())
        self.is_line_notification_start.set(
            self.settings.is_line_notification_start.get()
        )
        self.is_line_notification_end.set(self.settings.is_line_notification_end.get())
        self.is_discord_notification_start.set(
            self.settings.is_discord_notification_start.get()
        )
        self.is_discord_notification_end.set(
            self.settings.is_discord_notification_end.get()
        )
        self.discord_notification_image.set(self.settings.discord_notification_image)
        self.area_size.set(self.settings.area_size)
        self.stdout_destination.set(self.settings.stdout_destination)
        self.right_frame_widget_mode.set(self.settings.right_frame_widget_mode)
        self.mini_widget_mode.set(self.settings.mini_widget_mode)
        self.setLogLevel(self.settings.log_level)
        self.loadNote()
        self.pos_software_controller.set(self.settings.pos_software_controller)
        self.pos_dialogue_buttons.set(self.settings.pos_dialogue_buttons)

        # Shortcutボタンに名称とtooltipを設定する
        self.shortcut_button_tooltips = {}
        for num, button in self.shortcut_buttons.items():
            self.shortcut_button_texts[num].set(self.shortcut_command_name[num][:SHORTCUT_TEXT_LENGTH])
            self.shortcut_button_tooltips[num] = ToolTip(button, self.shortcut_command_name[num])

        # 実行履歴 (settingsのリストを直接更新し、設定保存時に書き出す)
        self.command_history = self.settings.command_history
        self.updateHistoryView()

        # 各コンボボックスを現在の設定値に合わせて表示
        self.fps_cb.current(self.fps_cb["values"].index(self.fps.get()))
        if self.capture_size.get() not in self.capture_size_cb["values"]:
            self.capture_size.set(DEFAULT_CAPTURE_SIZE)
        self.capture_size_cb.current(
            self.capture_size_cb["values"].index(self.capture_size.get())
        )
        self.updateShowSizeList()

        # 類似度の表示機能を反映する
        self.mode_change_show_value()

        # ガイドの表示機能を反映する
        self.mode_change_show_guide()

        # 標準出力をログにリダイレクト
        self.switchStdoutDestination()

        # Notificationの設定を反映する
        self.mode_change_notification()

        # ダイアログのOK/NGのボタンの位置を設定する
        self.change_buttons_position()

        if platform.system() == "Windows" or platform.system() == "Darwin":
            try:
                self.locateCameraCmbbox()
                self.camera_id_entry.config(state="disable")
            except Exception as e:
                # Locate an entry instead whenever dll is not imported successfully
                self.camera_name_fromDLL.set(
                    "An error occurred when displaying the camera name in the Win/Mac environment."
                )
                self._logger.warning(
                    "An error occurred when displaying the camera name in the Win/Mac environment."
                )
                self._logger.warning(e)
                self.camera_name_cb.config(state="disable")
                self.camera_id_entry.config(state="normal")
            try:
                self.locateDeviceCmbbox()
                self.set_init_device_name()
            except Exception as e:
                self._logger.warning(
                    "An error occurred when checking serial device list."
                )
                self._logger.warning(e)
        elif platform.system() == "Linux":
            self.camera_name_fromDLL.set(
                "Linux environment. So that cannot show Camera name."
            )
            self.camera_name_cb.config(state="disable")
            self.camera_id_entry.config(state="normal")
        else:
            self.camera_name_fromDLL.set(
                "Unknown environment. Cannot show Camera name."
            )
            self.camera_name_cb.config(state="disable")
            self.camera_id_entry.config(state="normal")
        if str(self.camera_id_entry.cget("state")) != "normal":
            # カメラの名前から選べる環境では、IDの欄は表示しない(番号はカメラの名前に付いている)
            self.camera_id_label.grid_remove()
            self.camera_id_entry.grid_remove()
        # open up a camera
        self.camera = Camera(self.fps.get(), self.capture_size.get())
        # プレビューの明るさ(表示だけ)
        self.applyPreviewBrightness()
        self.openCamera()
        # activate serial communication
        try:
            self.locateDeviceCmbbox()
            self.set_init_device_name()
        except Exception:
            self.serial_device_name_label.destroy()
            self.serial_device_name_cb.destroy()
            self.scan_device_button.destroy()
            self.com_port_entry["state"] = "normal"

        if platform.system() == "Windows" or platform.system() == "Darwin":
            pass
        else:
            self.com_port_entry["state"] = "normal"

        self.activateSerial()
        self.activateKeyboard()
        # 入力欄に文字を打っている間は、キーボードでの操作を止める
        self.watchTypingForKeyboard()
        self.preview = CaptureArea(
            self.camera,
            self.fps.get(),
            self.serial_data_format_name.get(),
            self.is_show_realtime,
            #    self.ser,
            KeyPress(self.ser, source=InputSource.MOUSE),
            self.camera_lf,
            *list(map(int, self.show_size.get().split("x"))),
        )
        self.preview.config(cursor="crosshair")
        # プレビューを引き伸ばさず、Main Panelの中央に配置する
        self.camera_lf.columnconfigure(0, weight=1)
        self.camera_lf.rowconfigure(2, weight=1)
        self.preview.grid(column="0", columnspan="7", row="2", padx=str(PREVIEW_PAD), pady=str(PREVIEW_PAD))
        self.preview.on_touchscreen_area_changed = self.updateTouchscreenEntries
        self.refreshMaskList()
        self.preview.setTouchscreenArea(
            self.touchscreen_start_x,
            self.touchscreen_start_y,
            self.touchscreen_end_x,
            self.touchscreen_end_y,
        )
        self._restoreTouchscreenRatio(self.settings.touchscreen_ratio)
        self.loadCommands()

        # キャンバスに自動化スクリプトからアクセスできるようにする。
        Command.canvas = self.preview

        self.root.bind("<Key-F5>", self.ReloadCommandWithF5)
        self._logger.debug("Bind F5 key to reload commands")
        self.root.bind("<Key-F6>", self.StartCommandWithF6)
        self._logger.debug("Bind F6 key to execute commands")
        self.root.bind("<Key-Escape>", self.StopCommandWithEsc)
        self._logger.debug("Bind Escape key to stop commands")

        # self.keys_software_controller = UnitCommand
        self.keys_software_controller = KeyPress(self.ser, source=InputSource.MOUSE)

        self.setSoftwareControllerLayout()

        # 前回オンだった場合は、起動後に音声の取り込みを始める
        if self.audio is not None:
            self.root.after(500, self.initAudio)

        # Main widget
        self.mainwindow = self.main_frame

        self.root.protocol("WM_DELETE_WINDOW", self.exit)
        self.preview.startCapture()
        self.set_serial_data_format()

        # 右側のパネルの位置を前回と同じにし、Output画面/Software-Controllerを再配置する
        if self.settings.side_panel_position in PANEL_POSITIONS:
            self.panel_position = self.settings.side_panel_position
        if self.settings.mini_side_panel_position in PANEL_POSITIONS:
            self.mini_panel_position = self.settings.mini_side_panel_position
        try:
            ratios = json.loads(self.settings.pane_ratios) if self.settings.pane_ratios else {}
            if isinstance(ratios, dict):
                self.pane_ratios = ratios
        except ValueError:
            pass
        self.replace_right_frame_widget()
        self.buildPanes()
        # 前回ミニ画面だった場合は、ミニ画面にする
        if self.settings.is_mini:
            self.setMiniMode(True)

        self.menu = PokeController_Menubar(self)
        # デフォルト以外のテーマでは、テーマの色のメニューバーを使う(Windows のメニューバーは色を変えられないため)
        self.themed_menubar = Theme.ThemedMenuBar(self.root, self.menu, self.main_frame)
        self.themed_menubar.update()
        # ここまで(メニューバーを付けるまで)は fitWindowSize を行わない。
        # メニューバーを付ける前に大きさを確定すると、メニューバーの高さの分だけ中身が隠れるため
        self.window_ready = True
        self.root.after(100, self._initWindowLayout)
        # メイン画面が表示された後に、機能紹介を表示する(「今後は表示しない」にしている場合を除く)
        self.root.after(INTRODUCTION_DELAY_MS, self.showIntroductionAtStartup)

    def run(self) -> None:
        """画面を表示し、ウィンドウを閉じるまで、操作を待ち続ける"""
        self._logger.debug("Start Poke-Controller")
        self.mainwindow.mainloop()

    def exit(self) -> None:
        """
        ウィンドウの × ボタン: 確認のうえ、アプリケーションを終了する
        (操作の記録・コントローラーでの操作・キーボードの受け付け・音声・カメラを止め、シリアルポートを切断し、設定を保存する)
        """
        ret = tkmsg.askyesno("確認", "Poke Controllerを終了しますか？")
        if ret:
            # Note の、まだ保存していない分を保存する
            self.saveNote()
            # 予約を消す(終了の途中で、予約の時刻が来ても、開始しないように)
            self.run_schedule.cancel_all()
            # 記録中なら終了して自動化スクリプトを出力する
            if self.ser.recording:
                self.stopRecord()
            # proconのスレッドを止める(シリアルを閉じる前に入力を離す)
            self.is_use_Pro_Controller.set(False)
            self.mode_change_Pro_Controller()

            if self.ser.isOpened():
                self.ser.closeSerial()
                print("Serial disconnected")
                # self._logger.info("Serial disconnected")

            # stop listening to keyboard events
            if self.keyboard is not None:
                self.keyboard.stop()
                self.keyboard = None

            self.saveSettings()

            self.stopAudio()
            self.camera.destroy()
            cv2.destroyAllWindows()
            self._logger.debug("Stop Poke Controller")
            self.root.destroy()

    def saveSettings(self) -> None:
        """
        画面の今の設定を、現在のプロファイルの設定ファイルに保存する
        """
        # (テーマを作る画面で色を試している間に終了した場合は、試す前のテーマを保存する)
        self.settings.theme = Theme.saved_theme_id()
        self.settings.is_show_realtime.set(self.is_show_realtime.get())
        self.settings.is_show_value.set(self.is_show_value.get())
        self.settings.is_show_guide.set(self.is_show_guide.get())
        self.settings.is_show_serial.set(self.is_show_serial.get())
        self.settings.is_use_keyboard.set(self.is_use_keyboard.get())
        self.settings.fps.set(self.fps.get())
        self.settings.show_size.set(self.mini_saved_show_size if self.is_mini else self.show_size.get())
        self.settings.is_mini = self.is_mini
        self.settings.capture_size.set(self.capture_size.get())
        self.settings.controller_device.set(self.controller_device.get())
        self.settings.software_controller_layout.set(self.software_controller_layout.get())
        self.settings.is_use_audio.set(self.is_use_audio.get())
        self.settings.is_use_mjpg.set(self.is_use_mjpg.get())
        self.settings.preview_gain, self.settings.preview_gamma = self._previewBrightnessValues()
        self.settings.is_show_mask = self.is_show_mask.get()
        self.settings.is_mask_apply_to_capture = self.is_mask_apply_to_capture.get()
        self.settings.masks = [mask.to_text() for mask in self.masks]
        self.settings.audio_device.set(self.audio_device.get())
        self.settings.is_audio_playback.set(self.is_audio_playback.get())
        self.settings.audio_output_device.set(self._audioOutputDeviceName())
        self.settings.audio_volume.set(self.audio_volume.get())
        self.settings.com_port.set(self.com_port.get())
        self.settings.baud_rate.set(self.baud_rate.get())
        self.settings.camera_id.set(self.camera_id.get())
        self.settings.capture_window.set(self.capture_window)
        self.settings.is_show_windows.set(self.is_show_windows.get())
        self.settings.serial_data_format_name.set(
            self.serial_data_format_name.get()
        )
        self.settings.touchscreen_start_x = self.preview.touchscreen_start_x
        self.settings.touchscreen_start_y = self.preview.touchscreen_start_y
        self.settings.touchscreen_end_x = self.preview.touchscreen_end_x
        self.settings.touchscreen_end_y = self.preview.touchscreen_end_y
        self.settings.is_touchscreen_capture_size = self.is_touchscreen_capture_size.get()
        self.settings.touchscreen_ratio = geometry.ratio_to_text(getattr(self, "touchscreen_ratio", None))
        for num in range(1, Settings.GuiSettings.SHORTCUT_NUM + 1):
            self.settings.command_class_dict[str(num)] = self.shortcut_command_class[num]
            self.settings.command_name_dict[str(num)].set(self.shortcut_command_name[num])
        self.settings.is_win_notification_start.set(
            self.is_win_notification_start.get()
        )
        self.settings.is_win_notification_end.set(
            self.is_win_notification_end.get()
        )
        self.settings.is_line_notification_start.set(
            self.is_line_notification_start.get()
        )
        self.settings.is_line_notification_end.set(
            self.is_line_notification_end.get()
        )
        self.settings.is_discord_notification_start.set(
            self.is_discord_notification_start.get()
        )
        self.settings.is_discord_notification_end.set(
            self.is_discord_notification_end.get()
        )
        self.settings.discord_notification_image = self.discord_notification_image.get()
        self.settings.area_size = self.area_size.get()
        self.settings.stdout_destination = self.stdout_destination.get()
        self.settings.right_frame_widget_mode = self.right_frame_widget_mode.get()
        self.settings.mini_widget_mode = self.mini_widget_mode.get()
        self.settings.log_level = self.getLogLevel()
        self.settings.pos_software_controller = self.pos_software_controller.get()
        self.settings.pos_dialogue_buttons = self.pos_dialogue_buttons.get()
        self.settings.side_panel_position = self.panel_position
        self.settings.mini_side_panel_position = self.mini_panel_position
        # 通常の画面のウィンドウの大きさ(ミニ画面のときは、ミニ画面にする前の大きさ)と、仕切り線の位置の比率
        if self.is_mini:
            normal_size = getattr(self, "normal_window_size", None)
        else:
            normal_size = (self.root.winfo_width(), self.root.winfo_height()) if self.root.state() == "normal" else None
        if normal_size is not None:
            self.settings.window_size = "{0}x{1}".format(*normal_size)
        self.settings.pane_ratios = json.dumps(self.pane_ratios)

        self.settings.save()

    def loadSettings(self) -> None:
        """現在のプロファイルの設定ファイルを読み込み、self.settings に入れる(起動時)"""
        self.settings = Settings.GuiSettings()
        self.settings.load()


def enableExtension(name: str) -> bool:
    """
    追加の機能(このファイルと同じ場所にある、name という名前のフォルダ)を有効にする。
    フォルダの enable() を呼ぶ。フォルダが無い場合・読み込めない場合は、無効のまま起動を続ける
    """
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if not name.isidentifier() or not os.path.isfile(os.path.join(folder, "__init__.py")):
        return False
    try:
        module = importlib.import_module(name)
        # 同じ名前の別のモジュール(標準ライブラリ等)を読み込んだ場合は、使わない
        if os.path.dirname(os.path.abspath(getattr(module, "__file__", None) or "")) != folder:
            return False
        return bool(module.enable())
    except Exception as e:
        getLogger(__name__).warning(f"Failed to enable the extension '{name}': {e}")
        return False


if __name__ == "__main__":
    import tkinter as tk

    parser = argparse.ArgumentParser(
        description="Switch/GC automation support software using Python"
    )
    # --profile を指定しない場合は、起動時にプロファイルを選ぶ
    parser.add_argument("--profile", "-p", help="profile", type=str, default=None)
    # --auto: プロファイルを選ぶ画面を出さず、起動されていないプロファイルを優先度の順に選ぶ
    parser.add_argument(
        "--auto", "-a", help="select a profile that is not running automatically", action="store_true"
    )
    # --ext NAME: 追加の機能(NAME という名前のフォルダ)を有効にする。複数ある場合は、--ext を繰り返す
    parser.add_argument("--ext", help="enable the extension in the folder NAME", metavar="NAME", action="append", default=[])
    # --ui web: 画面を、Web ブラウザで表示する(既定は tk: これまでのウィンドウ)
    parser.add_argument("--ui", help="user interface: tk (window, default) or web (web browser)", choices=("tk", "web"), default="tk")
    # --ds_ft: FTDI 直結の DS 基板用の Data Format (DS FT) を使えるようにする(ftd2xx が必要)
    parser.add_argument(
        "--ds_ft", "--ds-ft", dest="ds_ft", help="enable the data formats for the FTDI-wired DS board (DS FT)",
        action="store_true",
    )
    # --monitor: 補助ツール(Monitor.py)から、このウィンドウの状態・Output・映像を見て、操作できるようにする
    parser.add_argument(
        "--monitor", help="let the monitor tool (Monitor.py) watch and control this window", action="store_true"
    )
    # --port: --ui web のときに使うポート番号 / --no-browser: --ui web のときに、ブラウザを自動で開かない
    parser.add_argument("--port", help="port number for --ui web", type=int, default=None)
    parser.add_argument("--no-browser", help="do not open the web browser automatically (--ui web)", action="store_true")
    args = parser.parse_args()

    logger = PokeConLogger.root_logger()
    if args.ui != "web":
        # Output の Log タブに表示するために、ログを溜め始める(画面を作る前のログも表示できるように、ここでつなぐ)
        log_buffer.install()
    sys.setswitchinterval(GIL_SWITCH_INTERVAL)
    for extension in args.ext:
        enableExtension(extension)
    if args.ds_ft:
        from Commands.transport import ds_ft

        ds_ft.set_enabled(True)
    # logger.info('The root logger is created.')

    if args.ui == "web":
        # Web ブラウザ版の画面(tkinter のウィンドウは作らない)
        from web import main as web_main

        if not flag_import_plyer:
            print('"plyer" is not installed. Some notification functions are not available.')
        sys.exit(
            web_main.run(
                args.profile,
                auto=args.auto,
                port=args.port,
                open_browser=not args.no_browser,
                monitor=args.monitor,
            )
        )

    if not flag_import_plyer:
        tkmsg.showwarning(
            "Warning",
            '"plyer" is not installed. Some notification functions are not available. We recommend installing with "pip install plyer".',
        )

    root = tk.Tk()
    read_only_message = None
    if args.profile is None and args.auto:
        args.profile = Profile.select_auto_profile()
        if args.profile is None:
            # 対象のプロファイルがすべて起動されている: defaultで起動するか、新しく作るかを選ぶ
            args.profile = selectProfileAllRunning(root)
            if args.profile is None:
                root.destroy()
                sys.exit(0)
    elif args.profile is None:
        args.profile = selectProfile(root)
        if args.profile is None:
            # プロファイルを選ばずに閉じた場合は起動しない
            root.destroy()
            sys.exit(0)
    if not Profile.acquire_profile_lock(args.profile):
        read_only_message = (
            f"プロファイル「{args.profile}」はすでに起動されています。\n"
            "このウィンドウで変更した設定は保存されません。"
        )
    if read_only_message is not None:
        # 同じプロファイルで2つ目以降に起動した場合は、設定を保存しない
        Profile.set_read_only(True)
        root.withdraw()
        tkmsg.showwarning("Warning", read_only_message)
        root.deiconify()
    # プロファイルが決まったので、ログのファイル(log_プロファイル名_日時.log)を作る
    PokeConLogger.set_profile(args.profile)
    app = PokeControllerApp(root, args.profile)
    if args.monitor:
        from ui.monitor_link import MonitorLink

        app.monitor_link = MonitorLink(app, args.profile)
        app.monitor_link.start()
    app.run()
