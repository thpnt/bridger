from typing import Any

from pydantic import BaseModel


class ToolErrorPayload(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class BridgerToolError(RuntimeError):
    def __init__(
        self, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.payload = ToolErrorPayload(error=code, message=message, details=details)


def serialize_tool_call(call: Any) -> dict[str, Any]:
    try:
        result = call()
    except BridgerToolError as error:
        return {"ok": False, **error.payload.model_dump(mode="json", exclude_none=True)}
    return {"ok": True, **result}
