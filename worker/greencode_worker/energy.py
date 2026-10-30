"""Målebackends. Alle følger samme grensesnitt slik at workeren kan bytte
mellom RAPL (Intel/AMD på Linux), PMIC (Raspberry Pi 5) og estimat."""

from __future__ import annotations

import os
import resource
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class Measurement:
    joules: float
    seconds: float


class EnergyBackend(Protocol):
    name: str
    precision: str  # "counter", "sampled" eller "estimate"

    def available(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> Measurement: ...


class RaplBackend:
    """Leser energitellerne i /sys/class/powercap. Summerer alle
    prosessorpakker (intel-rapl:0, intel-rapl:1 …), ikke underdomenene,
    siden de allerede inngår i pakken."""

    name = "rapl"
    precision = "counter"

    def __init__(self, base: Path = Path("/sys/class/powercap")) -> None:
        self.base = base
        self.domains = sorted(
            d for d in base.glob("intel-rapl:*") if d.name.count(":") == 1
        )
        self._t0 = 0.0
        self._e0: dict[Path, int] = {}

    def available(self) -> bool:
        try:
            return bool(self.domains) and all(
                isinstance(self._read_one(d), int) for d in self.domains
            )
        except (PermissionError, OSError, ValueError):
            return False

    @staticmethod
    def _read_one(domain: Path) -> int:
        return int((domain / "energy_uj").read_text().strip())

    def _max_range(self, domain: Path) -> int:
        try:
            return int((domain / "max_energy_range_uj").read_text().strip())
        except (OSError, ValueError):
            return 2**32

    def start(self) -> None:
        self._e0 = {d: self._read_one(d) for d in self.domains}
        self._t0 = time.perf_counter()

    def stop(self) -> Measurement:
        t1 = time.perf_counter()
        total_uj = 0
        for d in self.domains:
            delta = self._read_one(d) - self._e0[d]
            if delta < 0:  # telleren har gått rundt
                delta += self._max_range(d)
            total_uj += delta
        return Measurement(joules=total_uj / 1e6, seconds=t1 - self._t0)


class EstimateBackend:
    """Fallback uten maskinvaresensor: CPU-tid for barneprosesser ganget
    med et anslått antall watt per kjerne. Bare for utvikling."""

    name = "estimate"
    precision = "estimate"

    def __init__(self, watts_per_core: Optional[float] = None) -> None:
        self.watts_per_core = watts_per_core or float(
            os.environ.get("GREENCODE_WATTS_PER_CORE", "10")
        )
        self._t0 = 0.0
        self._cpu0 = 0.0

    def available(self) -> bool:
        return True

    @staticmethod
    def _child_cpu() -> float:
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime

    def start(self) -> None:
        self._cpu0 = self._child_cpu()
        self._t0 = time.perf_counter()

    def stop(self) -> Measurement:
        seconds = time.perf_counter() - self._t0
        cpu = self._child_cpu() - self._cpu0
        return Measurement(joules=cpu * self.watts_per_core, seconds=seconds)


def pick_backend(prefer: Optional[str] = None) -> EnergyBackend:
    """Velger beste tilgjengelige backend. `prefer` tvinger et valg."""
    candidates: list[EnergyBackend] = [RaplBackend(), EstimateBackend()]
    if prefer:
        for b in candidates:
            if b.name == prefer:
                if not b.available():
                    raise RuntimeError(f"Backend '{prefer}' er ikke tilgjengelig på denne maskinen.")
                return b
        raise ValueError(f"Ukjent backend: {prefer}")
    return next(b for b in candidates if b.available())
