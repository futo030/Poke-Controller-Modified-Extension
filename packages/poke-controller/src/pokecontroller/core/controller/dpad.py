class DpadState:
    """十字キー（D-pad）の状態を管理するクラス.

    十字キーの方向を整数値で管理し、ニュートラル状態への
    リセット機能を提供します。
    """

    def __init__(self, neutral: int) -> None:
        """DpadStateインスタンスを初期化します.

        Args:
            neutral: ニュートラル状態（入力なし）を表す整数値.
        """
        self._neutral = neutral
        self._value = neutral

    @property
    def value(self) -> int:
        """現在の十字キーの状態を取得します.

        Returns:
            十字キーの方向を表す整数値.
        """
        return self._value

    def push(self, dpad: int) -> None:
        """十字キーを指定された方向に設定します.

        Args:
            dpad: 設定する方向を表す整数値.
        """
        self._value = dpad

    def release(self) -> None:
        """十字キーをニュートラル状態に戻します."""
        self._value = self._neutral

    def reset(self) -> None:
        """十字キーの状態をリセットします.

        release()と同じ動作をします。
        """
        self.release()
