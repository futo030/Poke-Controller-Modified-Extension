from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison


def clamp[T: SupportsRichComparison](
    value: T,
    min_value: T,
    max_value: T,
) -> T:
    """値を指定された範囲内に制限します.

    Args:
        value: 制限する値.
        min_value: 最小値.
        max_value: 最大値.

    Returns:
        min_value以上max_value以下に制限された値.
    """
    return max(min_value, min(value, max_value))
