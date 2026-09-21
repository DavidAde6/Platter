"""Data access.

Every SQL statement in the application lives in this package. Services above
it depend on these function signatures and the typed rows in read_models,
never on table or column names.

The one rule, stated in base.py and worth repeating: repository functions take
an open cursor. They do not open connections and they do not commit. The
caller owns the transaction boundary.

    from repositories.base import tx
    from repositories import meals as meals_repo

    with tx() as cur:
        meal_id = meals_repo.insert_meal(cur, user_id=1, source="web_upload")
"""

from repositories.base import tx

__all__ = ["tx"]
