from pokecontrollerext.api.v0_1_8.command.commands.mcu.base import (
    McuCommand,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.base import (
    PythonCommand,
    StopThread,
)
from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.papico.context import (
    PapicoExecContext,
    PapicoFailure,
    PapicoResult,
    PapicoSuccess,
)
from pokecontrollerext.papico.exception import (
    PapicoExecException,
)
from pokecontrollerext.papico.handlers import PapicoHandler
from pokecontrollerext.singletons.app.settings import get_app_settings


class PapicoCommandStopHandler(PapicoHandler):
    def handle(self, ctx: PapicoExecContext) -> PapicoResult[None]:
        if (params := ctx.params) is None:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException("params is required."),
            )
        if "command" not in params:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException("Command is required."),
            )

        app_settings = get_app_settings()

        command = params["command"]
        if issubclass(command.__class__, PythonCommand):
            sender = Sender(app_settings.serial.show_data)
            try:
                command.end(ser=sender)
            except StopThread:
                pass
            return PapicoSuccess(ctx=ctx, data=None)
        if issubclass(command.__class__, McuCommand):
            sender = Sender(app_settings.serial.show_data)
            command.end(ser=sender)
            return PapicoSuccess(ctx=ctx, data=None)

        return PapicoFailure(ctx=ctx, error=PapicoExecException("Invalid command."))
