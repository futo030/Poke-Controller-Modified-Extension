import logging
from pathlib import Path
from typing import Literal, Sequence

import pokecontroller.core.image as imagelib
import pokecontroller.gui.image as gui
from numpy import argmax, array
from pokecontroller.core.image import (
    ImageBinarizeHsvArgs,
    ImageCropArgs,
    RawImage,
    TemplateMatcherPreferredMode,
    create_template_matcher,
)
from pokecontroller.core.image.utils import (
    convert_to_default,
)

logger = logging.getLogger(__name__)


def crop_image(
    image: RawImage,
    crop: list[int] | None = None,
) -> RawImage:
    """
    画像をトリミングする
    [y軸始点, y軸終点, x軸始点, x軸終点]
    """
    return crop_image_extend(image, crop_fmt=13, crop=crop)


def crop_image_extend(  # noqa
    image: RawImage,
    crop_fmt: int | str | None = None,
    crop: list[int] | None = None,
) -> RawImage:
    """
    画像をトリミングする
    ・Pillow形式
    x軸(横軸),y軸(縦軸),画像の左上が原点
    crop_fmt=1: [x軸始点, y軸始点, x軸終点, y軸終点]
    crop_fmt=2: [x軸始点, y軸始点, トリミング後の画像のサイズ(横), トリミング後の画像のサイズ(縦)]
    crop_fmt=3: [x軸始点, x軸終点, y軸始点, y軸終点]
    crop_fmt=4: [x軸始点, トリミング後の画像のサイズ(横), y軸始点, トリミング後の画像のサイズ(縦)]
    ・opencv形式(y, xの順番)
    crop_fmt=11: [y軸始点, x軸始点, y軸終点, x軸終点]
    crop_fmt=12: [y軸始点, x軸始点, トリミング後の画像のサイズ(縦), トリミング後の画像のサイズ(横)]
    crop_fmt=13: [y軸始点, y軸終点, x軸始点, x軸終点]
    crop_fmt=14: [y軸始点, トリミング後の画像のサイズ(縦), x軸始点, トリミング後の画像のサイズ(横)]
    """

    fmt = int(crop_fmt) if crop_fmt is not None else None

    if fmt is None or crop is None:
        return image

    try:
        sy, ey, sx, ex = convert_to_default((crop[0], crop[1], crop[2], crop[3]), fmt)
        return imagelib.crop(image, ImageCropArgs(sx=sx, ex=ex, sy=sy, ey=ey))
    except Exception:  # noqa
        return image


def getInterframeDiff(  # noqa
    frame1: RawImage,
    frame2: RawImage,
    frame3: RawImage,
    threshold: float,
) -> RawImage:
    """
    Get interframe difference binarized image
    フレーム間差分により2値化された画像を取得する
    """
    return imagelib.binarize_by_interframe_diff(frame1, frame2, frame3, threshold)


def getImage(  # noqa
    path: str,
    mode: str = "color",
) -> RawImage | None:
    """
    画像の読み込みを行う。
    """
    if not path:
        return None

    try:
        return imagelib.read(path, "color" if mode == "color" else "grayscale")
    except Exception:
        logger.error(
            f"{path}が開けませんでした。ファイル名およびファイルの格納場所を確認してください。"
        )
        return None


def doPreprocessImage(  # noqa
    image: RawImage,
    use_gray: bool = True,
    crop: list[int] | None = None,
    BGR_range: dict[Literal["lower", "upper"], RawImage] | None = None,  # noqa
    threshold_binary: int | None = None,
) -> tuple[RawImage, int, int]:
    """
    画像をトリミングしてグレースケール化/2値化する
    2値化関連のContributor: mikan kochan 空太 (敬称略)
    """
    img = crop_image(image, crop=crop)  # トリミング
    if use_gray:
        img = imagelib.grayscale(img)
    elif BGR_range is not None:  # 2値化
        args = ImageBinarizeHsvArgs(
            lower=array(BGR_range["lower"]),
            upper=array(BGR_range["upper"]),
        )
        img = imagelib.binarize_by_hsv(img, args)
    if threshold_binary is not None:
        img = imagelib.binarize_by_threshold(img, threshold_binary)

    return img, img.shape[1], img.shape[0]


def openImage(  # noqa
    image: RawImage,
    crop: list[int] | None = None,
    title: str = "image",
) -> None:  # noqa
    """
    キー入力があるまで画像を表示する
    Contributor: kochan (敬称略)
    """
    src = crop_image(image, crop=crop)  # トリミング
    gui.show(src, title)
    gui.destroy_all_windows()


class ImageProcessing:
    """
    画像に関する処理を行う。
    """

    __use_gpu = False
    image_type = RawImage

    def __init__(self, use_gpu: bool = False):
        preferred: TemplateMatcherPreferredMode = "gpu" if use_gpu else "cpu"
        self.__matcher = create_template_matcher(preferred_mode=preferred)
        if self.__matcher.mode == "gpu":
            logger.debug("template matching:mask is ignored.")
            self.__use_gpu = True
        else:
            self.__use_gpu = False

    # noinspection PyMethodMayBeStatic
    def imwrite(
        self,
        filename: str,
        image: RawImage,
        params: Sequence[int],
    ) -> bool:
        """
        画像を書き込む
        """
        try:
            return imagelib.write(image, filename, params)
        except Exception as e:
            logger.error(f"Image Write Error: {e}")
            return False

    def doTemplateMatch(  # noqa
        self,
        image: RawImage,
        template_image: RawImage,
        mask_image: RawImage | None = None,
    ) -> tuple[float, tuple[int, int]]:
        """
        テンプレートマッチングをする
        画像は必要に応じて事前にグレースケール化やトリミングをしておく必要がある
        """
        result = (
            self.__matcher.set_image(image)
            .set_template(template_image)
            .set_mask(mask_image)
            .match()
        )
        if result is None:
            return 0.0, (0, 0)
        else:
            return result.value_max, result.location_max

    def isContainTemplate(  # noqa
        self,
        image: RawImage,
        template_image: RawImage,
        mask_image: RawImage | None = None,
        threshold: float = 0.7,
        use_gray: bool = True,
        crop: list[int] | None = None,
        BGR_range: dict[Literal["lower", "upper"], RawImage] | None = None,  # noqa
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
    ) -> tuple[bool, tuple[int, int], int, int, float]:
        """
        テンプレートマッチングを行い類似度が閾値を超えているかを確認する
        """
        # テンプレートマッチング対象画像を加工する
        src, _, _ = doPreprocessImage(
            image,
            use_gray=use_gray,
            crop=crop,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
        )

        # [DEBUG] テンプレートマッチング対象画像を表示する
        if show_image:
            gui.show(src, "image")

        # テンプレート画像を加工する
        template, width, height = doPreprocessImage(
            template_image,
            use_gray=use_gray,
            crop=crop_template,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
        )

        # テンプレートマッチングを行う
        max_val, max_loc = self.doTemplateMatch(src, template, mask_image=mask_image)

        # 類似度が閾値を超えたかを戻り値として返す(合わせて位置とテンプレート画像のサイズも返す)
        return max_val > threshold, max_loc, width, height, max_val

    def isContainTemplate_max(  # noqa
        self,
        image: RawImage,
        template_image_list: list[RawImage],
        mask_image_list: list[RawImage] | None = None,
        threshold: float = 0.7,
        use_gray: bool = True,
        crop: list[int] | None = None,
        BGR_range: dict[Literal["lower", "upper"], RawImage] | None = None,  # noqa
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
    ) -> tuple[
        int, list[float], list[tuple[int, int]], list[int], list[int], list[bool]
    ]:
        """
        複数のテンプレート画像を用いてそれぞれテンプレートマッチングを行い類似度が最も大きい画像のindexを返す
        """
        # パラメータチェックを行う
        masks = mask_image_list if mask_image_list is not None else []
        mask_image_list_temp: Sequence[RawImage | None]
        if len(template_image_list) == len(masks):
            mask_image_list_temp = masks
        elif len(masks) == 0:
            mask_image_list_temp = [None for _ in range(len(template_image_list))]
        else:
            logger.debug("The number of template images and mask images don't match. ")
            return -1, [], [], [], [], []

        # ループをまわしてテンプレート画像数分テンプレートマッチングを行う
        max_val_list: list[float] = []
        max_loc_list: list[tuple[int, int]] = []
        width_list: list[int] = []
        height_list: list[int] = []
        judge_threshold_list: list[bool] = []

        # テンプレートマッチング対象画像を加工する
        src, _, _ = doPreprocessImage(
            image,
            use_gray=use_gray,
            crop=crop,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
        )

        # [DEBUG] テンプレートマッチング対象画像を表示する
        if show_image:
            gui.show(src, "image")

        for template_image, mask_image in zip(
            template_image_list, mask_image_list_temp
        ):
            # テンプレート画像を加工する
            template, width, height = doPreprocessImage(
                template_image,
                use_gray=use_gray,
                crop=crop_template,
                BGR_range=BGR_range,
                threshold_binary=threshold_binary,
            )
            max_val, max_loc = self.doTemplateMatch(
                src, template, mask_image=mask_image
            )
            max_val_list.append(max_val)
            max_loc_list.append(max_loc)
            width_list.append(width)
            height_list.append(height)
            judge_threshold_list.append(max_val > threshold)

        return (
            int(argmax(max_val_list)),
            max_val_list,
            max_loc_list,
            width_list,
            height_list,
            judge_threshold_list,
        )

    def saveImage(  # noqa
        self,
        image: RawImage,
        filename: str,
        crop: list[int] | None = None,
    ) -> None:
        """
        画像を保存する。
        """
        cropped_image = crop_image(image, crop=crop)

        filepath = Path(filename)
        # ファイル名からパスを抽出する
        capture_dir = filepath.parent

        # 画像保存用ディレクトリの存在を確認し、なかったら作成する。
        if not capture_dir.exists() or not capture_dir.is_dir():
            capture_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Created Capture folder")

        # 画像を保存する
        try:
            self.imwrite(filename, cropped_image, [])
            logger.debug(f"Capture succeeded: {filename}")
        except Exception as e:
            logger.error(f"Capture Failed :{e}")
