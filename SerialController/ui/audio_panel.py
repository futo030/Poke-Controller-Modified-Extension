#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio タブ: 音声の取り込みと再生
"""
from __future__ import annotations

import tkinter as tk
import time
import tkinter.ttk as ttk
from Audio import (
    AUDIO_AVAILABLE,
    AudioCapture,
    AudioError,
)
from services import device_service
from ui.constants import (
    AUDIO_OUTPUT_DEFAULT,
    AUDIO_METER_INTERVAL_MS,
    AUDIO_METER_MIN_DB,
    AUDIO_NO_SIGNAL_SECONDS,
)


class AudioPanelMixin:
    """
    Audio タブ: 音声の取り込みと再生
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildAudioTab(self) -> None:
        """
        Audio タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        # Audioタブ: キャプチャーボード等の音声の取り込みと再生(sounddeviceが使える場合のみ表示する)
        self.audio = AudioCapture() if AUDIO_AVAILABLE else None
        self.audio_meter_after = None
        self.audio_f = ttk.Frame(self.controller_nb)
        # Input(取り込み。Levelは取り込んでいる音量) と Output(再生。Volumeは再生の音量) を左右に分ける
        self.audio_f.columnconfigure(0, weight=1, uniform="audio")
        self.audio_f.columnconfigure(1, weight=1, uniform="audio")
        self.audio_input_lf = ttk.Labelframe(self.audio_f)
        self.is_use_audio = tk.BooleanVar(value=False)
        self.use_audio_checkbox = ttk.Checkbutton(self.audio_input_lf)
        self.use_audio_checkbox.configure(text="Use Audio", variable=self.is_use_audio, command=self.applyAudio)
        self.use_audio_checkbox.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        # 選択中のデバイス名(設定に保存する)。コンボボックスには、同じ機器のカメラの番号を付けて表示する
        # (「No.1: 名前」。対応するカメラが無い、音声のみのデバイスは「No.x: 名前」)
        self.audio_device = tk.StringVar(value="")
        self.audio_device_display = tk.StringVar(value="")
        self.audio_device_labels = {}
        self.audio_device_numbers = {}
        self.audio_device_cb = ttk.Combobox(self.audio_input_lf)
        self.audio_device_cb.configure(
            state="readonly", textvariable=self.audio_device_display, width="20", postcommand=self.refreshAudioDevices
        )
        self.audio_device_cb.grid(column="0", padx="8", pady="4", row="1", sticky="ew")
        self.audio_device_cb.bind("<<ComboboxSelected>>", self.onAudioDeviceSelected)
        # 取り込んでいる音声の音量(再生をオフにしていても、取り込めていることを確認できる)
        self.audio_meter_f = ttk.Frame(self.audio_input_lf)
        self.audio_meter_label = ttk.Label(self.audio_meter_f)
        self.audio_meter_label.configure(text="Level:")
        self.audio_meter_label.pack(side="left", padx=(0, 4))
        self.audio_status_label = ttk.Label(self.audio_meter_f)
        self.audio_status_label.configure(text="", width="9")
        self.audio_status_label.pack(side="right", padx=(4, 0))
        self.audio_meter = ttk.Progressbar(self.audio_meter_f)
        self.audio_meter.configure(orient="horizontal", length=120, maximum=100, mode="determinate")
        self.audio_meter.pack(side="left", expand="true", fill="x")
        self.audio_meter_f.grid(column="0", padx="8", pady="4", row="2", sticky="ew")
        self.audio_input_lf.columnconfigure(0, weight=1)
        self.audio_input_lf.configure(text="Input")
        self.audio_input_lf.grid(column="0", padx="5", pady="3", row="0", sticky="nsew")

        self.audio_output_lf = ttk.Labelframe(self.audio_f)
        self.is_audio_playback = tk.BooleanVar(value=True)
        self.audio_playback_checkbox = ttk.Checkbutton(self.audio_output_lf)
        self.audio_playback_checkbox.configure(
            text="Playback", variable=self.is_audio_playback, command=self.applyAudioPlayback
        )
        self.audio_playback_checkbox.grid(column="0", columnspan="3", padx=(8, 4), pady="4", row="0", sticky="w")
        # 再生するデバイス(Defaultは既定の再生デバイス)
        self.audio_output_device = tk.StringVar(value=AUDIO_OUTPUT_DEFAULT)
        self.audio_output_cb = ttk.Combobox(self.audio_output_lf)
        self.audio_output_cb.configure(
            state="readonly",
            textvariable=self.audio_output_device,
            values=[AUDIO_OUTPUT_DEFAULT],
            width="20",
            postcommand=self.refreshAudioOutputDevices,
        )
        self.audio_output_cb.grid(column="0", columnspan="3", padx="8", pady="4", row="1", sticky="ew")
        self.audio_output_cb.bind("<<ComboboxSelected>>", self.applyAudioOutputDevice)
        self.audio_volume_label = ttk.Label(self.audio_output_lf)
        self.audio_volume_label.configure(text="Volume:")
        self.audio_volume_label.grid(column="0", padx=(8, 4), pady="4", row="2", sticky="w")
        self.audio_volume = tk.IntVar(value=100)
        self.audio_volume_scale = ttk.Scale(self.audio_output_lf)
        self.audio_volume_scale.configure(
            from_=0, to=100, orient="horizontal", length=120, command=self.applyAudioVolume
        )
        self.audio_volume_scale.grid(column="1", padx="4", pady="4", row="2", sticky="ew")
        self.audio_volume_value_label = ttk.Label(self.audio_output_lf)
        self.audio_volume_value_label.configure(text="100%", width="5")
        self.audio_volume_value_label.grid(column="2", padx=(0, 8), pady="4", row="2", sticky="w")
        self.audio_output_lf.columnconfigure(1, weight=1)
        self.audio_output_lf.configure(text="Output")
        self.audio_output_lf.grid(column="1", padx="5", pady="3", row="0", sticky="nsew")
        # sounddeviceが無い場合はタブに追加しない(ウィジェットは作るが、どこにも配置しない)
        if AUDIO_AVAILABLE:
            self.controller_nb.add(self.audio_f, padding="5", sticky="nsew", text="Audio")

    ############### 音声 ###############
    def initAudio(self) -> None:
        """
        起動時: 入力デバイスの一覧を表示し、前回オンだった場合は取り込みを始める
        """
        self.refreshAudioOutputDevices()
        if self.is_use_audio.get():
            self.applyAudio()
        else:
            self.refreshAudioDevices()

    def _audioDeviceLabel(self, name: str) -> str:
        """
        コンボボックスに表示する名前(同じ機器のカメラの番号を付ける。音声のみのデバイスは x)
        """
        return device_service.audio_label(name, self.audio_device_numbers)

    def refreshAudioDevices(self) -> None:
        """
        音声入力デバイスの一覧を更新する(接続・切断の反映は、取り込みを止めている間のみ行う)
        """
        if self.audio is None:
            return
        try:
            names, numbers = device_service.list_audio_inputs(self.camera_paths, refresh=not self.audio.is_running)
        except Exception as e:
            self._logger.error(f"Failed to list audio devices: {e}")
            print(f"音声入力デバイスの一覧を取得できませんでした: {e}")
            return
        # カメラと同じ機器のデバイスを番号順に並べ、音声のみのデバイスはその後ろに置く
        self.audio_device_numbers = numbers
        self.audio_device_labels = {self._audioDeviceLabel(n): n for n in names}
        self.audio_device_cb["values"] = list(self.audio_device_labels)
        self._updateAudioDeviceDisplay()

    def _updateAudioDeviceDisplay(self) -> None:
        """選択中の入力デバイスを、コンボボックスに表示する名前(番号付き)に直して表示する"""
        name = self.audio_device.get()
        self.audio_device_display.set(self._audioDeviceLabel(name) if name else "")

    def onAudioDeviceSelected(self, *event: tk.Event) -> None:
        """入力デバイスを選んだとき: 表示名から元のデバイス名を求めて選択中にし、取り込みに反映する"""
        name = self.audio_device_labels.get(self.audio_device_display.get())
        if name is not None:
            self.audio_device.set(name)
        self.applyAudio()

    def _selectDefaultAudioDevice(self) -> None:
        """
        入力デバイスが未選択(または見つからない)場合、選択中のカメラと同じ機器のデバイス(なければ先頭)を選ぶ
        """
        name = device_service.default_audio_input(
            list(self.audio_device_labels.values()), self.audio_device_numbers, self.audio_device.get(), self.camera_id.get()
        )
        if name is None:
            return
        self.audio_device.set(name)
        self._updateAudioDeviceDisplay()

    def applyAudio(self, *event: tk.Event) -> None:
        """
        Use Audioのオン・オフと入力デバイスの選択を反映する
        (オンなら取り込みを始め、開けなかった場合はオフに戻す。オフなら止める)
        event: 使わない(今の呼び出し元は、すべて引数なしで呼ぶ)
        """
        if self.audio is None:
            return
        self.audio_device_cb.selection_clear()
        if not self.is_use_audio.get():
            self.stopAudio()
            return
        # デバイスを切り替える場合に備えて、一度止めてから一覧を更新する
        self.stopAudio()
        self.refreshAudioDevices()
        self._selectDefaultAudioDevice()
        try:
            self.audio.start(self.audio_device.get())
            self.audio.set_volume(self.audio_volume.get() / 100)
        except AudioError as e:
            print(f"Audio: {e}")
            self._logger.error(f"Audio: {e}")
            self.stopAudio()
            self.is_use_audio.set(False)
            return
        # 再生を始める(再生デバイスを開けない場合は、取り込みは続けてPlaybackだけオフにする)
        self.audio.output_device_name = self._audioOutputDeviceName()
        self.applyAudioPlayback()
        print(
            f"Audio: {self._audioDeviceLabel(self.audio.device_name)}"
            f" ({self.audio.samplerate} Hz, {self.audio.channels} ch) の取り込みを開始しました"
        )
        self._updateAudioMeter()

    def stopAudio(self) -> None:
        """音声の取り込みと再生を止め、音量メーターの表示を消す(Use Audio をオフにしたとき、終了時など)"""
        if self.audio is None:
            return
        if self.audio_meter_after is not None:
            self.root.after_cancel(self.audio_meter_after)
            self.audio_meter_after = None
        self.audio.stop()
        self.audio_meter["value"] = 0
        self.audio_status_label["text"] = ""

    def applyAudioPlayback(self) -> None:
        """Playback のチェックを切り替えたとき: 取り込み中であれば、再生のオン・オフを反映する(再生できない場合はオフに戻す)"""
        if self.audio is None or not self.audio.is_running:
            return
        try:
            self.audio.set_playback(self.is_audio_playback.get())
        except AudioError as e:
            print(f"Audio: {e}")
            self._logger.error(f"Audio: {e}")
            self.is_audio_playback.set(False)

    def _audioOutputDeviceName(self) -> str:
        """
        選択中の再生デバイスの名前(既定の再生デバイスの場合は空文字)
        """
        name = self.audio_output_device.get()
        return "" if name == AUDIO_OUTPUT_DEFAULT else name

    def refreshAudioOutputDevices(self) -> None:
        """
        音声出力デバイスの一覧を更新する(接続・切断の反映は、取り込みを止めている間のみ行う)
        """
        if self.audio is None:
            return
        try:
            outputs = device_service.list_audio_outputs(refresh=not self.audio.is_running)
            self.audio_output_cb["values"] = [AUDIO_OUTPUT_DEFAULT] + outputs
        except Exception as e:
            self._logger.error(f"Failed to list audio output devices: {e}")
            print(f"音声出力デバイスの一覧を取得できませんでした: {e}")

    def applyAudioOutputDevice(self, *event: tk.Event) -> None:
        """
        Outputの選択を反映する(再生中の場合は、新しいデバイスで再生し直す)
        """
        self.audio_output_cb.selection_clear()
        if self.audio is None:
            return
        try:
            self.audio.set_output_device(self._audioOutputDeviceName())
        except AudioError as e:
            print(f"Audio: {e}")
            self._logger.error(f"Audio: {e}")
            self.is_audio_playback.set(False)
            return
        if self.audio.is_playing:
            print(f"Audio: 再生デバイスを {self.audio_output_device.get()} に変更しました")

    def applyAudioVolume(self, value: str | None = None) -> None:
        """
        Volume のスライダーを動かしたとき: 音量(0～100%)を表示し、再生の音量に反映する
        value: 使わない(スライダーから渡される値。音量はスライダーから読み直す)
        """
        volume = int(round(float(self.audio_volume_scale.get())))
        self.audio_volume.set(volume)
        self.audio_volume_value_label["text"] = f"{volume}%"
        if self.audio is not None:
            self.audio.set_volume(volume / 100)

    def _updateAudioMeter(self) -> None:
        """
        音量メーターを更新し、取り込みが止まっていないかを確認する
        (取り込み中は、after() で AUDIO_METER_INTERVAL_MS ごとに自分を呼び直す)
        """
        self.audio_meter_after = None
        audio = self.audio
        if audio is None or not audio.is_running:
            return
        if audio.error is not None:
            # デバイスが外れた等
            print(f"Audio: {audio.error}")
            self._logger.error(f"Audio: {audio.error}")
            self.stopAudio()
            self.is_use_audio.set(False)
            return
        if time.perf_counter() - audio.last_input_time > AUDIO_NO_SIGNAL_SECONDS:
            # ストリームは開いているが、音声が届いていない
            self.audio_meter["value"] = 0
            self.audio_status_label["text"] = "No signal"
        else:
            db = audio.get_volume(AUDIO_METER_INTERVAL_MS / 1000)
            self.audio_meter["value"] = min(max((db - AUDIO_METER_MIN_DB) / -AUDIO_METER_MIN_DB * 100, 0), 100)
            self.audio_status_label["text"] = f"{db:.0f} dB"
        self.audio_meter_after = self.root.after(AUDIO_METER_INTERVAL_MS, self._updateAudioMeter)
