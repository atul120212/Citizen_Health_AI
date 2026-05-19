from fastapi import Header, HTTPException, Depends
from .config import get_settings

def verify_admin(x_admin_key: str | None = Header(default=None)):
    """
    Dependency to verify the admin API key.
    If ADMIN_API_KEY is not set in settings, it allows access (demo mode).
    In production, always set ADMIN_API_KEY.
    """
    settings = get_settings()
    if settings.admin_api_key:
        if x_admin_key != settings.admin_api_key:
            raise HTTPException(status_code=401, detail="Invalid Admin Key")
    return True
