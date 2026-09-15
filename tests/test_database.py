from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import check_db_connection, get_db


def test_check_db_connection_success(test_db: Session) -> None:
    assert check_db_connection(test_db) is True


def test_check_db_connection_failure() -> None:
    mock_db = MagicMock(spec=Session)
    mock_db.execute.side_effect = SQLAlchemyError("Database connection lost")

    with pytest.raises(SQLAlchemyError) as exc_info:
        check_db_connection(mock_db)

    assert "Database connection lost" in str(exc_info.value)


def test_get_db_generator() -> None:
    generator = get_db()
    db_session = next(generator)
    assert isinstance(db_session, Session)
    # Ensure generator teardown closes session cleanly
    try:
        next(generator)
    except StopIteration:
        pass
