import logging
from pathlib import Path
from typing import Any

import requests

from pokecontroller.core.image import RawImage, to_bytes
from pokecontroller.core.notification.notifier import Notifier, RateLimit
from pokecontroller.utils.config import Config
from pokecontroller.utils.datetime import from_timestamp

logger = logging.getLogger(__name__)

LINE_API_URL_BASE = "https://notify-api.line.me/api"
LINE_STATUS_API_URL = f"{LINE_API_URL_BASE}/status"
LINE_NOTIFY_API_URL = f"{LINE_API_URL_BASE}/notify"


class LineConfig(Config):
    """LINE Notify通知の設定を管理するクラス.

    設定ファイルからLINE Notifyのトークンなどの情報を読み書きします。
    """

    def __init__(self, path: Path) -> None:
        """LineConfigインスタンスを初期化します.

        Args:
            path: 設定ファイルのパス.
        """
        super().__init__(path)
        self._initialize()

    def get_token(self, option: str) -> str | None:
        """指定されたオプション名のトークンを取得します.

        Args:
            option: トークンのオプション名.

        Returns:
            トークン、または存在しない場合はNone.
        """
        return self["LINE"][option]

    def set_token(self, option: str, value: str) -> None:
        """指定されたオプション名のトークンを設定します.

        Args:
            option: トークンのオプション名.
            value: 設定するトークン値.
        """
        self["LINE"][option] = value

    def get_tokens(self) -> dict[str, str]:
        """全てのトークンを取得します.

        Returns:
            オプション名をキーとし、トークンを値とする辞書.
        """
        return self.options("LINE")

    def _initialize(self) -> None:
        # load and create if not exists
        try:
            self.load()
        except FileNotFoundError:
            self._create()

    def _create(self) -> None:
        # set default token
        self.set_token("token", "")
        self.save(chmod=0o777, create_directory=True)


class LineNotifier(Notifier):
    """LINE Notifyを使用して通知を送信するクラス.

    複数のトークンを管理し、テキストメッセージと画像の送信をサポートします。
    レート制限情報（画像リクエスト制限を含む）の取得にも対応しています。
    """

    def __init__(self, config: LineConfig):
        """LineNotifierインスタンスを初期化します.

        Args:
            config: LINE設定オブジェクト.
        """
        self._config = config
        self._tokens = self._config.get_tokens()
        self._token_keys = list(self._tokens.keys())
        self._headers_list = self._make_headers_list()
        self._last_responses = self._fetch_statuses()

    @property
    def keys(self) -> list[str]:
        """利用可能な通知キーのリストを取得します.

        Returns:
            トークンのキー名のリスト.
        """
        return list(self._tokens.keys())

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
        """LINE Notifyを使用して通知を送信します.

        テキストメッセージと画像の両方をサポートします。
        複数のトークンに対して同時に送信できます。

        Args:
            message: 送信するメッセージ.
            image: 送信する画像.
            keys: 通知を送信する対象のトークンキーのリスト. Noneの場合は
                全てのトークンに送信します.
        """
        if not (targets := keys if keys is not None else self._token_keys):
            logger.error("有効なkeysを指定してください")
            return

        for response_index, key in enumerate(self._token_keys):
            if key not in targets:
                continue

            try:
                self._notify(
                    response_index=response_index,
                    key=key,
                    message=message,
                    image=image,
                )
            except Exception:
                logger.error("tokenを確認してください。")

    def get_late_limits(self) -> list[RateLimit]:
        """レート制限情報のリストを取得します.

        各トークンの最後のレスポンスヘッダーからレート制限情報を抽出します。
        画像リクエストの制限情報も含まれます。

        Returns:
            各トークンに対するレート制限情報のリスト.
        """
        return [
            RateLimit(
                key=key,
                limit=response.headers.get("X-RateLimit-Limit"),
                remaining=response.headers.get("X-RateLimit-Remaining"),
                image_limit=response.headers.get("X-RateLimit-ImageLimit"),
                image_remaining=response.headers.get("X-RateLimit-ImageRemaining"),
                reset_time=self._time(response.headers.get("X-RateLimit-Reset")),
            )
            for key, response in zip(self._token_keys, self._last_responses)
            if response is not None
        ]

    def apply_config(self) -> None:
        """設定を適用します.

        設定ファイルから最新のトークン情報を読み込み、ステータスを更新します。
        """
        self._tokens = self._config.get_tokens()
        self._token_keys = list(self._tokens.keys())
        self._headers_list = self._make_headers_list()
        self._last_responses = self._fetch_statuses()

    def _make_headers_list(self) -> list[dict[str, str]]:
        return [
            {"Authorization": f"Bearer {self._tokens[key]}"} for key in self._token_keys
        ]

    # noinspection PyMethodMayBeStatic
    def _make_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _fetch_statuses(self) -> list[requests.Response]:
        return [
            requests.get(LINE_STATUS_API_URL, headers=headers)
            for headers in self._headers_list
        ]

    def _notify(
        self,
        response_index: int,
        key: str,
        message: str | None = None,
        image: RawImage | None = None,
    ) -> None:
        params = self._make_params(message=message)
        files = self._make_files(image=image)
        headers = self._make_headers(token=key)
        self._last_responses[response_index] = response = requests.post(
            url=LINE_NOTIFY_API_URL,
            headers=headers,
            params=params,
            files=files,
        )
        self._log_response(
            response=response,
            message=message,
            image=image,
        )

    # noinspection PyMethodMayBeStatic
    def _make_params(self, message: str | None) -> dict[str, Any]:
        return {"message": message if message is not None else ""}

    # noinspection PyMethodMayBeStatic
    def _make_files(self, image: RawImage | None) -> dict[str, Any] | None:
        return {"imageFile": to_bytes(image, fmt="png")} if image is not None else None

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
            logger.error(f"{data_type_jpn}の送信に失敗しました。({status_code})")

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
