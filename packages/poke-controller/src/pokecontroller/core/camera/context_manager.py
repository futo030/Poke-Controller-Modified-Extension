from contextlib import contextmanager
from typing import Generator

from pokecontroller.core.camera.camera import Camera


@contextmanager
def use_camera(
    frame_size: tuple[int, int] = (1280, 720),
) -> Generator[Camera, None, None]:
    """カメラを使用するためのコンテキストマネージャー.

    このコンテキストマネージャーを使用すると、Cameraインスタンスを自動的に
    管理でき、コンテキストを抜ける際に確実にカメラがクローズされます。

    Args:
        frame_size: カメラのフレームサイズを表す(幅, 高さ)のタプル.
            デフォルトは(1280, 720)です。

    Yields:
        Camera: 使用可能なCameraインスタンス.

    Examples:
        >>> with use_camera(frame_size=(1920, 1080)) as camera:
        ...     camera.open(camera_id=0)
        ...     success, frame = camera.read()
    """
    camera = Camera(frame_size=frame_size)
    try:
        yield camera
    finally:
        camera.close()
