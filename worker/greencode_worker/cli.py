"""Kommandolinje for workeren.

  greencode-worker info                    viser tilgjengelige målebackends
  greencode-worker measure "<kommando>"    måler en kommando lokalt (fase 1)
  greencode-worker run [--once]            henter og kjører jobber fra API-et
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .client import ApiClient, ApiError
from .energy import EstimateBackend, RaplBackend, pick_backend
from .runner import CommandFailed, measure_command


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        sys.exit(f"Miljøvariabelen {name} mangler.")
    return value


def cmd_info(_: argparse.Namespace) -> int:
    rapl = RaplBackend()
    print(f"greencode-worker {__version__}")
    print(f"RAPL-domener funnet: {[d.name for d in rapl.domains] or 'ingen'}")
    if rapl.domains and not rapl.available():
        print("  RAPL finnes, men energy_uj kan ikke leses. Se README om tilgang.")
    print(f"RAPL tilgjengelig:   {rapl.available()}")
    print(f"Estimat tilgjengelig: {EstimateBackend().available()}")
    print(f"Valgt backend:        {pick_backend().name}")
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    backend = pick_backend(args.backend)
    try:
        result = measure_command(args.command, backend, cwd=Path(args.cwd) if args.cwd else None,
                                 iterations=args.iterations, warmup=args.warmup,
                                 idle_seconds=args.idle)
    except CommandFailed as e:
        print(e, file=sys.stderr)
        return 1
    print()
    print(result.describe())
    if args.json:
        print(json.dumps(result.as_payload(), indent=2))
    return 0


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=300).stdout.strip()


def process_job(job: dict, client: ApiClient, backend_name: str | None) -> None:
    jid = job["id"]
    print(f"\n=== Analyse #{jid}: {job['repo_url']}@{job['ref']} ===")
    payload: dict = {"status": "failed"}
    with tempfile.TemporaryDirectory(prefix=f"greencode-{jid}-") as tmp:
        src = Path(tmp) / "src"
        try:
            _git("clone", "--depth", "1", "--branch", job["ref"], job["repo_url"], str(src))
            payload["commit_sha"] = _git("rev-parse", "HEAD", cwd=src)
            if job.get("setup"):
                print(f"Setup (måles ikke): {job['setup']}")
                subprocess.run(job["setup"], shell=True, cwd=src, check=True, timeout=1800)
            backend = pick_backend(backend_name)
            result = measure_command(
                job["command"], backend, cwd=src, iterations=job["iterations"],
                warmup=int(os.environ.get("GREENCODE_WARMUP", "2")),
                idle_seconds=float(os.environ.get("GREENCODE_IDLE_SECONDS", "10")),
            )
            payload.update(result.as_payload())
            payload["status"] = "done"
            payload["meta"] = {"worker_version": __version__, "host": socket.gethostname()}
            print(result.describe())
        except (CommandFailed, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                RuntimeError) as e:
            payload["error"] = str(e)[-5000:]
            print(f"Feilet: {e}", file=sys.stderr)
    client.submit(jid, payload)
    print(f"Resultat for #{jid} lastet opp ({payload['status']}).")


def cmd_run(args: argparse.Namespace) -> int:
    client = ApiClient(_env("GREENCODE_API_URL"), _env("GREENCODE_WORKER_TOKEN"))
    worker_id = os.environ.get("GREENCODE_WORKER_ID", socket.gethostname())
    poll = float(os.environ.get("GREENCODE_POLL_SECONDS", "15"))
    print(f"Worker {worker_id} spør {client.base_url} hvert {poll:.0f}. sekund.")
    while True:
        try:
            job = client.claim(worker_id)
        except ApiError as e:
            print(f"API-feil: {e}", file=sys.stderr)
            job = None
            if args.once:
                return 1
        if job:
            process_job(job, client, args.backend)
        elif args.once:
            print("Ingen jobber i køen.")
            return 0
        if args.once:
            return 0
        if not job:
            time.sleep(poll)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="greencode-worker", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="vis målebackends").set_defaults(func=cmd_info)

    m = sub.add_parser("measure", help="mål en kommando lokalt")
    m.add_argument("command")
    m.add_argument("-n", "--iterations", type=int, default=10)
    m.add_argument("--warmup", type=int, default=2)
    m.add_argument("--idle", type=float, default=10.0, help="sekunder tomgangsmåling")
    m.add_argument("--cwd")
    m.add_argument("--backend", choices=["rapl", "estimate"])
    m.add_argument("--json", action="store_true", help="skriv rådata som JSON")
    m.set_defaults(func=cmd_measure)

    r = sub.add_parser("run", help="hent og kjør jobber fra API-et")
    r.add_argument("--once", action="store_true", help="kjør maks én jobb og avslutt")
    r.add_argument("--backend", choices=["rapl", "estimate"])
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
