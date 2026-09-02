import logging
from pathlib import Path

from pokecontroller.core import notification
from pokecontroller.core.image import RawImage

logger = logging.getLogger(__name__)


class Line_Notify:  # noqa
    LINE_TOKEN_PATH = Path("profiles") / "default" / "line_token.ini"

    def __init__(self, token_name: str = "token") -> None:
        self._config = notification.LineConfig(path=self.LINE_TOKEN_PATH)
        self._notifier = notification.LineNotifier(config=self._config)

    def __str__(self) -> str:
        if self._notifier.has_error:
            logger.error("Invalid token")
            return "LINE Token Check FAILED."

        logger.info("Valid token")
        return "LINE-Token Check OK!"

    def send_message(
        self,
        notification_message: str,
        image: RawImage | None = None,
        token: str = "token",
    ) -> None:
        """
        LINEにテキスト/画像を通知する
        imageが設定されていなければテキストのみ、設定されていればテキストと画像を通知する
        imageはBGRを想定する
        """
        self._notifier.notify(message=notification_message, image=image, keys=[token])

    def getRateLimit(self) -> None:  # noqa
        keys = self._notifier.keys
        limits = self._notifier.get_late_limits()
        for key, limit in [
            (key, limit) for key, limit in zip(keys, limits) if limit is not None
        ]:
            logger.info(f"For: {key}")
            logger.info(f"LINE API - Limit: {limit.limit}")
            logger.info(f"LINE API - Remaining: {limit.remaining}")
            logger.info(f"LINE API - ImageLimit: {limit.image_limit}")
            logger.info(f"LINE API - ImageRemaining: {limit.image_remaining}")
            logger.info(f"Reset time: {limit.reset_time}")
