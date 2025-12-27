from pokecontrollerext.api.v0_1_8.command.commands.python.base import (
    PythonCommand,
)
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


class PapicoCommandPauseHandler(PapicoHandler):
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

        command = params["command"]
        if issubclass(command.__class__, PythonCommand):
            command.isPause = True
            return PapicoSuccess(ctx=ctx, data=None)

        return PapicoFailure(ctx=ctx, error=PapicoExecException("Invalid command."))
