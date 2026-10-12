#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
映像・音声の入力デバイスの一覧の取得と、一覧での並べ方・既定の選び方

画面(tkinter)には触れない。カメラを開いて画像を読む処理は Camera.py、音声は Audio.py にある
(どちらも画面に依存しない)。
"""
from __future__ import annotations

import os
import platform
import subprocess
from logging import getLogger, DEBUG, NullHandler

from Audio import list_input_devices, list_output_devices, refresh_devices
from Camera import EXTRA_SOURCES
from DeviceMatch import match_audio_to_cameras
from WindowCapture import list_windows, window_label

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# カメラを使わないことを表す、一覧の最後の項目
DISABLE = "Disable"
# カメラの名前の取得に使うDLL(SerialController フォルダから見た場所)
DIRECTSHOW_DLL = r"..\DirectShowLib\DirectShowLib-2005"


def list_cameras() -> tuple[dict, dict | None] | None:
    """
    カメラの一覧を返す: (番号 -> 表示する名前, 番号 -> デバイスパス)。
    - 名前の一覧の最後には「Disable」を足す(キーは、次の番号の文字列)
    - デバイスパスを取得できない方法で一覧を作った場合、デバイスパスは None
    - カメラの名前を取得できない環境(Linux など)では None
    一覧を取得できなかった場合は、例外を送出する
    """
    system = platform.system()
    if system == "Windows":
        names, paths = _list_cameras_windows()
    elif system == "Darwin":
        names, paths = _list_cameras_mac(), None
    else:
        return None
    names[str(max(list(names.keys())) + 1)] = DISABLE
    return names, paths


def _list_cameras_windows() -> tuple[dict, dict | None]:
    """
    Windows のカメラの一覧: (番号 -> 名前, 番号 -> デバイスパス)。
    DirectShowLib を使えない場合は、理由を表示して、例外を送出する(呼び出し元は、カメラの番号を入力する欄に切り替える)
    """
    try:
        import clr

        clr.AddReference(DIRECTSHOW_DLL)
        from DirectShowLib import DsDevice, FilterCategory  # type: ignore

        # Get names of detected camera devices
        capture_devices = DsDevice.GetDevicesOfCat(FilterCategory.VideoInputDevice)
        names = {cam_id: device.Name + " (" + device.DevicePath + ")" for cam_id, device in enumerate(capture_devices)}
        paths = {cam_id: device.DevicePath for cam_id, device in enumerate(capture_devices)}
        return names, paths
    except Exception as e:
        # 失敗した理由を記録する
        _logger.warning(f"Failed to get the camera names with DirectShowLib: {e}")
        dll_path = os.path.abspath(DIRECTSHOW_DLL + ".dll")
        if "0x80131515" in str(e) or os.path.exists(dll_path + ":Zone.Identifier"):
            # インターネットから入手したzipを展開した場合に、DLLに付く印(ブロック)で読み込めない
            print("カメラの名前を取得できません。DLLのブロックを解除してください。")
            print(f"対象のファイル: {dll_path}")
            print("ファイルを右クリック > プロパティ > 全般 の「許可する」にチェックを入れて、起動し直してください。")
        raise RuntimeError(f"DirectShowLib でカメラの名前を取得できませんでした: {e}") from e


def _list_cameras_mac() -> dict:
    """macOS のカメラの一覧(番号 -> 名前)。system_profiler の出力から作る"""
    cmd = 'system_profiler SPCameraDataType | grep "^    [^ ]" | sed "s/    //" | sed "s/://" '
    res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
    # 出力結果の加工
    ret = res.stdout.decode("utf-8")
    cam_list = list(filter(lambda a: a != "", ret.split("\n")))
    return {cam_id: camera_name for cam_id, camera_name in enumerate(cam_list)}


def camera_labels(names: dict) -> list:
    """
    一覧に表示する文字(「No.番号: 名前」)
    """
    return ["No." + str(k) + ": " + v for k, v in names.items()]


def extra_source_labels(show_windows: bool, selected: str = "") -> dict:
    """
    カメラの後ろに並べる映像ソース: キー -> 表示する名前
    - 追加の映像ソース(起動時に登録されたもの)は、常に含める
    - 取り込めるウィンドウは、show_windows の場合のみ含める。
      選択中のウィンドウ(selected)は、見つからない場合も残す(ウィンドウが現れると取り込みを始める)
    """
    labels = {key: label for key, (label, _) in EXTRA_SOURCES.items()}
    if show_windows:
        labels.update({window.key: window_label(window.key, window.title) for window in list_windows()})
        if selected and selected not in labels:
            labels[selected] = window_label(selected)
    return labels


def replace_extra_sources(names: dict, source_ids: dict, labels: dict) -> dict:
    """
    カメラの一覧(names)の後ろの映像ソースを、labels に入れ替える(カメラの項目は変えない)。
    source_ids: 入れ替える前の、番号 -> キー。入れ替えた後の、番号 -> キー を返す
    """
    for source_id in source_ids:
        names.pop(source_id, None)
    new_ids = {}
    for key, label in labels.items():
        source_id = len(names)
        names[source_id] = label
        new_ids[source_id] = key
    return new_ids


def list_audio_inputs(camera_paths: dict, refresh: bool = True) -> tuple[list, dict]:
    """
    音声入力デバイスの一覧を返す: (名前の一覧, 名前 -> 同じ機器のカメラの番号)。
    カメラと同じ機器のデバイスを番号順に並べ、音声のみのデバイスはその後ろに置く。
    refresh: 接続・切断を反映する(取り込み中は反映できないので False にする)
    """
    if refresh:
        refresh_devices()
    names = list_input_devices()
    numbers = match_audio_to_cameras(camera_paths)
    return sort_audio_inputs(names, numbers), numbers


def sort_audio_inputs(names: list, numbers: dict) -> list:
    """入力デバイスの名前を、同じ機器のカメラの番号順に並べる(音声のみのデバイスは、その後ろ)"""
    return sorted(names, key=lambda n: (n not in numbers, numbers.get(n, 0)))


def list_audio_outputs(refresh: bool = True) -> list:
    """
    音声出力デバイスの名前の一覧
    """
    if refresh:
        refresh_devices()
    return list_output_devices()


def audio_label(name: str, numbers: dict) -> str:
    """
    一覧に表示する名前(同じ機器のカメラの番号を付ける。音声のみのデバイスは x)
    """
    number = numbers.get(name)
    return f"No.{'x' if number is None else number}: {name}"


def default_audio_input(names: list, numbers: dict, current: str, camera_id: int) -> str | None:
    """
    入力デバイスが未選択(または見つからない)場合に選ぶデバイス:
    選択中のカメラと同じ機器のデバイス(なければ先頭)。選び直す必要がない場合は None
    """
    if current in names or not names:
        return None
    matched = [n for n in names if numbers.get(n) == camera_id]
    return matched[0] if matched else names[0]
