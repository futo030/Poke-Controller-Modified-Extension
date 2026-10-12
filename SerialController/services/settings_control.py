#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定の変更(カメラ・シリアル・音声・通知・表示)と、選べる候補の一覧

画面(tkinter)には触れない。画面は、候補(options)と今の値(values)を表示し、変更を apply() で頼む。
"""
from __future__ import annotations

import platform
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any, Container

from Camera import CAPTURE_SIZE_LIST, EXTRA_SOURCES
from Commands.CommandBase import Command
from Commands.ControllerProfile import AUTO_DEVICE, device_label, list_joystick_names
from Commands.transport import transport_names
from services import device_service
from services.audio_service import OUTPUT_DEFAULT
from services.serial_service import port_number
from services.settings_store import NOTIFICATION_FIELDS

if TYPE_CHECKING:
    from services.app_core import AppCore

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

FPS_LIST = ("60", "45", "30", "15", "5")
BAUD_RATES = (9600, 4800, 115200)
PREVIEW_GAIN_RANGE = (50, 300)
PREVIEW_GAMMA_RANGE = (0.5, 2.5)
DIALOGUE_BUTTON_POSITIONS = ("1", "2", "3")
# 通知の設定の名前 -> コマンドに知らせる変数の名前
NOTIFICATION_FLAGS = {
    "is_win_notification_start": "isWinNotStart",
    "is_win_notification_end": "isWinNotEnd",
    "is_line_notification_start": "isLineNotStart",
    "is_line_notification_end": "isLineNotEnd",
    "is_discord_notification_start": "isDiscordNotStart",
    "is_discord_notification_end": "isDiscordNotEnd",
}
# 画面に渡す、今の値の項目
VALUE_NAMES = (
    "camera_id", "capture_size", "fps", "is_use_mjpg", "is_show_windows", "preview_gain", "preview_gamma",
    "is_show_realtime", "controller_device",
    "com_port", "baud_rate", "serial_data_format_name", "is_show_serial",
    "is_use_audio", "audio_device", "is_audio_playback", "audio_output_device", "audio_volume",
    "is_show_value", "is_show_guide", "stdout_destination", "pos_dialogue_buttons", "software_controller_layout",
    "controller_layout",
) + tuple(NOTIFICATION_FIELDS)


class SettingError(Exception):
    """設定を変更できない(メッセージは、そのまま表示できる文)"""


def serial_formats() -> list:
    """
    選べるデータの形式(送信方式の登録簿にあるもののうち、この環境で使えるもの。
    例: FTDI 直結の基板用の形式は、ftd2xx が使える場合のみ)
    """
    return transport_names()


def clamp(value: float, low: float, high: float) -> float:
    """value を、low 以上 high 以下に収める"""
    return min(max(value, low), high)


class SettingsControl:
    """
    設定の変更を受けて反映・保存し、選べる候補(カメラ・ポート・音声デバイスなど)の一覧を持つ。
    設定の値は、画面(JSON など)から届くので、型を決めずに受け取り(Any)、設定ごとの型に変えてから使う
    """

    def __init__(self, core: AppCore):
        """
        core: アプリ本体(AppCore)
        """
        self.core = core
        # カメラの番号 -> 表示する名前(名前を取得できない環境・取得に失敗した場合は None)
        self.camera_names = None
        # カメラの番号 -> デバイスパス(音声入力がどのカメラと同じ機器かを調べるために使う)
        self.camera_paths = {}
        # カメラの一覧に並べた、追加の映像ソース(ウィンドウなど)の番号 -> 識別名
        self.source_ids = {}
        self.ports = []
        # 接続中のコントローラーの名前(番号順。調べるのに1秒ほどかかるので、頼まれたときだけ調べる)
        self.controller_names = []

    # ---------------------------------------------------------------- 一覧

    def scan(self, announce: bool = True) -> None:
        """
        カメラ・シリアルポート・音声デバイスの一覧を取得し直す。
        選択中のカメラは、同じ機器が一覧にあればそのまま選び直す(番号が変わった場合は、新しい番号にする)
        announce: 見つかった台数を、出力画面に表示するか
        """
        core = self.core
        settings = core.settings
        old_names = self.camera_names
        old_name = old_names.get(settings.camera_id) if old_names and not core.capture_window else None
        try:
            listed = device_service.list_cameras()
        except Exception as e:
            listed = None
            print(f"カメラの一覧を取得できませんでした: {e}")
            _logger.warning(f"Failed to scan camera devices: {e}")
        if listed is not None:
            self.camera_names, paths = listed
            if paths is not None:
                self.camera_paths = paths
            self.source_ids = {}
            self._update_sources()
            cameras = {k: v for k, v in self.camera_names.items() if k not in self.source_ids and v != device_service.DISABLE}
            if old_name is not None and old_name != self.camera_names.get(settings.camera_id):
                # 選んでいたカメラの番号が変わった(または無くなった)
                new_ids = [k for k, v in cameras.items() if v == old_name]
                if new_ids:
                    print(f"選択中のカメラの番号が No.{settings.camera_id} から No.{new_ids[0]} に変わりました。")
                    settings.camera_id = new_ids[0]
                else:
                    print("選択中のカメラが一覧にありません。Device を選び直してください。")
            if announce:
                print(f"Scan Device: カメラ {len(cameras)} 台")
        self.scan_ports()
        audio = core.audio
        if audio.available:
            if settings.is_use_audio and audio.is_running:
                # デバイスの一覧は取り込みを止めている間しか更新できないので、一度止めて取り込み直す
                audio.apply(self.camera_paths, settings.camera_id)
            else:
                audio.refresh(self.camera_paths)
            if announce:
                print(f"Scan Device: 音声入力 {len(audio.inputs)} 台")

    def scan_controllers(self) -> None:
        """
        接続中のコントローラーを調べ直す(1秒ほどかかる)
        """
        try:
            self.controller_names = list_joystick_names()
        except Exception as e:
            _logger.error(f"Failed to list controllers: {e}")
            print(f"接続中のコントローラーを取得できませんでした: {e}")
            self.controller_names = []
        print(f"Scan Device: コントローラー {len(self.controller_names)} 台")

    def scan_ports(self) -> None:
        """シリアルポートの一覧を取得し直す(取得できない場合は、空にする)"""
        try:
            self.ports = self.core.serial.list_port_descriptions()
        except Exception as e:
            _logger.warning(f"An error occurred when checking serial device list. {e}")
            self.ports = []

    def _update_sources(self) -> None:
        """
        カメラの一覧のうち、追加の映像ソース(取り込めるウィンドウなど)を作り直す
        """
        if self.camera_names is None:
            return
        core = self.core
        show_windows = bool(core.settings.is_show_windows) and platform.system() == "Windows"
        labels = device_service.extra_source_labels(show_windows, core.capture_window)
        self.source_ids = device_service.replace_extra_sources(self.camera_names, self.source_ids, labels)

    def selected_camera(self) -> int:
        """
        一覧の中で、今選んでいる項目の番号(ウィンドウなどを取り込んでいる場合は、その項目の番号)
        """
        window = self.core.capture_window
        if window:
            for source_id, key in self.source_ids.items():
                if key == window:
                    return source_id
        return self.core.settings.camera_id

    def options(self) -> dict:
        """
        選べる候補(JSON にできる値だけ)
        """
        audio = self.core.audio
        cameras = None
        if self.camera_names is not None:
            cameras = [{"id": int(key), "label": f"No.{key}: {name}"} for key, name in self.camera_names.items()]
        ports = []
        for description in self.ports:
            try:
                ports.append({"number": port_number(description), "label": description})
            except (AttributeError, ValueError):
                continue
        return {
            "cameras": cameras,
            "windows_supported": platform.system() == "Windows",
            "capture_sizes": list(CAPTURE_SIZE_LIST),
            "fps": list(FPS_LIST),
            "preview_gain_range": list(PREVIEW_GAIN_RANGE),
            "preview_gamma_range": list(PREVIEW_GAMMA_RANGE),
            "ports": ports,
            "baud_rates": list(BAUD_RATES),
            "formats": serial_formats(),
            "audio_available": audio.available,
            "audio_inputs": [{"name": name, "label": audio.label(name)} for name in audio.inputs],
            "audio_outputs": [OUTPUT_DEFAULT] + list(audio.outputs),
            "dialogue_button_positions": list(DIALOGUE_BUTTON_POSITIONS),
            "controller_devices": [AUTO_DEVICE] + [device_label(i, name) for i, name in enumerate(self.controller_names)],
        }

    def values(self) -> dict:
        """今の設定の値(VALUE_NAMES の項目と、選んでいる映像の番号・音声の取り込み中か。JSON にできる値だけ)"""
        settings = self.core.settings
        values = {name: getattr(settings, name) for name in VALUE_NAMES}
        values["camera_source"] = self.selected_camera()
        values["audio_output_device"] = settings.audio_output_device or OUTPUT_DEFAULT
        values["audio_running"] = self.core.audio.is_running
        return values

    # ---------------------------------------------------------------- 変更

    def apply(self, name: str, value: Any) -> None:
        """
        設定を1つ変更して反映し、設定ファイルに保存する。変更できない場合は SettingError
        name: 設定の名前(_set_名前 のメソッドがあるものと、NOTIFICATION_FLAGS にあるもの)
        value: 新しい値(設定ごとの型に変えて使う。変えられない値は、ValueError / TypeError になることがある)
        """
        handler = getattr(self, f"_set_{name}", None)
        if handler is None:
            if name in NOTIFICATION_FLAGS:
                handler = lambda v: self._set_notification(name, v)  # noqa: E731
            else:
                raise SettingError(f"変更できない設定です: {name}")
        handler(value)
        self.core.settings.save()
        self.core._notify("settings")

    @staticmethod
    def _choice(value: Any, choices: Container, label: str) -> Any:
        """value が choices にあれば、そのまま返す。無ければ SettingError(label: メッセージに出す設定の名前)"""
        if value not in choices:
            raise SettingError(f"{label} に指定できない値です: {value}")
        return value

    # カメラ

    def _set_camera_source(self, value: Any) -> None:
        """映像の入力元を、一覧の番号で選んで、カメラを開き直す(カメラ、またはウィンドウなどの映像ソース)"""
        core = self.core
        source_id = int(value)
        if self.camera_names is not None and source_id not in [int(key) for key in self.camera_names]:
            raise SettingError(f"Device に指定できない値です: {value}")
        key = self.source_ids.get(source_id, "")
        core.settings.camera_id = source_id
        core.settings.capture_window = key
        core.open_camera()

    def _set_capture_size(self, value: Any) -> None:
        """取り込む大きさ("幅x高さ")を変える(変わった場合は、カメラを開き直す)"""
        core = self.core
        size = self._choice(str(value), CAPTURE_SIZE_LIST, "Size")
        core.settings.capture_size = size
        if size != "{0}x{1}".format(*core.camera.capture_size):
            core.camera.capture_size = tuple(map(int, size.split("x")))
            print(f"Changed capture size to: {size}")
            core.open_camera()

    def _set_fps(self, value: Any) -> None:
        """FPS を変える(MJPG を使っている場合は、カメラを開き直す)"""
        core = self.core
        core.settings.fps = self._choice(str(value), FPS_LIST, "FPS")
        print("changed FPS to: " + core.settings.fps + " [fps]")
        core.camera.fps = int(core.settings.fps)
        if core.settings.is_use_mjpg:
            # MJPGではカメラに要求するフレームレートにもFPSを使うので、カメラを開き直して反映する
            core.open_camera()

    def _set_is_use_mjpg(self, value: Any) -> None:
        """MJPG を使うかを変えて、カメラを開き直す"""
        self.core.settings.is_use_mjpg = bool(value)
        self.core.open_camera()

    def _set_is_show_windows(self, value: Any) -> None:
        """取り込めるウィンドウを、カメラの一覧に並べるかを変える"""
        core = self.core
        core.settings.is_show_windows = bool(value)
        if not value and core.capture_window and core.capture_window not in EXTRA_SOURCES:
            # ウィンドウを取り込んでいる間にチェックを外した場合は、カメラ(No.0)に戻して開き直す
            core.settings.capture_window = ""
            core.settings.camera_id = 0
            core.open_camera()
        self._update_sources()

    def _set_is_show_realtime(self, value: Any) -> None:
        """プレビューの画像を、リアルタイムで更新するか(オフの間は静止画のまま)を変える"""
        self.core.settings.is_show_realtime = bool(value)

    def _set_controller_device(self, value: Any) -> None:
        """操作に使うコントローラーを選ぶ(空文字と、改行を含む名前は SettingError)"""
        # 選択中のコントローラーが外れていても選択は残せるよう、一覧に無い名前も受け付ける(開始時に見つからなければエラーになる)
        value = str(value).strip()
        if value == "" or any(character in value for character in "\r\n"):
            raise SettingError(f"Device に指定できない値です: {value}")
        self.core.settings.controller_device = value

    def _set_preview_gain(self, value: Any) -> None:
        """プレビューの明るさ(%)を変える(PREVIEW_GAIN_RANGE に収める)"""
        self.core.settings.preview_gain = int(clamp(int(value), *PREVIEW_GAIN_RANGE))

    def _set_preview_gamma(self, value: Any) -> None:
        """プレビューのガンマを変える(PREVIEW_GAMMA_RANGE に収め、小数第 2 位に丸める)"""
        self.core.settings.preview_gamma = round(float(clamp(float(value), *PREVIEW_GAMMA_RANGE)), 2)

    # シリアル

    def _set_com_port(self, value: Any) -> None:
        """COM ポートの番号を変える(接続はし直さない。負の値は SettingError)"""
        port = int(value)
        if port < 0:
            raise SettingError(f"COM Port に指定できない値です: {value}")
        self.core.settings.com_port = port

    def _set_baud_rate(self, value: Any) -> None:
        """ボーレートを変える(BAUD_RATES にある値だけ。接続はし直さない)"""
        self.core.settings.baud_rate = self._choice(int(value), BAUD_RATES, "Baud Rate")

    def _set_serial_data_format_name(self, value: Any) -> None:
        """送るデータの形式を変えて、接続し直す"""
        # 送るデータの形式を変えたら、その形式で決まるボーレートに合わせて接続し直す
        self.core.settings.serial_data_format_name = self._choice(str(value), serial_formats(), "Format")
        self.core.connect_serial()

    def _set_is_show_serial(self, value: Any) -> None:
        """送ったデータを、出力画面に表示するかを変える"""
        self.core.settings.is_show_serial = bool(value)
        self.core.sender.set_show_serial(bool(value))

    # 音声

    def _set_is_use_audio(self, value: Any) -> None:
        """音声を取り込むかを変える(音声を使えない環境でオンにすると SettingError)"""
        core = self.core
        if value and not core.audio.available:
            raise SettingError("音声を使えません。(sounddevice を読み込めません)")
        core.settings.is_use_audio = bool(value)
        core.audio.apply(self.camera_paths, core.settings.camera_id)

    def _set_audio_device(self, value: Any) -> None:
        """音声の入力デバイスを選ぶ(取り込み中の場合は、取り込み直す)"""
        core = self.core
        core.settings.audio_device = self._choice(str(value), core.audio.inputs, "Input")
        if core.settings.is_use_audio:
            core.audio.apply(self.camera_paths, core.settings.camera_id)

    def _set_is_audio_playback(self, value: Any) -> None:
        """取り込んだ音声を再生するかを変える"""
        self.core.settings.is_audio_playback = bool(value)
        self.core.audio.apply_playback()

    def _set_audio_output_device(self, value: Any) -> None:
        """音声の再生デバイスを選ぶ(OUTPUT_DEFAULT は、既定の再生デバイス)"""
        core = self.core
        name = self._choice(str(value), [OUTPUT_DEFAULT] + list(core.audio.outputs), "Output")
        core.settings.audio_output_device = "" if name == OUTPUT_DEFAULT else name
        core.audio.apply_output_device()

    def _set_audio_volume(self, value: Any) -> None:
        """再生の音量を変える(0～100 に収める)"""
        self.core.settings.audio_volume = int(clamp(int(value), 0, 100))
        self.core.audio.apply_volume()

    # 通知・表示

    def _set_notification(self, name: str, value: Any) -> None:
        """通知の設定(NOTIFICATION_FLAGS のどれか)のオン・オフを変えて、コマンドにも知らせる"""
        setattr(self.core.settings, name, bool(value))
        setattr(Command, NOTIFICATION_FLAGS[name], bool(value))

    def _set_is_show_value(self, value: Any) -> None:
        """テンプレートマッチングの類似度を、コマンドの指定によらず出力するかを変える"""
        self.core.settings.is_show_value = bool(value)
        Command.isSimilarity = bool(value)

    def _set_is_show_guide(self, value: Any) -> None:
        """画像認識のガイド表示(認識した位置の表示)を有効にするかを変える"""
        self.core.settings.is_show_guide = bool(value)
        Command.isGuide = bool(value)

    def _set_stdout_destination(self, value: Any) -> None:
        """標準出力(print)の出力先の出力画面("1" / "2")を変える"""
        destination = self._choice(str(value), ("1", "2"), "Stdout")
        self.core.settings.stdout_destination = destination
        self.core.output.redirect_stdout(int(destination))
        Command.stdout_destination = destination
        print("standard output destination is switched.")

    def _set_software_controller_layout(self, value: Any) -> None:
        """Software-Controller のレイアウトを変える"""
        from services.software_controller import layout_names

        self.core.set_softcon_layout(self._choice(str(value), layout_names(), "Layout"))

    def _set_controller_layout(self, value: Any) -> None:
        """Controller Simulator のレイアウトを変える"""
        from services.software_controller import layout_names

        self.core.set_simulator_layout(self._choice(str(value), layout_names(large=True), "Layout"))

    def _set_pos_dialogue_buttons(self, value: Any) -> None:
        """ダイアログのボタンの位置(DIALOGUE_BUTTON_POSITIONS のどれか)を変える"""
        position = self._choice(str(value), DIALOGUE_BUTTON_POSITIONS, "Dialogue Buttons")
        self.core.settings.pos_dialogue_buttons = position
        Command.pos_dialogue_buttons = position
