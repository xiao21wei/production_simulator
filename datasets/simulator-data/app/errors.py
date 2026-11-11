"""统一 API 错误。"""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, message: str, detail=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail
