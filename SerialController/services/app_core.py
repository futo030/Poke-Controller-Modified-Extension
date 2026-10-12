#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アプリ本体: 設定・カメラ・シリアル・コマンドの実行・出力を組み立てて、まとめて操作する

画面(tkinter)には触れない。画面(Web 版など)は、このクラスを呼び、変化の知らせ(listener)を受けて表示する。
"""
from __future__ import annotations

import math
import threading
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

import Constant
import KeyMap
from Camera import Camera, CAPTURE_SIZE_LIST, DEFAULT_CAPTURE_SIZE, EXTRA_SOURCES
from Commands import PythonCommandBase, Sender
from Commands.CommandBase import Command
from Commands.ControllerProfile import load_profiles
from Commands.Keys import Direction, InputSource, KeyPress, Stick, Touchscreen, NEUTRAL
from Commands.transport import DEFAULT_NAME, get_transport
from Commands.ProController import ProController
from Keyboard import SwitchKeyboardController
from Mask import Mask, draw_masks
from services import command_catalog, command_service, geometry, notification_image, status_text
from services.audio_service import OUTPUT_DEFAULT, AudioService
from services.command_service import CommandLoadError, CommandService
from services.controller_setup_service import ControllerSetupService
from services.editor_service import EditorService
from services.output_service import OutputService
from services.profile_paths import apply_profile
from services.record_service import RecordError, RecordService
from services.run_schedule import format_remaining
from services.serial_service import SerialService
from services.settings_control import SettingsControl
from services.sleep_watch import SleepWatch
from services.tools_service import ToolsService
from services.software_controller import SoftwareController, layout_names
from services.settings_store import AppSettings

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

CONTROLLER_LOG_DIR = "Controller_Log"
# 接続したコントローラーのスレッドの終了を待つ時間(秒)
CONTROLLER_STOP_TIMEOUT = 3.0
# タッチスクリーンの座標の大きさ(3DS の下画面)
TOUCHSCREEN_WIDTH = 320.0
TOUCHSCREEN_HEIGHT = 240.0
# 出力先のページ(画面が1ページだけの場合)
OUTPUT_PAGE = 0


class AppCore:
    """設定・カメラ・シリアル・コマンドの実行・出力・手動操作をまとめて持ち、画面からの操作を受ける"""

    def __init__(
        self, profile: str = "default", gui: object | None = None, get_output_page: Callable[[], int] | None = None
    ):
        """
        profile: 使うプロファイル
        gui: 画像認識を使うコマンドに渡す、認識した位置の表示先(ImgRect / ImgText を持つもの。無ければ None)
        get_output_page: コマンドを開始するときの、出力先のページを返す関数(None のときは、いつも OUTPUT_PAGE)
        """
        self.profile = profile
        self.gui = gui
        self._get_output_page = get_output_page if get_output_page is not None else (lambda: OUTPUT_PAGE)
        # 状態が変わったときに呼ぶ関数(引数は、変わったものの名前: "command" / "serial" / "camera" / "input")
        self.listeners = []

        apply_profile(profile)
        Command.app_name = f"{Constant.NAME} ver.{Constant.VERSION}"
        Command.profilename = profile

        self.settings = AppSettings()
        self.sender = Sender.Sender(self.settings.is_show_serial)
        # 送信の失敗が続いたら・PC がスリープから戻ったら、実行中のコマンドを止める
        self.sender.on_send_failures = self._on_send_failures
        self.sleep_watch = SleepWatch(self._on_resume_from_sleep)
        self.serial = SerialService(self.sender)
        self.output = OutputService(Command.get_output_page_for_current_thread)
        self.commands = CommandService(lambda: self.camera, lambda: self.gui, self._on_command_state)
        self.record = RecordService(self.sender, lambda: self.commands.is_running, CONTROLLER_LOG_DIR)
        capture_size = self.settings.capture_size if self.settings.capture_size in CAPTURE_SIZE_LIST else DEFAULT_CAPTURE_SIZE
        self.camera = Camera(self.settings.fps, capture_size)
        self.masks = []
        for text in self.settings.masks:
            try:
                self.masks.append(Mask.from_text(text))
            except ValueError as e:
                _logger.warning(f"Invalid mask setting is ignored: {text} ({e})")
        self.capture_window = ""
        self.audio = AudioService(self.settings)
        # 設定の変更と、選べる候補(カメラ・ポート・音声デバイス)の一覧
        self.settings_control = SettingsControl(self)
        # ショートカット・目隠し・タッチスクリーンの範囲・キーコンフィグ・本体の色・通知先の編集
        self.editor = EditorService(self)
        # スクリーンショットの保存、ファイルを開く、通知の確認、ヘルプの文章など
        self.tools = ToolsService(self)
        # 接続したコントローラーの、ボタンの割り当ての設定
        self.controller_setup = ControllerSetupService(self)
        # 手動操作(マウス)の入力先
        self.mouse_keys = KeyPress(self.sender, source=InputSource.MOUSE)
        # Software-Controller(画面上のコントローラー)。レイアウトは、設定を反映するとき(start)に決める
        self.softcon = SoftwareController(KeyPress(self.sender, source=InputSource.MOUSE))
        # Controller Simulator(大きいレイアウトのコントローラー)
        self.simulator = SoftwareController(KeyPress(self.sender, source=InputSource.MOUSE), large=True)
        self.keyboard = None
        self.controller = None
        self.controller_thread = None
        self.started = False

    # ---------------------------------------------------------------- 知らせ

    def add_listener(self, listener: Callable[[str], None]) -> None:
        """状態が変わったときに呼ぶ関数を足す(引数は "command" / "serial" / "camera" / "input")"""
        self.listeners.append(listener)

    def _notify(self, topic: str) -> None:
        """変わったものの名前を、すべての listener に知らせる(listener の例外は、ログに残して続ける)"""
        for listener in list(self.listeners):
            try:
                listener(topic)
            except Exception:
                _logger.exception("A listener failed.")

    def _on_command_state(self, state: str) -> None:
        """コマンドの状態が変わったことを、listener に知らせる(state は使わない)"""
        self._notify("command")

    # ---------------------------------------------------------------- 起動と終了

    def start(self) -> None:
        """
        設定を反映し、カメラを開き、シリアルに接続し、コマンドの一覧を読み込む
        """
        settings = self.settings
        self.sleep_watch.start()
        # 出力画面: コマンドの print_t1 / print_t2 と、標準出力(print)の出力先
        Command.text_area_1 = self.output.channel(1)
        Command.text_area_2 = self.output.channel(2)
        destination = settings.stdout_destination if settings.stdout_destination in ("1", "2") else "1"
        self.output.redirect_stdout(int(destination))
        Command.stdout_destination = destination
        Command.canvas = self.gui
        Command.isSimilarity = settings.is_show_value
        Command.isGuide = settings.is_show_guide
        Command.pos_dialogue_buttons = settings.pos_dialogue_buttons
        Command.isWinNotStart = settings.is_win_notification_start
        Command.isWinNotEnd = settings.is_win_notification_end
        Command.isLineNotStart = settings.is_line_notification_start
        Command.isLineNotEnd = settings.is_line_notification_end
        Command.isDiscordNotStart = settings.is_discord_notification_start
        Command.isDiscordNotEnd = settings.is_discord_notification_end
        # 開始・終了の通知に付ける画像(この画面にはウィンドウがないので、いつも、カメラの今の画像)
        Command._notification_image = lambda: notification_image.pick(notification_image.CAMERA, self.camera.readFrame)

        # Software-Controller のレイアウトと、本体の色
        self.set_softcon_layout(settings.software_controller_layout, settings.controller_colors)
        self.set_simulator_layout(settings.controller_layout)
        self.open_camera()
        self.connect_serial()
        self.commands.load()
        # 選べる候補の一覧を作り、前回オンだった場合は音声の取り込みを始める
        self.settings_control.scan(announce=False)
        self.audio.apply(self.settings_control.camera_paths, settings.camera_id)
        self.started = True

    def close(self) -> None:
        """
        終了の処理: 入力を止め、シリアルを閉じ、設定を保存し、カメラを閉じる
        """
        self.sleep_watch.stop()
        if self.record.is_recording():
            self.stop_record()
        self.softcon.release_all()
        self.simulator.release_all()
        self.controller_setup.close()
        self.stop_controller()
        if self.commands.is_running:
            try:
                self.stop_command()
            except Exception:
                _logger.exception("Failed to stop the command.")
        self.set_keyboard_active(False)
        self.editor.stop_key_capture()
        if self.sender.isOpened():
            self.sender.closeSerial()
            print("Serial disconnected")
        self.settings.save()
        self.audio.stop()
        self.camera.destroy()
        _logger.debug("Stop Poke Controller")

    # ---------------------------------------------------------------- カメラ

    def open_camera(self) -> None:
        """設定(カメラの番号・映像ソース・fps・目隠し)を反映して、カメラを開き直す"""
        settings = self.settings
        self.camera.use_mjpg = settings.is_use_mjpg
        self.camera.fps = int(settings.fps)
        # ウィンドウの識別名は "実行ファイル名|ウィンドウクラス名"。それ以外は追加の映像ソースの識別名で、
        # その機能が有効でない場合は使わない(カメラに戻す)
        saved_window = settings.capture_window
        if saved_window in EXTRA_SOURCES or (settings.is_show_windows and "|" in saved_window):
            self.capture_window = saved_window
        else:
            self.capture_window = ""
        if settings.is_show_mask and settings.is_mask_apply_to_capture:
            self.camera.capture_filter = lambda frame: draw_masks(frame, self.masks)
        else:
            self.camera.capture_filter = None
        self.camera.openCamera(settings.camera_id, self.capture_window)
        self._notify("camera")

    # ---------------------------------------------------------------- シリアル

    def connect_serial(self) -> bool:
        """
        設定の形式・ポート・ボーレートで、シリアルに接続する。接続できたかを返す
        (使えない形式は既定の形式に、形式で決まるボーレートがあればその値に、設定を書き換える)
        """
        settings = self.settings
        format_name = settings.serial_data_format_name
        transport = get_transport(format_name)
        if not transport.is_available():
            # 保存されている形式が、この環境では使えない(例: ftd2xx が無い)
            print(f"{transport.unavailable_message()}{DEFAULT_NAME} に変更します。")
            format_name = settings.serial_data_format_name = DEFAULT_NAME
        baud_rate = self.serial.set_data_format(format_name)
        self.mouse_keys.init_hat()
        self.softcon.keys.init_hat()
        self.simulator.keys.init_hat()
        if baud_rate is not None and baud_rate != settings.baud_rate:
            print(f"ボーレートを強制的に{baud_rate}に変更します。")
            settings.baud_rate = baud_rate
        connected = self.serial.connect(settings.com_port, settings.com_port_name, settings.baud_rate)
        if self.keyboard is not None:
            # 接続し直した場合は、キーボードの入力先を新しい接続にする
            self.set_keyboard_active(False)
        self._notify("serial")
        return connected

    def disconnect_serial(self) -> None:
        """キーボードでの手動操作を止めて、シリアルを切断する"""
        self.set_keyboard_active(False)
        self.serial.disconnect()
        self._notify("serial")

    # ---------------------------------------------------------------- コマンド

    def command_names(self, command_type: str) -> list:
        """その種類("Python" / "Mcu")のコマンドの名前の一覧"""
        return [c.name for c in self.commands.commands[command_type]]

    def start_command(self, command_type: str, name: str) -> bool:
        """
        コマンドを開始する。開始できたかを返す(できない理由は、出力画面に表示する)
        command_type: 種別("Python" / "Mcu"。"py" や "MCU" などの書き方も受け付ける)、name: コマンドの名前
        """
        if self.commands.is_running:
            print("Command is now working!")
            return False
        if self.record.is_recording():
            print("操作記録中はコマンドを開始できません。Recordボタンを押して記録を終了してください。")
            return False
        command_type, error = command_catalog.find_named_command(
            command_type, name, self.command_names(command_service.PYTHON), self.command_names(command_service.MCU)
        )
        if command_type is None:
            print(error)
            return False
        # 接続したコントローラーでの操作は、コマンドの実行中は止める
        self.stop_controller()
        try:
            if not self.commands.assign(command_type, name):
                return False
        except CommandLoadError as e:
            print(f"コマンドの読み込みに失敗しました。({e.entry.file_path})")
            return False
        current = self.commands.current
        _logger.info("Start " + current.NAME)
        # Pythonコマンドは実行スレッド側で「スクリプト開始: ...」を表示するため、ここでは表示しない
        if not isinstance(current, PythonCommandBase.PythonCommand):
            print("Start " + current.NAME)
        # 履歴は開始の前に足す(開始の知らせを受けた画面が、新しい履歴を表示できるように)
        command_catalog.add_history(self.settings.command_history, command_type, name, AppSettings.HISTORY_MAX)
        self.commands.record_usage(command_type, name)
        self.commands.start(self.sender, self._get_output_page())
        return True

    def release_all_inputs(self) -> None:
        """
        押したまま・倒したままになっている入力を、すべて離す(画面上のコントローラーの固定、キーボードでの操作、そのほかの入力源)。
        実行中のコマンドは、止めない
        """
        self.softcon.release_all()
        self.simulator.release_all()
        if self.keyboard is not None:
            self.keyboard.releaseAll()
        if not self.sender.isOpened():
            print("すべての入力を離しました(シリアルに接続していないので、機器へは送っていません)。")
        else:
            self.sender.release_all(get_transport(self.settings.serial_data_format_name).end_row)
            print("すべての入力を離しました。")
        self._notify("input")

    def _on_send_failures(self, count: int, error: Exception) -> None:
        """
        送信の失敗が続いたとき: 知らせて、実行中のコマンドを止める(接続が切れたまま、スクリプトだけが進まないように)
        count: 続いた回数。error: 最後のエラー
        """
        print(f"[シリアル] 送信に {count} 回続けて失敗しました。接続が切れている可能性があります。({error})")
        if self.commands.state == command_service.RUNNING:
            print("[シリアル] 実行中のコマンドを止めます。")
            self.stop_command()
        print("[シリアル] ケーブルを確かめて、ポートをつなぎ直してください。")

    def _on_resume_from_sleep(self, seconds: float) -> None:
        """
        PC が止まっていた(スリープから戻った)とき: 実行中のコマンドを止める(スリープの間も、ゲーム機は動いているため)
        seconds: 止まっていた時間(秒)
        """
        if self.commands.state != command_service.RUNNING:
            return
        print(f"[スリープ] PC が約 {format_remaining(seconds)}、止まっていました(スリープなど)。実行中のコマンドを止めます。")
        print("[スリープ] シリアルの接続が切れている場合は、ポートをつなぎ直してください。")
        self.stop_command()

    def stop_command(self) -> None:
        """実行中のコマンドに停止を頼む(実行していない場合と、すでに頼んだ場合は何もしない)"""
        if not self.commands.is_running or self.commands.state == command_service.STOPPING:
            return
        current = self.commands.current
        # 停止時の出力は、開始時のページ(コマンドの出力先)に表示する
        with Command.output_to_page(Command.output_page):
            print("Stop " + current.NAME)
            _logger.info("Stop " + current.NAME)
            try:
                self.commands.stop(self.sender)
            except PythonCommandBase.StopThread:
                # コマンドが自分で終了を始めていた場合(終了の処理は済んでいる)
                pass

    def pause_command(self) -> None:
        """実行中のコマンドを一時停止する(一時停止できないコマンドでは何もしない)"""
        if self.commands.state == command_service.RUNNING and self.commands.can_pause:
            self.commands.pause()
            self._notify("command")

    def resume_command(self) -> None:
        """コマンドの一時停止を解く"""
        if self.commands.state == command_service.RUNNING and self.commands.can_pause:
            self.commands.resume()
            self._notify("command")

    def reload_commands(self) -> None:
        """コマンドの一覧を読み込み直す(コマンドの実行中は読み込み直さない)"""
        if self.commands.is_running:
            print("コマンド実行中は読み込み直せません。")
            return
        self.commands.reload()
        print("Finished reloading command modules.")
        self._notify("command")

    def refresh_command_list(self) -> None:
        """
        コマンドの一覧を取得し直して、画面に知らせる(コマンドのモジュールは、読み込み直さない。実行中でも行える)。
        タグを書き換えた後や、新しいスクリプトを作った後に使う
        """
        self.commands.reload()
        self._notify("command")

    # ---------------------------------------------------------------- 操作記録

    def start_record(self) -> bool:
        """手動操作の記録を始める。始められたかを返す(できない理由は、出力画面に表示する)"""
        try:
            recorder = self.record.start()
        except RecordError as e:
            print(e)
            return False
        print(f"操作記録を開始しました。生ログ: {recorder.raw_log_path}")
        self._notify("input")
        return True

    def stop_record(self) -> None:
        """手動操作の記録を終え、結果(出力した自動化スクリプトの場所など)を出力画面に表示する"""
        result = self.record.stop()
        if result.recorded:
            if result.error is not None:
                print(f"操作記録の変換に失敗しました。生ログ: {result.raw_log_path}")
            elif result.path is None:
                print("操作が記録されなかったため、自動化スクリプトは出力しませんでした。")
            else:
                print(f"操作記録を出力しました: {result.path}")
        self._notify("input")

    # ---------------------------------------------------------------- 手動操作: キーボード

    def keyboard_console(self) -> str:
        """今の Software-Controller のレイアウトに対応する、キーボード操作のゲーム機の名前"""
        return KeyMap.console_of_layout(self.settings.software_controller_layout)

    def set_keyboard_active(self, active: bool) -> bool:
        """
        キーボードでの手動操作の受け付けを始める / 止める(PC のキー入力を読む)。受け付けているかを返す
        """
        if active and self.keyboard is None and self.serial.key_press is not None:
            self.keyboard = SwitchKeyboardController(self.serial.key_press, self.keyboard_console())
            self.keyboard.listen()
        elif not active and self.keyboard is not None:
            self.keyboard.stop()
            self.keyboard = None
        return self.keyboard is not None

    def set_softcon_layout(self, name: str, color_settings: dict | None = None) -> None:
        """
        Software-Controller のレイアウトを切り替える(キーボード操作のキーの対応も、そのゲーム機のものにする)
        color_settings: 本体の色の設定(None なら、読み込み済みの色のまま)
        """
        layout = self.softcon.set_layout(name, color_settings)
        self.settings.software_controller_layout = layout["name"]
        if self.keyboard is not None:
            self.keyboard.reloadKeyMap(self.keyboard_console())

    def set_simulator_layout(self, name: str) -> None:
        """Controller Simulator のレイアウトを切り替える(選んだ名前は、設定に残す)"""
        layout = self.simulator.set_layout(name)
        self.settings.controller_layout = layout["name"]

    # ---------------------------------------------------------------- 手動操作: 接続したコントローラー

    @property
    def is_controller_active(self) -> bool:
        """接続したコントローラーでの操作を、受け付けているか"""
        return self.controller is not None

    def start_controller(self) -> bool:
        """
        接続したコントローラーでの操作を、別のスレッドで始める。始められたかを返す
        (コマンドの実行中と、コントローラーの設定中は始めない)
        """
        if self.commands.is_running:
            print("コマンド実行中は、コントローラーでの操作を開始できません。")
            return False
        if self.controller_setup.active:
            print("コントローラーの設定中は、コントローラーでの操作を開始できません。")
            return False
        # 前のスレッドが残っていれば止めてから起動する
        self.stop_controller()
        profiles, errors = load_profiles()
        for error in errors:
            print(f"コントローラーのプロファイルを読み込めませんでした: {error}")
        controller = ProController(profiles, self.settings.controller_device)
        self.controller = controller
        # 停止待ちがタイムアウトしてもアプリの終了を妨げないようにdaemonにする
        self.controller_thread = threading.Thread(
            target=self._run_controller, args=(controller,), name="ProController", daemon=True
        )
        self.controller_thread.start()
        self._notify("input")
        return True

    def _run_controller(self, controller: ProController) -> None:
        """コントローラーの入力を読み続ける(スレッドの中身)。自分から止まった場合は、無効の状態に戻す"""
        controller.controller_loop(self.sender)
        # 接続エラーや切断で止まった場合は、無効の状態に戻す
        if not controller.stop_requested and self.controller is controller:
            self.controller = None
            self.controller_thread = None
            self._notify("input")

    def stop_controller(self) -> None:
        """
        接続したコントローラーのスレッドに停止を要求し、終了処理(入力の解放・操作記録の出力)が終わるまで待つ
        """
        controller, thread = self.controller, self.controller_thread
        if controller is None:
            return
        controller.stop()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(CONTROLLER_STOP_TIMEOUT)
            if thread.is_alive():
                _logger.warning("Pro Controller thread did not stop in time.")
        self.controller = None
        self.controller_thread = None
        self._notify("input")

    # ---------------------------------------------------------------- 手動操作: プレビュー上のマウス

    @property
    def has_touchscreen(self) -> bool:
        """
        タッチスクリーンのある形式か(プレビュー上の右ドラッグが、右スティックではなくタッチになる)
        """
        return get_transport(self.settings.serial_data_format_name).has_touchscreen

    def touchscreen_ratio(self) -> tuple | None:
        """
        タッチスクリーンの範囲の、取り込み画像に対する割合 (start_x, start_y, end_x, end_y)
        """
        settings = self.settings
        ratio = geometry.parse_ratio(settings.touchscreen_ratio)
        if ratio is not None:
            return ratio
        try:
            width, height = map(int, settings.show_size.lower().split("x"))
            area = (settings.touchscreen_start_x, settings.touchscreen_start_y, settings.touchscreen_end_x, settings.touchscreen_end_y)
            ratio = geometry.area_to_ratio(area, width, height)
        except (ValueError, ZeroDivisionError):
            return None
        return ratio if all(0.0 <= v <= 1.0 for v in ratio) else None

    def move_stick(self, side: str, angle: float, magnitude: float) -> None:
        """
        スティックを倒す。side: "left" / "right"、angle: 角度(度。右が0、上が90)、magnitude: 倒す大きさ(0～1)
        """
        magnitude = min(max(float(magnitude), 0.0), 1.0)
        radian = math.radians(float(angle))
        x = int(128 + magnitude * 127.5 * math.cos(radian))
        y = 255 - int(128 - magnitude * 127.5 * math.sin(radian))
        self.mouse_keys.input(Direction(Stick.LEFT if side == "left" else Stick.RIGHT, (x, y)))

    def release_stick(self, side: str) -> None:
        """スティックを中央に戻す。side: "left" / "right"("left" 以外は、右スティック)"""
        self.mouse_keys.input(Direction(Stick.LEFT if side == "left" else Stick.RIGHT, NEUTRAL))

    def touch(self, x: float, y: float) -> bool:
        """
        タッチスクリーンを押す。x, y: 取り込み画像に対する位置(0～1)。範囲の外の場合は何もせず False
        """
        ratio = self.touchscreen_ratio()
        if ratio is None:
            return False
        start_x, start_y, end_x, end_y = ratio
        if not (start_x < x < end_x and start_y < y < end_y):
            return False
        pos_x = int(TOUCHSCREEN_WIDTH * (x - start_x) / (end_x - start_x))
        pos_y = int(TOUCHSCREEN_HEIGHT * (y - start_y) / (end_y - start_y))
        self.mouse_keys.input(Touchscreen(pos_x, pos_y))
        return True

    def release_touch(self) -> None:
        """タッチスクリーンから離す"""
        self.mouse_keys.inputEnd(Touchscreen(0, 0))

    # ---------------------------------------------------------------- 状態

    def state(self) -> dict:
        """
        画面に表示する状態(JSON にできる値だけ)
        """
        settings = self.settings
        commands = self.commands
        current = commands.current
        return {
            "app": f"{Constant.NAME} ver.{Constant.VERSION}",
            "profile": self.profile,
            "command": {
                "state": commands.state,
                "paused": bool(Command.isPause),
                "can_pause": bool(commands.is_running and commands.can_pause),
                "name": getattr(current, "NAME", "") if commands.is_running else "",
            },
            "commands": {
                command_type: [{"name": c.name, "tags": list(c.tags)} for c in entries]
                for command_type, entries in commands.commands.items()
            },
            "history": [dict(h) for h in settings.command_history],
            "serial": {
                "connected": self.serial.is_connected(),
                "port": settings.com_port,
                "format": settings.serial_data_format_name,
            },
            "camera": {
                "opened": self.camera.image_bgr is not None,
                "capture_size": list(self.camera.capture_size),
                "source": self.capture_window or f"Camera {settings.camera_id}",
            },
            "input": {
                "keyboard_enabled": bool(settings.is_use_keyboard),
                "keyboard_active": self.keyboard is not None,
                "controller_active": self.is_controller_active,
                "recording": self.record.is_recording(),
                "touchscreen": self.has_touchscreen,
                "touchscreen_ratio": self.touchscreen_ratio(),
            },
            "stdout_destination": Command.stdout_destination,
            "settings": {"values": self.settings_control.values(), "options": self.settings_control.options()},
            "softcon": {"layout": self.softcon.layout, "layouts": layout_names()},
            "simulator": {"layout": self.simulator.layout, "layouts": layout_names(large=True)},
            "shortcuts": self.editor.shortcuts(),
            "masks": self.editor.masks_state(),
            "touchscreen_area": self.editor.touchscreen_area(),
            "colors": self.editor.colors_state(),
            "line_token_set": self.editor.line_token_is_set(),
            "tools": self.tools.state(),
            "status": self.status(),
        }

    def status(self) -> dict:
        """
        Status の欄に表示する文字(今つながっている機器と、実行中のコマンド。行の名前 -> 文字)。
        ウィンドウの画面(tkinter 版)の Status タブと、同じ文字にする(services/status_text.py)
        """
        settings = self.settings
        control = self.settings_control
        commands = self.commands
        # カメラ: 取り込んでいるウィンドウの名前、または「No.番号: 名前」(名前が分からなければ、番号だけ)
        names = control.camera_names or {}
        camera_id = settings.camera_id
        name = names.get(camera_id, names.get(str(camera_id)))
        camera = self.capture_window or (f"No.{camera_id}: {name}" if name else f"Camera {camera_id}")
        width, height = self.camera.capture_size
        audio = self.audio
        running = commands.is_running and commands.current is not None
        return {
            "camera": status_text.camera_text(camera, f"{width}x{height}", self.camera.image_bgr is not None),
            "audio_input": status_text.audio_input_text(
                audio.label(settings.audio_device) if settings.audio_device else "", audio.is_running, audio.available
            ),
            "audio_output": status_text.audio_output_text(
                settings.audio_output_device or OUTPUT_DEFAULT, audio.is_running, bool(settings.is_audio_playback), audio.available
            ),
            "serial": status_text.serial_text(
                SerialService.find_description(control.ports, settings.com_port) or "", settings.com_port, settings.baud_rate,
                self._serial_opened(),
            ),
            "command": status_text.command_text(getattr(commands.current, "NAME", "") if running else None),
            "started": status_text.started_text(
                getattr(commands.current, "NAME", "") if running else None, getattr(commands, "started_at", None) if running else None
            ),
        }

    def _serial_opened(self) -> bool:
        """ポートを開いているか(Sender.isOpened と同じ判定。何度も呼ぶので、ログを出さない)"""
        port = getattr(self.sender, "ser", None)
        return bool(port is not None and port.isOpen())
