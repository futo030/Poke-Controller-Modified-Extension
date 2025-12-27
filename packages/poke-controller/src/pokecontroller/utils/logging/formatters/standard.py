import logging


class StandardFormatter(logging.Formatter):
    """ライブラリの標準ログフォーマッター.

    拡張属性（"class"など）をサポートし、存在しない場合は空文字列を設定します。
    """

    def format(self, record: logging.LogRecord) -> str:
        """ログレコードをフォーマットします.

        拡張属性が存在しない場合は空文字列を設定してから、
        親クラスのフォーマット処理を実行します。

        Args:
            record: ログレコード.

        Returns:
            フォーマットされたログ文字列.
        """
        extended_attr = ["class"]
        for attr in extended_attr:
            if not hasattr(record, attr):
                setattr(record, attr, "")

        return super().format(record)
