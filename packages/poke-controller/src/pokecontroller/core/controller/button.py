class ButtonState:
    """ボタンの押下状態を管理するクラス.

    ビットフラグを使用して複数のボタンの押下状態を効率的に管理します。
    """

    def __init__(self) -> None:
        """ButtonStateインスタンスを初期化します."""
        self._value = 0

    @property
    def value(self) -> int:
        """現在のボタン状態を取得します.

        Returns:
            ボタン状態を表すビットフラグの整数値.
        """
        return self._value

    def reset(self) -> None:
        """ボタン状態をリセットします.

        すべてのボタンを未押下の状態にします。
        """
        self._value = 0

    def push(self, buttons: list[int]) -> None:
        """指定されたボタンを押下状態にします.

        Args:
            buttons: 押下するボタンのビットフラグのリスト.
        """
        for button in buttons:
            self._value |= button

    def release(self, buttons: list[int]) -> None:
        """指定されたボタンを未押下状態にします.

        Args:
            buttons: 解放するボタンのビットフラグのリスト.
        """
        for button in buttons:
            self._value &= ~button
