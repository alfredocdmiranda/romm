import secrets
import base64
import binascii
from typing import Annotated
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, BaseConfig
from starlette.authentication import requires

from handler import dbh
from models.user import User, Role
from utils.cache import cache
from utils.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter()


class UserSchema(BaseModel):
    username: str
    disabled: bool
    role: Role

    class Config(BaseConfig):
        orm_mode = True


def credentials_exception(scheme: str):
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": scheme},
    )


@router.post("/token", response_model=UserSchema)
def generate_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise credentials_exception("Bearer")

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login")
def login(request: Request):
    if "Authorization" not in request.headers:
        raise credentials_exception("Basic")

    auth = request.headers["Authorization"]
    try:
        scheme, credentials = auth.split()
        if scheme.lower() != "basic":
            return
        decoded = base64.b64decode(credentials).decode("ascii")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise credentials_exception("Basic")

    username, _, password = decoded.partition(":")
    user = authenticate_user(username, password)
    if not user:
        raise credentials_exception("Basic")

    # Generate unique session key and store in cache
    request.session["session_id"] = secrets.token_hex(16)
    cache.set(f'romm:{request.session["session_id"]}', user.username)

    return {"message": "Successfully logged in"}


@router.get("/users")
@requires(["users.read"])
def users(request: Request) -> list[UserSchema]:
    return dbh.get_users()


@router.get("/users/me")
@requires(["me.read"])
def current_user(request: Request) -> UserSchema:
    return request.user


@router.post("/users/")
@requires(["users.write"])
def create_user(
    request: Request, username: str, password: str, role: str
) -> UserSchema:
    user = User(
        username=username,
        hashed_password=get_password_hash(password),
        disabled=False,
        role=Role[role.upper()],
    )
    dbh.add_user(user)

    return user
