"""green-code API.

Kjører som én Python-funksjon på Vercel. All trafikk til /api/* rutes hit
(se vercel.json). Workere på egne maskiner henter jobber herfra og laster
opp målingene; de trenger ingen åpne porter.
"""

from __future__ import annotations

import hmac
import os
import statistics
from contextlib import contextmanager
from typing import Any, Iterator, Literal, Optional

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
# Utslippsfaktor for strømmen workeren bruker. NO5 (Bergen) er standard.
# Erstattes av Electricity Maps senere.
CARBON_G_PER_KWH = float(os.environ.get("CARBON_G_PER_KWH", "21"))
CARBON_ZONE = os.environ.get("CARBON_ZONE", "NO5")

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id           BIGSERIAL PRIMARY KEY,
    repo_url     TEXT NOT NULL,
    ref          TEXT NOT NULL DEFAULT 'main',
    setup        TEXT,
    command      TEXT NOT NULL,
    iterations   INTEGER NOT NULL DEFAULT 10,
    status       TEXT NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'done', 'failed')),
    worker_id    TEXT,
    commit_sha   TEXT,
    backend      TEXT,
    precision    TEXT,
    idle_watts   DOUBLE PRECISION,
    runs         JSONB,
    summary      JSONB,
    meta         JSONB,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS analyses_queue_idx
    ON analyses (created_at) WHERE status = 'queued';
"""

app = FastAPI(title="green-code", version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json")

_schema_ready = False


@contextmanager
def db() -> Iterator[psycopg.Connection]:
    global _schema_ready
    if not DATABASE_URL:
        raise HTTPException(503, "Databasen er ikke koblet til (DATABASE_URL mangler).")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        if not _schema_ready:
            conn.execute(SCHEMA)
            conn.commit()
            _schema_ready = True
        yield conn


def _token_check(expected: str, authorization: Optional[str]) -> None:
    if not expected:
        raise HTTPException(503, "Tokenet er ikke satt i miljøvariablene på serveren.")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Ugyldig eller manglende token.")


def require_admin(authorization: Optional[str] = Header(None)) -> None:
    _token_check(ADMIN_TOKEN, authorization)


def require_worker(authorization: Optional[str] = Header(None)) -> None:
    _token_check(WORKER_TOKEN, authorization)


# ---------- Modeller ----------

class AnalysisIn(BaseModel):
    repo_url: str = Field(..., max_length=500)
    ref: str = Field("main", max_length=200)
    setup: Optional[str] = Field(None, max_length=1000,
                                 description="Kjøres én gang før målingen, telles ikke")
    command: str = Field(..., min_length=1, max_length=1000)
    iterations: int = Field(10, ge=1, le=50)

    @field_validator("repo_url")
    @classmethod
    def https_only(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("repo_url må være en https://-adresse")
        return v


class RunIn(BaseModel):
    joules: float = Field(..., ge=0)
    seconds: float = Field(..., gt=0)


class ResultIn(BaseModel):
    status: Literal["done", "failed"]
    commit_sha: Optional[str] = None
    backend: Optional[str] = None
    precision: Optional[str] = None
    idle_watts: Optional[float] = Field(None, ge=0)
    runs: list[RunIn] = []
    meta: dict[str, Any] = {}
    error: Optional[str] = Field(None, max_length=5000)


class ClaimIn(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=100)


# ---------- Beregninger ----------

def summarize(runs: list[RunIn], idle_watts: float) -> dict[str, Any]:
    """Netto energi per kjøring, spredning og CO₂."""
    net = [max(r.joules - idle_watts * r.seconds, 0.0) for r in runs]
    secs = [r.seconds for r in runs]
    median_j = statistics.median(net)
    mean_j = statistics.fmean(net)
    spread = (statistics.stdev(net) / mean_j * 100) if len(net) > 1 and mean_j > 0 else None
    kwh = median_j / 3.6e6
    return {
        "joules_net_median": round(median_j, 3),
        "seconds_median": round(statistics.median(secs), 4),
        "watts_net_avg": round(median_j / statistics.median(secs), 2),
        "spread_pct": round(spread, 2) if spread is not None else None,
        "kwh": kwh,
        "co2_mg": round(kwh * CARBON_G_PER_KWH * 1000, 4),
        "carbon_g_per_kwh": CARBON_G_PER_KWH,
        "carbon_zone": CARBON_ZONE,
        "iterations": len(runs),
    }


# ---------- Endepunkter ----------

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "database": bool(DATABASE_URL),
            "admin_token": bool(ADMIN_TOKEN), "worker_token": bool(WORKER_TOKEN)}


LIST_COLUMNS = ("id, repo_url, ref, command, iterations, status, worker_id, commit_sha, "
                "backend, summary, error, created_at, started_at, finished_at")


@app.post("/api/v1/analyses", status_code=201, dependencies=[Depends(require_admin)])
def create_analysis(body: AnalysisIn) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "INSERT INTO analyses (repo_url, ref, setup, command, iterations) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING " + LIST_COLUMNS,
            (body.repo_url, body.ref, body.setup, body.command, body.iterations),
        ).fetchone()
        conn.commit()
    return row


@app.get("/api/v1/analyses", dependencies=[Depends(require_admin)])
def list_analyses(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    with db() as conn:
        return conn.execute(
            f"SELECT {LIST_COLUMNS} FROM analyses ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()


@app.get("/api/v1/analyses/{analysis_id}", dependencies=[Depends(require_admin)])
def get_analysis(analysis_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = %s", (analysis_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Fant ingen analyse med den id-en.")
    return row


@app.post("/api/v1/worker/claim", dependencies=[Depends(require_worker)],
          response_model=None)
def claim_job(body: ClaimIn) -> Response | dict[str, Any]:
    """Gir workeren den eldste ventende jobben. SKIP LOCKED gjør at flere
    workere kan spørre samtidig uten å få samme jobb."""
    with db() as conn:
        row = conn.execute(
            """
            UPDATE analyses
               SET status = 'running', worker_id = %s, started_at = now()
             WHERE id = (SELECT id FROM analyses
                          WHERE status = 'queued'
                          ORDER BY created_at
                          FOR UPDATE SKIP LOCKED
                          LIMIT 1)
         RETURNING id, repo_url, ref, setup, command, iterations
            """,
            (body.worker_id,),
        ).fetchone()
        conn.commit()
    if not row:
        return Response(status_code=204)
    return row


@app.post("/api/v1/worker/analyses/{analysis_id}/result",
          dependencies=[Depends(require_worker)])
def submit_result(analysis_id: int, body: ResultIn) -> dict[str, Any]:
    summary = None
    if body.status == "done":
        if not body.runs:
            raise HTTPException(422, "En fullført analyse må ha minst én kjøring.")
        summary = summarize(body.runs, body.idle_watts or 0.0)
    with db() as conn:
        row = conn.execute(
            """
            UPDATE analyses
               SET status = %s, commit_sha = %s, backend = %s, precision = %s,
                   idle_watts = %s, runs = %s, summary = %s, meta = %s, error = %s,
                   finished_at = now()
             WHERE id = %s AND status = 'running'
         RETURNING id, status, summary
            """,
            (body.status, body.commit_sha, body.backend, body.precision, body.idle_watts,
             Jsonb([r.model_dump() for r in body.runs]),
             Jsonb(summary) if summary else None, Jsonb(body.meta), body.error,
             analysis_id),
        ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(409, "Analysen finnes ikke eller kjører ikke.")
    return row
