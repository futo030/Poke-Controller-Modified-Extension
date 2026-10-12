#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音声の解析(音量の計算)

音声は float32 の numpy 配列(-1.0～1.0)で扱う。形は (サンプル数, チャンネル数) またはモノラルの (サンプル数,)。
"""
from __future__ import annotations

import math
from logging import getLogger, DEBUG, NullHandler

import numpy as np

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 音量の下限(dBFS)。無音の場合に返す値
SILENCE_DB = -120.0


def to_mono(audio: np.ndarray) -> np.ndarray:
    """モノラル(チャンネルの平均)の float32 にする(もともとモノラルなら、そのまま)"""
    audio = np.asarray(audio, dtype=np.float32)
    return audio if audio.ndim == 1 else audio.mean(axis=1)


def rms(audio: np.ndarray | None) -> float:
    """
    音量(二乗平均平方根。0.0～1.0)。None や空の場合は 0.0
    """
    if audio is None or len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(np.asarray(audio, dtype=np.float32)))))


def to_db(value: float) -> float:
    """
    音量をdBFS(最大音量が0dB)に変換する
    """
    if value <= 0:
        return SILENCE_DB
    return max(20.0 * math.log10(value), SILENCE_DB)


def volume_db(audio: np.ndarray | None) -> float:
    """音声の音量(dBFS。最大音量が 0 dB、無音や空の場合は SILENCE_DB)"""
    return to_db(rms(audio))
