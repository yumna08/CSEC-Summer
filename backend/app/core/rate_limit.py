from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_STORAGE_URI,
)


limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
    storage_uri=RATE_LIMIT_STORAGE_URI,
    enabled=RATE_LIMIT_ENABLED,
)
