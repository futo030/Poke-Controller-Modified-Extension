#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
送信方式の登録簿(形式の名前 -> Transport)。

形式を足すときは、Transport を継承したクラスを作り、この下の register(...) に1行足す。
画面の Data Format の一覧には、登録した順に並ぶ。
"""
from __future__ import annotations

from Commands.FtdiPort import FTDI_FORMATS
from Commands.transport.base import Transport
from Commands.transport.controller_3ds import Controller3dsTransport
from Commands.transport.ds_ft import DsFtTransport
from Commands.transport.nx_macro import NxMacroTransport
from Commands.transport.qingpi import QingpiTransport
from Commands.transport.text_serial import TextSerialTransport

DEFAULT_NAME = "Default"

_transports: dict[str, Transport] = {}


def register(transport: Transport) -> Transport:
    """
    送信方式を登録して、そのまま返す。
    名前が空の場合と、同じ名前を登録済みの場合は ValueError
    """
    if not transport.name:
        raise ValueError("the transport has no name")
    if transport.name in _transports:
        raise ValueError(f"the transport {transport.name!r} is already registered")
    _transports[transport.name] = transport
    return transport


def get_transport(name: str) -> Transport:
    """
    形式の名前から、送信方式を返す。登録のない名前は、名前の一部から決める(これまでの判定と同じ)。
    どれにも当たらなければ Default
    """
    transport = _transports.get(name)
    if transport is not None:
        return transport
    if "3DS Controller" in name:
        return _transports["3DS Controller(FW:-x.3)" if "x.3" in name else "3DS Controller(FW:x.4-)"]
    return _transports[DEFAULT_NAME]


def port_transport(port: object, name: str) -> Transport:
    """
    今開いているポートに送るときの送信方式(port: 開いているポート。None でもよい。name: 設定の形式の名前)。
    ポートが形式を決めている場合(port.format_name。FTDI のデバイスなど)は、設定の形式より、そちらを使う
    (形式を切り替えた後、接続し直すまでの間に、合わない形式のデータを送らないため)
    """
    return get_transport(getattr(port, "format_name", None) or name)


def keyboard_transport_names() -> list[str]:
    """Switch へのキーボード入力を使える形式の名前の一覧"""
    return [name for name, transport in _transports.items() if transport.keyboard_steps("init") is not None]


def transport_names(available_only: bool = True) -> list[str]:
    """登録した順の、形式の名前の一覧(available_only: この環境で使えるものだけ)"""
    return [name for name, transport in _transports.items() if not available_only or transport.is_available()]


# 画面の Data Format の一覧に並ぶ順
register(TextSerialTransport())
register(NxMacroTransport())
register(QingpiTransport())
register(Controller3dsTransport("3DS Controller(FW:x.4-)", mode=1))
register(Controller3dsTransport("3DS Controller(FW:-x.3)", mode=0))
# FTDI 直結の DS 基板(新しいリビジョンを先に並べる)
for _name in reversed(list(FTDI_FORMATS)):
    register(DsFtTransport(_name))
