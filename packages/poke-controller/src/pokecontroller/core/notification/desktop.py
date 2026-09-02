import logging
import os

from plyer import notification

from pokecontroller.core.image.raw_image import RawImage
from pokecontroller.core.notification.notifier import Notifier, RateLimit
from pokecontroller.utils import platform

logger = logging.getLogger(__name__)


class DesktopNotifier(Notifier):
    """デスクトップ通知を送信するクラス.

    OSのネイティブ通知機能を使用してデスクトップに通知を表示します。
    macOSでは専用の実装を使用し、他のOSではplyerライブラリを使用します。
    画像とキーの指定には対応していません。
    """

    def __init__(self, title: str) -> None:
        """DesktopNotifierインスタンスを初期化します.

        Args:
            title: 通知のタイトル.
        """
        self._title = title

    @property
    def keys(self) -> list[str]:
        """利用可能な通知キーのリストを取得します.

        デスクトップ通知はキーの概念を持たないため、空のリストを返します。

        Returns:
            空のリスト.
        """
        logger.info("Desktop notification do not have any keys")
        return []

    @property
    def has_error(self) -> bool:
        """エラーが発生しているかどうかを取得します.

        デスクトップ通知はエラー状態を持たないため、常にFalseを返します。

        Returns:
            常にFalse.
        """
        return False

    def notify(
        self,
        message: str | None = None,
        image: RawImage | None = None,
        keys: list[str] | None = None,
    ) -> None:
        """デスクトップ通知を送信します.

        メッセージのみをサポートし、画像とキーは無視されます。
        macOSの場合はAppleScriptを使用し、それ以外ではplyerを使用します。

        Args:
            message: 送信するメッセージ. Noneの場合は通知を送信しません.
            image: 画像（無視されます）.
            keys: キー（無視されます）.
        """
        if message is None:
            logger.warning("Desktop notification is not supported empty message")
            return
        if image is not None:
            logger.info("Desktop notification is not supported image")
        if keys is not None:
            logger.info("Desktop notification is not supported keys")

        if platform.is_macos():
            self._notify_macos(message)
        else:
            self._notify(message)

    def get_late_limits(self) -> list[RateLimit]:
        """レート制限情報のリストを取得します.

        デスクトップ通知はレート制限を持たないため、空のリストを返します。

        Returns:
            空のリスト.
        """
        logger.info("Desktop notification is not supported rate limit")
        return []

    def apply_config(self) -> None:
        """設定を適用します.

        デスクトップ通知は設定ファイルを持たないため、何も行いません。
        """
        logger.info("Desktop notification is not supported config")

    def _notify(self, message: str) -> None:
        notification.notify(
            title=self._title,
            message=message,
            timeout=5,
        )

    def _notify_macos(self, message: str) -> None:
        sound_name = "default"

        message_text = f'display notification "{message}"'
        title_text = f'with title "{self._title}"'
        sound_text = f'sound name "{sound_name}"'
        notification_text = f"{message_text} {title_text} {sound_text}"
        os.system(f"osascript -e '{notification_text}'")
