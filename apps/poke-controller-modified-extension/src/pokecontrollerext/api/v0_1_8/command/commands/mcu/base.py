from abc import ABC

from pokecontrollerext.api.v0_1_8.command.commands.base import (
    Command,
    PostProcess,
)
from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.singletons.app.command import get_app_command_state


class McuCommand(Command, ABC):
    def __init__(self, sync_name: str):
        super().__init__()
        self.sync_name = sync_name
        self.postProcess: PostProcess | None = None
        self._command_state = get_app_command_state()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,  # noqa
    ) -> None:
        self._command_state.start()
        ser.writeRow(self.sync_name)
        self.isRunning = True
        self.postProcess = postProcess

    def end(self, ser: Sender) -> None:
        ser.writeRow("end")
        self.isRunning = False
        if (proc := self.postProcess) is not None:
            proc()
        self._command_state.finish()
