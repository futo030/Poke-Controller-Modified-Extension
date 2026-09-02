class AppException(Exception):
    pass


class AppRuntimeException(AppException):
    pass


class AppSettingsException(AppException):
    pass
