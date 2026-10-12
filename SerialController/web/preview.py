#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プレビュー(Web 版): カメラ画像を JPEG にしてブラウザへ送る準備と、認識した位置の表示の受け渡し
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Callable

import cv2
import numpy as np

from Mask import draw_masks

if TYPE_CHECKING:
    from Camera import Camera
    from services.app_core import AppCore

# ブラウザへ送る画像の幅の上限(これより大きい取り込み画像は、縮めて送る)
MAX_WIDTH = 960
# 選べる上限(0 は、縮めずに取り込みサイズのまま送る)
MAX_WIDTH_CHOICES = (480, 640, 960, 1280, 1920, 0)
# 送る枚数の上限(1秒あたり)と、JPEG の品質
MAX_FPS = 30
JPEG_QUALITY = 80
# カメラ画像が無い間に、画像を作り直す間隔(秒)
NO_IMAGE_INTERVAL = 0.5
NO_IMAGE_TEXT = "No Image"


def scaled_size(width: int, height: int, max_width: int = MAX_WIDTH) -> tuple[int, int]:
    """
    幅を max_width 以下にした大きさ(縦横比は保つ。もともと小さい場合はそのまま。max_width が 0 なら縮めない)
    """
    if not max_width or width <= max_width:
        return width, height
    return max_width, max(1, round(height * max_width / width))


def brightness_table(gain: int, gamma: float) -> np.ndarray | None:
    """
    プレビューの明るさ(表示だけ)の変換表(256 個の uint8)。変えない場合は None
    gain: ゲイン(%。100 で元のまま)、gamma: ガンマ(1.0 で元のまま)
    """
    if gain == 100 and gamma == 1.0:
        return None
    values = [min(255, int(round(255.0 * (value / 255.0) ** (1.0 / gamma) * gain / 100.0))) for value in range(256)]
    return np.array(values, dtype=np.uint8)


def no_image(width: int, height: int) -> np.ndarray:
    """カメラ画像が無い間に送る画像(黒地に "No Image"。BGR)"""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    scale = max(0.5, height / 240.0)
    (text_width, text_height), _ = cv2.getTextSize(NO_IMAGE_TEXT, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    origin = ((width - text_width) // 2, (height + text_height) // 2)
    cv2.putText(image, NO_IMAGE_TEXT, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 2, cv2.LINE_AA)
    return image


class FrameEncoder:
    """
    カメラの最新の画像を、ブラウザへ送る JPEG にする。
    見ているブラウザがある間だけ、専用のスレッドで作る
    """

    def __init__(self, core: AppCore, on_frame: Callable[[], None] | None = None):
        """
        core: アプリ本体(カメラ・目隠し・明るさの設定を読む)
        on_frame: 新しい画像ができたときに呼ぶ関数(作ったスレッドから呼ぶ)
        """
        self._core = core
        self._on_frame = on_frame
        # 送る画像の幅の上限(0 は、取り込みサイズのまま)
        self.max_width = MAX_WIDTH
        self._lock = threading.Lock()
        self._jpeg = None
        self._seq = 0
        self._viewers = 0
        self._thread = None
        self._stop = None

    def latest(self) -> tuple[bytes | None, int]:
        """最新の JPEG(まだ無ければ None)と、その通し番号(新しい画像ができるたびに増える)"""
        with self._lock:
            return self._jpeg, self._seq

    def add_viewer(self) -> None:
        """見ているブラウザを 1 つ足す(最初の 1 つのときに、画像を作るスレッドを始める)"""
        with self._lock:
            self._viewers += 1
            if self._thread is None:
                self._stop = threading.Event()
                self._thread = threading.Thread(target=self._run, args=(self._stop,), name="PreviewEncoder", daemon=True)
                self._thread.start()

    def remove_viewer(self) -> None:
        """見ているブラウザを 1 つ減らす(いなくなったら、画像を作るスレッドを止める)"""
        with self._lock:
            self._viewers = max(0, self._viewers - 1)
            if self._viewers == 0 and self._thread is not None:
                self._stop.set()
                self._thread = None

    def stop(self) -> None:
        """画像を作るスレッドを止める(終了するとき)"""
        with self._lock:
            self._viewers = 0
            if self._thread is not None:
                self._stop.set()
                self._thread = None

    def encode(self, frame: np.ndarray | None) -> bytes | None:
        """
        カメラ画像(BGR。無い場合は None)を JPEG にする(目隠し・縮小・明るさを反映する。作れなければ None)
        """
        core = self._core
        if frame is None:
            width, height = scaled_size(*core.camera.capture_size, self.max_width)
            image = no_image(width, height)
        else:
            image = frame
            if core.settings.is_show_mask and core.masks:
                image = draw_masks(image, core.masks)
            height, width = image.shape[:2]
            size = scaled_size(width, height, self.max_width)
            if size != (width, height):
                image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            table = brightness_table(core.settings.preview_gain, core.settings.preview_gamma)
            if table is not None:
                image = cv2.LUT(image, table)
        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return data.tobytes() if ok else None

    def _run(self, stop: threading.Event) -> None:
        """カメラの新しい画像を JPEG にし続ける(スレッドの中身。stop が立つまで。1 秒に MAX_FPS 枚まで)"""
        interval = 1.0 / MAX_FPS
        while not stop.is_set():
            started = time.perf_counter()
            # 新しい画像が来るまで待つ(カメラを開いていない場合は、すぐ None が返る)
            frame = self._core.camera.readFrame()
            try:
                jpeg = self.encode(frame)
            except Exception:
                jpeg = None
            if jpeg is not None:
                with self._lock:
                    self._jpeg = jpeg
                    self._seq += 1
                if self._on_frame is not None:
                    self._on_frame()
            wait = (NO_IMAGE_INTERVAL if frame is None else interval) - (time.perf_counter() - started)
            if wait > 0:
                stop.wait(wait)


class WebPreview:
    """
    画像認識を使うコマンドに渡す、認識した位置の表示先(tkinter 版の CaptureArea の代わり)。
    座標は取り込み画像の上の値のままブラウザへ送り、ブラウザが画像の上に描く
    """

    def __init__(self, camera: Camera | None, send: Callable[[dict], None]):
        """
        camera: カメラ(取り込みサイズを読む。None で作った場合は、使う前に self.camera に入れる)
        send: ブラウザへ送る関数(任意のスレッドから呼べること)
        """
        self.camera = camera
        self._send = send

    def _base(self, kind: str, tag: object, ms: float, flag: bool) -> dict:
        """ブラウザへ送る表示の、共通の部分(種類・tag・表示する時間・取り込みサイズ)"""
        width, height = self.camera.capture_size
        return {
            "type": "overlay",
            "kind": kind,
            "tag": str(tag),
            # flag が False の枠は、同じ tag の次の表示が消えるときに一緒に消える
            "ms": int(ms) if flag else None,
            "capture": [width, height],
        }

    def ImgRect(
        self, x1: float, y1: float, x2: float, y2: float, outline: str, tag: object, ms: float, flag: bool = True
    ) -> None:
        """
        枠を表示する(座標は、取り込み画像の上の値)。
        outline: 色、tag: 表示の名前(消すときに使う)、ms: 表示する時間(ミリ秒)
        flag: False の枠は、時間では消さず、同じ tag の次の表示が消えるときに一緒に消す
        """
        message = self._base("rect", tag, ms, flag)
        message.update({"x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2), "color": str(outline)})
        self._send(message)

    def ImgText(
        self,
        x1: float,
        y1: float,
        txt: object,
        tag: object,
        ms: float,
        ft: tuple = ("UD デジタル 教科書体 NP-B", 20),
        color: str = "black",
        flag: bool = True,
    ) -> None:
        """
        文字を表示する(座標は、取り込み画像の上の値)。
        txt: 表示する文字、tag: 表示の名前、ms: 表示する時間(ミリ秒)、color: 色
        ft: (フォントの名前, 大きさ)。Web 版では、大きさだけを使う
        """
        message = self._base("text", tag, ms, flag)
        message.update({"x": float(x1), "y": float(y1), "text": str(txt), "size": int(ft[1]), "color": str(color)})
        self._send(message)

    def deleteImageRect(self, tag: object) -> None:
        """その tag の表示(枠と文字)を消す"""
        self._send({"type": "overlay", "kind": "delete", "tag": str(tag)})

    def deleteImageText(self, tag: object) -> None:
        """その tag の表示(枠と文字)を消す(deleteImageRect と同じ)"""
        self.deleteImageRect(tag)
