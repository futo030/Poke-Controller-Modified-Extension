"""
.venv の Python で起動し直す(0.2.x の間だけ使う。0.3.0 で消す)

以前からの起動用のファイル(リポジトリの外にある bat など)は、PC に入っている Python で Window.py を実行する。
.venv ができた後は、そこから .venv の Python で同じものを起動し直して、どの入口からでも同じ環境で動くようにする。
"""
from __future__ import annotations

import os
import subprocess
import sys

from bootstrap import environment

# 起動し直した先で、もう一度起動し直さないための目印
RELAUNCHED = "POKECON_RELAUNCHED"


def should_relaunch(root: str, environ: dict | None = None) -> bool:
    """.venv があり、今のプロセスがその外で動いているか"""
    environ = os.environ if environ is None else environ
    if environ.get(RELAUNCHED):
        return False
    return os.path.isfile(environment.venv_python(root)) and not environment.in_venv(root)


def run_in_venv() -> None:
    """.venv の外で動いていたら、.venv の Python で同じスクリプトを同じ引数で実行し、その終了コードで終わる"""
    root = environment.repository_dir()
    if not should_relaunch(root):
        return
    try:
        code = subprocess.call(
            [environment.venv_python(root), *sys.argv], env={**os.environ, RELAUNCHED: "1"}
        )
    except OSError:
        # 起動し直せないときは、今の Python のまま続ける
        return
    sys.exit(code)
