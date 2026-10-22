"""/v1 的錯誤一律照 OpenAI 的格式回傳：{"error": {"message", "type", "param", "code"}}。

訊息用英文，讓現有的 OpenAI 用戶端照原本的方式處理。
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_TYPES = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "invalid_request_error",
    429: "rate_limit_error",
    502: "server_error",
    503: "service_unavailable",
}


class OpenAIError(Exception):
    def __init__(self, status: int, code: str, message: str, *, param: str | None = None,
                 headers: dict | None = None, type_: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.param = param
        self.headers = headers or {}
        self.type = type_ or _TYPES.get(status, "server_error")

    def body(self) -> dict:
        return {"error": {"message": self.message, "type": self.type, "param": self.param, "code": self.code}}


def invalid_api_key() -> OpenAIError:
    return OpenAIError(401, "invalid_api_key", "Incorrect API key provided.", headers={"WWW-Authenticate": "Bearer"})


def key_disabled(reason: str) -> OpenAIError:
    return OpenAIError(403, "key_disabled", reason)


def model_not_found(name: str) -> OpenAIError:
    return OpenAIError(404, "model_not_found", f"The model '{name}' does not exist or you do not have access to it.",
                       param="model")


def model_not_loaded(name: str) -> OpenAIError:
    return OpenAIError(503, "model_not_loaded", f"Model '{name}' is not loaded.", param="model")


def model_busy(name: str) -> OpenAIError:
    return OpenAIError(503, "model_busy", f"Model '{name}' is busy. Please retry later.", param="model",
                       headers={"Retry-After": "5"})


def unsupported(message: str, param: str | None = None, code: str = "unsupported_capability") -> OpenAIError:
    return OpenAIError(400, code, message, param=param)


def error_response(err: OpenAIError, extra_headers: dict | None = None) -> JSONResponse:
    return JSONResponse(err.body(), status_code=err.status, headers={**err.headers, **(extra_headers or {})})


def validation_error(exc: RequestValidationError) -> OpenAIError:
    first = (exc.errors() or [{}])[0]
    loc = [str(p) for p in first.get("loc", []) if p != "body"]
    return OpenAIError(400, "invalid_request_error", first.get("msg", "Invalid request."),
                       param=".".join(loc) or None)


def is_v1(request: Request) -> bool:
    return request.url.path.startswith("/v1/") or request.url.path == "/v1"
