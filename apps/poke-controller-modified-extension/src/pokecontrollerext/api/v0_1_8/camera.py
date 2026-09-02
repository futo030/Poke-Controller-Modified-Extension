import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Sequence

import cv2
from pokecontroller.core import (
    camera as cameralib,
    image as imagelib,
)
from pokecontroller.core.image import utils as imagelib_utils
from pokecontroller.utils import (
    datetime as datetimelib,
)

from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)

logger = logging.getLogger(__name__)


def imwrite(
    filename: str,
    img: imagelib.RawImage,
    params: Sequence[int],
) -> bool:
    """
    画像を書き込む
    """
    try:
        return imagelib.write(img, filename, params)
    except Exception as e:
        logger.error(f"Image Write Error: {e}")
        return False


CAPTURE_DIR = "Captures"


def _get_save_filespec(filename: str) -> str:
    """
    画像ファイルの保存パスを取得する。

    入力が絶対パスの場合は、`CAPTURE_DIR`につなげずに返す。

    Args:
        filename (str): 保存名／保存パス

    Returns:
        str: _description_
    """
    filepath = Path(filename)
    if filepath.is_absolute():
        return filename
    else:
        capture_dir = Path(CAPTURE_DIR)
        return str((capture_dir / filename).resolve())


class Camera:
    _camera: cameralib.Camera

    def __init__(self, fps: int = 45):
        self.image_bgr: imagelib.RawImage | None = None
        resources = get_app_resources()
        self._camera = resources.camera
        self._fps = fps
        self.capture_dir = "Captures"

    @property
    def camera(self) -> cv2.VideoCapture | None:
        return self._camera._video_capture

    @property
    def fps(self) -> int:
        return self._fps

    @fps.setter
    def fps(self, fps: int) -> None:
        # fpsを変更しても何も起こらない
        pass

    @property
    def capture_size(self) -> tuple[int, int]:
        return self._camera.frame_size

    @capture_size.setter
    def capture_size(self, size: tuple[int, int]) -> None:
        self._camera.frame_size = size

    def openCamera(self, cameraId: int) -> None:  # noqa
        self._camera.open(camera_id=cameraId)

    def isOpened(self) -> bool:  # noqa
        return self._camera.is_opened

    def readFrame(self) -> imagelib.RawImage | None:  # noqa
        _, self.image_bgr = self._camera.read()
        return self.image_bgr

    def saveCapture(  # noqa
        self,
        filename: str | None = None,
        crop: int | None = None,
        crop_ax: list[int] | None = None,
        img: imagelib.RawImage | None = None,
    ) -> None:
        if crop_ax is None:
            c = [0, 0, self.capture_size[0], self.capture_size[1]]
        else:
            c = crop_ax

        if img is not None:
            src = img
        elif self.image_bgr is not None:
            src = self.image_bgr
        else:
            # 保存するべきものが何もないのでここで処理を終える
            logger.warning("No image to save")
            return

        crop_fmt = int(crop) if crop is not None else None
        if crop_fmt is None:
            image = src
        else:
            imagelib_utils.convert_to_default(c, crop_fmt)
            args = imagelib.ImageCropArgs(
                sy=c[0],
                ey=c[1],
                sx=c[2],
                ex=c[3],
            )
            image = imagelib.crop(src, args)

        if not filename:
            fn = f"{datetimelib.format_datetime()}.png"
        else:
            fn = filename + ".png"
        save_path = Path(_get_save_filespec(fn))
        save_dir = save_path.parent
        if not save_dir.exists() or not save_dir.is_dir():
            save_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Created Capture folder")

        try:
            imwrite(str(save_path), image, [])
            logger.debug(f"Capture succeeded: {save_path}")
        except Exception as e:
            logger.error(f"Capture Failed :{e}")

    def destroy(self) -> None:
        self._camera.close()


@contextmanager
def use_camera(
    fps: int = 45,
) -> Generator[Camera, None, None]:
    camera = Camera(fps=fps)
    try:
        yield camera
    finally:
        camera.destroy()
