#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画面上の範囲と大きさの計算(範囲の収め方、タッチスクリーンの範囲の割合、プレビューの大きさ)

画面(tkinter)には触れない。
"""
from __future__ import annotations

from typing import Sequence


def clamp_area(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> tuple[int, int, int, int] | None:
    """
    範囲 (x1, y1)-(x2, y2) を、幅 width・高さ height の中に収める。収めた結果が空になる場合は None
    """
    x1, x2 = (min(max(v, 0), width) for v in (x1, x2))
    y1, y2 = (min(max(v, 0), height) for v in (y1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def area_to_ratio(area: Sequence[float], width: int, height: int) -> tuple[float, float, float, float]:
    """
    範囲 (start_x, start_y, end_x, end_y) を、幅・高さに対する割合にする
    """
    return area[0] / width, area[1] / height, area[2] / width, area[3] / height


def ratio_to_area(ratio: Sequence[float], width: int, height: int) -> tuple[int, int, int, int]:
    """
    割合を、幅・高さの上での範囲 (start_x, start_y, end_x, end_y) にする
    """
    return round(ratio[0] * width), round(ratio[1] * height), round(ratio[2] * width), round(ratio[3] * height)


def parse_ratio(text: str) -> tuple | None:
    """
    保存していた割合("0.1,0.2,0.3,0.4")を読む。4つの 0～1 の値でない場合は None
    """
    try:
        ratio = tuple(float(v) for v in text.split(","))
    except ValueError:
        return None
    if len(ratio) != 4 or not all(0.0 <= v <= 1.0 for v in ratio):
        return None
    return ratio


def ratio_to_text(ratio: Sequence[float] | None) -> str:
    """
    割合を、保存する文字にする(割合が無い場合は空文字)
    """
    return "" if ratio is None else ",".join(repr(float(v)) for v in ratio)


def ratio_matches_area(
    ratio: Sequence[float], area: Sequence[float], width: int, height: int, tolerance: float = 1
) -> bool:
    """
    割合から求めた範囲が、実際の範囲 area と(丸めの誤差の範囲で)合っているか
    """
    expected = (ratio[0] * width, ratio[1] * height, ratio[2] * width, ratio[3] * height)
    return all(abs(e - a) <= tolerance for e, a in zip(expected, area))


def size_for_height(height: float, aspect: float, min_height: int) -> tuple[int, int]:
    """
    高さから、縦横比(幅/高さ)を保った大きさ(幅, 高さ)を求める(高さは min_height 以上にする)
    """
    height = max(min_height, int(round(height)))
    return int(round(height * aspect)), height


def is_valid_size_text(text: object, aspect: float, min_height: int) -> bool:
    """
    "幅x高さ" が、縦横比(幅/高さ)と合っていて、高さが min_height 以上か
    text: 調べる値(文字にしてから読むので、文字以外でもよい。読めなければ False)
    """
    try:
        width, height = map(int, str(text).lower().split("x"))
    except ValueError:
        return False
    return height >= min_height and abs(width - height * aspect) <= 1
