#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import requests
import cv2
import io
import os
from PIL import Image
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

# ロガーの設定は1回だけ行う
# (インスタンスを作るたびにaddHandlerすると、ハンドラが増え続けてメモリを使い、ログの出力も遅くなる)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True


def convert_bgr_to_bytes(image_bgr: np.ndarray) -> bytes:
    """
    BGRの画像をbyte形式(PNG のデータ)に変換する
    """
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(image_rgb)
    png = io.BytesIO()  # 空のio.BytesIOオブジェクトを用意
    image.save(png, format="png")  # 空のio.BytesIOオブジェクトにpngファイルとして書き込み
    b_frame = png.getvalue()  # io.BytesIOオブジェクトをbytes形式で読みとり
    return b_frame


class Line_Notify:
    """
    LINE Notify への通知(テキスト・画像)。
    LINE_TOKEN_PATH: トークンの設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    """

    LINE_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "line_token.ini")

    def __init__(self, token_name: str = "token"):
        """
        設定ファイルの [LINE] にあるトークンをすべて読み、それぞれが有効かを LINE に問い合わせる(通信する)。
        token_name: 使っていない(以前の呼び出し方との互換のために残している)
        設定ファイルに [LINE] が無い場合は KeyError、通信できない場合は requests の例外
        """
        self._logger = _logger

        self.res = None
        self.token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
        self.open_file_with_utf8()
        self.token_list = {key: self.token_file["LINE"][key] for key in self.token_file["LINE"]}
        self.token_num = len(self.token_list)
        # self.line_notify_token = self.token_file['LINE'][token_name]
        self.headers = [{"Authorization": f"Bearer {token}"} for key, token in self.token_list.items()]
        self.res = [requests.get("https://notify-api.line.me/api/status", headers=head) for head in self.headers]
        # 確認の応答は、別にも持っておく(self.res は、send_message が送信の応答で置き換える)
        self._check_res = self.res
        self.status = [responses.status_code for responses in self.res]
        self.chk_token_json = [responses.json() for responses in self.res]

    def open_file_with_utf8(self) -> None:
        """
        utf-8 のファイルを BOM ありかどうかを自動判定して読み込む
        (ファイルがない場合は空のファイルを作成する)
        """
        if os.path.isfile(self.LINE_TOKEN_PATH):
            is_with_bom = self.is_utf8_file_with_bom(self.LINE_TOKEN_PATH)

            encoding = "utf-8-sig" if is_with_bom else "utf-8"

            self._logger.debug("Load token file")
            self.token_file.read(self.LINE_TOKEN_PATH, encoding)
        else:
            dirname = os.path.dirname(self.LINE_TOKEN_PATH)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
                self._logger.debug(f"mkdir: '{dirname}'")
            self.token_file["LINE"] = {"token": ""}
            with open(self.LINE_TOKEN_PATH, "w", encoding="utf-8") as file:
                self.token_file.write(file)
            os.chmod(path=self.LINE_TOKEN_PATH, mode=0o777)
            self._logger.debug("Generate token file")

    def is_utf8_file_with_bom(self, filename: str) -> bool:
        """
        utf-8 ファイルが BOM ありかどうかを判定する(空のファイルの場合は False)
        """
        with open(filename, encoding="utf-8") as file:
            return file.readline().startswith("\ufeff")

    def __str__(self) -> str:
        """
        トークンの確認の結果の文(最初に 401 か 200 だったトークンの結果)。
        どのトークンも 401 / 200 でない場合(トークンが無い、ほかの状態が返ったなど)は、確認できなかった旨の文
        """
        for stat in self.status:
            if stat == 401:
                self._logger.error("Invalid token")
                return "LINE Token Check FAILED."
            elif stat == 200:
                self._logger.info("Valid token")
                return "LINE-Token Check OK!"
        self._logger.warning(f"Token check was not confirmed: {self.status}")
        return "LINE Token Check: not confirmed."

    def send_message(self, notification_message: str, image: np.ndarray | None = None, token: str = "token") -> None:
        """
        LINEにテキスト/画像を通知する
        imageが設定されていなければテキストのみ、設定されていればテキストと画像を通知する
        imageはBGRを想定する
        token: 使うトークンの、設定ファイルでの名前(無い名前の場合は、メッセージを表示するだけ)
        """
        line_notify_api = "https://notify-api.line.me/api/notify"
        try:
            data = None
            files = None
            headers = {"Authorization": f"Bearer {self.token_list[token]}"}
            data = {"Message": f"{notification_message}"}
            if image is not None:
                b_frame = convert_bgr_to_bytes(image)
                files = {"imageFile": b_frame}

            # 何故か画像のみの送信はできなかった。
            if files is not None:  # テキストと画像
                self.res = requests.post(line_notify_api, headers=headers, params=data, files=files)
                send_data_type = "テキスト・画像"
                send_data_type_eng = "image with text"
            else:  # テキスト
                self.res = requests.post(line_notify_api, headers=headers, params=data)
                send_data_type = "テキスト"
                send_data_type_eng = "text"

            if self.res.status_code == 200:
                print(f"[LINE]{send_data_type}を送信しました。")
                self._logger.info(f"Send {send_data_type_eng}")
            else:
                print(f"[LINE]{send_data_type}の送信に失敗しました。")
                self._logger.error(f"Failed to send {send_data_type_eng}")
        except KeyError:
            print("token名が間違っています")
            self._logger.error("Using the wrong token")

    def getRateLimit(self) -> None:
        """
        トークンごとの、送信できる回数の上限・残り・リセットの時刻(日本時間)を表示する。
        作ったときの、確認の応答を使う(send_message の後でも使える)。応答に情報が無い場合は、ログに残すだけ
        """
        try:
            # self.res は、send_message の後は送信の応答になるので、作ったときの確認の応答を見る
            responses = self._check_res
            for i in range(self.token_num):
                print(f"For: {list(self.token_list.keys())[i]}")
                print("X-RateLimit-Limit: " + responses[i].headers["X-RateLimit-Limit"])
                print("X-RateLimit-ImageLimit: " + responses[i].headers["X-RateLimit-ImageLimit"])
                print("X-RateLimit-Remaining: " + responses[i].headers["X-RateLimit-Remaining"])
                print("X-RateLimit-ImageRemaining: " + responses[i].headers["X-RateLimit-ImageRemaining"])
                import datetime

                dt = datetime.datetime.fromtimestamp(
                    int(responses[i].headers["X-RateLimit-Reset"]), datetime.timezone(datetime.timedelta(hours=9))
                )
                print("Reset time:", dt, "\n")

                self._logger.info(f"LINE API - Limit: {responses[i].headers['X-RateLimit-Limit']}")
                self._logger.info(f"LINE API - Remaining: {responses[i].headers['X-RateLimit-Remaining']}")
                self._logger.info(f"LINE API - ImageLimit: {responses[i].headers['X-RateLimit-ImageLimit']}")
                self._logger.info(f"LINE API - ImageRemaining: {responses[i].headers['X-RateLimit-ImageRemaining']}")
                self._logger.info(f"Reset time: {dt}")
        except (AttributeError, TypeError, IndexError) as e:
            self._logger.error(e)
            pass
        except KeyError as e:
            self._logger.error(e)
            pass


if __name__ == "__main__":
    """
    status  HTTPステータスコードに準拠した値
       200  成功時
       401  アクセストークンが無効
    """
    LINE = Line_Notify()
    print(LINE)
    LINE.getRateLimit()
