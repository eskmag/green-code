from pathlib import Path

from greencode_worker.energy import RaplBackend
from greencode_worker.runner import MeasureResult
from greencode_worker.energy import Measurement


def _domain(path: Path, name: str, start: int, max_range: int = 1_000_000) -> Path:
    path.mkdir()
    (path / "name").write_text(name + "\n")
    (path / "energy_uj").write_text(str(start))
    (path / "max_energy_range_uj").write_text(str(max_range))
    return path


def _fake_powercap(tmp_path: Path, start: int, max_range: int = 1_000_000) -> Path:
    pkg = _domain(tmp_path / "intel-rapl:0", "package-0", start, max_range)
    _domain(tmp_path / "intel-rapl:0:0", "core", start, max_range)  # underdomene
    return pkg


def test_rapl_reads_only_package_domains(tmp_path):
    _fake_powercap(tmp_path, 100)
    b = RaplBackend(base=tmp_path)
    assert [d.name for d in b.domains] == ["intel-rapl:0"]
    assert b.available()


def test_rapl_delta(tmp_path):
    pkg = _fake_powercap(tmp_path, 1_000)
    b = RaplBackend(base=tmp_path)
    b.start()
    (pkg / "energy_uj").write_text(str(1_001_000))
    m = b.stop()
    assert m.joules == 1.0  # 1 000 000 µJ


def test_rapl_wraparound(tmp_path):
    pkg = _fake_powercap(tmp_path, 900_000, max_range=1_000_000)
    b = RaplBackend(base=tmp_path)
    b.start()
    (pkg / "energy_uj").write_text("100000")  # telleren gikk rundt
    m = b.stop()
    assert abs(m.joules - 0.2) < 1e-9  # 100 000 til topp + 100 000 etter


def test_net_joules_subtracts_idle():
    r = MeasureResult(backend="rapl", precision="counter", idle_watts=5.0,
                      runs=[Measurement(joules=60.0, seconds=2.0)])
    assert r.net_joules() == [50.0]


def test_rapl_ignores_psys(tmp_path):
    """Bærbare har ofte psys som eget toppnivådomene. Det inkluderer pakken
    og skal ikke summeres med den."""
    pkg = _fake_powercap(tmp_path, 0)
    psys = _domain(tmp_path / "intel-rapl:1", "psys", 0)
    b = RaplBackend(base=tmp_path)
    assert [d.name for d in b.domains] == ["intel-rapl:0"]
    b.start()
    (pkg / "energy_uj").write_text("2000000")
    (psys / "energy_uj").write_text("5000000")
    assert b.stop().joules == 2.0


def test_rapl_sums_multiple_packages(tmp_path):
    p0 = _domain(tmp_path / "intel-rapl:0", "package-0", 0)
    p1 = _domain(tmp_path / "intel-rapl:1", "package-1", 0)
    b = RaplBackend(base=tmp_path)
    b.start()
    (p0 / "energy_uj").write_text("1000000")
    (p1 / "energy_uj").write_text("3000000")
    assert b.stop().joules == 4.0
