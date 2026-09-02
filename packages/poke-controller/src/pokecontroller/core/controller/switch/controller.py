from pokecontroller.core.controller.button import ButtonState
from pokecontroller.core.controller.dpad import DpadState
from pokecontroller.core.controller.stick import StickState
from pokecontroller.core.controller.switch.serializers.leonardo import (
    SwitchControllerStateSerializer,
)
from pokecontroller.core.controller.switch.state import SwitchControllerState
from pokecontroller.core.serial import Serial


class SwitchController:
    """Nintendo Switchコントローラーを制御するクラス.

    シリアル通信を通じてSwitchコントローラーの状態を送信します。
    """

    def __init__(self, serial: Serial):
        """SwitchControllerインスタンスを初期化します.

        Args:
            serial: シリアル通信インスタンス.
        """
        self._state: SwitchControllerState = SwitchControllerState()
        self._serial: Serial = serial

    @property
    def state(self) -> SwitchControllerState:
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
    def lstick(self) -> StickState:
        """左アナログスティックの状態を取得します.

        Returns:
            左アナログスティック状態管理オブジェクト.
        """
        return self._state.lstick

    @property
    def rstick(self) -> StickState:
        """右アナログスティックの状態を取得します.

        Returns:
            右アナログスティック状態管理オブジェクト.
        """
        return self._state.rstick

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
        """現在のコントローラー状態をシリアルポートに送信します."""
        serialized = SwitchControllerStateSerializer.serialize(self._state)
        self._serial.write_line(serialized)
