from threading import Thread

from pokecontrollerext.api.v0_1_8.camera import Camera
from pokecontrollerext.api.v0_1_8.command.commands.mcu.base import (
    McuCommand,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.base import (
    PythonCommand,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.image_processing import (
    ImageProcPythonCommand,
)
from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.command.info import CommandInfo
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


class PapicoCommandStartHandler(PapicoHandler):
    def handle(
        self, ctx: PapicoExecContext
    ) -> PapicoResult[tuple[PythonCommand | McuCommand, Thread | None]]:
        if (params := ctx.params) is None:
            return PapicoFailure(
                ctx=ctx, error=PapicoExecException("params is required.")
            )
        if "info" not in params:
            return PapicoFailure(
                ctx=ctx, error=PapicoExecException("info is required.")
            )

        info = params["info"]
        if not isinstance(info, CommandInfo):
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException("info must be CommandInfo."),
            )

        app_settings = get_app_settings()

        klass = info.klass
        if issubclass(klass, ImageProcPythonCommand):
            camera = Camera(app_settings.capture.fps.get())
            post_process = params.get("post_process", None)
            sender = Sender(app_settings.serial.show_data)
            image_proc_python_command = klass(cam=camera)
            image_proc_python_command.start(ser=sender, postProcess=post_process)
            return PapicoSuccess(
                ctx=ctx,
                data=(image_proc_python_command, image_proc_python_command.thread),
            )
        if issubclass(klass, PythonCommand):
            post_process = params.get("post_process", None)
            sender = Sender(app_settings.serial.show_data)
            python_command = klass()
            python_command.start(ser=sender, postProcess=post_process)
            return PapicoSuccess(
                ctx=ctx,
                data=(python_command, python_command.thread),
            )
        if issubclass(klass, McuCommand):
            if "sync_name" not in params:
                return PapicoFailure(
                    ctx=ctx,
                    error=PapicoExecException("sync_name is required."),
                )
            sync_name = params["sync_name"]
            post_process = params.get("post_process", None)
            sender = Sender(app_settings.serial.show_data)
            mcu_command = klass(sync_name=sync_name)
            mcu_command.start(ser=sender, postProcess=post_process)
            return PapicoSuccess(ctx=ctx, data=(mcu_command, None))

        return PapicoFailure(
            ctx=ctx, error=PapicoExecException("Invalid command class.")
        )
