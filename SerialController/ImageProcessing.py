#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import cv2
from numpy import ndarray, array, argmax
import os
import time
from typing import List, Tuple, Optional
from logging import getLogger, DEBUG, NullHandler

# ロガーの設定は1回だけ行う
# (インスタンスを作るたびにaddHandlerすると、ハンドラが増え続けてメモリを使い、ログの出力も遅くなる)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True


def crop_image(image: ndarray, crop: List[int] | None = None) -> ndarray:
    """
    画像をトリミングする
    [y軸始点, y軸終点, x軸始点, x軸終点]
    crop が None・空・読めない形の場合は、トリミングせずに image をそのまま返す
    """
    try:
        cropped_image = image[crop[0] : crop[1], crop[2] : crop[3]]
    except Exception:
        cropped_image = image

    return cropped_image


def crop_image_extend(image: ndarray, crop_fmt: int | str | None = None, crop: List[int] | None = None) -> ndarray:
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
    crop_fmt は、数値でも文字("1" など)でもよい。上のどれでもない場合と、crop が読めない場合は、image をそのまま返す
    """

    try:
        # pillow形式
        if crop_fmt == 1 or crop_fmt == "1":
            cropped_image = image[crop[1] : crop[3], crop[0] : crop[2]]
        elif crop_fmt == 2 or crop_fmt == "2":
            cropped_image = image[crop[1] : crop[1] + crop[3], crop[0] : crop[0] + crop[2]]
        elif crop_fmt == 3 or crop_fmt == "3":
            cropped_image = image[crop[2] : crop[3], crop[0] : crop[1]]
        elif crop_fmt == 4 or crop_fmt == "4":
            cropped_image = image[crop[2] : crop[2] + crop[3], crop[0] : crop[0] + crop[1]]
        # opencv形式
        elif crop_fmt == 11 or crop_fmt == "11":
            cropped_image = image[crop[0] : crop[2], crop[1] : crop[3]]
        elif crop_fmt == 12 or crop_fmt == "12":
            cropped_image = image[crop[0] : crop[0] + crop[2], crop[1] : crop[1] + crop[3]]
        elif crop_fmt == 13 or crop_fmt == "13":
            cropped_image = image[crop[0] : crop[1], crop[2] : crop[3]]
        elif crop_fmt == 14 or crop_fmt == "14":
            cropped_image = image[crop[0] : crop[0] + crop[1], crop[2] : crop[2] + crop[3]]
        else:
            cropped_image = image
    except Exception:
        cropped_image = image

    return cropped_image


def getInterframeDiff(frame1: ndarray, frame2: ndarray, frame3: ndarray, threshold: float) -> ndarray:
    """
    Get interframe difference binarized image
    フレーム間差分により2値化された画像を取得する
    frame1 / frame2 / frame3: 連続する 3 枚の画像(同じ大きさ)、threshold: 2値化のしきい値(0～255)
    """
    diff1 = cv2.absdiff(frame1, frame2)
    diff2 = cv2.absdiff(frame2, frame3)

    diff = cv2.bitwise_and(diff1, diff2)

    # binarize
    img_th = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)[1]

    # remove noise
    mask = cv2.medianBlur(img_th, 3)
    return mask


def getImage(path: str, mode: str = "color") -> ndarray | None:
    """
    画像の読み込みを行う。
    mode: "gray" / "binary" はグレースケール(どちらも同じ)、それ以外はカラー(BGR)で読む
    path が空の場合は None。読み込めない場合は、どのファイルかを表示して None を返す
    """
    if path:
        try:
            if mode == "binary":
                image = cv2.imread(path, 0)
            elif mode == "gray":
                image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            else:
                image = cv2.imread(path, cv2.IMREAD_COLOR)
        except Exception:
            image = None
        if image is None:
            # cv2.imread は、ファイルが無い・読めない場合に例外を出さずNoneを返す
            reportMissingFile(path, "画像")
        return image
    else:
        return None


# 同じファイルについて続けて表示しない時間(秒)。繰り返し呼ばれる処理で、Outputが埋まらないようにする
MISSING_FILE_REPORT_INTERVAL = 5.0
_missing_file_reported = {}


def reportMissingFile(path: str, kind: str) -> None:
    """
    画像認識などで使うファイルを読み込めなかった場合に、どのファイルかをOutputに表示する
    kind: ファイルの種類("画像"など)
    同じファイルについては、MISSING_FILE_REPORT_INTERVAL 秒の間、続けて表示しない
    """
    full_path = os.path.abspath(path)
    now = time.monotonic()
    if now - _missing_file_reported.get(full_path, -MISSING_FILE_REPORT_INTERVAL) < MISSING_FILE_REPORT_INTERVAL:
        return
    _missing_file_reported[full_path] = now
    if os.path.isfile(full_path):
        print(f"{kind}ファイルを読み込めません: {os.path.basename(full_path)} ({full_path})")
        print("ファイルが壊れていないか、ファイル名に使えない文字が無いかを確認してください。")
    else:
        print(f"{kind}ファイルがありません: {os.path.basename(full_path)} ({full_path})")
        print("ファイル名およびファイルの格納場所を確認してください。")


def doPreprocessImage(
    image: ndarray,
    use_gray: bool = True,
    crop: List[int] | None = None,
    BGR_range: Optional[dict] = None,
    threshold_binary: Optional[int] = None,
) -> Tuple[ndarray, int, int]:
    """
    画像をトリミングしてグレースケール化/2値化する。(加工した画像, 幅, 高さ) を返す
    crop: トリミングする範囲([y軸始点, y軸終点, x軸始点, x軸終点]。None や空ならトリミングしない)
    use_gray: グレースケール化するか(True の場合、BGR_range は使わない)
    BGR_range: 色の範囲で2値化する場合の {"lower": [B, G, R], "upper": [B, G, R]}
    threshold_binary: しきい値で2値化する場合のしきい値(0～255。None ならしない)
    2値化関連のContributor: mikan kochan 空太 (敬称略)
    """
    src = crop_image(image, crop=crop)  # トリミング

    if use_gray:
        src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)  # グレースケール化
    elif BGR_range is not None:  # 2値化
        src = cv2.inRange(
            src, array(BGR_range["lower"]), array(BGR_range["upper"])
        )  # inRangeで元画像を２値化(指定した色の範囲を抽出できる)

    if threshold_binary is not None:
        _, src = cv2.threshold(src, threshold_binary, 255, cv2.THRESH_BINARY)

    width, height = src.shape[1], src.shape[0]  # テンプレート画像のサイズ

    return src, width, height


def opneImage(image: ndarray, crop: List[int] | None = None, title: str = "image") -> None:
    """
    キー入力があるまで画像を表示する
    crop: 表示する範囲([y軸始点, y軸終点, x軸始点, x軸終点]。None なら全体)、title: ウィンドウの題名
    Contributor: kochan (敬称略)
    """
    src = crop_image(image, crop=crop)  # トリミング
    cv2.imshow(f"{title}", src)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


class ImageProcessing:
    """
    画像に関する処理を行う。
    """

    __logger = _logger
    __gsrc = None
    __gtmpl = None
    __gresult = None
    __use_gpu = False
    image_type = ndarray

    def __init__(self, use_gpu: bool = False):
        """use_gpu: テンプレートマッチングを GPU(OpenCV の CUDA)で行うか(使えない環境では、CPU で行う)"""
        # GUP使用時、デバイスのメモリを確保する(1回だけ)
        if use_gpu:
            """
            テンプレートマッチングをGPUで行うようにする。
            うまく設定できたらuse_gpuのフラグをTrueにする。
            """
            try:
                if self.__gsrc is None:
                    self.__gsrc = cv2.cuda_GpuMat()
                if self.__gtmpl is None:
                    self.__gtmpl = cv2.cuda_GpuMat()
                if self.__gresult is None:
                    self.__gresult = cv2.cuda_GpuMat()
                self.__use_gpu = True
                print("template matching:mask is ignored.")
            except Exception:
                self.__use_gpu = False
        else:
            self.__use_gpu = False

    def imwrite(self, filename: str, image: ndarray, params: List[int] | None = None) -> bool:
        """
        画像を書き込む(日本語などを含むパスにも保存できる)。書き込めたかを返す
        filename: 保存先(拡張子で形式が決まる)、params: cv2.imencode に渡す設定(None なら既定)
        失敗した場合は、例外にせず、理由を表示して False を返す
        """
        try:
            ext = os.path.splitext(filename)[1]
            result, n = cv2.imencode(ext, image, params)

            if result:
                with open(filename, mode="w+b") as f:
                    n.tofile(f)
                return True
            else:
                return False
        except Exception as e:
            print(e)
            self.__logger.error(f"Image Write Error: {e}")
            return False

    def doTemplateMatch(
        self, image: ndarray, template_image: ndarray, mask_image: ndarray | None = None
    ) -> Tuple[float, tuple]:
        """
        テンプレートマッチングをする
        画像は必要に応じて事前にグレースケール化やトリミングをしておく必要がある
        (類似度の最大値, その位置 (x, y)) を返す
        mask_image: マスク画像(ある場合は TM_CCORR_NORMED、無い場合は TM_CCOEFF_NORMED で比べる)
        """
        # 比較方式を設定する
        method = cv2.TM_CCORR_NORMED if isinstance(mask_image, ndarray) else cv2.TM_CCOEFF_NORMED

        # テンプレートマッチングをする
        if self.__use_gpu:  # GPUを使用する場合(マスク非対応)
            print("template matching mode:GPU")
            self.__gsrc.upload(image)
            self.__gtmpl.upload(template_image)
            matcher = cv2.cuda.createTemplateMatching(cv2.CV_8UC1, method)
            self.__gresult = matcher.match(self.__gsrc, self.__gtmpl)
            res = self.__gresult.download()
        else:
            res = cv2.matchTemplate(image, template_image, method, mask=mask_image)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)  # 結果から類似度と類似度が最大となる場所を抽出

        return max_val, max_loc

    def isContainTemplate(
        self,
        image: ndarray,
        template_image: ndarray,
        mask_image: ndarray | None = None,
        threshold: float = 0.7,
        use_gray: bool = True,
        crop: List[int] = [],
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: list[int] = [],
        show_image: bool = False,
    ) -> Tuple[bool, tuple, int, int, float]:
        """
        テンプレートマッチングを行い類似度が閾値を超えているかを確認する
        (閾値を超えたか, 類似度が最大の位置 (x, y), テンプレート画像の幅, 高さ, 類似度の最大値) を返す
        threshold: 類似度の閾値、crop / crop_template: 画像 / テンプレート画像をトリミングする範囲
        use_gray / BGR_range / threshold_binary: doPreprocessImage と同じ(画像とテンプレート画像の両方に掛ける)
        show_image: [DEBUG] 加工した画像を表示して、キー入力を待つ
        """
        # テンプレートマッチング対象画像を加工する
        src, _, _ = doPreprocessImage(
            image, use_gray=use_gray, crop=crop, BGR_range=BGR_range, threshold_binary=threshold_binary
        )

        # [DEBUG] テンプレートマッチング対象画像を表示する
        if show_image:
            cv2.imshow("image", src)
            cv2.waitKey()

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

    def isContainTemplate_max(
        self,
        image: ndarray,
        template_image_list: List[ndarray],
        mask_image_list: List[ndarray] = [],
        threshold: float = 0.7,
        use_gray: bool = True,
        crop: List[int] = [],
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: list[int] = [],
        show_image: bool = False,
    ) -> Tuple[int, List[float], List[tuple], List[int], List[int], List[bool]]:
        """
        複数のテンプレート画像を用いてそれぞれテンプレートマッチングを行い類似度が最も大きい画像のindexを返す
        (index, 類似度のリスト, 位置のリスト, 幅のリスト, 高さのリスト, 閾値を超えたかのリスト) を返す
        (index は numpy の整数。リストは、テンプレート画像の順)
        mask_image_list: マスク画像のリスト(テンプレート画像と同じ数・同じ順。空なら、マスクを使わない)。
        数が合わない場合は、その旨を表示して (-1, [], [], [], [], []) を返す
        そのほかの引数は isContainTemplate と同じ
        """
        # パラメータチェックを行う
        if len(mask_image_list) == 0:
            mask_image_list_temp = [None for i in range(len(template_image_list))]
        elif len(template_image_list) == len(mask_image_list):
            mask_image_list_temp = mask_image_list
        else:
            print("The number of template images and mask images don't match. ")
            return -1, [], [], [], [], []

        # ループをまわしてテンプレート画像数分テンプレートマッチングを行う
        max_val_list = []
        max_loc_list = []
        width_list = []
        height_list = []
        judge_threshold_list = []

        # テンプレートマッチング対象画像を加工する
        src, _, _ = doPreprocessImage(
            image, use_gray=use_gray, crop=crop, BGR_range=BGR_range, threshold_binary=threshold_binary
        )

        # [DEBUG] テンプレートマッチング対象画像を表示する
        if show_image:
            cv2.imshow("image", src)
            cv2.waitKey()

        for template_image, mask_image in zip(template_image_list, mask_image_list_temp):
            # テンプレート画像を加工する
            template, width, height = doPreprocessImage(
                template_image,
                use_gray=use_gray,
                crop=crop_template,
                BGR_range=BGR_range,
                threshold_binary=threshold_binary,
            )
            max_val, max_loc = self.doTemplateMatch(src, template, mask_image=mask_image)
            max_val_list.append(max_val)
            max_loc_list.append(max_loc)
            width_list.append(width)
            height_list.append(height)
            judge_threshold_list.append(max_val > threshold)

        return argmax(max_val_list), max_val_list, max_loc_list, width_list, height_list, judge_threshold_list

    def saveImage(self, image: ndarray, filename: str | None = None, crop: List[int] | None = None) -> None:
        """
        画像を保存する。
        filename: 保存先(拡張子まで。無いフォルダーは作る)。
                  None や空の場合は、保存せずに、その旨を表示する
        crop: 保存する範囲([y軸始点, y軸終点, x軸始点, x軸終点]。None なら全体)
        保存できなかった場合は、例外にせず、"Capture Failed" と表示する
        """
        if not filename:
            print("Capture Failed: 保存するファイル名が指定されていません。")
            self.__logger.error("Capture Failed: filename is not specified")
            return

        # トリミングを行う
        cropped_image = crop_image(image, crop=crop)

        # ファイル名からパスを抽出する
        capture_dir = os.path.dirname(filename)

        # 画像保存用ディレクトリの存在を確認し、なかったら作成する。
        # (フォルダーの部分がない名前は、今のフォルダーに保存する)
        if capture_dir and not os.path.exists(capture_dir):
            os.makedirs(capture_dir)
            self.__logger.debug("Created Capture folder")

        # 画像を保存する(imwrite は、失敗しても例外を出さずに False を返す)
        try:
            saved = self.imwrite(filename, cropped_image)
        except cv2.error as e:
            saved = False
            self.__logger.error(f"Capture Failed :{e}")
        if saved:
            self.__logger.debug(f"Capture succeeded: {filename}")
            print("capture succeeded: " + filename)
        else:
            print("Capture Failed")
            self.__logger.error(f"Capture Failed: {filename}")


if __name__ == "__main__":
    # 動作の確認用: 0 番のカメラの画像の中に、今のフォルダーの test.png があるかを表示する
    ImgProc = ImageProcessing()
    template = getImage("./test.png")
    camera = cv2.VideoCapture(0)
    if camera.isOpened() and template is not None:
        _, image = camera.read()
        ret, _, _, _, max_val = ImgProc.isContainTemplate(image, template)
        print(ret, max_val)
    camera.release()
