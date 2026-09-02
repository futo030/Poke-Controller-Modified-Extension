class N3dsTouchscreenState:
    """ニンテンドー3DSのタッチスクリーンの状態を管理するクラス.

    タッチ位置のXY座標を管理します。
    """

    def __init__(self) -> None:
        """N3dsTouchscreenStateインスタンスを初期化します."""
        self._x = 0
        self._y = 0

    @property
    def x(self) -> int:
        """タッチ位置のX座標を取得します.

        Returns:
            X座標値.
        """
        return self._x

    @property
    def y(self) -> int:
        """タッチ位置のY座標を取得します.

        Returns:
            Y座標値.
        """
        return self._y

    def touch(self, x: int, y: int) -> None:
        """タッチスクリーンの指定位置にタッチします.

        Args:
            x: タッチするX座標.
            y: タッチするY座標.
        """
        self._x = x
        self._y = y

    def untouch(self) -> None:
        """タッチを解除します."""
        self._x = 0
        self._y = 0

    def reset(self) -> None:
        """タッチスクリーンの状態をリセットします.

        untouch()と同じ動作をします。
        """
        self.untouch()
