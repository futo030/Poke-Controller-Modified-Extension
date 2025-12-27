from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.model import AppModel

_app_model: AppModel | None = None


def get_app_model() -> AppModel:
    global _app_model
    if _app_model is None:
        raise AppRuntimeException("App model is not initialized.")
    return _app_model


def setup_app_model() -> AppModel:
    global _app_model
    _app_model = AppModel()
    return _app_model
