#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

import threading
import time

import pygame
from collections import OrderedDict
from logging import getLogger, DEBUG, NullHandler

from Commands.ControllerProfile import (
    AUTO_DEVICE,
    ControllerProfile,
    ControllerProfileError,
    JOYSTICK_LOCK,
    load_profiles,
    select_device,
)
from Commands.Keys import Hat, InputSource, KeyPress, convert_button_bits, get_button_conversion

if TYPE_CHECKING:
    from Commands.Sender import Sender

# 入力を読み取る間隔(秒)。間隔を空けないとCPUを使い続け、他のスレッドのタイミングがずれる
POLL_INTERVAL = 0.001


class ProController:
    """
    PCに接続したコントローラーの入力をSwitchへ送る
    (コントローラーの種類ごとのボタン番号などの違いはControllerProfileで吸収する)
    """

    def __init__(self, profiles: list[ControllerProfile] | None = None, device: str = AUTO_DEVICE) -> None:
        """
        profiles: 使えるプロファイルの一覧(None: フォルダーから読み込む)
        device: 使うコントローラー(AUTO_DEVICE、または device_label で作った "番号: 名前" の文字列)
        """
        # controller_loopの停止要求(インスタンスごとに持つので、新旧のスレッドが混ざらない)
        self._stop_event = threading.Event()

        if profiles is None:
            profiles, _ = load_profiles()
        self.profiles = profiles
        # 使うコントローラー(Auto または ControllerProfile.device_label の文字列)
        self.device = device
        # 実際に使うプロファイル(controller_loopでコントローラーを開いたときに名前から決まる)
        self.profile: ControllerProfile | None = None

        # Defaultのボタンビット、Hatの値、スティック[lx, ly, rx, ry](0～255)
        self.buttons = 0
        self.hat = int(Hat.CENTER)
        self.sticks = [128, 128, 128, 128]
        # 最後にSenderへ渡した状態
        self.sent_state = None

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    @property
    def stop_requested(self) -> bool:
        """stop で、停止を要求済みか"""
        return self._stop_event.is_set()

    def open_joystick(self) -> pygame.joystick.JoystickType:
        """
        選択されたコントローラーを開き、名前からself.profileを決める
        (pygame を初期化した後で呼ぶ。コントローラーがない、指定のものがない場合は ControllerProfileError)
        """
        count = pygame.joystick.get_count()
        names = [pygame.joystick.Joystick(i).get_name() for i in range(count)]
        index, self.profile, notes = select_device(names, self.profiles, self.device)
        joystick = pygame.joystick.Joystick(index)
        joystick.init()
        print(f"コントローラー: {index}: {joystick.get_name()} / プロファイル: {self.profile.name}")
        for note in notes:
            print(note)
        for warning in self.profile.check(joystick):
            print(f"プロファイルの警告: {warning}")
        return joystick

    def poll(self, joystick: pygame.joystick.JoystickType) -> None:
        """コントローラーの今の入力を読み取り、buttons / hat / sticks に入れる(open_joystick の後で呼ぶ)"""
        self.buttons, self.hat, self.sticks = self.profile.read(joystick)

    def send_message(self, ser: Sender) -> None:
        """読み取った入力を、前に渡したものから変わっていれば、Sender に渡す"""
        # 状態が変化した場合のみ送る(他の入力源との合成・送信形式への変換・操作記録はSenderが行う)
        state = self.current_state()
        if state != self.sent_state:
            ser.send_state(self, InputSource.PROCON, state)
            self.sent_state = state

    def current_state(self) -> OrderedDict:
        """
        現在の入力状態をSendFormat.formatと同じ形式で返す
        """
        convert = get_button_conversion(KeyPress.serial_data_format_name)
        return OrderedDict(
            [
                ("btn", convert_button_bits(self.buttons, convert)),
                ("hat", self.hat),
                ("lx", self.sticks[0]),
                ("ly", self.sticks[1]),
                ("rx", self.sticks[2]),
                ("ry", self.sticks[3]),
                ("sx", 0),
                ("sy", 0),
            ]
        )

    def end_sequence(self, ser: Sender) -> None:
        """このコントローラーの入力を、すべて離した状態にする"""
        # Proコントローラーの入力を離す(他の入力源の入力は残す)
        ser.release(self)
        self.sent_state = None

    def stop(self) -> None:
        """
        controller_loopに停止を要求する(どのスレッドからでも呼べる)
        """
        self._stop_event.set()

    def controller_loop(self, ser: Sender) -> None:
        """
        コントローラーを開き、stop が呼ばれるまで、入力を読み取って Sender に渡し続ける(専用のスレッドで呼ぶ)。
        コントローラーが外れた場合や、エラーの場合は、その旨を表示して終わる(例外は出さない)
        """
        self._logger.info("Activate Pro Controller")
        print("*****Activate Pro Controller*****")
        # コントローラー一覧の取得と同時にpygameを初期化・解放しないようにする
        with JOYSTICK_LOCK:
            try:
                # pygame初期化
                pygame.init()
                joystick = self.open_joystick()

                instance_id = joystick.get_instance_id()
                while not self._stop_event.is_set():
                    # コントローラーが外れたら止める(他のイベントは使わないので捨てる)
                    for event in pygame.event.get():
                        if event.type == pygame.JOYDEVICEREMOVED and event.instance_id == instance_id:
                            raise ControllerProfileError("コントローラーが切断されました")
                    # 入力の読み取り
                    self.poll(joystick)
                    # シリアルデータの送信
                    self.send_message(ser)
                    # Windowsでは Event.wait より time.sleep の方が精度が高い(Python 3.11以降)
                    time.sleep(POLL_INTERVAL)
            except ControllerProfileError as e:
                self._logger.error(f"Pro Controller stopped: {e}")
                print(f"Proコントローラーを停止しました: {e}")
            except Exception as e:
                self._logger.error(f"Pro Controller loop stopped by an error: {e}")
                print(f"Proコントローラーの処理でエラーが発生したため停止しました: {e}")
            finally:
                # 終了処理
                self.end_sequence(ser)
                pygame.quit()
        self._logger.info("Inactivate Pro Controller")
        print("*****Inactivate Pro Controller*****")
