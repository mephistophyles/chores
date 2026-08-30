"""Identity resolution.

There is no login here and never will be: the proxy resolves the caller and
sets the headers, and the app is reachable only through it. AUTH_MODE=none
runs single-user, which is the default until forward-auth exists.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException

from . import config


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str

    @property
    def may_write(self) -> bool:
        return self.role in config.WRITE_ROLES


def identity(
    x_auth_user: str | None = Header(default=None),
    x_auth_role: str | None = Header(default=None),
) -> Identity:
    if config.AUTH_MODE == "none":
        return Identity(user_id=config.SINGLE_USER_ID, role="owner")

    if config.AUTH_MODE != "proxy":
        raise HTTPException(status_code=500, detail="AUTH_MODE must be 'none' or 'proxy'")

    user = (x_auth_user or "").strip()
    role = (x_auth_role or "").strip().lower()
    # Unknown user or unknown role is a 403. Never default-allow.
    if not user or role not in config.KNOWN_ROLES:
        raise HTTPException(status_code=403, detail="not authorised")
    return Identity(user_id=user, role=role)


def require_write(who: Identity) -> Identity:
    if not who.may_write:
        raise HTTPException(status_code=403, detail="read-only role")
    return who
