from functools import wraps
from time import sleep
from typing import Callable, Concatenate, Protocol

from pokecontrollerext.singletons.app.command import get_app_command_state


class Pausable(Protocol):
    isPause: bool

    def show_var(self) -> None: ...

    def checkIfAlive(self) -> bool: ...


def pausable[**P, S: Pausable, R](
    func: Callable[Concatenate[S, P], R],
) -> Callable[Concatenate[S, P], R]:
    """
    メソッドを一時停止できるできるようにします
    """

    @wraps(func)
    def inner(self: S, /, *args: P.args, **kwargs: P.kwargs) -> R:
        result: R = func(self, *args, **kwargs)
        command_state = get_app_command_state()
        if self.isPause:
            command_state.pause()
            self.show_var()
        while self.isPause:
            sleep(0.5)
            self.checkIfAlive()
        if command_state.is_paused.get():
            command_state.resume()
        return result

    return inner
