"""_post_json 재시도/빈응답 처리 단위테스트 (네트워크 없이 가짜 req로)."""
import json as _json
from bz_sync.scrape import _post_json


class _Resp:
    def __init__(self, text):
        self._text = text
    def text(self):
        return self._text
    def json(self):
        return _json.loads(self._text)


class _Req:
    """미리 준비한 응답들을 순서대로 반환하는 가짜 request context."""
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = 0
    def post(self, url, form=None, timeout=None):
        self.calls += 1
        return _Resp(self._texts.pop(0))


def test_valid_json_first_try():
    req = _Req(['[{"a":1}]'])
    assert _post_json(req, "u", {}) == [{"a": 1}]
    assert req.calls == 1


def test_all_empty_means_no_data():
    # 서버가 '데이터 없음'일 때 주는 빈 문자열 → 재시도 후 [] (오류 아님)
    req = _Req(["", "", ""])
    assert _post_json(req, "u", {}, retries=3) == []
    assert req.calls == 3


def test_empty_then_valid_retries():
    req = _Req(["", '[{"b":2}]'])
    assert _post_json(req, "u", {}, retries=3) == [{"b": 2}]
    assert req.calls == 2


def test_persistent_invalid_json_is_error():
    # HTML 에러페이지 등 비정상 응답이 계속되면 None(진짜 오류)
    req = _Req(["<html>err</html>", "<html>err</html>", "<html>err</html>"])
    assert _post_json(req, "u", {}, retries=3) is None
    assert req.calls == 3
