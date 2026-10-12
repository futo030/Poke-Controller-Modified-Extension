#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キャプチャ画面の目隠し(長方形・楕円の塗りつぶし)

- 座標はカメラ画像の座標(取り込みサイズ)で持つ。表示サイズを変えても同じ場所を隠す
- プレビューにはCanvasの図形として重ねる(カメラ画像は書き換えないので、コマンドの画像認識には影響しない)
- スクリーンショットの保存やタッチ画面の表示に使う画像には、draw_masksで描き込む
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

import cv2
import numpy as np

SHAPE_RECTANGLE = "Rectangle"
SHAPE_ELLIPSE = "Ellipse"
MASK_SHAPES = (SHAPE_RECTANGLE, SHAPE_ELLIPSE)
DEFAULT_MASK_COLOR = "#000000"


@dataclass
class Mask:
    """1 つの目隠し(形、カメラ画像の座標、色("#rrggbb")、有効か)"""

    shape: str = SHAPE_RECTANGLE
    # カメラ画像の座標(x1 < x2, y1 < y2)
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0
    color: str = DEFAULT_MASK_COLOR
    enabled: bool = True

    def normalized(self) -> Mask:
        """
        座標の大小を揃えたものを返す
        """
        return replace(
            self,
            x1=min(self.x1, self.x2),
            y1=min(self.y1, self.y2),
            x2=max(self.x1, self.x2),
            y2=max(self.y1, self.y2),
        )

    def to_text(self) -> str:
        """
        設定ファイルに保存する文字列
        """
        return ",".join(
            [self.shape, str(self.x1), str(self.y1), str(self.x2), str(self.y2), self.color, "1" if self.enabled else "0"]
        )

    @staticmethod
    def from_text(text: str) -> Mask:
        """設定ファイルの文字列(to_text の形)から作る(項目の数・形・色・数値が正しくない場合は ValueError)"""
        shape, x1, y1, x2, y2, color, enabled = [v.strip() for v in text.split(",")]
        if shape not in MASK_SHAPES:
            raise ValueError(f"unknown shape: {shape}")
        hex_to_bgr(color)
        return Mask(shape, int(x1), int(y1), int(x2), int(y2), color, enabled == "1").normalized()


def hex_to_bgr(color: str) -> tuple[int, int, int]:
    """
    "#rrggbb" を OpenCV の色(B, G, R)に変換する(この形でない場合は ValueError)
    """
    if len(color) != 7 or color[0] != "#":
        raise ValueError(f"invalid color: {color}")
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return b, g, r


def draw_masks(image: np.ndarray, masks: list[Mask], offset: tuple[int, int] = (0, 0)) -> np.ndarray:
    """
    BGR画像に有効な目隠しを描き込んだ画像を返す(元の画像は書き換えない。目隠しが無ければ元の画像をそのまま返す)
    offset: imageの左上が、カメラ画像のどの座標にあたるか(切り出した画像に描く場合に指定する)
    """
    active = [m for m in masks if m.enabled]
    if not active:
        return image
    result = image.copy()
    ox, oy = offset
    for mask in active:
        x1, y1, x2, y2 = mask.x1 - ox, mask.y1 - oy, mask.x2 - ox, mask.y2 - oy
        color = hex_to_bgr(mask.color)
        if mask.shape == SHAPE_ELLIPSE:
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
            axes = (max((x2 - x1) // 2, 0), max((y2 - y1) // 2, 0))
            cv2.ellipse(result, center, axes, 0, 0, 360, color, -1)
        else:
            cv2.rectangle(result, (x1, y1), (x2, y2), color, -1)
    return result


def save_masks(path: str, masks: list[Mask]) -> None:
    """
    目隠しの一覧をファイル(JSON)に書き出す
    """
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"masks": [asdict(mask) for mask in masks]}, file, ensure_ascii=False, indent=2)


def load_masks(path: str) -> list[Mask]:
    """
    save_masksで書き出したファイルから目隠しの一覧を読み込む(内容が正しくない場合はValueError)
    """
    try:
        with open(path, encoding="utf-8-sig") as file:
            data = json.load(file)
        masks = []
        for item in data["masks"]:
            shape, color = item["shape"], item.get("color", DEFAULT_MASK_COLOR)
            if shape not in MASK_SHAPES:
                raise ValueError(f"unknown shape: {shape}")
            hex_to_bgr(color)
            masks.append(
                Mask(
                    shape, int(item["x1"]), int(item["y1"]), int(item["x2"]), int(item["y2"]), color,
                    bool(item.get("enabled", True)),
                ).normalized()
            )  # fmt: skip
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as e:
        raise ValueError(f"invalid mask file: {e!r}") from e
    return masks
