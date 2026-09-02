from pokecontrollerext.app.exception import AppException


class PapicoException(AppException):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class PapicoExecException(PapicoException):
    pass
