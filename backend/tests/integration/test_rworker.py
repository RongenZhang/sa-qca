import shutil
from pathlib import Path

import pytest

from app.api.service import _reference_decision
from app.demo import load_demo
from app.engine.rinput import build_r_input
from app.rclient import run_pipeline_local
from app.rworker import RWorker, RWorkerError

RSERVICE = str(Path(__file__).resolve().parents[3] / "rservice")
pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")


def payload():
    d = load_demo()
    return build_r_input(_reference_decision(d), d["data"], d["directions"], d["dir_exp"], d["outcome"])


@pytest.fixture(scope="module")
def worker():
    w = RWorker(RSERVICE)
    yield w
    w.stop()


def test_worker_result_equals_a_fresh_r_process(worker):
    p = payload()
    assert worker.run(p) == run_pipeline_local(p, RSERVICE)


def test_repeated_calls_are_identical(worker):
    p = payload()
    first = worker.run(p)
    assert all(worker.run(p) == first for _ in range(3))


def test_different_inputs_do_not_leak_state_between_calls(worker):
    p = payload()
    q = payload()
    q["truth_table"]["consistency_threshold"] = 0.95
    a1, b, a2 = worker.run(p), worker.run(q), worker.run(p)
    assert a1 == a2 and a1 != b


def test_r_errors_come_back_as_results_not_crashes(worker):
    p = payload()
    del p["conditions"][0]["anchors"]["crossover"]
    assert worker.run(p)["status"] == "r_error"
    assert worker.run(payload())["status"] in ("ok", "valid_no_solution")  # worker still healthy


def test_recovers_after_the_r_process_is_killed(worker):
    worker.run(payload())
    assert worker._proc is not None
    worker._proc.kill()
    worker._proc.wait()
    assert worker.run(payload())["status"] in ("ok", "valid_no_solution")


def test_recycles_after_many_calls():
    w = RWorker(RSERVICE, recycle_after=2)
    try:
        w.run(payload())
        first_pid = w._proc.pid
        w.run(payload())
        w.run(payload())  # third call triggers a fresh process
        assert w._proc.pid != first_pid
    finally:
        w.stop()


def test_timeout_discards_the_worker_and_raises():
    w = RWorker(RSERVICE, call_timeout=0.001)
    try:
        w.warm()
        with pytest.raises(RWorkerError):
            w.run(payload())
        assert w._proc is None  # never reused after an unknown state
    finally:
        w.stop()
