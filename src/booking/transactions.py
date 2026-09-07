"""Composable SQLite transactions: nested operations use savepoints."""

from contextlib import contextmanager
from functools import wraps
from uuid import uuid4


@contextmanager
def atomic(connection):
    nested = connection.in_transaction
    marker = "sp_" + uuid4().hex
    connection.execute(f"SAVEPOINT {marker}" if nested else "BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if nested:
            connection.execute(f"ROLLBACK TO {marker}")
            connection.execute(f"RELEASE {marker}")
        else:
            connection.rollback()
        raise
    else:
        if nested:
            connection.execute(f"RELEASE {marker}")
        else:
            connection.commit()


def transactional_method(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with atomic(self.connection):
            return method(self, *args, **kwargs)
    return wrapped
