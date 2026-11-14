from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from chesscoach.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as c:
        yield c
