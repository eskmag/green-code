"""API-tester kjører mot ekte Postgres. Sett DATABASE_URL til en testdatabase:

    DATABASE_URL=postgresql://postgres@localhost:5433/postgres pytest tests
"""

import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL mangler. Pek den på en lokal testdatabase, "
                       "for eksempel postgresql://postgres@localhost:5433/postgres.")
if "neon.tech" in DATABASE_URL:
    raise RuntimeError("Testene tømmer tabellene. Bruk aldri produksjonsdatabasen.")

os.environ["ADMIN_TOKEN"] = "adm"
os.environ["WORKER_TOKEN"] = "wrk"

from fastapi.testclient import TestClient  # noqa: E402

from api import index  # noqa: E402

ADMIN = {"Authorization": "Bearer adm"}
WORKER = {"Authorization": "Bearer wrk"}


@pytest.fixture(autouse=True)
def clean_db():
    index._schema_ready = False
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(index.SCHEMA)
        conn.execute("TRUNCATE analyses RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS workers")
    yield


@pytest.fixture
def client():
    return TestClient(index.app)


@pytest.fixture
def sql():
    """Kjør SQL direkte, for å sette opp tilstand API-et ikke kan lage selv."""
    def run(query, params=None):
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            return conn.execute(query, params).fetchall() if query.lstrip().upper().startswith("SELECT") \
                else conn.execute(query, params)
    return run
