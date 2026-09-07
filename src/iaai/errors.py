"""Bounded, structured errors shared by entry points."""

from uuid import uuid4


class IAAIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message[:2000]
        self.operation_id = str(uuid4())
        super().__init__(self.message)

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "operation_id": self.operation_id}
