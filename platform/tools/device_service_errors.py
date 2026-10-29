"""Public error contract for the Device Service."""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        **extra,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                **self.extra,
            }
        }
