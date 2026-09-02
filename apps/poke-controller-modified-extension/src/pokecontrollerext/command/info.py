from dataclasses import dataclass
from types import ModuleType
from typing import Literal


@dataclass(kw_only=True, frozen=True)
class CommandInfo[T]:
    """コマンドのメタデータを保持するデータクラス.

    コマンドの名前、表示名、タグ、モジュール、クラス型、APIバージョン、
    実行種別などの情報を不変（frozen）データクラスとして管理します。

    Attributes:
        name: コマンドの内部名（識別子）.
        display_name: 表示用のコマンド名.
        tags: コマンドに関連付けられたタグのリスト.
        module: コマンドが定義されているモジュール.
        klass: コマンドのクラス型.
        api_version: 対応するAPIのバージョン.
        kind: コマンドの実行種別（"python" または "mcu"）.
    """

    name: str
    display_name: str
    tags: list[str]
    module: ModuleType
    klass: type[T]
    api_version: str
    kind: Literal["python", "mcu"]
