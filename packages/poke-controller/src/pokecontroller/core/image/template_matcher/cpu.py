from typing import Literal, Self

from pokecontroller.core.image.image_processing import match_template
from pokecontroller.core.image.raw_image import RawImage
from pokecontroller.core.image.template_matcher.template_matcher import (
    TemplateMatchResult,
    TemplateMatcher,
)


class CpuTemplateMatcher(TemplateMatcher):
    """CPUを使用してテンプレートマッチングを実行する実装クラス.

    OpenCVのCPU版matchTemplate関数を使用して画像マッチングを行います。
    初期化が不要で、画像とテンプレートが設定されればすぐに使用できます。
    """

    @property
    def mode(self) -> str:
        """マッチャーのモードを取得します.

        Returns:
            "cpu" を返します.
        """
        return "cpu"

    @property
    def is_initialized(self) -> bool:
        """マッチャーが初期化されているかどうかを取得します.

        CPU版は初期化が不要なため、常にTrueを返します。

        Returns:
            常にTrue.
        """
        return True

    @property
    def is_ready(self) -> bool:
        """マッチング実行の準備ができているかどうかを取得します.

        Returns:
            画像とテンプレートの両方が設定されている場合はTrue、それ以外はFalse.
        """
        ready, *_ = self._ready_state()
        return ready

    def set_image(self, image: RawImage | None) -> Self:
        """検索対象の画像を設定します.

        Args:
            image: 設定する画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._image = image
        return self

    def set_template(self, template: RawImage | None) -> Self:
        """テンプレート画像を設定します.

        Args:
            template: 設定するテンプレート画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._template = template
        return self

    def set_mask(self, mask: RawImage | None) -> Self:
        """マスク画像を設定します.

        Args:
            mask: 設定するマスク画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._mask = mask
        return self

    def initialize(self) -> None:
        """マッチャーを初期化します.

        CPU版は初期化が不要なため、何も行いません。
        """
        pass

    def match(self) -> TemplateMatchResult | None:
        """テンプレートマッチングを実行します.

        設定された画像とテンプレートを使用してマッチングを実行し、
        最大一致位置と一致度を含む結果を返します。

        Returns:
            マッチング結果。準備ができていない場合はNone.
        """
        ready, *state = self._ready_state()
        if not ready:
            return None

        result = match_template(*state)
        return self._result_from(result)

    def _ready_state(
        self,
    ) -> (
        tuple[Literal[True], RawImage, RawImage, RawImage | None]
        | tuple[Literal[False], None, None, None]
    ):
        if (img := self._image) is None or (tmpl := self._template) is None:
            return False, None, None, None
        return True, img, tmpl, self._mask
