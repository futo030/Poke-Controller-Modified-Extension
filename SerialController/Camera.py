# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import os
import threading
import time
from logging import DEBUG, NullHandler, getLogger
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    from collections.abc import Sequence
    from logging import Logger
    from typing import Literal

    from cv2.typing import MatLike


def imwrite(filename: str, img: MatLike, params: Sequence[int] | None = None) -> bool:
    _logger = getLogger(__name__)
    _logger.addHandler(NullHandler())
    _logger.setLevel(DEBUG)
    _logger.propagate = True
    try:
        ext = os.path.splitext(filename)[1]
        if params is None:
            result, n = cv2.imencode(ext, img)
        else:
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


def _get_save_filespec(filename: str) -> str:
    """
    画像ファイルの保存パスを取得する。

    入力が絶対パスの場合は、`CAPTURE_DIR`につなげずに返す。

    Args:
        filename (str): 保存名／保存パス

    Returns:
        str: _description_
    """
    if os.path.isabs(filename):
        return filename
    else:
        return os.path.join(CAPTURE_DIR, filename)


class Camera:
    def __init__(self, fps: int = 45) -> None:
        self.camera: cv2.VideoCapture | None = None
        self.fps: int = int(fps)
        self.capture_size: tuple[int, int] = (1280, 720)
        self.capture_dir: str = "Captures"
        self.image_bgr: MatLike = cv2.imread("../Images/disabled.png", cv2.IMREAD_COLOR)
        self.thread: threading.Thread
        self._logger: Logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    def openCamera(self, cameraId: int) -> None:
        if self.camera is not None and self.camera.isOpened():
            self._logger.debug("Camera is already opened")
            self.destroy()

        if os.name == "nt":
            self._logger.debug("NT OS")
            self.camera = cv2.VideoCapture(cameraId, cv2.CAP_DSHOW)
        else:
            self._logger.debug("Not NT OS")
            self.camera = cv2.VideoCapture(cameraId)

        if not self.camera.isOpened():
            print("Camera ID " + str(cameraId) + " can't open.")
            self._logger.error(f"Camera ID {cameraId} cannot open.")
            return
        print("Camera ID " + str(cameraId) + " opened successfully")
        self._logger.debug(f"Camera ID {cameraId} opened successfully.")
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[0])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[1])
        self.camera_thread_start()

    def isOpened(self) -> bool:
        if self.camera is not None:
            return self.camera.isOpened()
        else:
            return False

    def readFrame(self) -> MatLike:
        return self.image_bgr

    def saveCapture(
        self,
        filename: str | None = None,
        crop: int | Literal["1"] | Literal["2"] | None = None,
        crop_ax: list[int] | None = None,
        img: MatLike | None = None,
    ) -> None:
        if crop_ax is None:
            crop_ax = [0, 0, 1280, 720]

        dt_now = datetime.datetime.now()
        if filename is None or filename == "":
            filename = dt_now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        else:
            filename = filename + ".png"

        if crop is None:
            image = self.image_bgr
        elif crop == 1 or crop == "1":
            image = self.image_bgr[crop_ax[1] : crop_ax[3], crop_ax[0] : crop_ax[2]]
        elif crop == 2 or crop == "2":
            image = self.image_bgr[
                crop_ax[1] : crop_ax[1] + crop_ax[3],
                crop_ax[0] : crop_ax[0] + crop_ax[2],
            ]
        elif img is not None:
            image = img
        else:
            image = self.image_bgr

        save_path = _get_save_filespec(filename)

        if not os.path.exists(os.path.dirname(save_path)) or not os.path.isdir(
            os.path.dirname(save_path)
        ):
            # 保存先ディレクトリが存在しないか、同名のファイルが存在する場合（existsはファイルとフォルダを区別しない）
            os.makedirs(os.path.dirname(save_path))
            self._logger.debug("Created Capture folder")

        try:
            imwrite(save_path, image)
            self._logger.debug(f"Capture succeeded: {save_path}")
            print("capture succeeded: " + save_path)
        except cv2.error as e:
            print("Capture Failed")
            self._logger.error(f"Capture Failed :{e}")

    def destroy(self) -> None:
        if self.camera is not None and self.camera.isOpened():
            self.camera.release()
            self.camera_thread_stop()
            time.sleep(0.1)  # sleepしないと同じカメラを開けない
            self._logger.debug("Camera destroyed")

    def camera_thread_start(self) -> None:
        if self.camera is None:
            self._logger.error("Camera is not opened")
            return
        self._logger.debug("Camera thread starting")
        self.thread = threading.Thread(target=self.camera_update, name="CameraThread")
        self.thread.start()

    def camera_thread_stop(self) -> None:
        if self.camera is None:
            self._logger.error("Camera is not opened")
            return
        self._logger.debug("Camera thread stopping")
        self.thread.join()
        self.camera.release()
        self._logger.debug("Camera thread stopped")

    def camera_update(self) -> None:
        if self.camera is None:
            self._logger.error("Camera is not opened")
            return
        else:
            self._logger.debug("Camera update thread started")
            while self.isOpened():
                ret, frame = self.camera.read()
                if ret:
                    self.image_bgr = frame
