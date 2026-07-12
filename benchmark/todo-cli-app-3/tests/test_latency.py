"""Quality bar: cold end-to-end `todo` subprocess < 1s with a 500-item store."""

from __future__ import annotations

import time

from conftest import populate, run


def test_glance_latency_under_1s_with_500_items(home):
    populate(home, [{"title": f"할일 {i}", "seq": i} for i in range(1, 501)])
    start = time.monotonic()
    result = run(home)
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 1.0, f"took {elapsed:.3f}s"
