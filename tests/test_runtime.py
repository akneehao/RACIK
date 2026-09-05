"""Tests for the deployment profile — solver settings derived from real CPU.

The failure these guard against is silent and expensive: a deploy that reports
itself healthy while burning a twelve-second solve budget on a tenth of a core,
and returning a *worse* menu than a four-second budget would have produced.
Measured on one core, five days, SD/Jawa Tengah: 220 candidates at 12 s scores
0.725 adequacy, 60 candidates at 4 s scores 0.860.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import racik.config as config

TUNABLES = ("RACIK_CPU_BUDGET", "RACIK_CANDIDATES_PER_SLOT", "RACIK_SOLVE_SECONDS")


def reloaded(monkeypatch, **env):
    """Re-import config under a given environment and hand back the module."""
    for key in TUNABLES:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def restore_config():
    """Put the real module back, so a reload here cannot leak into other tests."""
    yield
    for key in TUNABLES:
        __import__("os").environ.pop(key, None)
    importlib.reload(config)


# ---------------------------------------------------------------- profiles

def test_low_cpu_profile_shrinks_the_search(monkeypatch):
    """A tenth of a vCPU must not ask for eight workers and a 12 s budget."""
    cfg = reloaded(monkeypatch, RACIK_CPU_BUDGET="0.1")
    assert cfg.LOW_CPU is True
    assert cfg.SOLVER_WORKERS == 1
    assert cfg.DEFAULT_CANDIDATES_PER_SLOT == 60
    assert cfg.DEFAULT_SOLVE_SECONDS == 4.0


def test_normal_cpu_keeps_the_full_pool(monkeypatch):
    """A real machine should not be penalised for the deployment's constraints."""
    cfg = reloaded(monkeypatch, RACIK_CPU_BUDGET="8")
    assert cfg.LOW_CPU is False
    assert cfg.SOLVER_WORKERS == 8
    assert cfg.DEFAULT_CANDIDATES_PER_SLOT == 220
    assert cfg.DEFAULT_SOLVE_SECONDS == 12.0


@pytest.mark.parametrize("budget,workers", [
    ("0.05", 1), ("0.5", 1), ("1", 1), ("2", 2), ("4", 4), ("64", 8),
])
def test_workers_stay_within_range(monkeypatch, budget, workers):
    """Never zero workers, never more than the portfolio can use."""
    assert reloaded(monkeypatch, RACIK_CPU_BUDGET=budget).SOLVER_WORKERS == workers


@pytest.mark.parametrize("budget", ["0.1", "8"])
def test_default_pool_clears_the_infeasibility_cliff(monkeypatch, budget):
    """Below ~50 candidates the variety constraints deadlock and no menu exists.

    Measured cliff: 60 solves, 40 returns INFEASIBLE. Neither profile may ship a
    default anywhere near it, because an unpinned infeasible solve surfaces to
    the operator as "no menu could be built".
    """
    assert reloaded(monkeypatch, RACIK_CPU_BUDGET=budget).DEFAULT_CANDIDATES_PER_SLOT >= 50


# ---------------------------------------------------------------- overrides

def test_explicit_overrides_win(monkeypatch):
    cfg = reloaded(monkeypatch, RACIK_CPU_BUDGET="0.1",
                   RACIK_CANDIDATES_PER_SLOT="80", RACIK_SOLVE_SECONDS="6")
    assert cfg.DEFAULT_CANDIDATES_PER_SLOT == 80
    assert cfg.DEFAULT_SOLVE_SECONDS == 6.0
    assert cfg.SOLVER_WORKERS == 1, "an override of the pool must not change workers"


def test_unparseable_env_is_ignored_not_fatal(monkeypatch):
    """A typo in a dashboard env var must not take the deployment down."""
    cfg = reloaded(monkeypatch, RACIK_CPU_BUDGET="banyak",
                   RACIK_CANDIDATES_PER_SLOT="", RACIK_SOLVE_SECONDS="4s")
    assert cfg.CPU_BUDGET > 0
    assert cfg.DEFAULT_CANDIDATES_PER_SLOT in (60, 220)
    assert cfg.DEFAULT_SOLVE_SECONDS in (4.0, 12.0)


def test_cgroup_quota_is_read_when_present(monkeypatch, tmp_path):
    """Containers report the host's cores; the cgroup is the honest number."""
    quota = tmp_path / "cpu.max"
    quota.write_text("10000 100000")          # 0.1 of a core
    real_path = config.Path

    class FakePath(type(real_path())):
        def __new__(cls, *a):
            if a and str(a[0]) == "/sys/fs/cgroup/cpu.max":
                return real_path(quota)
            return real_path(*a)

    monkeypatch.setattr(config, "Path", FakePath)
    assert config._cgroup_cpu_quota() == pytest.approx(0.1)


def test_no_cgroup_falls_back_without_raising(monkeypatch):
    monkeypatch.setattr(config.Path, "read_text",
                        lambda self, *a, **k: (_ for _ in ()).throw(OSError))
    assert config._cgroup_cpu_quota() is None


# ---------------------------------------------------------------- warm-up

def test_startup_warms_the_corpus_without_blocking_boot():
    """The port must open immediately; the corpus loads behind it."""
    import time

    from fastapi.testclient import TestClient

    from racik.api import app

    started = time.perf_counter()
    with TestClient(app) as client:
        boot = time.perf_counter() - started
        assert boot < 2.0, f"lifespan blocked boot for {boot:.2f}s"
        assert client.get("/api/health").json()["dishes"] > 0


def test_warm_up_failure_does_not_kill_boot(monkeypatch):
    """A broken warm-up must degrade to lazy loading, not refuse to start."""
    from fastapi.testclient import TestClient

    import racik.api as api

    def boom():
        raise RuntimeError("no database here")

    monkeypatch.setattr(api, "_optimizer", boom)
    with TestClient(api.app) as client:
        assert client.get("/api/health").status_code == 200
