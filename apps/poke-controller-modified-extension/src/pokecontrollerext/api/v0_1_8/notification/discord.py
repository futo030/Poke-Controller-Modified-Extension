import logging
from pathlib import Path

from pokecontroller.core import notification
from pokecontroller.core.image import RawImage

logger = logging.getLogger(__name__)


class Discord_Notify:  # noqa
    DISCORD_TOKEN_PATH = Path("profiles") / "default" / "discord_token.ini"

    def __init__(
        self,
        webhook_url: str = "webhook_url",
        username: str = "username",
        avatar_url: str = "",
        token_name: str = "token",
    ) -> None:
        self._config = notification.DiscordConfig(path=self.DISCORD_TOKEN_PATH)
        self._notifier = notification.DiscordNotifier(config=self._config)

    def __str__(self) -> str:
        if self._notifier.has_error:
            logger.error("Invalid url")
            return "DISCORD API Check FAILED."

        logger.info("Valid url")
        return "DISCORD API Check OK!"

    def send_message(
        self,
        notification_message: str,
        image: RawImage | None = None,
        keys: str | list[str] = "DISCORD_WEBHOOK",
    ) -> None:
        """
        DISCORDにテキスト/画像を通知する
        imageが設定されていなければテキストのみ、設定されていればテキストと画像を通知する
        imageはBGRを想定する
        """
        if isinstance(keys, str):
            if keys == "ALL":
                ks = None
            else:
                ks = [keys]
        else:
            ks = keys
        self._notifier.notify(message=notification_message, image=image, keys=ks)

    def getRateLimit(self) -> None:  # noqa
        keys = self._notifier.keys
        limits = self._notifier.get_late_limits()
        for key, limit in [
            (key, limit) for key, limit in zip(keys, limits) if limit is not None
        ]:
            logger.info(f"For: {key}")
            logger.info(f"DISCORD API - Limit: {limit.limit}")
            logger.info(f"DISCORD API - Remaining: {limit.remaining}")
            logger.info(f"Reset time: {limit.reset_time}")
