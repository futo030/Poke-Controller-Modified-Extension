#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音声の取り込みと再生の管理(設定の反映、デバイスの一覧)

画面(tkinter)には触れない。取り込みと再生そのものは Audio.py の AudioCapture が行う。
"""
from __future__ import annotations

from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING

from Audio import AUDIO_AVAILABLE, AudioCapture, AudioError
from services import device_service

if TYPE_CHECKING:
    from services.settings_store import AppSettings

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 既定の再生デバイスを表す名前(設定ファイルでは空文字で保存する)
OUTPUT_DEFAULT = "Default"
# 音量メーター: 音量を測る長さ(秒)、メーターの下限(dB)、音声が届いていないとみなすまでの時間(秒)
METER_SECONDS = 0.1
METER_MIN_DB = -60.0
NO_SIGNAL_SECONDS = 1.0


class AudioService:
    """音声の取り込み・再生・音量を設定に合わせ、入力と再生のデバイスの一覧を持つ"""

    def __init__(self, settings: AppSettings, capture: AudioCapture | None = None):
        """
        settings: 設定(is_use_audio / audio_device / is_audio_playback / audio_output_device / audio_volume を読み書きする)
        capture: 取り込みに使う AudioCapture(省略した場合は、使える環境なら作る。使えない環境では None のまま)
        """
        self.settings = settings
        if capture is None and AUDIO_AVAILABLE:
            capture = AudioCapture()
        self.capture = capture
        # 入力デバイスの名前(カメラと同じ機器の番号順)と、名前 -> 同じ機器のカメラの番号
        self.inputs = []
        self.numbers = {}
        self.outputs = []

    @property
    def available(self) -> bool:
        """音声を使える環境か(必要なライブラリがあるか)"""
        return self.capture is not None

    @property
    def is_running(self) -> bool:
        """取り込み中か"""
        return self.capture is not None and self.capture.is_running

    def label(self, name: str) -> str:
        """入力デバイスの、一覧に表示する名前(同じ機器のカメラの番号を付ける)"""
        return device_service.audio_label(name, self.numbers)

    def refresh(self, camera_paths: dict) -> bool:
        """
        デバイスの一覧を更新する(接続・切断の反映は、取り込みを止めている間のみ行う)。更新できたかを返す
        camera_paths: カメラの番号 -> デバイスパス(同じ機器の音声デバイスを探すのに使う)
        """
        if self.capture is None:
            return False
        try:
            self.inputs, self.numbers = device_service.list_audio_inputs(camera_paths, refresh=not self.capture.is_running)
            self.outputs = device_service.list_audio_outputs(refresh=False)
        except Exception as e:
            _logger.error(f"Failed to list audio devices: {e}")
            print(f"音声デバイスの一覧を取得できませんでした: {e}")
            return False
        return True

    def output_name(self) -> str:
        """
        選択中の再生デバイスの名前(既定の再生デバイスの場合は空文字)
        """
        name = self.settings.audio_output_device
        return "" if name == OUTPUT_DEFAULT else name

    def apply(self, camera_paths: dict, camera_id: int) -> None:
        """
        Use Audio のオン・オフと入力デバイスの選択を反映する(取り込み中の場合は、一度止めて取り込み直す)
        camera_paths: カメラの番号 -> デバイスパス、camera_id: 選択中のカメラの番号
        取り込みを始められない場合は、理由を表示して Use Audio をオフにする
        """
        if self.capture is None:
            return
        settings = self.settings
        self.stop()
        if not settings.is_use_audio:
            self.refresh(camera_paths)
            return
        self.refresh(camera_paths)
        # 入力デバイスが未選択(または見つからない)場合、選択中のカメラと同じ機器のデバイス(なければ先頭)を選ぶ
        default = device_service.default_audio_input(self.inputs, self.numbers, settings.audio_device, camera_id)
        if default is not None:
            settings.audio_device = default
        try:
            self.capture.start(settings.audio_device)
            self.capture.set_volume(min(max(settings.audio_volume, 0), 100) / 100)
        except AudioError as e:
            print(f"Audio: {e}")
            _logger.error(f"Audio: {e}")
            self.stop()
            settings.is_use_audio = False
            return
        # 再生を始める(再生デバイスを開けない場合は、取り込みは続けて Playback だけオフにする)
        self.capture.output_device_name = self.output_name()
        self.apply_playback()
        print(
            f"Audio: {self.label(self.capture.device_name)}"
            f" ({self.capture.samplerate} Hz, {self.capture.channels} ch) の取り込みを開始しました"
        )

    def stop(self) -> None:
        """取り込みと再生を止める"""
        if self.capture is not None:
            self.capture.stop()

    def apply_playback(self) -> None:
        """Playback のオン・オフを反映する(取り込み中のみ。再生デバイスを開けない場合は Playback をオフにする)"""
        if not self.is_running:
            return
        try:
            self.capture.set_playback(self.settings.is_audio_playback)
        except AudioError as e:
            print(f"Audio: {e}")
            _logger.error(f"Audio: {e}")
            self.settings.is_audio_playback = False

    def apply_output_device(self) -> None:
        """
        再生デバイスの選択を反映する(再生中の場合は、新しいデバイスで再生し直す)
        """
        if self.capture is None:
            return
        try:
            self.capture.set_output_device(self.output_name())
        except AudioError as e:
            print(f"Audio: {e}")
            _logger.error(f"Audio: {e}")
            self.settings.is_audio_playback = False
            return
        if self.capture.is_playing:
            print(f"Audio: 再生デバイスを {self.settings.audio_output_device or OUTPUT_DEFAULT} に変更しました")

    def meter(self) -> dict | None:
        """
        音量メーターの値: {"percent": 0～100, "text": 表示する文字}。取り込んでいない場合は None。
        取り込みが止まっていた場合の値には、"stopped": True が付く。
        デバイスが外れた等で取り込みが止まっていた場合は、取り込みをやめて Use Audio をオフにする
        """
        import time

        capture = self.capture
        if capture is None or not capture.is_running:
            return None
        if capture.error is not None:
            print(f"Audio: {capture.error}")
            _logger.error(f"Audio: {capture.error}")
            self.stop()
            self.settings.is_use_audio = False
            return {"percent": 0, "text": "", "stopped": True}
        if time.perf_counter() - capture.last_input_time > NO_SIGNAL_SECONDS:
            # ストリームは開いているが、音声が届いていない
            return {"percent": 0, "text": "No signal"}
        db = capture.get_volume(METER_SECONDS)
        percent = min(max((db - METER_MIN_DB) / -METER_MIN_DB * 100, 0), 100)
        return {"percent": round(percent, 1), "text": f"{db:.0f} dB"}

    def apply_volume(self) -> None:
        """設定の音量(0～100)を、再生の音量に反映する"""
        if self.capture is not None:
            self.capture.set_volume(min(max(self.settings.audio_volume, 0), 100) / 100)
