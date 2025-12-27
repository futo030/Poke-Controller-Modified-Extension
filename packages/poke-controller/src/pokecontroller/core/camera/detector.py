import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2

from pokecontroller.utils import platform

logger = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    """検出されたカメラの情報を保持するデータクラス.

    Attributes:
        index: カメラのインデックス番号.
        name: カメラの名前.
        backend: カメラが使用するバックエンドの名前. 省略可能.
    """

    index: int
    name: str
    backend: str | None = None


class CameraDetector:
    """システムに接続されているカメラデバイスを検出するクラス.

    このクラスは、Windows、macOS、Linuxの各プラットフォームで利用可能な
    カメラデバイスを検出し、その情報を取得します。
    """

    def __init__(self, max_cameras: int) -> None:
        """CameraDetectorインスタンスを初期化します.

        Args:
            max_cameras: 検出を試みるカメラの最大数.
        """
        self._max_cameras = max_cameras

    def detect(self) -> list[CameraInfo]:
        """システムに接続されているカメラを検出します.

        指定された最大カメラ数まで順番にカメラデバイスを開いて確認し、
        利用可能なカメラの情報を収集します。各プラットフォーム固有の
        方法でカメラ名を取得します。

        Returns:
            検出されたカメラ情報のリスト. 各要素はCameraInfoインスタンス.
        """
        camera_names = self._get_all_camera_names()
        logger.debug(f"camera_name_map: {camera_names}")

        cameras: list[CameraInfo] = []
        for i in range(self._max_cameras):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                name = camera_names[i] if i < len(camera_names) else f"Camera {i}"
                backend = cap.getBackendName()
                cameras.append(CameraInfo(i, name, backend))
                cap.release()
                logger.debug(f"Found camera {i}: {name} (backend: {backend})")

        logger.info(f"Found {len(cameras)} cameras.")
        return cameras

    def _get_all_camera_names(self) -> list[str]:
        if platform.is_windows():
            return self._get_windows_camera_names()
        elif platform.is_macos():
            return self._get_macos_camera_names()
        elif platform.is_linux():
            return self._get_linux_camera_names()
        else:
            return []

    def _get_windows_camera_names(self) -> list[str]:
        try:
            import clr

            # XXX
            direct_show_lib_path = (
                Path(__file__).parent.parent.parent.parent.parent.parent.parent
                / "DirectShowLib"
                / "DirectShowLib-2005.dll"
            )
            clr.AddReference(str(direct_show_lib_path))
            from DirectShowLib import (  # type: ignore[attr-defined]
                DsDevice,
                FilterCategory,
            )

            return [
                device.Name
                for device in DsDevice.GetDevicesOfCat(FilterCategory.VideoInputDevice)
            ]
        except Exception as e:
            logger.warning(f"DirectShowLib not available, falling back to ffmpeg: {e}")
            return self._get_windows_camera_names_ffmpeg()

    def _get_windows_camera_names_ffmpeg(self) -> list[str]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                capture_output=True,
                text=True,
                stderr=subprocess.STDOUT,
                timeout=5,
            )
            lines = result.stdout.splitlines()
            cameras = []
            in_video_section = False

            for line in lines:
                if "DirectShow video devices" in line:
                    in_video_section = True
                    continue
                if "DirectShow audio devices" in line:
                    break
                if in_video_section:
                    match = re.search(r'"([^"]+)"', line)
                    if match:
                        cameras.append(match.group(1))
            return cameras

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"ffmpeg not available, falling back to PowerShell: {e}")
            return self._get_windows_camera_names_powershell()

    def _get_windows_camera_names_powershell(self) -> list[str]:
        try:
            ps_command = (
                "Get-CimInstance Win32_PnPEntity | "
                + "Where-Object {$_.PNPClass -eq 'Camera' -or $_.PNPClass -eq 'Image'} | "
                + "Select-Object -ExpandProperty Name"
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return [
                    name.strip() for name in result.stdout.splitlines() if name.strip()
                ]
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to get camera names via PowerShell: {e}")

        return []

    def _get_macos_camera_names(self) -> list[str]:
        try:
            result = subprocess.run(
                ["system_profiler", "SPCameraDataType"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return re.findall(r"Model ID:\s*(.+)", result.stdout)

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to get camera names via system_profiler: {e}")

        return []

    def _get_linux_camera_names(self) -> list[str]:
        return []
