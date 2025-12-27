import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from pokecontroller.core.image import RawImage, to_bytes
from pokecontroller.core.notification.notifier import Notifier, RateLimit
from pokecontroller.utils.config import Config
from pokecontroller.utils.datetime import from_timestamp

logger = logging.getLogger(__name__)

DISCORD_SECTION_DEFAULT = "DISCORD"
DISCORD_WEBHOOK_SECTION_DEFAULT = "DISCORD_WEBHOOK"
DISCORD_WEBHOOK_SECTION_KEYWORD = "DISCORD_WEBHOOK"


@dataclass(kw_only=True, frozen=True)
class DiscordWebhookOptions:
    """Discord Webhookのオプションを保持するデータクラス.

    Attributes:
        webhook_url: WebhookのURL.
        username: 送信者として表示されるユーザー名.
        avatar_url: 送信者のアバター画像のURL.
    """

    webhook_url: str = ""
    username: str = ""
    avatar_url: str = ""


class DiscordConfig(Config):
    """Discord通知の設定を管理するクラス.

    設定ファイルからDiscord WebhookのURLやトークンなどの情報を読み書きします。
    """

    def __init__(self, path: Path) -> None:
        """DiscordConfigインスタンスを初期化します.

        Args:
            path: 設定ファイルのパス.
        """
        super().__init__(path)
        self._initialize()

    def get_channel_id(self, section: str) -> str | None:
        """指定されたセクションのチャンネルIDを取得します.

        Args:
            section: 設定セクション名.

        Returns:
            チャンネルID、または存在しない場合はNone.
        """
        return self[section]["channel_id"]

    def set_channel_id(self, section: str, channel_id: str) -> None:
        """指定されたセクションのチャンネルIDを設定します.

        Args:
            section: 設定セクション名.
            channel_id: 設定するチャンネルID.
        """
        self[section]["channel_id"] = channel_id

    def get_token(self, section: str) -> str | None:
        """指定されたセクションのトークンを取得します.

        Args:
            section: 設定セクション名.

        Returns:
            トークン、または存在しない場合はNone.
        """
        return self[section]["token"]

    def set_token(self, section: str, token: str) -> None:
        """指定されたセクションのトークンを設定します.

        Args:
            section: 設定セクション名.
            token: 設定するトークン.
        """
        self[section]["token"] = token

    def get_webhook_url(self, section: str) -> str | None:
        """指定されたセクションのWebhook URLを取得します.

        Args:
            section: 設定セクション名.

        Returns:
            Webhook URL、または存在しない場合はNone.
        """
        return self[section]["webhook_url"]

    def set_webhook_url(self, section: str, webhook_url: str) -> None:
        """指定されたセクションのWebhook URLを設定します.

        Args:
            section: 設定セクション名.
            webhook_url: 設定するWebhook URL.
        """
        self[section]["webhook_url"] = webhook_url

    def get_username(self, section: str) -> str | None:
        """指定されたセクションのユーザー名を取得します.

        Args:
            section: 設定セクション名.

        Returns:
            ユーザー名、または存在しない場合はNone.
        """
        return self[section]["username"]

    def set_username(self, section: str, username: str) -> None:
        """指定されたセクションのユーザー名を設定します.

        Args:
            section: 設定セクション名.
            username: 設定するユーザー名.
        """
        self[section]["username"] = username

    def get_avatar_url(self, section: str) -> str | None:
        """指定されたセクションのアバターURLを取得します.

        Args:
            section: 設定セクション名.

        Returns:
            アバターURL、または存在しない場合はNone.
        """
        return self[section]["avatar_url"]

    def set_avatar_url(self, section: str, avatar_url: str) -> None:
        """指定されたセクションのアバターURLを設定します.

        Args:
            section: 設定セクション名.
            avatar_url: 設定するアバターURL.
        """
        self[section]["avatar_url"] = avatar_url

    def get_directory_basename(self) -> str:
        """設定ファイルが格納されているディレクトリ名を取得します.

        Returns:
            ディレクトリの名前.
        """
        return Path(self._path).parent.name

    def get_webhook_sections(self) -> list[str]:
        """Webhook設定セクションのリストを取得します.

        Returns:
            Webhookキーワードを含むセクション名のリスト.
        """
        return [
            section
            for section in self.sections()
            if DISCORD_WEBHOOK_SECTION_KEYWORD in section
        ]

    def get_webhook_options(self) -> dict[str, DiscordWebhookOptions]:
        """全てのWebhook設定オプションを取得します.

        Returns:
            セクション名をキーとし、DiscordWebhookOptionsを値とする辞書.
        """
        return {
            section: DiscordWebhookOptions(
                webhook_url=self[section]["webhook_url"],
                username=self[section]["username"],
                avatar_url=self[section]["avatar_url"],
            )
            for section in self.sections()
            if DISCORD_WEBHOOK_SECTION_KEYWORD in section
        }

    def _initialize(self) -> None:
        # load and create if not exists
        try:
            self.load()
        except FileNotFoundError:
            self._create()

    def _create(self) -> None:
        options = (
            (
                DISCORD_SECTION_DEFAULT,
                ["channel_id", "token"],
            ),
            (
                DISCORD_WEBHOOK_SECTION_DEFAULT,
                ["webhook_url", "username", "avatar_url"],
            ),
        )
        for section, ops in options:
            self.add_section(section)
            self[section] = {o: "" for o in ops}
        self.save(chmod=0o777, create_directory=True)


class DiscordNotifier(Notifier):
    """Discord Webhookを使用して通知を送信するクラス.

    複数のWebhookを管理し、テキストメッセージと画像の送信をサポートします。
    レート制限情報の取得にも対応しています。
    """

    def __init__(self, config: DiscordConfig) -> None:
        """DiscordNotifierインスタンスを初期化します.

        Args:
            config: Discord設定オブジェクト.
        """
        self._config = config
        self._default_username = self._make_default_username()
        self._sections = self._config.get_webhook_sections()
        self._options = self._config.get_webhook_options()
        self._last_responses = self._fetch_statuses()

    @property
    def keys(self) -> list[str]:
        """利用可能な通知キーのリストを取得します.

        Returns:
            Webhook設定セクション名のリスト.
        """
        return self._sections

    @property
    def has_error(self) -> bool:
        """エラーが発生しているかどうかを取得します.

        最後のレスポンスのステータスコードが4xxの場合にTrueを返します。

        Returns:
            エラーが発生している場合はTrue、それ以外はFalse.
        """
        return any(
            400 <= response.status_code < 500
            for response in self._last_responses
            if response is not None
        )

    def notify(
        self,
        message: str | None = None,
        image: RawImage | None = None,
        keys: list[str] | None = None,
    ) -> None:
        """Discord Webhookを使用して通知を送信します.

        テキストメッセージと画像の両方をサポートします。
        複数のWebhookに対して同時に送信できます。

        Args:
            message: 送信するメッセージ.
            image: 送信する画像.
            keys: 通知を送信する対象のWebhookキーのリスト. Noneの場合は
                全てのWebhookに送信します.
        """
        if not (targets := keys if keys is not None else self._sections):
            logger.error(f"有効なkeysを指定してください。(keys={keys})")
            return

        for response_index, section in enumerate(self._sections):
            if section not in targets:
                logger.warning(f"[Discord]無効なkey({section})")
                continue

            try:
                self._notify(
                    response_index=response_index,
                    key=section,
                    message=message,
                    image=image,
                )
            except Exception:
                logger.error("webhook_urlを確認してください。")

    def get_late_limits(self) -> list[RateLimit]:
        """レート制限情報のリストを取得します.

        各Webhookの最後のレスポンスヘッダーからレート制限情報を抽出します。

        Returns:
            各Webhookに対するレート制限情報のリスト.
        """
        return [
            RateLimit(
                key=key,
                limit=response.headers.get("X-RateLimit-Limit"),
                remaining=response.headers.get("X-RateLimit-Remaining"),
                reset_time=self._time(response.headers.get("X-RateLimit-Reset")),
            )
            for key, response in zip(self._sections, self._last_responses)
            if response is not None
        ]

    def apply_config(self) -> None:
        """設定を適用します.

        設定ファイルから最新のWebhook情報を読み込み、ステータスを更新します。
        """
        self._sections = self._config.get_webhook_sections()
        self._options = self._config.get_webhook_options()
        self._last_responses = self._fetch_statuses()

    def _fetch_statuses(self) -> list[requests.Response]:
        return [requests.get(self._options[key].webhook_url) for key in self._sections]

    def _make_default_username(self) -> str:
        return f"Poke-Controller (profile: {self._get_profile_name()})"

    def _get_profile_name(self) -> str:
        return self._config.get_directory_basename()

    def _notify(
        self,
        response_index: int,
        key: str,
        message: str | None = None,
        image: RawImage | None = None,
    ) -> None:
        files = self._make_files(key=key, message=message, image=image)
        self._last_responses[response_index] = response = requests.post(
            url=self._options[key].webhook_url,
            files=files,
        )
        self._log_response(
            response=response,
            message=message,
            image=image,
        )

    def _make_files(
        self,
        key: str,
        message: str | None,
        image: RawImage | None,
    ) -> dict[str, Any]:
        payload = self._make_payload(key=key, message=message)
        files: dict[str, Any] = {"payload_json": (None, json.dumps(payload))}
        if image is not None:
            files["media"] = ("pokecon_image.png", to_bytes(image, fmt="png"))
        return files

    def _make_payload(self, key: str, message: str | None) -> dict[str, str]:
        payload: dict[str, str] = {
            "username": self._options[key].username or self._default_username,
            "content": message or "",
        }
        if avatar_url := self._options[key].avatar_url:
            payload["avatar_url"] = avatar_url
        return payload

    def _log_response(
        self,
        response: requests.Response,
        message: str | None,
        image: RawImage | None,
    ) -> None:
        data_type, data_type_jpn = self._make_send_data_type(message, image)
        if (status_code := response.status_code) in [200, 204]:
            logger.info(f"{data_type_jpn}を送信しました。")
        else:
            logger.info(f"{data_type_jpn}の送信に失敗しました。({status_code})")

    # noinspection PyMethodMayBeStatic
    def _make_send_data_type(
        self,
        message: str | None,
        image: RawImage | None,
    ) -> tuple[str, str]:
        if message is not None and image is not None:
            return "テキスト・画像", "Text & Image"
        elif message is not None:
            return "テキスト", "Text"
        elif image is not None:
            return "画像", "Image"
        else:
            return "(empty)", "empty"

    # noinspection PyMethodMayBeStatic
    def _time(self, timestamp: str | None) -> str | None:
        return str(from_timestamp(int(timestamp), 9)) if timestamp else None
