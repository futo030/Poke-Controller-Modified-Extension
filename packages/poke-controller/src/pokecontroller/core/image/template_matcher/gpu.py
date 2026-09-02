from typing import Literal, Self

import cv2

from pokecontroller.core.image.image_processing import (
    GpuTemplateMatchable,
    match_template_by_gpu,
)
from pokecontroller.core.image.raw_image import RawImage
from pokecontroller.core.image.template_matcher.template_matcher import (
    TemplateMatchResult,
    TemplateMatcher,
)


class GpuTemplateMatcher(TemplateMatcher):
    """GPUを使用してテンプレートマッチングを実行する実装クラス.

    CUDAを使用してGPU上で高速な画像マッチングを行います。
    初期化時にGPUリソースを確保し、画像データをGPUメモリにアップロードします。
    マスク画像には対応していません。
    """

    def __init__(self, threshold: float = 0.8) -> None:
        """GpuTemplateMatcherインスタンスを初期化します.

        Args:
            threshold: マッチング判定の閾値. デフォルトは0.8.
        """
        super().__init__(threshold)

        self._initialized: bool = False
        self._gpu_matcher: GpuTemplateMatchable | None = None
        self._gpu_image: cv2.cuda.GpuMat | None = None
        self._gpu_template: cv2.cuda.GpuMat | None = None
        self.initialize()

    @property
    def mode(self) -> str:
        """マッチャーのモードを取得します.

        Returns:
            "gpu" を返します.
        """
        return "gpu"

    @property
    def is_initialized(self) -> bool:
        """マッチャーが初期化されているかどうかを取得します.

        Returns:
            GPUリソースの初期化に成功した場合はTrue、それ以外はFalse.
        """
        return self._initialized

    @property
    def mask(self) -> None:
        """マスク画像を取得します.

        GPU版はマスク画像に対応していないため、常にNoneを返します。

        Returns:
            常にNone.
        """
        return None

    @property
    def is_ready(self) -> bool:
        """マッチング実行の準備ができているかどうかを取得します.

        Returns:
            初期化済みで、画像とテンプレートの両方がGPUにアップロードされている
            場合はTrue、それ以外はFalse.
        """
        ready, *_ = self._ready_state()
        return ready

    def initialize(self) -> None:
        """マッチャーを初期化します.

        CUDAテンプレートマッチャーとGPUメモリバッファを作成します。
        既に初期化済みの場合は何もしません。
        """
        if self._initialized:
            return

        self._gpu_matcher = cv2.cuda.createTemplateMatching(  # type: ignore[attr-defined]
            cv2.CV_8UC1,
            cv2.TM_CCOEFF_NORMED,
        )
        self._gpu_image = cv2.cuda.GpuMat()
        self._gpu_template = cv2.cuda.GpuMat()
        self._initialized = True

    def set_image(self, image: RawImage | None) -> Self:
        """検索対象の画像を設定します.

        画像をCPUメモリに保存し、GPUメモリにアップロードします。

        Args:
            image: 設定する画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._image = image
        self._upload_image(self._gpu_image, image)
        return self

    def set_template(self, template: RawImage | None) -> Self:
        """テンプレート画像を設定します.

        テンプレート画像をCPUメモリに保存し、GPUメモリにアップロードします。

        Args:
            template: 設定するテンプレート画像.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        self._template = template
        self._upload_image(self._gpu_template, template)
        return self

    def set_mask(self, mask: RawImage | None) -> Self:
        """マスク画像を設定します.

        GPU版はマスク画像に対応していないため、何も行いません。

        Args:
            mask: マスク画像（無視されます）.

        Returns:
            自身のインスタンス（メソッドチェーン用）.
        """
        return self

    def match(self) -> TemplateMatchResult | None:
        """テンプレートマッチングを実行します.

        GPU上で設定された画像とテンプレートを使用してマッチングを実行し、
        最大一致位置と一致度を含む結果を返します。

        Returns:
            マッチング結果。準備ができていない場合はNone.
        """
        ready, *state = self._ready_state()
        if not ready:
            return None

        result = match_template_by_gpu(*state)
        return self._result_from(result)

    def _ready_state(
        self,
    ) -> (
        (tuple[Literal[True], GpuTemplateMatchable, cv2.cuda.GpuMat, cv2.cuda.GpuMat])
        | (tuple[Literal[False], None, None, None])
    ):
        if not self._initialized:
            return False, None, None, None
        if self._image is None or self._template is None:
            return False, None, None, None
        if (matcher := self._gpu_matcher) is None:
            return False, None, None, None
        if (img := self._gpu_image) is None or img.empty():
            return False, None, None, None
        if (tmpl := self._gpu_template) is None or tmpl.empty():
            return False, None, None, None
        return True, matcher, img, tmpl

    def _upload_image(self, var: cv2.cuda.GpuMat | None, val: RawImage | None) -> None:
        if not self._initialized:
            return

        if var is None or val is None:
            return

        var.upload(val)
