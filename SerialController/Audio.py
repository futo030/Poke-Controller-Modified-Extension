#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キャプチャーボード等の音声入力の取り込みと再生

- 取り込みと再生は別のストリームにする。再生をオフにしても取り込みは続くので、
  音を鳴らさずにコマンドから音声を検出できる
- 取り込んだ音声は、直近 BUFFER_SECONDS 秒分をバッファーに保持する(コマンドはここから取り出す)
- 音声の処理は sounddevice(PortAudio) のスレッドで行う。カメラの読み取りスレッドとメインスレッドには処理を足さない

sounddeviceパッケージが必要(pip install sounddevice)。
無い環境でもこのモジュールは読み込める(AUDIO_AVAILABLEがFalseになる)。
"""
from __future__ import annotations

import threading
import time
from logging import getLogger, DEBUG, NullHandler

import numpy as np

import AudioProcessing

try:
    import sounddevice as sd

    AUDIO_AVAILABLE = True
    AUDIO_IMPORT_ERROR = None
except Exception as e:  # パッケージが無い場合のほか、PortAudioを読み込めない場合も含む
    sd = None
    AUDIO_AVAILABLE = False
    AUDIO_IMPORT_ERROR = e

# 保持する音声の長さ(秒)
BUFFER_SECONDS = 10.0
# 取り込み・再生のチャンネル数の上限(ステレオ)
MAX_CHANNELS = 2
# 再生のチャンネル数
OUTPUT_CHANNELS = 2
# 再生の遅延の目標(秒)。入力と出力のデバイスの時計のずれを吸収するため、この分を溜めてから再生する
PLAYBACK_TARGET_DELAY = 0.04
# 再生待ちがこの長さ(秒)を超えたら、古い音声を捨てて遅延を目標に戻す
PLAYBACK_MAX_DELAY = 0.20
# 再生待ちのバッファーの長さ(秒)
PLAYBACK_BUFFER_SECONDS = 1.0
# Windowsで優先して使うホストAPI(デバイス名が省略されず、遅延が小さい)
PREFERRED_HOSTAPI = "Windows WASAPI"

# sounddevice以外の音声入力。 名前 -> 入力(samplerate・channels と、open(受け取る関数) を持つもの)
# open は、stop / close で止められるものを返す。受け取る関数には、sounddeviceと同じ形((サンプル数, チャンネル数)の
# float32, サンプル数, None, None)で音声を渡す。追加の機能が、起動時に登録する
EXTERNAL_INPUTS = {}


class AudioError(Exception):
    """音声のデバイスを開けない・見つからないなど(メッセージは、そのまま表示できる文)"""

    pass


def _hostapi_index() -> int:
    """
    使うホストAPIの番号(WindowsではWASAPI、それ以外は既定のホストAPI)
    """
    for index, api in enumerate(sd.query_hostapis()):
        if api["name"] == PREFERRED_HOSTAPI:
            return index
    return sd.default.hostapi


def refresh_devices() -> None:
    """
    デバイスの一覧を更新する(接続・切断を反映する)。ストリームを開いている間は呼ばないこと
    """
    sd._terminate()
    sd._initialize()


def list_input_devices() -> list[str]:
    """
    音声入力デバイスの名前の一覧
    """
    if not AUDIO_AVAILABLE:
        return []
    hostapi = _hostapi_index()
    names = [d["name"] for d in sd.query_devices() if d["hostapi"] == hostapi and d["max_input_channels"] > 0]
    return names + list(EXTERNAL_INPUTS)


def list_output_devices() -> list[str]:
    """
    音声出力(再生)デバイスの名前の一覧
    """
    if not AUDIO_AVAILABLE:
        return []
    hostapi = _hostapi_index()
    return [d["name"] for d in sd.query_devices() if d["hostapi"] == hostapi and d["max_output_channels"] > 0]


def _find_output_device(name: str) -> int:
    """その名前の音声出力デバイスの番号を返す(見つからなければ AudioError)"""
    hostapi = _hostapi_index()
    for index, device in enumerate(sd.query_devices()):
        if device["hostapi"] == hostapi and device["max_output_channels"] > 0 and device["name"] == name:
            return index
    raise AudioError(f"音声出力デバイス '{name}' が見つかりません")


def _find_input_device(name: str) -> tuple[int, dict]:
    """その名前の音声入力デバイスの (番号, sounddevice のデバイスの情報) を返す(見つからなければ AudioError)"""
    hostapi = _hostapi_index()
    for index, device in enumerate(sd.query_devices()):
        if device["hostapi"] == hostapi and device["max_input_channels"] > 0 and device["name"] == name:
            return index, device
    raise AudioError(f"音声入力デバイス '{name}' が見つかりません")


class AudioCapture:
    """音声入力デバイスから取り込み、直近の音声を保持する。取り込んだ音声を、再生デバイスから鳴らすこともできる"""

    def __init__(self, buffer_seconds: float = BUFFER_SECONDS):
        """buffer_seconds: 保持する音声の長さ(秒)"""
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.buffer_seconds = float(buffer_seconds)
        self.device_name = None
        # 取り込み中の形式(デバイスの既定値に合わせる)
        self.samplerate = 0
        self.channels = 0

        # 直近の音声を保持する循環バッファー
        self._lock = threading.Lock()
        self._buffer = None
        self._write_pos = 0
        # 取り込んだサンプル数の累計と、最後に取り込んだ時刻(time.perf_counter)
        self.total_frames = 0
        self.last_input_time = 0.0

        self._input = None
        self._output = None
        self._stopping = False
        # 取り込みが止まった原因(メインスレッドから定期的に確認する)
        self.error = None

        # 再生
        self.volume = 1.0
        # 再生するデバイスの名前(空文字なら既定の再生デバイス)
        self.output_device_name = ""
        self._play_lock = threading.Lock()
        self._play_buffer = None
        self._play_write = 0
        self._play_read = 0
        self._play_started = False

    # --- 取り込み
    @property
    def is_running(self) -> bool:
        """取り込み中か"""
        return self._input is not None

    @property
    def is_playing(self) -> bool:
        """再生中か"""
        return self._output is not None

    def start(self, device_name: str) -> None:
        """
        音声入力デバイスを開いて取り込みを始める(デバイスの既定のサンプリング周波数で開く)
        device_name: デバイスの名前(list_input_devices の値)。取り込み中の場合は、止めてから始める。
        sounddevice を使えない場合と、デバイスが見つからない・開けない場合は AudioError
        """
        if not AUDIO_AVAILABLE:
            raise AudioError(f"sounddeviceを読み込めません ({AUDIO_IMPORT_ERROR})")
        self.stop()
        external = EXTERNAL_INPUTS.get(device_name)
        if external is not None:
            samplerate, channels = int(external.samplerate), min(MAX_CHANNELS, int(external.channels))
        else:
            index, device = _find_input_device(device_name)
            samplerate = int(device["default_samplerate"])
            channels = min(MAX_CHANNELS, int(device["max_input_channels"]))
        with self._lock:
            self.samplerate = samplerate
            self.channels = channels
            self._buffer = np.zeros((int(self.buffer_seconds * samplerate), channels), dtype=np.float32)
            self._write_pos = 0
            self.total_frames = 0
        self.error = None
        self._stopping = False
        try:
            if external is not None:
                stream = external.open(self._on_input)
            else:
                stream = sd.InputStream(
                    device=index,
                    samplerate=samplerate,
                    channels=channels,
                    dtype="float32",
                    latency="low",
                    callback=self._on_input,
                    finished_callback=self._on_input_finished,
                )
                stream.start()
        except Exception as e:
            raise AudioError(f"音声入力デバイス '{device_name}' を開けません: {e}") from e
        self._input = stream
        self.device_name = device_name
        self._logger.info(f"Audio capture started: {device_name} ({samplerate} Hz, {channels} ch)")

    def stop(self) -> None:
        """
        取り込みと再生を止める
        """
        self.set_playback(False)
        stream, self._input = self._input, None
        if stream is None:
            return
        self._stopping = True
        try:
            stream.stop()
            stream.close()
        except Exception as e:
            self._logger.error(f"Failed to close the audio input: {e}")
        self._logger.info("Audio capture stopped")

    def _on_input(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        """
        取り込んだ音声を受け取り、バッファーに書く(再生中は、再生待ちにも渡す)。
        indata: (サンプル数, チャンネル数) の float32、frames: サンプル数
        time_info / status: sounddevice が渡す値(使わない。sounddevice 以外の入力は None を渡す)
        """
        # sounddeviceのスレッドで呼ばれる
        with self._lock:
            buffer = self._buffer
            size = len(buffer)
            block = indata[-size:]
            n = len(block)
            end = self._write_pos + n
            if end <= size:
                buffer[self._write_pos : end] = block
            else:
                first = size - self._write_pos
                buffer[self._write_pos :] = block[:first]
                buffer[: n - first] = block[first:]
            self._write_pos = end % size
            self.total_frames += frames
            self.last_input_time = time.perf_counter()
        if self._output is not None:
            self._push_playback(indata)

    def _on_input_finished(self) -> None:
        """取り込みのストリームが止まったときに、sounddevice から呼ばれる"""
        # 自分で止めた場合以外(デバイスが外れた等)は、エラーとして記録する
        if not self._stopping:
            self.error = f"音声入力デバイス '{self.device_name}' からの取り込みが止まりました"

    # --- 再生
    def set_volume(self, volume: float) -> None:
        """再生の音量を変える(0.0～1.0 に収める。取り込んだ音声そのものは変えない)"""
        self.volume = min(max(float(volume), 0.0), 1.0)

    def set_output_device(self, name: str) -> None:
        """
        再生するデバイスを変える(空文字なら既定の再生デバイス)。再生中の場合は、新しいデバイスで再生し直す
        """
        if name == self.output_device_name:
            return
        self.output_device_name = name
        if self._output is not None:
            self.set_playback(False)
            self.set_playback(True)

    def set_playback(self, enabled: bool) -> None:
        """
        取り込んだ音声を、再生デバイス(output_device_name。空文字なら既定の再生デバイス)から鳴らす / 止める
        取り込みを始めていない場合と、再生デバイスを開けない場合は AudioError
        """
        if not enabled:
            stream, self._output = self._output, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:
                    self._logger.error(f"Failed to close the audio output: {e}")
            return
        if self._output is not None:
            return
        if self._input is None:
            raise AudioError("音声の取り込みを開始していません")
        with self._play_lock:
            self._play_buffer = np.zeros((int(PLAYBACK_BUFFER_SECONDS * self.samplerate), OUTPUT_CHANNELS), dtype=np.float32)
            self._play_write = 0
            self._play_read = 0
            self._play_started = False
        try:
            self._output = self._open_output()
        except Exception as e:
            self._output = None
            raise AudioError(f"再生デバイスを開けません: {e}") from e

    def _open_output(self) -> sd.OutputStream:
        """再生のストリームを開いて始める(デバイスの指定が無い場合は、既定の再生デバイス。開けなければ例外)"""
        options = dict(
            samplerate=self.samplerate,
            channels=OUTPUT_CHANNELS,
            dtype="float32",
            latency="low",
            callback=self._on_output,
        )
        hostapi = sd.query_hostapis(_hostapi_index())
        # 入力と出力のサンプリング周波数が違っても鳴らせるよう、WASAPIの自動変換を使う
        extra = sd.WasapiSettings(auto_convert=True) if hostapi["name"] == PREFERRED_HOSTAPI else None
        if self.output_device_name:
            # 指定されたデバイスで開く(開けない場合は、他のデバイスでは鳴らさずエラーにする)
            device = _find_output_device(self.output_device_name)
            stream = sd.OutputStream(device=device, extra_settings=extra, **options)
        else:
            try:
                stream = sd.OutputStream(device=hostapi["default_output_device"], extra_settings=extra, **options)
            except Exception as e:
                # 既定のホストAPI(MME等)で開き直す
                self._logger.warning(f"Failed to open the output with {hostapi['name']}: {e}")
                stream = sd.OutputStream(**options)
        stream.start()
        return stream

    def _push_playback(self, indata: np.ndarray) -> None:
        """取り込んだ音声を、再生待ちのバッファーに足す(モノラルは、左右に同じ音を入れる)"""
        block = indata if indata.shape[1] == OUTPUT_CHANNELS else np.repeat(indata[:, :1], OUTPUT_CHANNELS, axis=1)
        with self._play_lock:
            buffer = self._play_buffer
            size = len(buffer)
            block = block[-size:]
            n = len(block)
            pos = self._play_write % size
            end = pos + n
            if end <= size:
                buffer[pos:end] = block
            else:
                first = size - pos
                buffer[pos:] = block[:first]
                buffer[: n - first] = block[first:]
            self._play_write += n
            # 溢れた分は古い方から捨てる
            if self._play_write - self._play_read > size:
                self._play_read = self._play_write - size

    def _on_output(self, outdata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        """
        再生する音声を、outdata((サンプル数, チャンネル数) の float32)に書く。足りない分は無音にする。
        time_info / status: sounddevice が渡す値(使わない)
        """
        # sounddeviceのスレッドで呼ばれる
        target = int(PLAYBACK_TARGET_DELAY * self.samplerate)
        with self._play_lock:
            buffer = self._play_buffer
            size = len(buffer)
            available = self._play_write - self._play_read
            if not self._play_started:
                # 目標の遅延分が溜まるまでは無音を出す
                if available < target + frames:
                    outdata.fill(0)
                    return
                self._play_started = True
            if available > int(PLAYBACK_MAX_DELAY * self.samplerate):
                # 遅延が大きくなりすぎたら、古い音声を捨てて目標に戻す
                self._play_read = self._play_write - target - frames
                available = self._play_write - self._play_read
            n = min(frames, available)
            pos = self._play_read % size
            end = pos + n
            if end <= size:
                outdata[:n] = buffer[pos:end]
            else:
                first = size - pos
                outdata[:first] = buffer[pos:]
                outdata[first:n] = buffer[: n - first]
            self._play_read += n
            if n < frames:
                # 足りない分は無音にして、溜まり直すのを待つ
                outdata[n:].fill(0)
                self._play_started = False
        if self.volume != 1.0:
            outdata *= self.volume

    # --- コマンド・GUIからの利用
    def get_audio(self, seconds: float | None = None) -> np.ndarray:
        """
        直近seconds秒分の音声を返す(古い順。形は (サンプル数, チャンネル数) のfloat32)
        seconds: Noneならバッファー全体。取り込んだ量がそれより少ない場合は、取り込んだ分だけを返す
        """
        with self._lock:
            if self._buffer is None:
                return np.zeros((0, max(self.channels, 1)), dtype=np.float32)
            size = len(self._buffer)
            n = size if seconds is None else int(float(seconds) * self.samplerate)
            n = max(min(n, size, self.total_frames), 0)
            start = (self._write_pos - n) % size
            if start + n <= size:
                return self._buffer[start : start + n].copy()
            return np.concatenate((self._buffer[start:], self._buffer[: n - (size - start)]))

    def get_volume(self, seconds: float = 0.1) -> float:
        """
        直近seconds秒分の音量(dBFS。最大音量が0dB、無音は-120dB)
        """
        return AudioProcessing.volume_db(self.get_audio(seconds))
