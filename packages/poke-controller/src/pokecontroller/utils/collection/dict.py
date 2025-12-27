from typing import Any


def deep_merge[T, U](
    original: dict[T, U],
    update: dict[T, U],
) -> dict[T, U]:
    """2つの辞書を再帰的にマージします.

    ネストされた辞書構造を保持しながら、updateの値でoriginalの値を
    上書きします。元の辞書は変更されず、新しい辞書が返されます。

    Args:
        original: 元となる辞書.
        update: マージする辞書.

    Returns:
        マージされた新しい辞書.

    Raises:
        RuntimeError: マージ中に辞書以外の型が検出された場合.
    """

    def updater(d: Any, u: Any) -> None:
        if not isinstance(d, dict) or not isinstance(u, dict):
            raise RuntimeError()

        for k, v in u.items():
            if isinstance(v, dict):
                d.setdefault(k, {})
                updater(d[k], v)
            else:
                d[k] = v

    result: dict[T, U] = {}
    updater(result, original)
    updater(result, update)
    return result
