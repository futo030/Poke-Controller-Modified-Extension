from pokecontrollerext.api.v0_1_8.external_tools import (
    MQTTCommunications,
    SocketCommunications,
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
from pokecontrollerext.papico.handlers.handler import (
    PapicoHandler,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)


class PapicoExternalToolsInitializeHandler(PapicoHandler):
    def handle(self, ctx: PapicoExecContext) -> PapicoResult[None]:
        runtime_info = get_app_runtime_info()
        profile = runtime_info.profile
        base_dir = runtime_info.base_dir
        token_path = base_dir / "profiles" / profile / "external_token.ini"
        try:
            SocketCommunications.SOCKET_TOKEN_PATH = str(token_path)
            MQTTCommunications.MQTT_TOKEN_PATH = str(token_path)
            return PapicoSuccess(ctx=ctx, data=None)
        except Exception as e:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException(f"{e}"),
            )
