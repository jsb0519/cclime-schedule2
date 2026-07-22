from bz_sync.sync import summarize, _months


def test_summarize_failures():
    msg = summarize({"01. 신사본점": "ok", "04. 삼성점": "fail:Timeout"})
    assert "1/2 실패" in msg and "04. 삼성점" in msg


def test_summarize_all_ok():
    assert "전체 성공" in summarize({"01. 신사본점": "ok"})


def test_months_rollover():
    assert _months("2026-12-15T00:00:00+09:00") == [(2026, 12), (2027, 1)]
    assert _months("2026-07-01T00:00:00+09:00") == [(2026, 7), (2026, 8)]
