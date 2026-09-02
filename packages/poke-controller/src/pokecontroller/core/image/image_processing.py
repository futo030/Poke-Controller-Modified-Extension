import io
import logging
import os
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import cv2
from PIL import Image

from pokecontroller.core.image.raw_image import RawImage

logger = logging.getLogger(__name__)

ImageReadMode = Literal["grayscale", "color"]


@dataclass(kw_only=True, frozen=True)
class ImageCropArgs:
    """画像のクロップ（切り抜き）パラメータを保持するデータクラス.

    Attributes:
        sx: 開始X座標.
        ex: 終了X座標.
        sy: 開始Y座標.
        ey: 終了Y座標.
    """

    sx: int
    ex: int
    sy: int
    ey: int


@dataclass(kw_only=True, frozen=True)
class ImageBinarizeHsvArgs:
    """HSV色空間による二値化パラメータを保持するデータクラス.

    Attributes:
        lower: HSV色空間の下限値.
        upper: HSV色空間の上限値.
    """

    lower: RawImage
    upper: RawImage


@dataclass(kw_only=True, frozen=True)
class TemplateMatchResult:
    """テンプレートマッチングの結果を保持するデータクラス.

    Attributes:
        contains: テンプレートが画像内に含まれているかどうか.
        location_max: 最大一致位置の座標 (x, y).
        width: テンプレートの幅.
        height: テンプレートの高さ.
        value_max: 最大一致度の値.
    """

    contains: bool
    location_max: tuple[int, int]
    width: int
    height: int
    value_max: float


class RawImageDownloadable(Protocol):
    """GPU上の画像をダウンロード可能なオブジェクトのプロトコル."""

    def download(self) -> RawImage:
        """GPU上の画像をCPUメモリにダウンロードします.

        Returns:
            ダウンロードされた画像.
        """
        ...


class GpuTemplateMatchable(Protocol):
    """GPUでテンプレートマッチングを実行可能なオブジェクトのプロトコル."""

    def match(
        self,
        image: cv2.cuda.GpuMat,
        template: cv2.cuda.GpuMat,
    ) -> RawImageDownloadable:
        """GPU上でテンプレートマッチングを実行します.

        Args:
            image: 検索対象の画像 (GPU上).
            template: テンプレート画像 (GPU上).

        Returns:
            マッチング結果をダウンロード可能なオブジェクト.
        """
        ...


def crop(src: RawImage, args: ImageCropArgs) -> RawImage:
    """画像を指定された領域で切り抜きます.

    Args:
        src: 元画像.
        args: クロップパラメータ.

    Returns:
        切り抜かれた画像.
    """
    logger.debug(f"src[{args.sy} : {args.ey}, {args.sx} : {args.ex}]")
    return src[args.sy : args.ey, args.sx : args.ex]


def resize(src: RawImage, size: tuple[int, int]) -> RawImage:
    """画像を指定されたサイズにリサイズします.

    Args:
        src: 元画像.
        size: リサイズ後のサイズ (幅, 高さ).

    Returns:
        リサイズされた画像.
    """
    return cv2.resize(src, size, interpolation=cv2.INTER_LINEAR)


def grayscale(src: RawImage) -> RawImage:
    """画像をグレースケールに変換します.

    Args:
        src: 元画像 (BGR形式).

    Returns:
        グレースケール画像.
    """
    return cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)


def bgr_to_rgb(src: RawImage) -> RawImage:
    """BGRフォーマットの画像をRGBに変換します.

    Args:
        src: 元画像 (BGR形式).

    Returns:
        RGB形式の画像.
    """
    return cv2.cvtColor(src, cv2.COLOR_BGR2RGB)


def binarize_by_hsv(src: RawImage, args: ImageBinarizeHsvArgs) -> RawImage:
    """HSV色空間に基づいて画像を二値化します.

    Args:
        src: 元画像.
        args: HSV二値化パラメータ.

    Returns:
        二値化された画像.
    """
    return cv2.inRange(src, args.lower, args.upper)


def binarize_by_threshold(src: RawImage, threshold: float) -> RawImage:
    """閾値に基づいて画像を二値化します.

    Args:
        src: 元画像.
        threshold: 二値化の閾値.

    Returns:
        二値化された画像.
    """
    return cv2.threshold(src, threshold, 255, cv2.THRESH_BINARY)[1]


def binarize_by_interframe_diff(
    src1: RawImage,
    src2: RawImage,
    src3: RawImage,
    threshold: float,
) -> RawImage:
    """フレーム間差分に基づいて画像を二値化します.

    3つの連続フレームの差分を取り、動きを検出します。

    Args:
        src1: 1番目のフレーム.
        src2: 2番目のフレーム.
        src3: 3番目のフレーム.
        threshold: 二値化の閾値.

    Returns:
        二値化された差分画像.
    """
    diff1 = cv2.absdiff(src1, src2)
    diff2 = cv2.absdiff(src2, src3)
    diff = cv2.bitwise_and(diff1, diff2)
    th = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)[1]
    return cv2.medianBlur(th, 3)


def write(src: RawImage, path: str, params: Sequence[int]) -> bool:
    """画像をファイルに書き込みます.

    Args:
        src: 保存する画像.
        path: 保存先のファイルパス.
        params: エンコードパラメータ.

    Returns:
        書き込みに成功した場合はTrue、それ以外はFalse.
    """
    ext = os.path.splitext(path)[1]
    success, encoded = cv2.imencode(ext, src, params)

    if not success:
        return False

    with open(path, mode="w+b") as f:
        encoded.tofile(f)
    return True


def read(path: str, mode: ImageReadMode = "color") -> RawImage | None:
    """ファイルから画像を読み込みます.

    Args:
        path: 読み込む画像ファイルのパス.
        mode: 読み込みモード ("grayscale" または "color").
            デフォルトは "color".

    Returns:
        読み込まれた画像。パスが空の場合はNone.
    """
    if not path:
        return None

    match mode:
        case "grayscale":
            return cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        case "color":
            return cv2.imread(path, cv2.IMREAD_COLOR)


def to_bytes(src: RawImage, fmt: str | None = None) -> bytes:
    """画像をバイト列に変換します.

    Args:
        src: 変換する画像 (BGR形式).
        fmt: 出力フォーマット (例: "PNG", "JPEG"). Noneの場合は自動判定.

    Returns:
        画像のバイト列表現.
    """
    rgb = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    bio = io.BytesIO()
    image.save(bio, format=fmt)
    return bio.getvalue()


def match_template(
    image: RawImage,
    template: RawImage,
    mask: RawImage | None = None,
) -> RawImage:
    """テンプレートマッチングを実行します.

    Args:
        image: 検索対象の画像.
        template: テンプレート画像.
        mask: マスク画像（オプション）.

    Returns:
        マッチング結果のスコアマップ.
    """
    if mask is None:
        method = cv2.TM_CCOEFF_NORMED
    else:
        method = cv2.TM_CCORR_NORMED
    return cv2.matchTemplate(image, template, method, mask=mask)


def match_template_by_gpu(
    matcher: GpuTemplateMatchable,
    image: cv2.cuda.GpuMat,
    template: cv2.cuda.GpuMat,
) -> RawImage:
    """GPUを使用してテンプレートマッチングを実行します.

    Args:
        matcher: GPUマッチャー.
        image: 検索対象の画像 (GPU上).
        template: テンプレート画像 (GPU上).

    Returns:
        マッチング結果のスコアマップ.
    """
    result = matcher.match(image, template)
    return result.download()
