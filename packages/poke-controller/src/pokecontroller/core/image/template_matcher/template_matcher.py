from abc import ABC, abstractmethod
from typing import Self

import cv2

from pokecontroller.core.exception.base import PokeControllerException
from pokecontroller.core.image.image_processing import TemplateMatchResult
from pokecontroller.core.image.raw_image import RawImage


class TemplateMatcher(ABC):
    """テンプレートマッチングを実行する抽象基底クラス.

    画像内からテンプレート画像を検索し、一致位置と一致度を返します。
    CPU版とGPU版の実装があります。
    """

    def __init__(self, threshold: float = 0.8):
        """TemplateMatcherインスタンスを初期化します.

        Args:
            threshold: マッチング判定の閾値. デフォルトは0.8.
        """
        self._image: RawImage | None = None
        self._template: RawImage | None = None
        self._mask: RawImage | None = None
        self._threshold: float = threshold
        self._last_result: TemplateMatchResult | None = None

    @property
    @abstractmethod
    def mode(self) -> str:
        """マッチャーのモード ("cpu" または "gpu") を取得します.

        Returns:
            マッチャーのモード文字列.
        """
        ...

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """マッチャーが初期化されているかどうかを取得します.

        Returns:
            初期化済みの場合はTrue、それ以外はFalse.
        """
        ...

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """マッチング実行の準備ができているかどうかを取得します.

        Returns:
            準備ができている場合はTrue、それ以外はFalse.
        """
        ...

    @property
    def image(self) -> RawImage | None:
        """検索対象の画像を取得します.

        Returns:
            設定されている画像、または未設定の場合はNone.
        """
        return self._image

    @property
    def template(self) -> RawImage | None:
        """テンプレート画像を取得します.

        Returns:
            設定されているテンプレート画像、または未設定の場合はNone.
        """
        return self._template

    @property
    def mask(self) -> RawImage | None:
        """マスク画像を取得します.

        Returns:
            設定されているマスク画像、または未設定の場合はNone.
        """
        return self._mask

    @property
    def threshold(self) -> float:
        """マッチング判定の閾値を取得します.

        Returns:
            現在の閾値.
        """
        return self._threshold

    @property
    def last_result(self) -> TemplateMatchResult | None:
        """最後のマッチング結果を取得します.

        Returns:
            最後のマッチング結果、またはまだマッチングを実行していない場合はNone.
        """
        return self._last_result

    @abstractmethod
    def initialize(self) -> None:
        """マッチャーを初期化します."""
        ...

    @abstractmethod
    def match(self) -> TemplateMatchResult | None:
        """テンプレートマッチングを実行します.

        Returns:
            マッチング結果、または準備ができていない場合はNone.
        """
        ...

    @abstractmethod
    def set_image(self, image: RawImage | None) -> Self:
        """検索対象の画像を設定します.

        Args:
            image: 設定する画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        ...

    @abstractmethod
    def set_template(self, template: RawImage | None) -> Self:
        """テンプレート画像を設定します.

        Args:
            template: 設定するテンプレート画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        ...

    @abstractmethod
    def set_mask(self, mask: RawImage | None) -> Self:
        """マスク画像を設定します.

        Args:
            mask: 設定するマスク画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        ...

    def set_threshold(self, threshold: float) -> Self:
        """マッチング判定の閾値を設定します.

        Args:
            threshold: 設定する閾値.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._threshold = threshold
        return self

    def _result_from(self, result: RawImage) -> TemplateMatchResult:
        _, value_max, _, location_max = cv2.minMaxLoc(result)

        if (tmpl := self._template) is None:
            raise PokeControllerException("Template is not set")

        h, w, *_ = tmpl.shape
        self._last_result = TemplateMatchResult(
            contains=value_max > self._threshold,
            location_max=(location_max[0], location_max[1]),
            width=w,
            height=h,
            value_max=value_max,
        )
        return self._last_result
