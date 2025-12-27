import datetime
import logging
import os
import random
import string
import time
from typing import Any

from pokecontroller.core.image import RawImage

from pokecontrollerext.api.v0_1_8.camera import Camera
from pokecontrollerext.api.v0_1_8.command.commands.base import (
    PostProcess,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.base import (
    PythonCommand,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.decorators import (
    pausable,
)
from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.api.v0_1_8.image_processing import (
    ImageProcessing,
    crop_image,
    getImage,
    openImage,
)

logger = logging.getLogger(__name__)


def generateRandomCharacter(n: int) -> str:
    """
    指定数のランダムな文字列を生成する
    Contributor: kochan (敬称略)
    """
    c = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return "".join([random.choice(c) for _ in range(n)])


def convertCv2Format(
    crop_fmt: int | str = "", crop: list[int] | None = None
) -> tuple[list[int], list[int]]:
    """
    リストをopencv/pillow形式に対応するよう変換する。
    ・Pillow形式
    x軸(横軸),y軸(縦軸),画像の左上が原点
    crop_fmt=1: [x軸始点, y軸始点, x軸終点, y軸終点] (res_pillowとして出力されるリスト)
    crop_fmt=2: [x軸始点, y軸始点, トリミング後の画像のサイズ(横), トリミング後の画像のサイズ(縦)]
    crop_fmt=3: [x軸始点, x軸終点, y軸始点, y軸終点]
    crop_fmt=4: [x軸始点, トリミング後の画像のサイズ(横), y軸始点, トリミング後の画像のサイズ(縦)]
    ・opencv形式(y, xの順番)
    crop_fmt=11: [y軸始点, x軸始点, y軸終点, x軸終点]
    crop_fmt=12: [y軸始点, x軸始点, トリミング後の画像のサイズ(縦), トリミング後の画像のサイズ(横)]
    crop_fmt=13: [y軸始点, y軸終点, x軸始点, x軸終点] (res_cv2として出力されるリスト)
    crop_fmt=14: [y軸始点, トリミング後の画像のサイズ(縦), x軸始点, トリミング後の画像のサイズ(横)]
    """
    if crop is None:
        return [], []

    try:
        # pillow形式
        if crop_fmt == 1 or crop_fmt == "1":
            res_cv2 = [crop[1], crop[3], crop[0], crop[2]]
        elif crop_fmt == 2 or crop_fmt == "2":
            res_cv2 = [crop[1], crop[1] + crop[3], crop[0], crop[0] + crop[2]]
        elif crop_fmt == 3 or crop_fmt == "3":
            res_cv2 = [crop[2], crop[3], crop[0], crop[1]]
        elif crop_fmt == 4 or crop_fmt == "4":
            res_cv2 = [crop[2], crop[2] + crop[3], crop[0], crop[0] + crop[1]]
        # opencv形式
        elif crop_fmt == 11 or crop_fmt == "11":
            res_cv2 = [crop[0], crop[2], crop[1], crop[3]]
        elif crop_fmt == 12 or crop_fmt == "12":
            res_cv2 = [crop[0], crop[0] + crop[2], crop[1], crop[1] + crop[3]]
        elif crop_fmt == 13 or crop_fmt == "13":
            res_cv2 = [crop[0], crop[1], crop[2], crop[3]]
        elif crop_fmt == 14 or crop_fmt == "14":
            res_cv2 = [crop[0], crop[0] + crop[1], crop[2], crop[2] + crop[3]]
        else:
            res_cv2 = [crop[1], crop[3], crop[0], crop[2]]
        res_pillow = [res_cv2[2], res_cv2[0], res_cv2[3], res_cv2[1]]
    except Exception:
        res_cv2 = []
        res_pillow = []

    return res_cv2, res_pillow


class ImageProcPythonCommand(PythonCommand):
    template_path_name = "./Template/"
    capture_path_name = "./Captures/"

    def __init__(
        self,
        cam: Camera,
        gui: Any | None = None,
    ) -> None:
        super().__init__()

        self.camera = cam
        self.gui: Any | None = gui

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        ImageProcPythonCommand.template_path_name = "./Template"
        super().start(ser, postProcess)

    def get_filespec(self, filename: str, mode: str = "t") -> str:
        """
        画像ファイルの保存パスを取得する。

        入力が絶対パスの場合は、modeに合わせて、`template_path_name/capture_path_name`につなげずに返す。

        Args:
            filename (str): 保存名／保存パス
            mode (str): 相対パスの種類

        Returns:
            str: _description_
        """
        if os.path.isabs(filename):
            return filename
        elif mode == "c":
            return os.path.join(self.capture_path_name, filename)
        elif mode == "t":
            return os.path.join(self.template_path_name, filename)
        else:
            return filename

    def setTemplateDir(self, path: str) -> None:
        ImageProcPythonCommand.template_path_name = path

    def getCameraImage(
        self,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
    ) -> RawImage | None:
        """
        カメラから画像データを取得する
        """
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("getCameraImage: camera is not initialized.")
            return None

        # トリミング
        return crop_image(src, crop=crop_cv2)

    def openImage(
        self,
        filename: str,
        mode: str = "t",
    ) -> RawImage | None:
        """
        指定されたパスの画像データを取得する
        """
        return getImage(self.get_filespec(filename, mode=mode), mode="color")

    @pausable
    def isContainTemplate(
        self,
        template_path: str | RawImage,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        mask_path: str | RawImage | None = None,
        use_gpu: bool = False,
        BGR_range: dict | None = None,
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
        color: list[str] | None = None,
    ) -> bool:
        """
        現在のスクリーンショットと指定した画像のテンプレートマッチングを行います。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。
        """
        if crop is None:
            crop = []
        if crop_template is None:
            crop_template = []
        if color is None:
            color = ["blue", "red", "orange"]

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop_template)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("isContainTemplate: camera is not initialized.")
            return False

        # テンプレート画像を取得
        if not isinstance(template_path, str):
            template_image = template_path
        else:
            if (
                t := getImage(self.get_filespec(template_path, mode="t"), mode="color")
            ) is None:
                logger.warning(f"isContainTemplate: {template_path} is not found.")
                return False
            template_image = t

        # マスク画像を取得
        if not isinstance(mask_path, str):
            mask_image = mask_path
        else:
            mask_image = (
                getImage(self.get_filespec(mask_path, mode="t"), mode="binary")
                if mask_path is not None
                else None
            )

        # テンプレートマッチング
        res, max_loc, width, height, max_val = ImageProcessing(
            use_gpu=use_gpu
        ).isContainTemplate(
            src,
            template_image,
            mask_image=mask_image,
            threshold=threshold,
            use_gray=use_gray,
            crop=crop_cv2,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template_cv2,
            show_image=show_image,
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = "NCC" if mask_path is not None else "ZNCC"
            print(f"{template_path} {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            ml = (
                (max_loc[0] + crop_pillow[0], max_loc[1] + crop_pillow[1])
                if crop_pillow
                else max_loc
            )
            tag = str(time.perf_counter()) + str(random.random())
            if res:
                self.displayRectangle(
                    ml,
                    width,
                    height,
                    tag,
                    ms,
                    color=[color[0], color[2]],
                    crop=crop_pillow,
                )
            elif not show_only_true_rect:
                self.displayRectangle(
                    ml,
                    width,
                    height,
                    tag,
                    ms,
                    color=[color[1], color[2]],
                    crop=crop_pillow,
                )

        return res

    @pausable
    def isContainTemplate_max(
        self,
        template_path_list: list[str | RawImage],
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        mask_path_list: list[str | RawImage] | None = None,
        BGR_range: dict | None = None,
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
        color: list[str] | None = None,
    ) -> tuple[int, list[float], list[bool]]:
        """
        # 現在のスクリーンショットと指定した複数の画像のテンプレートマッチングを行います。
        # 相関値が最も大きい値となった画像のインデックス、各画像のテンプレートマッチングの閾値、閾値判定結果を返します。
        # 色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。
        """
        if crop is None:
            crop = []
        if mask_path_list is None:
            mask_path_list = []
        if crop_template is None:
            crop_template = []
        if color is None:
            color = ["blue", "red", "orange"]

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop_template)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("isContainTemplate_max: camera is not initialized.")
            return -1, [], []

        # テンプレート画像を取得
        template_image_list = []
        for i in template_path_list:
            if not isinstance(i, str):
                template_image_list.append(i)
            else:
                if (
                    t := getImage(self.get_filespec(i, mode="t"), mode="color")
                ) is not None:
                    template_image_list.append(t)

        # マスク画像を取得
        mask_image_list: list[RawImage] = []
        if mask_path_list is not None:
            for i in mask_path_list:
                if not isinstance(i, str):
                    mask_image_list.append(i)
                else:
                    if (
                        m := getImage(self.get_filespec(i, mode="t"), mode="binary")
                    ) is not None:
                        mask_image_list.append(m)

        # テンプレートマッチング
        max_idx, max_val_list, max_loc_list, width_list, height_list, judge_list = (
            ImageProcessing(use_gpu=False).isContainTemplate_max(
                src,
                template_image_list,
                mask_image_list=mask_image_list,
                threshold=threshold,
                use_gray=use_gray,
                crop=crop_cv2,
                BGR_range=BGR_range,
                threshold_binary=threshold_binary,
                crop_template=crop_template_cv2,
                show_image=show_image,
            )
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = (
                "ZNCC" if (mask_path_list == [] or mask_path_list is None) else "NCC"
            )
            for template_path, max_val in zip(template_path_list, max_val_list):
                print(f"{template_path} {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            max_loc = max_loc_list[max_idx]
            ml = (
                (max_loc[0] + crop_pillow[0], max_loc[1] + crop_pillow[1])
                if crop_pillow
                else max_loc
            )
            tag = str(time.perf_counter()) + str(random.random())
            if True in judge_list:
                self.displayRectangle(
                    ml,
                    width_list[max_idx],
                    height_list[max_idx],
                    tag,
                    ms,
                    color=[color[0], color[2]],
                    crop=crop_pillow,
                )
            elif not show_only_true_rect:
                self.displayRectangle(
                    ml,
                    width_list[max_idx],
                    height_list[max_idx],
                    tag,
                    ms,
                    color=[color[1], color[2]],
                    crop=crop_pillow,
                )
            else:
                pass

        return max_idx, max_val_list, judge_list

    @pausable
    def isContainTemplateGPU(
        self,
        template_path: str,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        mask_path: str | RawImage | None = None,
        BGR_range: dict | None = None,
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
        color: list[str] | None = None,
    ) -> bool:
        """
        現在のスクリーンショットと指定した画像のテンプレートマッチングを行います。
        テンプレートマッチングにGPUを使用します。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。
        """
        if crop is None:
            crop = []
        if crop_template is None:
            crop_template = []
        if color is None:
            color = ["blue", "red", "orange"]

        # テンプレートマッチング
        res = self.isContainTemplate(
            template_path,
            threshold=threshold,
            use_gray=use_gray,
            show_value=show_value,
            show_position=show_position,
            show_only_true_rect=show_only_true_rect,
            ms=ms,
            crop_fmt=crop_fmt,
            crop=crop,
            mask_path=mask_path,
            use_gpu=True,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template,
            show_image=show_image,
            color=color,
        )

        return res

    @pausable
    def isContainedImage(
        self,
        image_path: str | RawImage,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        mask_path: str | RawImage | None = None,
        use_gpu: bool = False,
        BGR_range: dict | None = None,
        threshold_binary: int | None = None,
        crop_template: list[int] | None = None,
        show_image: bool = False,
        color: list[str] | None = None,
    ) -> bool:
        """
        指定した画像に対して現在のスクリーンショットから生成したテンプレート画像を用いてテンプレートマッチングを行います。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。
        """

        if crop is None:
            crop = []
        if crop_template is None:
            crop_template = []
        if color is None:
            color = ["blue", "red", "orange"]

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, crop_template_pillow = convertCv2Format(
            crop_fmt=crop_fmt, crop=crop_template
        )

        # カメラの画像を取得
        if (template_image := self.camera.readFrame()) is None:
            return False

        # テンプレートマッチング対象画像を取得
        if not isinstance(image_path, str):
            image = image_path
        elif (
            i := getImage(self.get_filespec(image_path, mode="t"), mode="color")
        ) is not None:
            image = i
        else:
            logger.warning(f"{image_path} is not found.")
            return False

        # マスク画像を取得
        if not isinstance(mask_path, str):
            mask_image = mask_path
        else:
            mask_image = (
                getImage(self.get_filespec(mask_path, mode="t"), mode="binary")
                if mask_path is not None
                else None
            )

        # テンプレートマッチング
        res, _, width, height, max_val = ImageProcessing(
            use_gpu=use_gpu
        ).isContainTemplate(
            image,
            template_image,
            mask_image=mask_image,
            threshold=threshold,
            use_gray=use_gray,
            crop=crop_cv2,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template_cv2,
            show_image=show_image,
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = "NCC" if mask_path is not None else "ZNCC"
            print(f"capture_image {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            tag = str(time.perf_counter()) + str(random.random())
            if res:
                self.displayRectangle(
                    tuple(crop_template_pillow[0:2]),
                    width,
                    height,
                    tag,
                    ms,
                    color=[color[0], color[2]],
                    crop=[],
                )
            elif not show_only_true_rect:
                self.displayRectangle(
                    tuple(crop_template_pillow[0:2]),
                    width,
                    height,
                    tag,
                    ms,
                    color=[color[1], color[2]],
                    crop=[],
                )
            else:
                pass

        return res

    def displayRectangle(
        self,
        max_loc: tuple,
        width: int,
        height: int,
        tag: str | None = None,
        ms: float = 2000,
        color: list[str] | None = None,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
    ) -> None:
        """
        GUIの画面に四角形を表示します。
        互換性維持のため、gui/canvas(元をたどると同じ変数)の両方に対応します。
        """
        if color is None:
            color = ["blue", "orange"]
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        _, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        top_left = max_loc
        bottom_right = (top_left[0] + width + 1, top_left[1] + height + 1)
        if self.gui is not None:
            canvas = self.gui
        else:
            canvas = self.canvas

        if tag is None:
            tag = generateRandomCharacter(10)

        if self.gui is not None or self.isGuide:
            if crop_pillow != []:
                start = tuple(crop_pillow[0:2])
                end = tuple(crop_pillow[2:4])
                canvas.draw_rect(
                    start=start,
                    end=end,
                    outline=color[1],
                    tag=tag,
                    delete_after_ms=None,
                )
            canvas.draw_rect(
                top_left,
                bottom_right,
                outline=color[0],
                tag=tag,
                delete_after_ms=int(ms),
            )

    def displayText(
        self,
        position: tuple,
        txt: str,
        tag: str | None = None,
        ms: int = 2000,
        font: str = "UD デジタル 教科書体 NP-B",
        fontsize: int = 20,
        color: str = "black",
    ) -> None:
        if self.gui is not None:
            canvas = self.gui
        else:
            canvas = self.canvas

        ft = (font, fontsize)

        if tag is None:
            tag = generateRandomCharacter(10)

        if self.gui is not None or self.isGuide:
            canvas.draw_text(
                position[0],
                position[1],
                text=txt,
                tag=tag,
                delete_after_ms=int(ms),
                font=ft,
                color=color,
            )

    def saveCapture(
        self,
        filename: str | None = None,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        mode: bool = True,
    ) -> None:
        """
        画面をキャプチャします。
        (camera.saveCaptureと同じ機能。)
        """
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("saveCapture: camera is not initialized.")
            return

        # ファイル名を設定する
        if filename is None or filename == "":
            dt_now = datetime.datetime.now()
            filename = dt_now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        else:
            filename = filename + ".png"
        if mode:
            save_path = self.get_filespec(filename, mode="c")
        else:
            save_path = self.get_filespec(filename, mode="n")

        # 画像を保存する
        ImageProcessing().saveImage(src, filename=save_path, crop=crop_cv2)

    def popupImage(
        self,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        title: str = "image",
    ) -> None:
        """
        popupで画像を表示する
        """
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("popupImage: camera is not initialized.")
            return

        openImage(src, crop=crop_cv2, title=title)

    def LINE_image(
        self,
        txt: str,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        token: str = "token",
    ) -> None:
        """
        Lineにテキストと画像を通知します。
        """
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        if (src := self.camera.readFrame()) is None:
            logger.warning("LINE_image: camera is not initialized.")
            return

        # トリミング
        cropped_image = crop_image(src, crop=crop_cv2)

        # 送信
        try:
            if (line := self.Line) is not None:
                line.send_message(txt, cropped_image, token)
            else:
                logger.warning("LINE_image: LINE is not initialized.")
        except Exception:
            pass

    def discord_image(
        self,
        content: str = "",
        index: int = 0,
        crop_fmt: int | str = "",
        crop: list[int] | None = None,
        keys: str | list = "DISCORD_WEBHOOK",
    ) -> None:
        """
        Discordにテキストと画像を通知します。
        """
        if crop is None:
            crop = []

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        if (src := self.camera.readFrame()) is None:
            logger.error("Camera image is None. Cannot send Discord notification.")
            return

        # トリミング
        cropped_image = crop_image(src, crop=crop_cv2)

        # webhook_urlのindex指定とkey設定
        if index != 0 and keys == "DISCORD_WEBHOOK":
            keys = f"DISCORD_WEBHOOK{index}"
        elif index == 0 and keys != "DISCORD_WEBHOOK":
            pass
        elif index != 0 and keys != "DISCORD_WEBHOOK":
            keys = f"DISCORD_WEBHOOK{index}"

        # 送信
        if (notifier := self.Discord) is not None:
            try:
                notifier.send_message(
                    notification_message=content, image=cropped_image, keys=keys
                )
            except Exception:
                pass
