#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
カメラ(映像)と音声入力が同じ機器かどうかを調べる(Windowsのみ)

Windowsは、同じ機器(キャプチャーボード等)に属するデバイスに同じ「コンテナID」を付ける。
カメラのデバイスパスと音声入力の名前からそれぞれコンテナIDを調べ、一致するものを同じ機器とみなす。
(名前では対応を決められない。映像と音声で名前が違う機器や、同じ名前の機器が複数ある場合があるため)

Windows以外や、情報を取得できない場合は、対応なしとして扱う。
"""
from __future__ import annotations

import ctypes
import platform
from ctypes import wintypes
from logging import getLogger, DEBUG, NullHandler

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 音声の入出力(AudioEndpoint)のデバイスクラス
AUDIO_ENDPOINT_CLASS = "{c166523c-fe0c-4a94-a586-f1a80cfbbf3e}"
# 機器に属さないデバイス(内蔵デバイス等)に付くコンテナID
NULL_CONTAINER_ID = "{00000000-0000-0000-ffff-ffffffffffff}"

CR_SUCCESS = 0x00
CR_BUFFER_SMALL = 0x1A
CM_GETIDLIST_FILTER_PRESENT = 0x100
CM_GETIDLIST_FILTER_CLASS = 0x200


class _GUID(ctypes.Structure):
    """Windows の GUID(文字にすると "{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}" の形)"""

    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __str__(self) -> str:
        """波かっこ付きの、小文字の 16 進数の文字にする"""
        d4 = bytes(self.Data4)
        return f"{{{self.Data1:08x}-{self.Data2:04x}-{self.Data3:04x}-{d4[:2].hex()}-{d4[2:].hex()}}}"


class _DEVPROPKEY(ctypes.Structure):
    """デバイスのプロパティの名前(DEVPROPKEY)"""

    _fields_ = [("fmtid", _GUID), ("pid", wintypes.ULONG)]


def _propkey(data1: int, data2: int, data3: int, data4: bytes, pid: int) -> _DEVPROPKEY:
    """GUID の 4 つの部分(data4 は 8 バイト)と番号から、プロパティの名前を作る"""
    return _DEVPROPKEY(_GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4)), pid)


# DEVPKEY_Device_ContainerId / DEVPKEY_Device_FriendlyName
_KEY_CONTAINER_ID = _propkey(0x8C7ED206, 0x3F8A, 0x4827, bytes.fromhex("b3abae9e1faefc6c"), 2)
_KEY_FRIENDLY_NAME = _propkey(0xA45C254E, 0xDF1C, 0x4EFD, bytes.fromhex("802067d146a850e0"), 14)


def _cfgmgr() -> ctypes.WinDLL:
    """cfgmgr32.dll を読み込み、使う関数の引数の型を決めて返す(Windows のみ)"""
    cfgmgr = ctypes.WinDLL("cfgmgr32")
    cfgmgr.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG]
    cfgmgr.CM_Get_DevNode_PropertyW.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(_DEVPROPKEY),
        ctypes.POINTER(wintypes.ULONG),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.ULONG,
    ]
    cfgmgr.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(wintypes.ULONG), wintypes.LPCWSTR, wintypes.ULONG]
    cfgmgr.CM_Get_Device_ID_ListW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG]
    return cfgmgr


def _get_property(cfgmgr: ctypes.WinDLL, instance_id: str, key: _DEVPROPKEY) -> bytes | None:
    """デバイス(インスタンス ID)のプロパティの値を、そのままのバイト列で返す(取得できなければ None)"""
    devinst = wintypes.DWORD()
    if cfgmgr.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0) != CR_SUCCESS:
        return None
    prop_type = wintypes.ULONG()
    size = wintypes.ULONG(0)
    result = cfgmgr.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(prop_type), None, ctypes.byref(size), 0)
    if result != CR_BUFFER_SMALL or size.value == 0:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    if cfgmgr.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(prop_type), buffer, ctypes.byref(size), 0) != CR_SUCCESS:
        return None
    return buffer.raw[: size.value]


def _container_id(cfgmgr: ctypes.WinDLL, instance_id: str) -> str | None:
    """デバイスのコンテナ ID を返す(取得できない場合と、機器に属さないデバイスの場合は None)"""
    data = _get_property(cfgmgr, instance_id, _KEY_CONTAINER_ID)
    if data is None or len(data) < ctypes.sizeof(_GUID):
        return None
    container = str(_GUID.from_buffer_copy(data))
    return None if container == NULL_CONTAINER_ID else container


def _list_instance_ids(cfgmgr: ctypes.WinDLL, device_class: str) -> list[str]:
    """そのデバイスクラスの、接続されているデバイスのインスタンス ID の一覧(取得できなければ空)"""
    flags = CM_GETIDLIST_FILTER_CLASS | CM_GETIDLIST_FILTER_PRESENT
    size = wintypes.ULONG(0)
    if cfgmgr.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), device_class, flags) != CR_SUCCESS or size.value == 0:
        return []
    buffer = ctypes.create_unicode_buffer(size.value)
    if cfgmgr.CM_Get_Device_ID_ListW(device_class, buffer, size.value, flags) != CR_SUCCESS:
        return []
    # NUL区切りの文字列の並び
    return [s for s in buffer[: size.value].split("\0") if s]


def camera_instance_id(device_path: str) -> str | None:
    r"""
    カメラのデバイスパス(@device:pnp:\\?\usb#vid_xxxx&pid_xxxx&mi_00#...#{...}\global)を
    デバイスのインスタンスIDに変換する。仮想カメラ等(@device:sw:...)は変換できないのでNoneを返す
    """
    start = device_path.find("\\\\?\\")
    if start < 0:
        return None
    body = device_path[start + 4 :]
    end = body.find("#{")
    if end < 0:
        return None
    return body[:end].replace("#", "\\")


def match_audio_to_cameras(camera_paths: dict[int, str]) -> dict[str, int]:
    """
    音声入力デバイスの名前 -> 同じ機器のカメラの番号 を返す(対応するカメラが無いデバイスは含めない)
    camera_paths: カメラの番号 -> デバイスパス
    """
    if platform.system() != "Windows":
        return {}
    try:
        cfgmgr = _cfgmgr()
        containers = {}
        for number, path in camera_paths.items():
            instance_id = camera_instance_id(path)
            container = _container_id(cfgmgr, instance_id) if instance_id else None
            # 同じコンテナIDのカメラが複数ある場合は、番号の小さい方を使う
            if container is not None and container not in containers:
                containers[container] = number
        result = {}
        for instance_id in _list_instance_ids(cfgmgr, AUDIO_ENDPOINT_CLASS):
            container = _container_id(cfgmgr, instance_id)
            if container not in containers:
                continue
            name = _get_property(cfgmgr, instance_id, _KEY_FRIENDLY_NAME)
            if name is None:
                continue
            result[name.decode("utf-16-le").rstrip("\0")] = containers[container]
        return result
    except Exception as e:
        _logger.warning(f"Failed to match audio devices to cameras: {e}")
        return {}
