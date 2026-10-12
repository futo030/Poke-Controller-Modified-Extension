#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import requests
import json
import cv2
import io
import os
import numpy as np
from PIL import Image
from logging import getLogger, DEBUG, NullHandler

# ロガーの設定は1回だけ行う
# (インスタンスを作るたびにaddHandlerすると、ハンドラが増え続けてメモリを使い、ログの出力も遅くなる)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 受信用の設定のセクション(通知先ではない)
RECEIVE_SECTION = "DISCORD"
# 既定の通知先の名前(必ず作成される。Notificationタブ・Main PanelのDiscordボタンの送り先)
DEFAULT_WEBHOOK = "DISCORD_WEBHOOK"
# 通知先の名前に使えない名前("ALL" は、すべての通知先に送る指定として使う)
RESERVED_NAMES = (RECEIVE_SECTION, "DEFAULT", "ALL")


def webhook_names(setting: configparser.ConfigParser) -> list:
    """
    通知先の名前(webhook_url を持つセクションの名前)の一覧。
    既定の通知先を先頭に、それ以外は設定ファイルに書かれている順に並べる(この順番が index になる)
    """
    names = [
        name
        for name in setting.sections()
        if name != RECEIVE_SECTION and setting.has_option(name, "webhook_url")
    ]
    if DEFAULT_WEBHOOK in names:
        names.remove(DEFAULT_WEBHOOK)
        names.insert(0, DEFAULT_WEBHOOK)
    return names


def is_default_webhook_set(setting: configparser.ConfigParser) -> bool:
    """
    既定の通知先に Webhook URL が設定されているか
    """
    return setting.has_section(DEFAULT_WEBHOOK) and setting.get(DEFAULT_WEBHOOK, "webhook_url", fallback="") != ""


def next_webhook_name(names: list) -> str:
    """
    新しい通知先の名前の初期値: DISCORD_WEBHOOK に、使用していない番号の最小値を付けたもの
    (DISCORD_WEBHOOK が無い場合は DISCORD_WEBHOOK)
    """
    if DEFAULT_WEBHOOK not in names:
        return DEFAULT_WEBHOOK
    number = 1
    while f"{DEFAULT_WEBHOOK}{number}" in names:
        number += 1
    return f"{DEFAULT_WEBHOOK}{number}"


def check_webhook_name(name: str) -> str | None:
    """
    通知先の名前として使えない場合は、理由を返す(使える場合はNone)
    """
    if name == "":
        return "名前を入力してください。"
    if name in RESERVED_NAMES:
        return f"「{name}」は名前に使えません。"
    if any(character in name for character in "[]\r\n") or name != name.strip():
        return "名前に「[」「]」・改行・前後の空白は使えません。"
    return None


def load_setting(path: str) -> configparser.ConfigParser:
    """
    設定ファイルを読み込む(BOMありのUTF-8にも対応。ファイルが無い場合は空の設定を返す)
    """
    setting = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as file:
            with_bom = file.readline()[:1] == "﻿"
        setting.read(path, "utf-8-sig" if with_bom else "utf-8")
    return setting


def save_setting(path: str, setting: configparser.ConfigParser) -> None:
    """設定を、ファイル(UTF-8)に保存する(フォルダーが無ければ作る)"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        setting.write(file)
    os.chmod(path=path, mode=0o777)


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


class Discord_Notify:
    """
    Discord の Webhook への通知(テキスト・画像)。
    DISCORD_SETTING_PATH: 通知先の設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    """

    DISCORD_SETTING_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "discord_token.ini")

    def __init__(
        self, webhook_url: str = "webhook_url", username: str = "username", avatar_url: str = "",
        token_name: str = "token",
    ):  # fmt: skip
        """
        設定ファイルの通知先(webhook_url を持つセクション)をすべて読み、それぞれに接続できるかを確かめる(通信する)。
        引数は、どれも使っていない(以前の呼び出し方との互換のために残している)
        接続を確かめられなかった場合は、self.status などを空のままにして続ける
        """
        self._logger = _logger

        self.default_username = f"Poke-Controller Modified Extension (profile: {os.path.basename(os.path.dirname(self.DISCORD_SETTING_PATH))})"

        self.res = None
        self.setting_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
        self.open_file_with_utf8()

        self.section_list = list(self.setting_file.keys())
        # 通知先は、webhook_url を持つセクション(名前は自由。受信用の [DISCORD] は除く)
        self.webhook_keys = webhook_names(self.setting_file)
        self.webhook_url_dict = {key: self.setting_file[key]["webhook_url"] for key in self.webhook_keys}
        self.username_dict = {key: self.setting_file.get(key, "username", fallback="") for key in self.webhook_keys}
        self.avatar_url_dict = {key: self.setting_file.get(key, "avatar_url", fallback="") for key in self.webhook_keys}

        # 確認の応答と結果(接続を確かめられなかった場合は、空のまま)
        self._check_res = []
        self.status = []
        self.chk_webhook_json = []
        try:
            self.res = [requests.get(self.webhook_url_dict[key]) for key in self.webhook_keys]
            # 確認の応答は、別にも持っておく(self.res は、send_message が送信の応答で置き換える)
            self._check_res = self.res
            self.status = [responses.status_code for responses in self.res]
            self.chk_webhook_json = [responses.json() for responses in self.res]
        except Exception:
            pass

    def open_file_with_utf8(self) -> None:
        """
        utf-8 のファイルを BOM ありかどうかを自動判定して読み込む
        (ファイルがない場合は空のファイルを作成する)
        """
        if os.path.isfile(self.DISCORD_SETTING_PATH):
            is_with_bom = self.is_utf8_file_with_bom(self.DISCORD_SETTING_PATH)

            encoding = "utf-8-sig" if is_with_bom else "utf-8"

            self._logger.debug("Load token file")
            self.setting_file.read(self.DISCORD_SETTING_PATH, encoding)
        else:
            dirname = os.path.dirname(self.DISCORD_SETTING_PATH)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
                self._logger.debug(f"mkdir: '{dirname}'")
            self.setting_file["DISCORD"] = {
                "channel_id": "",
                "token": "",
            }
            self.setting_file["DISCORD_WEBHOOK"] = {
                "webhook_url": "",
                "username": "",
                "avatar_url": "",
            }
            with open(self.DISCORD_SETTING_PATH, "w", encoding="utf-8") as file:
                self.setting_file.write(file)
            os.chmod(path=self.DISCORD_SETTING_PATH, mode=0o777)
            self._logger.debug("Generate token file")

    def is_utf8_file_with_bom(self, filename: str) -> bool:
        """
        utf-8 ファイルが BOM ありかどうかを判定する(空のファイルの場合は False)
        """
        with open(filename, encoding="utf-8") as file:
            return file.readline().startswith("\ufeff")

    def __str__(self) -> str:
        """
        通知先の確認の結果の文(最初に 401 か 200 だった通知先の結果)。
        どの通知先も 401 / 200 でない場合(通知先が無い、接続を確かめられなかったなど)は、確認できなかった旨の文
        """
        for stat in self.status:
            if stat == 401:
                self._logger.error("Invalid url")
                return "DISCORD API Check FAILED."
            elif stat == 200:
                self._logger.info("Valid url")
                return "DISCORD API Check OK!"
        self._logger.warning(f"Webhook check was not confirmed: {self.status}")
        return "DISCORD API Check: not confirmed."

    def resolve(self, index: int = 0, name: str | None = None) -> str | None:
        """
        通知先の名前を決める。name(通知先の名前)が index(0始まりの番号)より優先。
        name の通知先が無い場合は index の通知先にし、それも無い場合はNoneを返す
        """
        if name is not None:
            if name in self.webhook_keys:
                return name
            print(f"Discordの通知先「{name}」がありません。index={index} の通知先に送ります。")
            self._logger.warning(f"Discord webhook '{name}' is not found.")
        if isinstance(index, int) and 0 <= index < len(self.webhook_keys):
            return self.webhook_keys[index]
        print(f"Discordの通知先がありません。(index={index})")
        self._logger.warning(f"Discord webhook index {index} is out of range.")
        return None

    def send_message(
        self,
        notification_message: str | None = None,
        image: np.ndarray | None = None,
        keys: str | list[str] = "DISCORD_WEBHOOK",
    ) -> bool:
        """
        DISCORDにテキスト/画像を通知する
        imageが設定されていなければテキストのみ、設定されていればテキストと画像を通知する
        imageはBGRを想定する
        keys: 通知先の名前、または名前のリスト("ALL" は、すべての通知先)
        戻り値: すべての通知先に送信できたか
        """
        result = True
        if keys == "ALL":
            keys = self.webhook_keys
        elif isinstance(keys, str):
            keys = [keys]
        elif isinstance(keys, list):
            pass
        else:
            print("keysのフォーマットが間違っています")
            self._logger.error('Using the wrong "keys" format')
            return False

        # 画像の有無判定
        flag_image = False
        if isinstance(image, np.ndarray):
            flag_image = True

        for key in keys:
            try:
                content = {}
                if self.username_dict[key] != "":
                    content["username"] = self.username_dict[key]
                else:
                    content["username"] = self.default_username
                if self.avatar_url_dict[key] != "":
                    content["avatar_url"] = self.avatar_url_dict[key]
                if notification_message:
                    content["content"] = notification_message
                else:
                    content["content"] = ""

                files = {"payload_json": (None, json.dumps(content))}

                if flag_image:
                    files["media"] = ("pokecon_image.png", convert_bgr_to_bytes(image))
                else:
                    pass

                if notification_message:
                    if flag_image:
                        send_data_type = "テキスト・画像"
                        send_data_type_eng = "Text & Image"
                    else:
                        send_data_type = "テキスト"
                        send_data_type_eng = "Text"
                else:
                    if flag_image:
                        send_data_type = "画像"
                        send_data_type_eng = "Image"
                    else:
                        send_data_type = "(empty)"
                        send_data_type_eng = "empty"

                self.res = requests.post(self.webhook_url_dict[key], files=files)

                if self.res.status_code in [200, 204]:
                    print(f"[{key}]{send_data_type}を送信しました。")
                    self._logger.info(f"Send {send_data_type_eng}")
                else:
                    print(f"[{key}]{send_data_type}の送信に失敗しました。({self.res.status_code})")
                    self._logger.error(f"Failed to send {send_data_type_eng}")
                    result = False
            except Exception:
                print(f"[{key}]webhook urlを確認してください。")
                self._logger.error("Using the wrong token")
                result = False
        return result

    def getRateLimit(self) -> None:
        """
        通知先ごとの、送信できる回数の上限・残り・リセットの時刻(日本時間)を表示する。
        作ったときの、確認の応答を使う(send_message の後でも使える)。応答に情報が無い場合は、ログに残すだけ
        """
        try:
            # self.res は、send_message の後は送信の応答になるので、作ったときの確認の応答を見る
            responses = self._check_res
            for i, name in enumerate(self.webhook_keys):
                print(f"For: {name}")
                print("X-RateLimit-Limit: " + responses[i].headers["X-RateLimit-Limit"])
                print("X-RateLimit-Remaining: " + responses[i].headers["X-RateLimit-Remaining"])
                import datetime

                dt = datetime.datetime.fromtimestamp(
                    int(responses[i].headers["X-RateLimit-Reset"]), datetime.timezone(datetime.timedelta(hours=9))
                )
                print("Reset time:", dt, "\n")

                self._logger.info(f"DISCORD API - Limit: {responses[i].headers['X-RateLimit-Limit']}")
                self._logger.info(f"DISCORD API - Remaining: {responses[i].headers['X-RateLimit-Remaining']}")
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
    # import cv2
    # cap = cv2.VideoCapture(0)
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # ret, frame = cap.read()

    DISCORD = Discord_Notify()
    DISCORD.getRateLimit()
    # DISCORD.send_message(notification_message="test")
    # DISCORD.send_message(notification_message="test", image=frame)
