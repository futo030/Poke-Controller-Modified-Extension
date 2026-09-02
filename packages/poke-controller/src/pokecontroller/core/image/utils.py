VALID_CROP_FORMATS = [1, 2, 3, 4, 11, 12, 13, 14]


def convert_crop_format(
    crop: list[int] | tuple[int, int, int, int],
    src_format: int,
    dst_format: int,
) -> list[int] | tuple[int, int, int, int]:
    """cropをsrc_fmt形式からdst_formatに変換するユーティリティ関数

    formatは以下の形式をサポートしています。

    * Pillow形式
        * format=1: [x-start, y-start, x-end, y-end]
        * format=2: [x-start, y-start, width, height]
        * format=3: [x-start, x-end, y-start, y-end]
        * format=4: [x-start, width, y-start, height]
    * OpenCV形式
        * format=11: [y-start, x-start, y-end, x-end]
        * format=12: [y-start, x-start, height, width]
        * format=13: [y-start, y-end, x-start, x-end]
        * format=14: [y-start, height, x-start, width]

    Args:
        crop: 変換したいcropのタプル
        src_format: 変換前のフォーマット
        dst_format: 変換後のフォーマット

    Returns:
        変換後のcropタプル

    Raises:
        ValueError: 不正なフォーマットが指定された場合

    Example:
        >>> convert_crop_format(crop=(10, 20, 30, 40), src_format=1, dst_format=2)
        (10, 20, 20, 20)
    """
    # input handling
    if src_format == dst_format:
        return crop
    if src_format not in VALID_CROP_FORMATS or dst_format not in VALID_CROP_FORMATS:
        raise ValueError("invalid crop format")

    default = convert_to_default(crop, src_format)
    return convert_from_default(default, dst_format)


def convert_to_default(
    crop: list[int] | tuple[int, int, int, int],
    src_format: int,
) -> list[int] | tuple[int, int, int, int]:
    """cropをsrc_fmt形式からformat=13に変換するユーティリティ関数

    formatは以下の形式をサポートしています。

    * Pillow形式
        * format=1: [x-start, y-start, x-end, y-end]
        * format=2: [x-start, y-start, width, height]
        * format=3: [x-start, x-end, y-start, y-end]
        * format=4: [x-start, width, y-start, height]
    * OpenCV形式
        * format=11: [y-start, x-start, y-end, x-end]
        * format=12: [y-start, x-start, height, width]
        * format=13: [y-start, y-end, x-start, x-end]
        * format=14: [y-start, height, x-start, width]

    Args:
        crop: 変換したいcropのタプル
        src_format: 変換前のフォーマット

    Returns:
        変換後のcropタプル

    Raises:
        ValueError: 不正なフォーマットが指定された場合

    Example:
        >>> convert_to_default(crop=(10, 20, 30, 40), src_format=1)
        (20, 40, 10, 30)
    """
    if src_format < 10:
        if src_format == 1:
            return [crop[1], crop[3], crop[0], crop[2]]
        if src_format == 2:
            return [crop[1], crop[1] + crop[3], crop[0], crop[0] + crop[2]]
        if src_format == 3:
            return [crop[2], crop[3], crop[0], crop[1]]
        if src_format == 4:
            return [crop[2], crop[2] + crop[3], crop[0], crop[0] + crop[1]]
        raise ValueError("invalid crop format")
    else:
        #
        if src_format == 11:
            return [crop[0], crop[2], crop[1], crop[3]]
        if src_format == 12:
            return [crop[0], crop[0] + crop[2], crop[1], crop[1] + crop[3]]
        if src_format == 13:
            return crop
        if src_format == 14:
            return [crop[0], crop[0] + crop[1], crop[2], crop[2] + crop[3]]
        raise ValueError("invalid crop format")


def convert_from_default(
    crop: list[int] | tuple[int, int, int, int],
    dst_format: int,
) -> list[int] | tuple[int, int, int, int]:
    """cropをformat=13形式からdst_formatに変換するユーティリティ関数

    formatは以下の形式をサポートしています。

    * Pillow形式
        * format=1: [x-start, y-start, x-end, y-end]
        * format=2: [x-start, y-start, width, height]
        * format=3: [x-start, x-end, y-start, y-end]
        * format=4: [x-start, width, y-start, height]
    * OpenCV形式
        * format=11: [y-start, x-start, y-end, x-end]
        * format=12: [y-start, x-start, height, width]
        * format=13: [y-start, y-end, x-start, x-end]
        * format=14: [y-start, height, x-start, width]

    Args:
        crop: 変換したいcropのタプル
        dst_format: 変換後のフォーマット

    Returns:
        変換後のcropタプル

    Raises:
        ValueError: 不正なフォーマットが指定された場合

    Example:
        >>> convert_from_default(crop=(10, 20, 30, 40), dst_format=1)
        (30, 10, 40, 20)
    """
    if dst_format < 10:
        if dst_format == 1:
            return [crop[2], crop[0], crop[3], crop[1]]
        if dst_format == 2:
            return [crop[2], crop[0], crop[3] - crop[2], crop[1] - crop[0]]
        if dst_format == 3:
            return [crop[2], crop[3], crop[0], crop[1]]
        if dst_format == 4:
            return [crop[2], crop[3] - crop[2], crop[0], crop[1] - crop[0]]
        raise ValueError("invalid crop format")
    else:
        if dst_format == 11:
            return [crop[0], crop[2], crop[1], crop[3]]
        if dst_format == 12:
            return [crop[0], crop[2], crop[1] - crop[0], crop[3] - crop[2]]
        if dst_format == 13:
            return crop
        if dst_format == 14:
            return [crop[0], crop[1] - crop[0], crop[2], crop[3] - crop[2]]
        raise ValueError("invalid crop format")
