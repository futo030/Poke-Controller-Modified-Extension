from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.settings import AppSettings

_app_settings: AppSettings | None = None


def setup_app_settings(settings: AppSettings) -> AppSettings:
    global _app_settings
    _app_settings = settings
    return settings


def get_app_settings() -> AppSettings:
    global _app_settings
    if _app_settings is None:
        raise AppRuntimeException("App settings is not initialized")
    return _app_settings


def get_app_settings_or_none() -> AppSettings | None:
    global _app_settings
    return _app_settings
