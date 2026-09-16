"""
Unit of Work Protocol definition for application transaction management.
"""

from typing import Protocol


class UnitOfWorkProtocol(Protocol):
    """
    Protocol defining transaction boundary capabilities for application services.
    Services call commit() or rollback() through this interface without direct
    dependency on database ORM frameworks (e.g. SQLAlchemy Session).
    """

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "UnitOfWorkProtocol": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None: ...
