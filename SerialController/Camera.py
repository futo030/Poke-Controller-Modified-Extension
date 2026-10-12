#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, TYPE_CHECKING

import cv2
import datetime
import os
import threading
import time
from logging import getLogger, DEBUG, NullHandler

from PIL import Image

from WindowCapture import WindowCapture

if TYPE_CHECKING:
    import numpy


def imwrite(filename: str, img: numpy.ndarray, params: list[int] | None = None) -> bool:
    """
    画像をファイルに保存する(cv2.imwrite と違い、日本語などを含むパスにも保存できる)。保存できたかを返す
    filename: 保存先(拡張子で形式が決まる)、img: 保存する画像(BGR)
    params: cv2.imencode に渡す設定(例: [cv2.IMWRITE_JPEG_QUALITY, 90]。None なら既定)
    失敗した場合は、例外にせず、理由を表示して False を返す
    """
    _logger = getLogger(__name__)
    _logger.addHandler(NullHandler())
    _logger.setLevel(DEBUG)
    _logger.propagate = True
    try:
        ext = os.path.splitext(filename)[1]
        result, n = cv2.imencode(ext, img, params)

        if result:
            with open(filename, mode="w+b") as f:
                n.tofile(f)
            return True
        else:
            return False
    except Exception as e:
        print(e)
        _logger.error(f"Image Write Error: {e}")
        return False


CAPTURE_DIR = "./Captures/"

# カメラ・ウィンドウ以外の映像ソース。 識別名 -> (Deviceの一覧に出す名前, ソースを作る関数(識別名, 取り込みサイズ))
# ソースは cv2.VideoCapture と同じ呼び方(isOpened / read / release)で使えるもの。追加の機能が、起動時に登録する
EXTRA_SOURCES = {}


def _get_save_filespec(filename: str) -> str:
    """
    画像ファイルの保存パスを取得する。

    入力が絶対パスの場合は、`CAPTURE_DIR`につなげずに返す。

    Args:
        filename (str): 保存名／保存パス

    Returns:
        str: 保存パス
    """
    if os.path.isabs(filename):
        return filename
    else:
        return os.path.join(CAPTURE_DIR, filename)


# readFrame()で次のフレームを待つ最大時間(秒)
FRAME_WAIT_TIMEOUT = 1.0

CAPTURE_SIZE_LIST = ["720x480", "1280x720", "1920x1080", "400x480", "256x384"]
DEFAULT_CAPTURE_SIZE = "1280x720"

# 取り込みサイズごとの表示サイズ候補(取り込み画像の縦横比を保つ)と既定値
# 1280x720 と 1920x1080 は縦横比が同じ(16:9)なので、同じ候補を使う
_SHOW_SIZE_LIST_16_9 = ["284x160", "320x180", "640x360", "960x540", "1280x720", "1600x900", "1920x1080"]
SHOW_SIZE_LIST = {
    "720x480": ["240x160", "360x240", "720x480", "1080x720", "1440x960"],  # 3:2
    "1280x720": _SHOW_SIZE_LIST_16_9,
    "1920x1080": _SHOW_SIZE_LIST_16_9,
    "400x480": ["133x160", "200x240", "400x480", "600x720", "800x960"],  # 5:6
    "256x384": ["107x160", "128x192", "256x384", "384x576", "512x768"],  # 2:3
}
DEFAULT_SHOW_SIZE = {
    "720x480": "720x480",
    "1280x720": "640x360",
    "1920x1080": "640x360",
    "400x480": "400x480",
    "256x384": "256x384",
}


def parse_capture_size(size: str) -> tuple[int, int]:
    """
    "WIDTHxHEIGHT"形式の文字列を(width, height)に変換する。

    不正な値の場合はデフォルトの取り込みサイズを返す。
    """
    try:
        width, height = map(int, str(size).lower().split("x"))
        if width > 0 and height > 0:
            return width, height
    except ValueError:
        pass
    width, height = map(int, DEFAULT_CAPTURE_SIZE.split("x"))
    return width, height


class Camera:
    """
    カメラ(または、ウィンドウなどの映像ソース)の取り込み。
    読み取りは専用のスレッドで行い、最新のフレームを保持する
    """

    def __init__(self, fps: int = 45, capture_size: str = DEFAULT_CAPTURE_SIZE):
        """
        fps: フレームレート(MJPG で取り込むときに、カメラに要求する値)
        capture_size: 取り込みサイズ("幅x高さ"。読めない値は、既定の取り込みサイズにする)
        """
        self.camera = None
        self.capture_size = parse_capture_size(capture_size)
        self.capture_dir = "Captures"
        self.fps = int(fps)

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        # カメラの読み取りは専用スレッドで行い、最新フレームを保持する
        # (画面表示とコマンド実行スレッドがVideoCaptureを取り合わないようにする)
        self._lock = threading.Lock()
        self._frame_updated = threading.Condition(self._lock)
        self._frame = None
        self._frame_seq = 0
        # スレッド毎に最後に返したフレームの通し番号
        self._last_read_seq = {}
        self._reader = None
        self._reader_stop = None
        # 画面表示用画像(PIL, RGB)。変換も読み取りスレッドで行い、メインスレッドの負荷を減らす
        self._display_size = None
        self._display_image = None
        # 明るさを変える前の画面表示用画像(スクリーンショットの保存時に使う)
        self._display_raw = None
        self._display_seq = 0
        # 画面表示用画像の明るさを変える変換表(PIL の point に渡す。None なら変えない)。
        # プレビューの表示だけに使い、カメラ画像(キャプチャー・コマンドの画像処理)には使わない
        self._display_lut = None
        # スクリーンショットの保存時に、カメラ画像に掛ける処理(目隠し等。Noneなら何もしない)
        # BGR画像を受け取り、処理した画像を返す関数(元の画像は書き換えないこと)
        self.capture_filter = None
        # MJPG(圧縮形式)で取り込むか。Falseならカメラの既定の形式(多くは非圧縮)で取り込む。
        # 非圧縮ではUSBの帯域が足りず、取り込みサイズによってはフレームレートが下がる機器がある。
        # MJPGにするとフレームレートは上がるが、圧縮による画質の劣化が入る(次にカメラを開くときに反映する)
        self.use_mjpg = False

    def openCamera(self, cameraId: int, window: str | None = None) -> None:
        """
        カメラを開いて、読み取りを始める(すでに開いている場合は、閉じてから開く)。開けない場合は、理由を表示する
        cameraId: カメラの番号
        window: 取り込むウィンドウの識別名(WindowCapture)、または EXTRA_SOURCES の識別名。
                指定した場合は、カメラの代わりにそれを取り込む
        """
        if self.camera is not None and self.camera.isOpened():
            self._logger.debug("Camera is already opened")
            self.destroy()

        if window:
            if window in EXTRA_SOURCES:
                self.camera = EXTRA_SOURCES[window][1](window, self.capture_size)
            else:
                self.camera = WindowCapture(window, self.capture_size)
            if self.camera.isOpened():
                self._start_reader()
            return

        if os.name == "nt":
            self._logger.debug("NT OS")
            self.camera = cv2.VideoCapture(cameraId, cv2.CAP_DSHOW)
        # self.camera = cv2.VideoCapture(cameraId)
        else:
            self._logger.debug("Not NT OS")
            self.camera = cv2.VideoCapture(cameraId)

        if not self.camera.isOpened():
            print("Camera ID " + str(cameraId) + " can't open.")
            self._logger.error(f"Camera ID {cameraId} cannot open.")
            return
        print("Camera ID " + str(cameraId) + " opened successfully")
        self._logger.debug(f"Camera ID {cameraId} opened successfully.")
        # print(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        # self.camera.set(cv2.CAP_PROP_FPS, 60)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[0])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[1])
        if self.use_mjpg:
            # サイズ → フレームレート → 形式 の順に指定する
            # (形式を指定した後にサイズを指定すると、非圧縮に戻る機器がある)
            # フレームレートは self.fps (CameraタブのFPS)を要求する。
            # 機器が対応していない値の場合は、機器が選んだフレームレートになる
            self.camera.set(cv2.CAP_PROP_FPS, self.fps)
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            actual_format = self.getFormat()
            if actual_format == "MJPG":
                print(f"Capture format: MJPG (requested {self.fps} fps)")
                self._logger.debug(f"Capture format: MJPG (requested {self.fps} fps)")
            else:
                print(f"Requested capture format MJPG, but device returned {actual_format}.")
                self._logger.warning(f"Capture format mismatch: requested MJPG, actual {actual_format}")
        actual_size = (
            int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if actual_size != self.capture_size:
            print(
                f"Requested capture size {self.capture_size[0]}x{self.capture_size[1]}, "
                f"but device returned {actual_size[0]}x{actual_size[1]}."
            )
            self._logger.warning(f"Capture size mismatch: requested {self.capture_size}, actual {actual_size}")
        else:
            self._logger.debug(f"Capture size: {self.capture_size[0]}x{self.capture_size[1]}")
        self._start_reader()

    def getFormat(self) -> str:
        """
        取り込み中の映像の形式(FOURCC。例: "YUY2", "MJPG")
        文字として読めない値の場合は、16進数で返す
        """
        if self.camera is None:
            return ""
        if not isinstance(self.camera, cv2.VideoCapture):
            return "Window" if isinstance(self.camera, WindowCapture) else type(self.camera).__name__
        value = int(self.camera.get(cv2.CAP_PROP_FOURCC)) & 0xFFFFFFFF
        chars = [chr((value >> (8 * i)) & 0xFF) for i in range(4)]
        if all(c.isascii() and (c.isalnum() or c == " ") for c in chars):
            return "".join(chars).strip()
        return f"0x{value:08X}"

    def setCaptureSize(self, size: str, cameraId: int, window: str | None = None) -> None:
        """
        取り込みサイズを変更し、カメラ取り込みを再起動する。
        size: 取り込みサイズ("幅x高さ")、cameraId / window: openCamera と同じ
        """
        self.capture_size = parse_capture_size(size)
        print(f"Changed capture size to: {self.capture_size[0]}x{self.capture_size[1]}")
        self._logger.info(f"Changed capture size to: {self.capture_size[0]}x{self.capture_size[1]}")
        self.openCamera(cameraId, window)

    # self.camera.set(cv2.CAP_PROP_SETTINGS, 0)

    def isOpened(self) -> bool:
        """カメラを開いているか(一度も開いていない場合は False)"""
        self._logger.debug("Camera is opened")
        return self.camera is not None and bool(self.camera.isOpened())

    def _start_reader(self) -> None:
        """読み取りのスレッドを始める(動いている場合は、止めてから始める)"""
        self._stop_reader()
        with self._lock:
            self._frame = None
            self._display_image = None
            self._display_raw = None
        self._reader_stop = threading.Event()
        self._reader = threading.Thread(
            target=self._read_loop, args=(self.camera, self._reader_stop), name="CameraReader", daemon=True
        )
        self._reader.start()

    def _stop_reader(self) -> None:
        """読み取りのスレッドを止める(最大 2 秒待つ)"""
        if self._reader is not None:
            self._reader_stop.set()
            self._reader.join(timeout=2.0)
            self._reader = None
            self._reader_stop = None

    def _read_loop(self, camera: cv2.VideoCapture | WindowCapture, stop: threading.Event) -> None:
        """
        フレームを読み続け、最新のフレームと、画面表示用の画像を更新する(スレッドの中身。stop が立つまで)
        camera: 読み取る映像ソース(cv2.VideoCapture と同じ呼び方で使えるもの。EXTRA_SOURCES のソースを含む)
        """
        while not stop.is_set():
            ret, frame = camera.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue
            display_size = self._display_size
            display_image = display_raw = None
            if display_size is not None:
                image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                display_raw = Image.fromarray(image_rgb).resize(display_size)
                # 明るさは、縮めた後の表示用画像にだけ掛ける(元のフレームは変えない)
                display_image = self.adjustDisplayImage(display_raw)
            with self._lock:
                if stop.is_set():
                    break
                self._frame = frame
                self._frame_seq += 1
                self._frame_updated.notify_all()
                if display_image is not None:
                    self._display_image = display_image
                    self._display_raw = display_raw
                    self._display_seq += 1

    @property
    def image_bgr(self) -> numpy.ndarray | None:
        """
        最新フレーム(コピーしないので書き換えないこと。未取得・カメラ未オープンの場合は None)
        """
        with self._lock:
            return self._frame

    def latestFrame(self) -> tuple[numpy.ndarray | None, int]:
        """
        最新フレームと、その通し番号を返す(コピーしないので書き換えないこと。待たない)。
        通し番号は、新しいフレームを読むたびに増える(前に見たフレームと同じかどうかを、番号で確かめられる)。
        未取得・カメラ未オープンの場合、フレームは None
        """
        with self._lock:
            return self._frame, self._frame_seq

    def readFrame(self, timeout: float = FRAME_WAIT_TIMEOUT) -> numpy.ndarray | None:
        """
        最新フレームのコピーを返す(未取得・カメラ未オープンの場合はNone)
        同じスレッドから続けて呼ばれ、前回と同じフレームしかない場合は次のフレームを待つ
        (従来のVideoCapture.read()と同様に、呼ぶたびに新しいフレームを返す)
        メインスレッドからの呼び出しでは待たない
        timeout: 次のフレームを待つ時間の上限(秒)
        """
        ident = threading.get_ident()
        with self._frame_updated:
            if (
                self._frame is not None
                and self._reader is not None
                and threading.current_thread() is not threading.main_thread()
                and self._last_read_seq.get(ident) == self._frame_seq
            ):
                self._frame_updated.wait(timeout)
            frame = self._frame
            self._last_read_seq[ident] = self._frame_seq
        return None if frame is None else frame.copy()

    def setDisplaySize(self, size: tuple[int, int] | None) -> None:
        """
        画面表示用画像のサイズを設定する(None: 表示用画像を生成しない)
        """
        self._display_size = None if size is None else tuple(size)

    def setDisplayAdjust(self, gain: int = 100, gamma: float = 1.0) -> None:
        """
        画面表示用画像(プレビュー・タッチスクリーンの表示)の明るさを設定する
        gain: 色の値を何%にするか(100 で変えない) / gamma: ガンマ(1.0 で変えない。大きいほど暗い部分が明るくなる)
        """
        if gain == 100 and gamma == 1.0:
            self._display_lut = None
            return
        table = [min(255, int(round(255.0 * (value / 255.0) ** (1.0 / gamma) * gain / 100.0))) for value in range(256)]
        # R・G・B の3つに同じ表を使う
        self._display_lut = table * 3

    def isDisplayAdjusted(self) -> bool:
        """画面表示用画像の明るさを変える設定になっているか"""
        return self._display_lut is not None

    def adjustDisplayImage(self, image: Image.Image | None) -> Image.Image | None:
        """
        画面表示用の画像(PIL, RGB)に、設定した明るさを掛けた画像を返す(元の画像は変えない)
        明るさを変えない設定の場合と、image が None の場合は、image をそのまま返す
        """
        lut = self._display_lut
        if lut is None or image is None:
            return image
        return image.point(lut)

    def getDisplayImage(self, raw: bool = False) -> tuple[Image.Image | None, int]:
        """
        画面表示用画像とその通し番号を返す(未生成・サイズ不一致の場合は画像がNone)
        raw: 明るさを変える前の画像を返す(スクリーンショットの保存時)
        """
        with self._lock:
            image, seq = (self._display_raw if raw else self._display_image), self._display_seq
            if self._frame is None:
                image = None
        if image is not None and image.size != self._display_size:
            image = None
        return image, seq

    def saveCapture(
        self,
        filename: str | None = None,
        crop: int | str | None = None,
        crop_ax: List[int] | None = None,
        img: numpy.ndarray | None = None,
    ) -> None:
        """
        最新のカメラ画像を、PNG で保存する(capture_filter がある場合は、それを掛けた画像)。
        filename: 保存名(拡張子なし。".png" を足す。None や空文字なら日時の名前)。
                  相対パスは CAPTURE_DIR の中、絶対パスはその場所に保存する
        crop: 切り抜き方。None: 切り抜かない / 1 または "1": crop_ax を [x1, y1, x2, y2] として切り抜く /
              2 または "2": crop_ax を [x, y, 幅, 高さ] として切り抜く / それ以外: 切り抜かない
        crop_ax: 切り抜く範囲(None なら画像の全体)
        img: カメラ画像の代わりに保存する画像(BGR)。渡した場合は、切り抜きも、この画像に対して行う
             (capture_filter は掛けない)
        保存できなかった場合(画像がない、書き込めないなど)は、例外にせず、"Capture Failed" と表示する
        """
        if crop_ax is None:
            crop_ax = [0, 0, self.capture_size[0], self.capture_size[1]]
        else:
            pass
            # print(crop_ax)

        dt_now = datetime.datetime.now()
        if filename is None or filename == "":
            filename = dt_now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        else:
            filename = filename + ".png"

        # 保存するカメラ画像(目隠しを保存にも適用する設定の場合は、目隠しを描いた画像)
        # img を渡された場合は、カメラ画像の代わりに、その画像を保存する
        if img is not None:
            frame = img
        else:
            frame = self.image_bgr
            if self.capture_filter is not None and frame is not None:
                frame = self.capture_filter(frame)

        save_path = _get_save_filespec(filename)
        if frame is None:
            # カメラを開いていない、または、まだ画像が届いていない
            print("Capture Failed")
            self._logger.error(f"Capture Failed: no image ({save_path})")
            return

        if crop == 1 or crop == "1":
            image = frame[crop_ax[1] : crop_ax[3], crop_ax[0] : crop_ax[2]]
        elif crop == 2 or crop == "2":
            image = frame[crop_ax[1] : crop_ax[1] + crop_ax[3], crop_ax[0] : crop_ax[0] + crop_ax[2]]
        else:
            image = frame

        if not os.path.exists(os.path.dirname(save_path)) or not os.path.isdir(os.path.dirname(save_path)):
            # 保存先ディレクトリが存在しないか、同名のファイルが存在する場合（existsはファイルとフォルダを区別しない）
            os.makedirs(os.path.dirname(save_path))
            self._logger.debug("Created Capture folder")

        # imwrite は、失敗しても例外を出さずに False を返す
        try:
            saved = imwrite(save_path, image)
        except cv2.error as e:
            saved = False
            self._logger.error(f"Capture Failed :{e}")
        if saved:
            self._logger.debug(f"Capture succeeded: {save_path}")
            print("capture succeeded: " + save_path)
        else:
            print("Capture Failed")
            self._logger.error(f"Capture Failed: {save_path}")

    def destroy(self) -> None:
        """読み取りのスレッドを止めて、カメラを閉じる"""
        self._stop_reader()
        with self._lock:
            self._frame = None
            self._display_image = None
            self._display_raw = None
        if self.camera is not None and self.camera.isOpened():
            self.camera.release()
            self.camera = None
            self._logger.debug("Camera destroyed")
