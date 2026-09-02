import logging
from typing import overload

import cv2

from pokecontroller.core.image import RawImage
from pokecontroller.utils.platform import is_windows

logger = logging.getLogger(__name__)


class PokeControllerCameraException(Exception):
    """PokeControllerのカメラ関連エラーで発生する例外."""

    pass


class Camera:
    """ビデオフレームをキャプチャするためのカメラインターフェース.

    このクラスはcv2.VideoCaptureのラッパーを提供し、カメラデバイスの
    オープン、クローズ、フレームの読み込みなどの操作を行います。
    """

    def __init__(
        self,
        *,
        frame_size: tuple[int, int] = (1280, 720),
    ) -> None:
        """Cameraインスタンスを初期化します.

        Args:
            frame_size: カメラのフレームサイズを表す(幅, 高さ)のタプル.
                デフォルトは(1280, 720)です。
        """
        self._video_capture: cv2.VideoCapture | None = None
        self._frame: RawImage | None = None
        self._frame_size = frame_size

    @property
    def is_opened(self) -> bool:
        """カメラが現在開かれているかどうかを確認します.

        Returns:
            カメラが開かれて使用可能な場合はTrue、それ以外はFalse.
        """
        if self._video_capture is None:
            logger.debug("Camera is not opened")
            return False
        is_opened = self._video_capture.isOpened()
        logger.debug(f"Camera is_opened: {is_opened}")
        return is_opened

    @property
    def frame_size(self) -> tuple[int, int]:
        """現在のフレームサイズを取得します.

        Returns:
            フレームサイズを表す(幅, 高さ)のタプル.
        """
        return self._frame_size

    @frame_size.setter
    def frame_size(self, size: tuple[int, int]) -> None:
        """フレームサイズを設定します.

        Args:
            size: 設定するフレームサイズを表す(幅, 高さ)のタプル.
        """
        self._frame_size = size

    @property
    def frame(self) -> RawImage | None:
        """最後にキャプチャしたフレームを取得します.

        Returns:
            カメラがキャプチャした最後のフレーム。
            まだフレームがキャプチャされていない場合はNone.
        """
        return self._frame

    @overload
    def open(self, *, camera_id: int) -> None: ...

    @overload
    def open(self, *, camera_path: str) -> None: ...

    def open(
        self,
        *,
        camera_id: int | None = None,
        camera_path: str | None = None,
    ) -> None:
        """フレームをキャプチャするためにカメラデバイスを開きます.

        このメソッドは新しいカメラを開く前に、現在開いているカメラを閉じます。
        Windowsでは、より良い互換性のためにDirectShow (CAP_DSHOW) APIを使用します。

        Args:
            camera_id: カメラデバイスID（整数インデックス）。
                camera_pathとは排他的です。
            camera_path: カメラデバイスへのパス（文字列）。
                camera_idとは排他的です。

        Raises:
            PokeControllerCameraException: camera_idとcamera_pathのどちらも
                指定されていない場合。
        """
        self.close()

        if is_windows():
            logger.debug("Windows OS")
            if camera_id is not None:
                self._video_capture = cv2.VideoCapture(
                    index=camera_id, apiPreference=cv2.CAP_DSHOW
                )
            elif camera_path is not None:
                self._video_capture = cv2.VideoCapture(
                    filename=camera_path, apiPreference=cv2.CAP_DSHOW
                )
            else:
                raise PokeControllerCameraException(
                    "Camera ID or Name is not specified."
                )
        else:
            logger.debug("Not Windows OS")
            if camera_id is not None:
                self._video_capture = cv2.VideoCapture(index=camera_id)
            elif camera_path is not None:
                self._video_capture = cv2.VideoCapture(filename=camera_path)
            else:
                raise PokeControllerCameraException(
                    "Camera ID or Name is not specified."
                )

        if not self.is_opened:
            logger.error(f"Camera ID {camera_id} cannot open.")
            return

        logger.debug(f"Camera ID {camera_id} opened successfully.")
        vc = self._video_capture
        vc.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._frame_size[0]))
        vc.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._frame_size[1]))

    def close(self) -> None:
        """現在開いているカメラデバイスを閉じます.

        ビデオキャプチャリソースを解放し、内部状態をNoneに設定します。
        カメラが開かれていない場合、このメソッドは何もしません。
        """
        if (vc := self._video_capture) is None:
            logger.debug("Camera is not opened")
            return
        if vc.isOpened():
            logger.debug("Closing camera")
            vc.release()
            logging.debug("Camera closed")
        self._video_capture = None

    def read(self) -> tuple[bool, RawImage | None]:
        """カメラからフレームを読み込みます.

        開いているカメラデバイスから1フレームをキャプチャし、内部に保存します。
        キャプチャしたフレームはframeプロパティを通じてアクセスできます。

        Returns:
            (success, frame)のタプル。successはフレームが正常にキャプチャ
            された場合にTrue、frameはキャプチャされた画像データ、または
            キャプチャが失敗した場合やカメラが開かれていない場合はNone.
        """
        if (vc := self._video_capture) is None:
            return False, None

        if vc.isOpened():
            success, self._frame = vc.read()
            return success, self._frame
        return False, None
