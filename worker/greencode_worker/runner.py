"""Kjører en kommando under måling: tomgang, oppvarming, målte kjøringer."""

from __future__ import annotations

import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .energy import EnergyBackend, Measurement


class CommandFailed(RuntimeError):
    pass


@dataclass
class MeasureResult:
    backend: str
    precision: str
    idle_watts: float
    runs: list[Measurement] = field(default_factory=list)

    def net_joules(self) -> list[float]:
        return [max(r.joules - self.idle_watts * r.seconds, 0.0) for r in self.runs]

    def as_payload(self) -> dict:
        return {
            "backend": self.backend,
            "precision": self.precision,
            "idle_watts": round(self.idle_watts, 4),
            "runs": [asdict(r) for r in self.runs],
        }

    def describe(self) -> str:
        net = self.net_joules()
        secs = [r.seconds for r in self.runs]
        med = statistics.median(net)
        spread = (statistics.stdev(net) / statistics.fmean(net) * 100
                  if len(net) > 1 and statistics.fmean(net) > 0 else 0.0)
        return (f"backend={self.backend} ({self.precision})  tomgang={self.idle_watts:.2f} W\n"
                f"netto energi (median): {med:.2f} J  ±{spread:.1f} %\n"
                f"kjøretid (median):     {statistics.median(secs):.3f} s\n"
                f"kjøringer:             {len(self.runs)}")


def _run_once(command: str, cwd: Optional[Path], timeout: float) -> None:
    proc = subprocess.run(command, shell=True, cwd=cwd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace")[-2000:]
        raise CommandFailed(f"Kommandoen avsluttet med kode {proc.returncode}:\n{tail}")


def measure_idle(backend: EnergyBackend, seconds: float) -> float:
    """Gjennomsnittlig effekt i watt uten last."""
    if seconds <= 0 or backend.precision == "estimate":
        return 0.0
    backend.start()
    time.sleep(seconds)
    m = backend.stop()
    return m.joules / m.seconds


def measure_command(command: str, backend: EnergyBackend, *, cwd: Optional[Path] = None,
                    iterations: int = 10, warmup: int = 2, idle_seconds: float = 10.0,
                    timeout: float = 600.0, log=print) -> MeasureResult:
    log(f"Måler tomgang i {idle_seconds:.0f} s …")
    idle = measure_idle(backend, idle_seconds)
    for i in range(warmup):
        log(f"Oppvarming {i + 1}/{warmup}")
        _run_once(command, cwd, timeout)
    result = MeasureResult(backend=backend.name, precision=backend.precision, idle_watts=idle)
    for i in range(iterations):
        backend.start()
        _run_once(command, cwd, timeout)
        m = backend.stop()
        result.runs.append(m)
        log(f"Kjøring {i + 1}/{iterations}: {m.joules:.2f} J på {m.seconds:.3f} s")
    return result
