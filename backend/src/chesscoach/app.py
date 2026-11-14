from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from chesscoach import auth
from chesscoach.db import Base, make_engine


def create_app(database_url: str) -> FastAPI:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)

    app = FastAPI(title="Chess Coach")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(auth.auth_router)
    app.include_router(auth.player_router)
    return app
