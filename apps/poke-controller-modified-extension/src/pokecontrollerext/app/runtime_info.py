from dataclasses import dataclass
from pathlib import Path


@dataclass(kw_only=True, frozen=True)
class AppRuntimeInfo:
    """アプリケーションの実行時の情報を持つクラス。

    Attributes:
        base_dir: アプリケーションの実行ファイルがあるディレクトリ
        profile: 実行中のプロファイル名
    """

    base_dir: Path
    profile: str
