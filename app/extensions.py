"""Extensoes instanciadas sem app, ligadas no create_app."""

from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
sessao = Session()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
