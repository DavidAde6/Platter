"""The unit of work.

Every repository function in this package takes an open cursor and never
opens a connection, starts a transaction, or commits. The caller decides
where a transaction begins and ends by choosing where to put a ``tx()``
block.

That rule is what makes two otherwise-awkward things possible:

  * The upload path can commit the meal row, then do 15-30s of external I/O
    holding no database connection, then commit the analysis separately.
    Repository functions that committed internally could not express that.
  * A test can hand a repository a cursor from a transaction it intends to
    roll back, giving perfect isolation with no teardown SQL at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Cursor

from db import get_connection


@contextmanager
def tx() -> Iterator[Cursor]:
    """One transaction. Commits on clean exit, rolls back on exception.

    Keep the block as small as the work requires. Anything slow and external
    -- R2, an Anthropic call -- belongs between blocks, not inside one.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            yield cur
