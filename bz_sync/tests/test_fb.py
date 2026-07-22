from bz_sync.fb import build_payload, write_branch

def test_build_payload_passthrough_dates():
    p = build_payload({"김효은": ["2026-07-01", "2026-07-06"]}, "2026-07-22T03:00:00+09:00")
    assert p["김효은"] == ["2026-07-01", "2026-07-06"]
    assert p["_syncedAt"] == "2026-07-22T03:00:00+09:00"

def test_write_branch_url_and_body():
    calls = {}
    class R: status_code = 200
    def fake_put(url, json, timeout):
        calls["url"] = url; calls["json"] = json; return R()
    st = write_branch("https://db.example", 2026, 7, "01. 신사본점", {"김효은": ["2026-07-01"]}, put=fake_put)
    assert st == 200
    # 금지문자 '.'은 '_'로 치환된다(프론트 fbBranchKey와 동일): "01. 신사본점" → "01_ 신사본점".
    assert calls["url"] == "https://db.example/beautyzzang/2026_07/01_ 신사본점.json"

def test_write_branch_sanitizes_namespace_escape():
    # '/'·'.'이 모두 '_'로 치환되어 /beautyzzang/YYYY_MM/ 아래를 벗어날 수 없다.
    calls = {}
    class R: status_code = 200
    def fake_put(url, json, timeout):
        calls["url"] = url; return R()
    write_branch("https://db.example", 2026, 7, "../schedule/2026_07/x", {}, put=fake_put)
    assert calls["url"].startswith("https://db.example/beautyzzang/2026_07/")
    tail = calls["url"].split("/beautyzzang/2026_07/", 1)[1]
    assert "/" not in tail.replace(".json", "") and "." not in tail.replace(".json", "")
