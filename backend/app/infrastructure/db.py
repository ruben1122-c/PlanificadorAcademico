from typing import Any

import psycopg
from psycopg.rows import dict_row


def get_db_connection(database_url: str) -> psycopg.Connection[dict[str, Any]]:
    """Open a psycopg connection using DATABASE_URL with dict row mapping."""
    return psycopg.connect(database_url, row_factory=dict_row)
