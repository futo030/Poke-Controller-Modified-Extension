import json
from pathlib import Path
from typing import Any

from pokecontroller.utils.collection.dict import deep_merge


class Translation:
    """多言語・マルチプラットフォーム対応の翻訳管理クラス.

    JSONファイルから翻訳テキストを読み込み、キーベースでアクセスできます。
    プラットフォーム固有の翻訳ファイルがあれば、ベース翻訳とマージします。
    """

    def __init__(
        self,
        base_path: Path,
        platform: str = "windows",
        language: str = "en",
    ) -> None:
        """Translationインスタンスを初期化します.

        Args:
            base_path: 翻訳ファイルが格納されているディレクトリのパス.
            platform: プラットフォーム名 ("windows", "macos", "linux").
                デフォルトは "windows".
            language: 言語コード ("en", "ja"など). デフォルトは "en".
        """
        self._base_path = base_path
        self._platform = platform
        self._language = language
        self._translations = self._load_translations()

    def get(self, key: str, **kwargs: Any) -> str:
        """指定されたキーの翻訳テキストを取得します.

        キーはドット区切りで階層を表現します（例: "menu.file.open"）。
        取得したテキストは、kwargsで指定された値でフォーマットされます。

        Args:
            key: 翻訳キー（ドット区切り）.
            **kwargs: テキストフォーマット用のキーワード引数.

        Returns:
            翻訳されたテキスト。キーが見つからない場合はキー自体を返します.
        """
        ts: Any = self._translations
        for k in key.split("."):
            if k not in ts:
                break
            ts = ts[k]
        if isinstance(ts, dict):
            if "text" not in ts:
                return key
            if not isinstance(txt := ts["text"], str):
                return key
            text = txt
        elif isinstance(ts, list):
            text = "\n".join(ts)
        elif isinstance(ts, str):
            text = ts
        else:
            return key
        return text.format_map(kwargs)

    def _load_translations(self) -> dict[str, Any]:
        base_file = self._base_path / f"{self._language}.json"

        with open(base_file, "r", encoding="utf-8-sig") as f:
            base = json.load(f)

        platform_file = self._base_path / f"{self._language}.{self._platform}.json"
        if not platform_file.exists():
            return base  # type: ignore[no-any-return]

        with open(platform_file, "r", encoding="utf-8-sig") as f:
            platform = json.load(f)

        return deep_merge(base, platform)
