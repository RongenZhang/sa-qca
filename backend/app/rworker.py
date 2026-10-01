"""A long-lived R process for the QCA pipeline.

Starting R and loading QCA costs seconds (about 30 s on a throttled free-tier CPU), so the pipeline runs in one
persistent process that is reused for every call. The computation is the same pure function as before
(`run_pipeline_json` in rservice/R/pipeline.R): each request carries all of its inputs and R keeps no state between
requests that could change a result. Results are line-delimited JSON behind a sentinel prefix so that any stray
output from R cannot be mistaken for a result."""

from __future__ import annotations

import atexit
import json
import os
import select
import subprocess
import threading
import time
from typing import Any

SENTINEL = b"@@SAQCA@@"
LOOP_R = r"""
source("R/pipeline.R")
con <- file("stdin"); open(con)
cat("@@SAQCA@@READY\n"); flush(stdout())
while (length(line <- readLines(con, n = 1, warn = FALSE)) > 0) {
  out <- tryCatch(run_pipeline_json(line),
                  error = function(e) canonical_json(list(status = "r_error", error = conditionMessage(e))))
  cat("@@SAQCA@@", out, "\n", sep = ""); flush(stdout())
}
"""


class RWorkerError(RuntimeError):
    pass


class RWorker:
    def __init__(self, rservice_dir: str, rscript: str = "Rscript", call_timeout: float = 600.0,
                 start_timeout: float = 300.0, recycle_after: int = 400) -> None:
        self.dir, self.rscript = rservice_dir, rscript
        self.call_timeout, self.start_timeout, self.recycle_after = call_timeout, start_timeout, recycle_after
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._buf = b""
        self._calls = 0
        atexit.register(self.stop)

    # ---- process management ----
    def _read_line(self, timeout: float) -> bytes:
        assert self._proc is not None and self._proc.stdout is not None
        fd = self._proc.stdout.fileno()
        deadline = time.monotonic() + timeout
        while b"\n" not in self._buf:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RWorkerError("R did not answer in time")
            ready, _, _ = select.select([fd], [], [], min(left, 1.0))
            if ready:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    raise RWorkerError("R process ended unexpectedly")
                self._buf += chunk
            elif self._proc.poll() is not None:
                raise RWorkerError("R process ended unexpectedly")
        line, _, self._buf = self._buf.partition(b"\n")
        return line

    def _start(self) -> None:
        self.stop()
        self._proc = subprocess.Popen([self.rscript, "--vanilla", "-e", LOOP_R], cwd=self.dir, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._buf, self._calls = b"", 0
        while True:  # wait for READY, ignoring anything R prints while loading packages
            line = self._read_line(self.start_timeout)
            if line.startswith(SENTINEL + b"READY"):
                return

    def stop(self) -> None:
        p, self._proc = self._proc, None
        if p is not None and p.poll() is None:
            p.kill()
            p.wait(timeout=5)

    def warm(self) -> None:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()

    # ---- calls ----
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps(payload).encode() + b"\n"
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._proc is None or self._proc.poll() is not None or self._calls >= self.recycle_after:
                        self._start()
                    assert self._proc is not None and self._proc.stdin is not None
                    self._proc.stdin.write(request)
                    self._proc.stdin.flush()
                    while True:
                        line = self._read_line(self.call_timeout)
                        if line.startswith(SENTINEL):
                            break
                    self._calls += 1
                    out: dict[str, Any] = json.loads(line[len(SENTINEL):])
                    return out
                except (RWorkerError, BrokenPipeError, ValueError) as e:
                    self.stop()  # a worker in an unknown state is discarded, never reused
                    if attempt == 2:
                        raise RWorkerError(f"R worker failed: {e}") from e
        raise RWorkerError("unreachable")
