#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
他のアプリケーションのウィンドウを、カメラの代わりに取り込む(Windowsのみ)。

キャプチャーボードのビューアー(例: 3DS用の nonstd 3pairs Diff Signal Viewer)の画面を、
OBSの仮想カメラを通さずに直接取り込むために使う。

ウィンドウの中身(クライアント領域)を PrintWindow で取り込むので、ウィンドウが他のウィンドウに
隠れていても取り込める(最小化している間は取り込めない)。

Windows以外の環境でも、このモジュールは読み込める(WINDOW_CAPTURE_AVAILABLEがFalseになる)。
"""
from __future__ import annotations

import os
import threading
import time
from logging import getLogger, DEBUG, NullHandler
from typing import NamedTuple

import cv2
import numpy

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

WINDOW_CAPTURE_AVAILABLE = os.name == "nt"

# 取り込みの最大フレームレート
MAX_FPS = 60
# ウィンドウが見つからない間に、探し直す間隔(秒)
FIND_INTERVAL = 1.0

if WINDOW_CAPTURE_AVAILABLE:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class _BITMAPINFOHEADER(ctypes.Structure):
        """GetDIBits に渡す、画像の形式(BITMAPINFOHEADER)"""

        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    # クライアント領域だけを、DirectX等で描いた内容も含めて取り込む
    _PW_CLIENTONLY = 0x1
    _PW_RENDERFULLCONTENT = 0x2
    _DWMWA_CLOAKED = 14
    # ウィンドウの、目に見える範囲(影や、見えない枠を含まない)
    _DWMWA_EXTENDED_FRAME_BOUNDS = 9
    # 画面の拡大率(DPI)に関わらず、ウィンドウの実際の画素数で取り込むための指定
    _DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

    try:
        _dwmapi = ctypes.WinDLL("dwmapi")
        _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    except OSError:
        _dwmapi = None


class WindowInfo(NamedTuple):
    """取り込めるウィンドウの情報"""

    hwnd: int
    title: str
    # ウィンドウの識別名("実行ファイル名|ウィンドウクラス名")。タイトルは表示内容で変わるため使わない
    key: str


def _set_thread_dpi_aware() -> None:
    """今のスレッドを、画面の拡大率(DPI)に関わらず、実際の画素数で扱うようにする(使えない Windows では何もしない)"""
    try:
        _user32.SetThreadDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        # Windows 10 (1607) より前では使えない
        pass


def _process_name(hwnd: int) -> str:
    """ウィンドウを持つプロセスの、実行ファイルの名前(取得できなければ空文字)"""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(buffer.value)
    finally:
        _kernel32.CloseHandle(handle)


def _is_cloaked(hwnd: int) -> bool:
    """ウィンドウが、見えない状態(cloaked)か"""
    # 表示されていないストアアプリ等のウィンドウ(見えないが、IsWindowVisibleはTrueになる)
    if _dwmapi is None:
        return False
    cloaked = wintypes.DWORD()
    _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return cloaked.value != 0


def _client_size(hwnd: int) -> tuple[int, int]:
    """ウィンドウの中身(クライアント領域)の (幅, 高さ)。取得できなければ (0, 0)。最小化している間は 0 になる"""
    rect = wintypes.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return 0, 0
    return rect.right - rect.left, rect.bottom - rect.top


def list_windows() -> list[WindowInfo]:
    """
    取り込めるウィンドウ(表示中で、タイトルがあるもの)の一覧を返す。

    自分自身(Poke-Controller)のウィンドウは含めない。同じ識別名のウィンドウが複数ある場合は、最初の1つだけを返す。
    """
    if not WINDOW_CAPTURE_AVAILABLE:
        return []
    windows: list[WindowInfo] = []
    keys = set()
    own_pid = os.getpid()

    def callback(hwnd: int, _: int) -> bool:
        """EnumWindows が、ウィンドウごとに呼ぶ(取り込めるウィンドウを windows に足す。True を返して続ける)"""
        if not _user32.IsWindowVisible(hwnd) or _is_cloaked(hwnd):
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == own_pid:
            return True
        title = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, title, 512)
        if not title.value:
            return True
        class_name = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, class_name, 256)
        process_name = _process_name(hwnd)
        # Progman: デスクトップ(Program Manager)
        if not process_name or class_name.value == "Progman":
            return True
        key = f"{process_name}|{class_name.value}"
        if key not in keys:
            keys.add(key)
            windows.append(WindowInfo(hwnd, title.value, key))
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return windows


def find_window(key: str) -> int | None:
    """
    識別名に合うウィンドウを探す(無ければNone)
    """
    for window in list_windows():
        if window.key == key:
            return window.hwnd
    return None


def window_label(key: str, title: str | None = None) -> str:
    """
    ウィンドウの表示名(カメラの一覧に出す名前)
    """
    process_name = key.split("|")[0]
    return f"Window: {title if title else '(not found)'} [{process_name}]"


def capture_whole_window(hwnd: int | None) -> numpy.ndarray | None:
    """
    ウィンドウ全体(タイトルバーを含む)を取り込んで、BGR の画像で返す(取り込めなければ None)。
    PrintWindow を使うので、ほかのウィンドウに隠れていても、そのウィンドウの中身だけが写る(ほかのウィンドウは写らない)。
    最小化している間は、取り込めない。Windows 以外では、いつも None。どのスレッドから呼んでもよい(tkinter に触れない)
    """
    if not WINDOW_CAPTURE_AVAILABLE or not hwnd or not _user32.IsWindow(hwnd) or _user32.IsIconic(hwnd):
        return None
    _set_thread_dpi_aware()
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    screen_dc = _user32.GetDC(None)
    dc = bitmap = None
    try:
        dc = _gdi32.CreateCompatibleDC(screen_dc)
        bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not dc or not bitmap:
            return None
        _gdi32.SelectObject(dc, bitmap)
        if not _user32.PrintWindow(hwnd, dc, _PW_RENDERFULLCONTENT):
            return None
        # 高さを負にして、上から下の順(画像と同じ並び)で受け取る
        info = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = numpy.empty((height, width, 4), numpy.uint8)
        if _gdi32.GetDIBits(dc, bitmap, 0, height, buffer.ctypes.data, ctypes.byref(info), 0) != height:
            return None
    finally:
        if bitmap:
            _gdi32.DeleteObject(bitmap)
        if dc:
            _gdi32.DeleteDC(dc)
        _user32.ReleaseDC(None, screen_dc)
    left = top = 0
    right, bottom = width, height
    if _dwmapi is not None:
        # ウィンドウの範囲には、見えない枠(大きさを変えるための余白)が含まれるので、見える範囲だけを切り出す
        frame = wintypes.RECT()
        size = ctypes.sizeof(frame)
        if _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame), size) == 0:
            left, top = max(frame.left - rect.left, 0), max(frame.top - rect.top, 0)
            right, bottom = min(frame.right - rect.left, width), min(frame.bottom - rect.top, height)
    if right <= left or bottom <= top:
        return None
    # BGRA の A を捨てる
    return numpy.ascontiguousarray(buffer[top:bottom, left:right, :3])


class WindowCapture:
    """
    ウィンドウの中身を取り込む。cv2.VideoCapture と同じ呼び方(isOpened / read / release)で使える。

    ウィンドウが見つからない・最小化している間は read() が失敗を返し、ウィンドウが現れると取り込みを再開する
    (ビューアーを後から起動・再起動しても、開き直す必要がない)。
    取り込んだ画像の大きさが size と違う場合は、size に拡大・縮小する。
    """

    def __init__(self, key: str, size: tuple[int, int]):
        """
        key: ウィンドウの識別名("実行ファイル名|ウィンドウクラス名")
        size: 返す画像の大きさ(幅, 高さ)
        """
        self.key = key
        self.size = tuple(size)
        self._opened = WINDOW_CAPTURE_AVAILABLE
        self._lock = threading.Lock()
        self._hwnd = None
        self._last_find = 0.0
        self._last_read = 0.0
        self._dpi_thread = None
        # 取り込み用のGDIオブジェクト(ウィンドウの大きさが変わったら作り直す)
        self._buffer_size = None
        self._dc = None
        self._bitmap = None
        self._buffer = None
        self._info = None
        # メッセージを状態が変わったときだけ出すための、直前の状態
        self._state = None
        self._reported_size = None

        if not self._opened:
            print("Window capture is available only on Windows.")
            _logger.error("Window capture is available only on Windows.")
            return
        with self._lock:
            self._find()

    def isOpened(self) -> bool:
        """取り込める状態か(Windows で、release していない間は True。ウィンドウが見つかっているかは問わない)"""
        return self._opened

    def _report(self, state: str, message: str) -> None:
        """状態(found / missing / minimized)が変わったときだけ、メッセージを表示する"""
        if self._state != state:
            self._state = state
            print(message)
            _logger.info(message)

    def _find(self) -> None:
        """識別名に合うウィンドウを探して、self._hwnd に入れる(無ければ None)"""
        self._last_find = time.perf_counter()
        self._hwnd = find_window(self.key)
        if self._hwnd is None:
            self._report("missing", f"Window '{self.key}' is not found. Waiting for the window...")
        else:
            self._report("found", f"Window '{self.key}' opened successfully")

    def _free_buffer(self) -> None:
        """取り込み用の GDI オブジェクトとバッファーを捨てる"""
        if self._bitmap is not None:
            _gdi32.DeleteObject(self._bitmap)
        if self._dc is not None:
            _gdi32.DeleteDC(self._dc)
        self._buffer_size = self._dc = self._bitmap = self._buffer = self._info = None

    def _prepare_buffer(self, width: int, height: int) -> bool:
        """その大きさの、取り込み用の GDI オブジェクトとバッファーを用意する(同じ大きさなら使い回す)。用意できたかを返す"""
        if self._buffer_size == (width, height):
            return True
        self._free_buffer()
        screen_dc = _user32.GetDC(None)
        try:
            self._dc = _gdi32.CreateCompatibleDC(screen_dc)
            self._bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        finally:
            _user32.ReleaseDC(None, screen_dc)
        if not self._dc or not self._bitmap:
            self._free_buffer()
            return False
        _gdi32.SelectObject(self._dc, self._bitmap)
        # 高さを負にして、上から下の順(画像と同じ並び)で受け取る
        self._info = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        self._buffer = numpy.empty((height, width, 4), numpy.uint8)
        self._buffer_size = (width, height)
        return True

    def read(self) -> tuple[bool, numpy.ndarray | None]:
        """
        ウィンドウの中身を取り込む。(成否, BGR画像) を返す(失敗の場合、画像は None)
        """
        # 取り込みが速いウィンドウでも、必要以上に取り込まないよう間隔を空ける
        wait = self._last_read + 1.0 / MAX_FPS - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        self._last_read = time.perf_counter()

        with self._lock:
            if not self._opened:
                return False, None
            if self._dpi_thread != threading.get_ident():
                _set_thread_dpi_aware()
                self._dpi_thread = threading.get_ident()

            if self._hwnd is not None and not _user32.IsWindow(self._hwnd):
                self._hwnd = None
                self._report("missing", f"Window '{self.key}' was closed. Waiting for the window...")
            if self._hwnd is None:
                if time.perf_counter() - self._last_find < FIND_INTERVAL:
                    return False, None
                self._find()
                if self._hwnd is None:
                    return False, None

            width, height = _client_size(self._hwnd)
            if width <= 0 or height <= 0:
                # 最小化している間は、中身を取り込めない
                self._report("minimized", f"Window '{self.key}' is minimized. Restore the window to capture.")
                return False, None
            self._report("found", f"Window '{self.key}' capture resumed")
            if not self._prepare_buffer(width, height):
                return False, None
            if not _user32.PrintWindow(self._hwnd, self._dc, _PW_CLIENTONLY | _PW_RENDERFULLCONTENT):
                return False, None
            lines = _gdi32.GetDIBits(
                self._dc, self._bitmap, 0, height, self._buffer.ctypes.data, ctypes.byref(self._info), 0
            )
            if lines != height:
                return False, None

            # BGRAのAを捨てる(取り込み用のバッファは使い回すので、コピーして返す)
            frame = numpy.ascontiguousarray(self._buffer[:, :, :3])
            if (width, height) != self.size:
                if self._reported_size != (width, height):
                    self._reported_size = (width, height)
                    message = (
                        f"Window size {width}x{height} is resized to capture size {self.size[0]}x{self.size[1]}."
                    )
                    print(message)
                    _logger.warning(message)
                shrink = width > self.size[0] or height > self.size[1]
                frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR)
            return True, frame

    def release(self) -> None:
        """取り込みをやめる(この後の read は、失敗を返す)"""
        with self._lock:
            self._opened = False
            self._hwnd = None
            if WINDOW_CAPTURE_AVAILABLE:
                self._free_buffer()
