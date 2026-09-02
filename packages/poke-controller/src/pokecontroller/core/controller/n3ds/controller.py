import logging

from pokecontroller.core.controller.button import ButtonState
from pokecontroller.core.controller.dpad import DpadState
from pokecontroller.core.controller.n3ds.serializers.n3ds_controller import (
    N3dsControllerStateSerializer as N3dsControllerSerializer,
)
from pokecontroller.core.controller.n3ds.serializers.qingpi import (
    N3dsControllerStateSerializer as QingpiSerializer,
)
from pokecontroller.core.controller.n3ds.state import N3dsControllerState
from pokecontroller.core.controller.n3ds.touchscreen import N3dsTouchscreenState
from pokecontroller.core.controller.stick import StickState
from pokecontroller.core.serial import Serial

logger = logging.getLogger(__name__)


class N3dsController:
    """ニンテンドー3DSコントローラーを制御するクラス.

    シリアル通信を通じて3DSコントローラーの状態を送信します。
    複数のシリアライゼーション形式（QingPi、3DS Controller）に対応しています。
    """

    def __init__(self, serial: Serial, fmt: str):
        """N3dsControllerインスタンスを初期化します.

        Args:
            serial: シリアル通信インスタンス.
            fmt: シリアライゼーション形式（"qingpi"または"3ds controller"）.
        """
        self._state: N3dsControllerState = N3dsControllerState()
        self._serial: Serial = serial
        self.format = fmt

    @property
    def format(self) -> str:
        """シリアライゼーション形式を取得します.

        Returns:
            現在の形式名（小文字）.
        """
        return self._format

    @format.setter
    def format(self, value: str) -> None:
        """シリアライゼーション形式を設定します.

        Args:
            value: 形式名（"qingpi"または"3ds controller"）.
        """
        self._format = value.lower()
        self._is_qingpi = self._format == "qingpi"
        self._is_3ds_controller = self._format == "3ds controller"

    @property
    def state(self) -> N3dsControllerState:
        """コントローラーの状態を取得します.

        Returns:
            現在のコントローラー状態.
        """
        return self._state

    @property
    def buttons(self) -> ButtonState:
        """ボタンの状態を取得します.

        Returns:
            ボタン状態管理オブジェクト.
        """
        return self._state.button

    @property
    def dpad(self) -> DpadState:
        """十字キーの状態を取得します.

        Returns:
            十字キー状態管理オブジェクト.
        """
        return self._state.dpad

    @property
    def stick(self) -> StickState:
        """アナログスティックの状態を取得します.

        Returns:
            アナログスティック状態管理オブジェクト.
        """
        return self._state.stick

    @property
    def touchscreen(self) -> N3dsTouchscreenState:
        """タッチスクリーンの状態を取得します.

        Returns:
            タッチスクリーン状態管理オブジェクト.
        """
        return self._state.touchscreen

    @property
    def is_opened(self) -> bool:
        """シリアルポートが開かれているかどうかを取得します.

        Returns:
            シリアルポートが開かれている場合はTrue、それ以外はFalse.
        """
        return self._serial.is_opened

    def open(self, name: str, baud_rate: int) -> None:
        """シリアルポートを開きます.

        Args:
            name: シリアルポート名.
            baud_rate: ボーレート.
        """
        self._serial.open(name, baud_rate)

    def close(self) -> None:
        """シリアルポートを閉じます."""
        self._serial.close()

    def send_state(self) -> None:
        """現在のコントローラー状態をシリアルポートに送信します.

        設定された形式に基づいて状態をシリアライズし、送信します。
        """
        if self._is_qingpi:
            serialized = QingpiSerializer.serialize(self._state)
        elif self._is_3ds_controller:
            serialized = N3dsControllerSerializer.serialize(self._state)
        else:
            logger.warning(f"Unknown format: {self._format}")
            return
        self._serial.write(serialized)  # type: ignore[arg-type]
