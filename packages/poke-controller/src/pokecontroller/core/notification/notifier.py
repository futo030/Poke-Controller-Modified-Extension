from abc import ABC, abstractmethod
from dataclasses import dataclass

from pokecontroller.core.image import RawImage


@dataclass(kw_only=True, frozen=True)
class RateLimit:
    """APIのレート制限情報を保持するデータクラス.

    Attributes:
        key: レート制限の識別キー.
        limit: リクエストの上限数.
        remaining: 残りリクエスト数.
        reset_time: レート制限がリセットされる時刻.
        image_limit: 画像リクエストの上限数.
        image_remaining: 残り画像リクエスト数.
    """

    key: str | None = None
    limit: str | None = None
    remaining: str | None = None
    reset_time: str | None = None
    image_limit: str | None = None
    image_remaining: str | None = None


class Notifier(ABC):
    """通知を送信するための抽象基底クラス.

    様々な通知サービス（デスクトップ通知、Discord、LINEなど）の
    共通インターフェースを定義します。
    """

    @property
    @abstractmethod
    def keys(self) -> list[str]:
        """利用可能な通知キーのリストを取得します.

        Returns:
            通知キーのリスト.
        """
        ...

    @property
    @abstractmethod
    def has_error(self) -> bool:
        """エラーが発生しているかどうかを取得します.

        Returns:
            エラーが発生している場合はTrue、それ以外はFalse.
        """
        ...

    @abstractmethod
    def notify(
        self,
        message: str | None = None,
        image: RawImage | None = None,
        keys: list[str] | None = None,
    ) -> None:
        """通知を送信します.

        Args:
            message: 送信するメッセージ.
            image: 送信する画像.
            keys: 通知を送信する対象のキーのリスト. Noneの場合は全ての
                利用可能なキーに送信します.
        """
        ...

    @abstractmethod
    def get_late_limits(self) -> list[RateLimit]:
        """レート制限情報のリストを取得します.

        Returns:
            各通知キーに対するレート制限情報のリスト.
        """
        ...

    @abstractmethod
    def apply_config(self) -> None:
        """設定を適用します.

        設定ファイルから最新の設定を読み込んで適用します。
        """
        ...
