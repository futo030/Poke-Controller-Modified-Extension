import datetime


def from_timestamp(
    timestamp: float,
    timezone_delta: int | None = 9,
) -> datetime.datetime:
    """タイムスタンプからdatetimeオブジェクトを生成します.

    Args:
        timestamp: UNIXタイムスタンプ（秒）.
        timezone_delta: UTCからのタイムゾーン時差（時間）.
            デフォルトは9（日本標準時）. Noneの場合はタイムゾーン情報なし.

    Returns:
        生成されたdatetimeオブジェクト.
    """
    tz = None
    if timezone_delta is not None:
        tz = datetime.timezone(datetime.timedelta(hours=timezone_delta))
    return datetime.datetime.fromtimestamp(
        timestamp=timestamp,
        tz=tz,
    )


def format_datetime(
    dt: datetime.datetime | None = None,
    fmt: str = "%Y-%m-%d_%H-%M-%S",
) -> str:
    """datetimeオブジェクトを指定されたフォーマットで文字列に変換します.

    Args:
        dt: フォーマットするdatetimeオブジェクト. Noneの場合は現在時刻を使用します.
        fmt: 日時のフォーマット文字列. デフォルトは "%Y-%m-%d_%H-%M-%S".

    Returns:
        フォーマットされた日時文字列.
    """
    if dt is None:
        return datetime.datetime.now().strftime(fmt)
    return dt.strftime(fmt)
