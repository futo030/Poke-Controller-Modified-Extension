from typing import Any

from pokecontrollerext.singletons.app.translation import get_translation


def t(key: str, **kwargs: Any) -> str:
    """多言語対応のためのテキスト取得関数。

    Args:
        key (str): 取得するテキストのキー
        **kwargs: テキストに埋め込む変数
    Returns:
        str: 取得したテキスト
    """
    translation = get_translation()
    return translation.get(key, **kwargs)
