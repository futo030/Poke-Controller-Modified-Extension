#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web ブラウザ版の画面の起動(python Window.py --ui web から呼ばれる)
"""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser

import uvicorn

import PokeConLogger
import Profile
from services.app_core import AppCore
from web.server import WebApp

DEFAULT_PORT = 8765
# ポート番号を指定しない場合に、空いている番号を探す範囲(DEFAULT_PORT から、この個数まで)
PORT_SEARCH_COUNT = 50
# 接続を受け付けるのは、このアプリを動かしている PC からだけ
HOST = "127.0.0.1"
DEFAULT_PROFILE = "default"
# サーバーが待ち受けを始めてから、ブラウザを開くまでの時間(秒)
BROWSER_DELAY = 1.0


def select_profile(profile: str | None, auto: bool) -> str:
    """
    使うプロファイルを決める。同じプロファイルがすでに起動されている場合は、設定を保存しないようにする
    """
    console = sys.__stdout__ or sys.stdout
    if profile is None and auto:
        profile = Profile.select_auto_profile()
        if profile is None:
            print("起動されていないプロファイルがありません。default で起動します。", file=console)
    if profile is None:
        profile = DEFAULT_PROFILE
    if not Profile.acquire_profile_lock(profile):
        Profile.set_read_only(True)
        print(f"プロファイル「{profile}」はすでに起動されています。変更した設定は保存されません。", file=console)
    return profile


def is_port_free(port: int) -> bool:
    """
    そのポート番号で待ち受けを始められるか
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def find_free_port(start: int = DEFAULT_PORT, count: int = PORT_SEARCH_COUNT) -> int | None:
    """
    start から順に、空いているポート番号を探す(見つからない場合は None)。
    複数のプロファイルを同時に起動したときに、2つ目以降が別の番号になる
    """
    for port in range(start, start + count):
        if is_port_free(port):
            return port
    return None


def run(
    profile: str | None = None,
    auto: bool = False,
    port: int | None = None,
    open_browser: bool = True,
    monitor: bool = False,
) -> int:
    """
    port: 使うポート番号(None なら、DEFAULT_PORT から順に、空いている番号を使う)
    monitor: 補助ツール(Monitor.py)から、状態・Output・映像を見て、操作できるようにするか(--monitor)
    """
    console = sys.__stdout__ or sys.stdout
    if port is None:
        port = find_free_port()
        if port is None:
            print(
                f"空いているポート番号が見つかりませんでした。({DEFAULT_PORT} ～ {DEFAULT_PORT + PORT_SEARCH_COUNT - 1})"
                " --port で番号を指定してください。",
                file=console,
            )
            return 1
    elif not is_port_free(port):
        print(f"ポート番号 {port} は、ほかで使われています。別の番号を指定するか、--port を付けずに起動してください。", file=console)
        return 1
    profile = select_profile(profile, auto)
    # プロファイルが決まったので、ログのファイル(log_プロファイル名_日時.log)を作る
    PokeConLogger.set_profile(profile)
    web_app = WebApp(lambda gui: AppCore(profile, gui=gui), port, monitor_profile=profile if monitor else None)
    url = f"http://{HOST}:{port}/"
    print(f"Web 版の画面を起動します (profile: {profile})", file=console)
    print(f"ブラウザで開く: {url}", file=console)
    print("終了するには、画面の「終了」ボタンを押すか、このウィンドウで Ctrl+C を押してください。", file=console, flush=True)
    # アクセスの記録は標準出力に出るので止める(標準出力は、アプリの出力画面に送っている)
    config = uvicorn.Config(web_app.app, host=HOST, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    # 画面の「終了」ボタンで、サーバーを止める(Ctrl+C と同じく、終了の処理をしてから止まる)
    web_app.on_exit = lambda: setattr(server, "should_exit", True)
    if open_browser:
        timer = threading.Timer(BROWSER_DELAY, webbrowser.open, [url])
        timer.daemon = True
        timer.start()
    try:
        server.run()
    except KeyboardInterrupt:
        # Ctrl+C での終了(終了の処理は、サーバーが止まるときに済んでいる)
        pass
    return 0
