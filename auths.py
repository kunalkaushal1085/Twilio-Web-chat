# auths.py
# ------------------------------------------------------------------
# Password hashing + JWT helpers for The Paul Group admin endpoints
# ------------------------------------------------------------------

import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()                                  

# ───────────────  JWT settings  ───────────────
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-change-me")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30             

# ─────────────  password hasher  ──────────────
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    return _pwd.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain password matches hashed one."""
    return _pwd.verify(plain, hashed)

# ────────────────  JWT helpers  ───────────────
# def create_access_token(data: dict, *, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
#     """
#     Return a signed JWT containing `data` plus an `exp` claim.
#     `minutes` overrides the default lifetime when needed.
#     """
#     to_encode = data.copy()
#     to_encode["exp"] = datetime.utcnow() + timedelta(minutes=minutes)
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(data: dict, *, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    to_encode = data.copy()
    to_encode["exp"] = expire
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token, expire

def decode_token(token: str) -> dict | None:
    """
    Decode the JWT. Returns payload dict on success,
    or None if token is invalid / expired.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
