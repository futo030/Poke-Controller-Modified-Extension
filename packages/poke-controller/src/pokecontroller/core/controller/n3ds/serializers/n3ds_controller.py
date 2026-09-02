from pokecontroller.core.controller.n3ds.state import N3dsControllerState


class N3dsControllerStateSerializer:
    """3DS Controller形式でコントローラー状態をシリアライズするクラス."""

    @staticmethod
    def serialize(state: N3dsControllerState) -> list[int]:
        """コントローラー状態を3DS Controller形式のバイト列にシリアライズします.

        Args:
            state: シリアライズするコントローラー状態.

        Returns:
            シリアライズされたバイト値のリスト.
        """
        headers = [0xA1, 0xA2]
        buttons = state.button.value
        dpad = state.dpad.value
        stick_x = state.stick.x if state.stick.x >= 128 else 127 - state.stick.x
        stick_y = state.stick.y if state.stick.y >= 128 else 127 - state.stick.y

        return [
            headers[0],
            ((buttons & 0xF) << 4) | dpad,
            (buttons >> 4) & 0x3F,
            headers[1],
            stick_x,
            stick_y,
        ]
