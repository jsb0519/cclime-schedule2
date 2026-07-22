from bz_sync.sync import summarize


def test_summarize_failures():
    msg = summarize({"01. 신사본점": "ok", "04. 삼성점": "fail:Timeout"})
    assert "1/2 실패" in msg and "04. 삼성점" in msg


def test_summarize_all_ok():
    assert "전체 성공" in summarize({"01. 신사본점": "ok"})
