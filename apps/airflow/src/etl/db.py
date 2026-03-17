import os
from contextlib import contextmanager
from typing import Iterator

import psycopg


DATABASE_URL_ENV = "DATABASE_URL"


def _get_database_url() -> str:
    url = os.getenv(DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not set")
    return url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(_get_database_url())
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Iterator[psycopg.Cursor]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()

