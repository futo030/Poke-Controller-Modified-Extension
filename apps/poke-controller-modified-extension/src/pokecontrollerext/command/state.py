import tkinter as tk

from pokecontrollerext.command.info import CommandInfo


class AppCommandState:
    """アプリケーションのコマンド実行状態を管理するクラス.

    コマンドの実行状態（実行中、一時停止中、キャンセル済みなど）を
    Tkinterの変数として管理し、UIとの連携を容易にします。
    """

    def __init__(self) -> None:
        """AppCommandStateインスタンスを初期化します.

        全ての状態フラグを初期値に設定し、実行中コマンドと
        選択中コマンドの情報をNoneで初期化します。
        """
        self._is_running = tk.BooleanVar(value=False)
        self._is_paused = tk.BooleanVar(value=False)
        self._is_alive = tk.BooleanVar(value=False)
        self._is_cancelled = tk.BooleanVar(value=False)
        self._is_stopped = tk.BooleanVar(value=True)
        self.running_command_info: CommandInfo | None = None
        self._selected_command_info: CommandInfo | None = None

    @property
    def is_running(self) -> tk.BooleanVar:
        """コマンドが実行中かどうかを示すTkinter変数を取得します.

        Returns:
            実行中フラグのBooleanVar.
        """
        return self._is_running

    @property
    def is_paused(self) -> tk.BooleanVar:
        """コマンドが一時停止中かどうかを示すTkinter変数を取得します.

        Returns:
            一時停止中フラグのBooleanVar.
        """
        return self._is_paused

    @property
    def is_alive(self) -> tk.BooleanVar:
        """コマンドが生存（アクティブ）かどうかを示すTkinter変数を取得します.

        Returns:
            生存フラグのBooleanVar.
        """
        return self._is_alive

    @property
    def is_cancelled(self) -> tk.BooleanVar:
        """コマンドがキャンセルされたかどうかを示すTkinter変数を取得します.

        Returns:
            キャンセル済みフラグのBooleanVar.
        """
        return self._is_cancelled

    @property
    def is_stopped(self) -> tk.BooleanVar:
        """コマンドが停止中かどうかを示すTkinter変数を取得します.

        Returns:
            停止中フラグのBooleanVar.
        """
        return self._is_stopped

    @property
    def selected_command_info(self) -> CommandInfo | None:
        """現在選択されているコマンドの情報を取得します.

        Returns:
            選択中のコマンド情報、または選択されていない場合はNone.
        """
        return self._selected_command_info

    def select(self, info: CommandInfo) -> None:
        """コマンドを選択します.

        Args:
            info: 選択するコマンドの情報.
        """
        self._selected_command_info = info

    def start(self, info: CommandInfo | None = None) -> None:
        """コマンドの実行を開始します.

        実行中、生存フラグをTrueに設定し、一時停止、キャンセル、
        停止フラグをFalseに設定します。

        Args:
            info: 実行するコマンドの情報. Noneの場合は状態のみ更新します.
        """
        self._is_running.set(True)
        self._is_paused.set(False)
        self._is_alive.set(True)
        self._is_cancelled.set(False)
        self._is_stopped.set(False)

        if info is not None:
            self._running_command_info = info

    def stop(self) -> None:
        """コマンドを停止します.

        生存フラグをFalseに、停止フラグをTrueに設定します。
        """
        self._is_alive.set(False)
        self._is_stopped.set(True)

    def pause(self) -> None:
        """コマンドを一時停止します.

        一時停止フラグをTrueに設定します。
        """
        self._is_paused.set(True)

    def resume(self) -> None:
        """コマンドの実行を再開します.

        一時停止フラグをFalseに設定します。
        """
        self._is_paused.set(False)

    def cancel(self) -> None:
        """コマンドをキャンセルします.

        生存フラグをFalseに、キャンセル済みフラグをTrueに設定します。
        """
        self._is_alive.set(False)
        self._is_cancelled.set(True)

    def finish(self) -> None:
        """コマンドの実行を終了します.

        全ての実行関連フラグをFalseに、停止フラグをTrueに設定し、
        実行中コマンド情報をクリアします。
        """
        self._is_running.set(False)
        self._is_paused.set(False)
        self._is_alive.set(False)
        self._is_cancelled.set(False)
        self._is_stopped.set(True)

        self.running_command_info = None
