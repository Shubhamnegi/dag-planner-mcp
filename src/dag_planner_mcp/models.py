from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime, timezone


class ResponseEnvelope(BaseModel):
    ok: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    meta: dict = {}


def ok_response(data, **meta_kwargs):
    return ResponseEnvelope(
        ok=True,
        data=data,
        meta={"timestamp": datetime.now(timezone.utc).isoformat(), **meta_kwargs},
    ).model_dump()


def err_response(code, message, **meta_kwargs):
    return ResponseEnvelope(
        ok=False,
        error=message,
        error_code=code,
        meta={"timestamp": datetime.now(timezone.utc).isoformat(), **meta_kwargs},
    ).model_dump()
