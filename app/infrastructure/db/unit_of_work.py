"""
SQLAlchemy implementation of UnitOfWorkProtocol.
"""

from typing import Self

from sqlalchemy.orm import Session

from app.services.unit_of_work import UnitOfWorkProtocol


class SQLAlchemyUnitOfWork(UnitOfWorkProtocol):
    """
    SQLAlchemy implementation wrapping a Session instance.
    Provides explicit transaction boundaries (commit/rollback) to Application Services.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
