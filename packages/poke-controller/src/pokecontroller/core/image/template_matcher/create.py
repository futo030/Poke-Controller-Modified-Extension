from typing import Literal

from pokecontroller.core.image.template_matcher.cpu import CpuTemplateMatcher
from pokecontroller.core.image.template_matcher.gpu import GpuTemplateMatcher
from pokecontroller.core.image.template_matcher.template_matcher import TemplateMatcher

TemplateMatcherPreferredMode = Literal["cpu", "gpu"]


def create_template_matcher(
    preferred_mode: TemplateMatcherPreferredMode = "cpu",
) -> TemplateMatcher:
    """テンプレートマッチャーのインスタンスを生成します.

    指定されたモードに応じてCPU版またはGPU版のマッチャーを作成します。
    GPU版を選択した場合でも、初期化に失敗した場合は自動的にCPU版に
    フォールバックします。

    Args:
        preferred_mode: 優先するマッチャーのモード ("cpu" または "gpu").
            デフォルトは "cpu".

    Returns:
        作成されたTemplateMatcherインスタンス.
        GPU版の初期化に失敗した場合はCPU版を返します。
    """
    if preferred_mode == "gpu":
        try:
            gpu = GpuTemplateMatcher()
            if gpu.is_initialized:
                return gpu
        except Exception:  # noqa
            pass
    cpu = CpuTemplateMatcher()
    return cpu
