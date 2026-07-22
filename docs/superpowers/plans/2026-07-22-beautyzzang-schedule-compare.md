# 뷰티짱 휴무 ↔ 근무표 대조 Implementation Plan (JSON API 확정판)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 맥미니에서 매일 뷰티짱 예약현황판 JSON API로 지점별 휴무를 받아 Firebase에 올리고, 근무표 앱이 지점 근무표 아래에 동일 양식의 뷰티짱 휴무 그리드를 붙여 불일치를 하이라이트한다.

**Architecture:** Task 1 정찰로 데이터 소스가 **JSON API로 확정**됨(HTML 파싱 불필요). 맥미니의 Python+Playwright 봇이 로그인→지점별 2개 AJAX POST(BanList=휴무, ReservationList=담당자명)→집계→Firebase `/beautyzzang/YYYY_MM/{지점}` write. 근무표 정적 앱이 이를 read해 `buildTable()` 직후 비교 그리드를 렌더. 기존 `/schedule`·`/overflow`는 불변.

**Tech Stack:** Python 3.11+, Playwright(Python, `context.request.post`), pytest, requests(Firebase REST), 바닐라 JS(index.html), launchd.

## Global Constraints

- 뷰티짱 자격증명은 `bz_sync/credentials.json`(gitignored)에만. repo·로그·출력 노출 금지 — 성공/실패만 로깅.
- 기존 Firebase 노드 `/schedule/**`, `/overflow/**`는 **절대 write 금지**. 신규 `/beautyzzang/**`만.
- Firebase base: `https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app`
- 지점 키 표기 = 근무표와 동일(`01. 신사본점` … `20. 성수점`). 근무표키→oidStore 맵은 `bz_sync/branch_stores.json`(실측 완료).
- 날짜는 `YYYY-MM-DD` 문자열로 일관.
- 휴무 판정: BanList 항목 중 `n1DayHoliday === 1`(종일)만. 부분금지(0)는 1차 제외.
- 데이터 소스(실측 확정, `bz_sync/RECON.md` 참조):
  - 휴무: `POST /CRM.reservation/StatusBoardV2-AjaxReservationBanList`, body `seloidStore={oid}&strDateS={YYYY-MM-DD}&strDateE={YYYY-MM-DD}&viewStaff=ALL`
  - 담당자명: `POST /CRM.reservation/StatusBoardV2-AjaxReservationList`, 같은 body, 응답에 `oidStaff`+`strStaffName`

---

## File Structure
- `bz_sync/banparse.py` — BanList/ReservationList JSON → 집계(순수 함수)
- `bz_sync/names.py` — 시스템계정 필터 + oidStaff→근무표명 해석
- `bz_sync/fb.py` — Firebase `/beautyzzang` write
- `bz_sync/scrape.py` — Playwright 로그인 + 지점별 2개 AJAX POST
- `bz_sync/sync.py` — 오케스트레이터 + launchd
- `bz_sync/config.example.json` — 시스템계정·이름매핑·알림설정 예시
- `bz_sync/branch_stores.json` — 근무표키→oidStore (Task1 산출, 완료)
- `bz_sync/requirements.txt`
- `bz_sync/tests/` — 픽스처(Task1 산출) + 테스트
- `index.html` — `buildBeautyzzangTable()` + `buildTable()` 말미 호출

## 상태
- **Task 1 (정찰): 완료** — `bz_sync/RECON.md`, `branch_stores.json`, 픽스처 2종(`banlist_sinsa_2026_07.json`, `reservationlist_staffnames_sinsa.json`) 커밋됨.

---

## Task 2: JSON 파서 (`banparse.py`)

**Files:**
- Create: `bz_sync/banparse.py`, `bz_sync/tests/test_banparse.py`, `bz_sync/requirements.txt`

**Interfaces (Produces):**
- `parse_offdays(ban: list[dict]) -> dict[int, list[str]]` — `{oidStaff: [YYYY-MM-DD 정렬·중복제거]}`, `n1DayHoliday==1`만.
- `parse_staff_names(rv: list[dict]) -> dict[int, str]` — `{oidStaff: strStaffName}` (마지막 값 우선, 공백 제외).

- [ ] **Step 1: requirements.txt**
```
playwright==1.48.0
pytest==8.3.3
requests==2.32.3
```

- [ ] **Step 2: 실패 테스트** — `bz_sync/tests/test_banparse.py`:
```python
import json
from pathlib import Path
from bz_sync.banparse import parse_offdays, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_offdays_fullday_only():
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    off = parse_offdays(ban)
    assert off[847079] == ["2026-07-01", "2026-07-06"]      # 종일 휴무 2건
    assert off[857465] == ["2026-07-04", "2026-07-05"]
    assert 860807 not in off                                 # n1DayHoliday=0(부분) → 제외

def test_parse_offdays_dedup_sorted():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
    ]
    assert parse_offdays(ban) == {1: ["2026-07-02", "2026-07-05"]}

def test_parse_staff_names():
    rv = json.loads((FIX / "reservationlist_staffnames_sinsa.json").read_text(encoding="utf-8"))
    names = parse_staff_names(rv)
    assert names[847079] == "김효은"
    assert names[857465] == "박세영"
    assert names[564937] == "대기"
```

- [ ] **Step 3: 실패 확인** — Run `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_banparse.py -v` → FAIL(ModuleNotFound).

- [ ] **Step 4: 구현** — `bz_sync/banparse.py`:
```python
"""뷰티짱 StatusBoardV2 JSON → 집계. 네트워크 의존 없음."""


def parse_offdays(ban: list[dict]) -> dict[int, list[str]]:
    """BanList JSON → {oidStaff: [YYYY-MM-DD]}. 종일 휴무(n1DayHoliday==1)만."""
    acc: dict[int, set[str]] = {}
    for row in ban:
        if row.get("n1DayHoliday") != 1:
            continue
        oid = row.get("oidStaff")
        date = row.get("strDate")
        if oid is None or not date:
            continue
        acc.setdefault(int(oid), set()).add(date[:10])
    return {oid: sorted(dates) for oid, dates in acc.items()}


def parse_staff_names(rv: list[dict]) -> dict[int, str]:
    """ReservationList JSON → {oidStaff: strStaffName}."""
    names: dict[int, str] = {}
    for row in rv:
        oid = row.get("oidStaff")
        name = (row.get("strStaffName") or "").strip()
        if oid is None or not name:
            continue
        names[int(oid)] = name
    return names
```

- [ ] **Step 5: 통과 확인** — Run 위 pytest → PASS(3 passed).

- [ ] **Step 6: Commit**
```bash
git add bz_sync/banparse.py bz_sync/tests/test_banparse.py bz_sync/requirements.txt
git commit -m "파서: BanList/ReservationList JSON 집계 + 테스트"
```

---

## Task 3: 이름 해석 (`names.py`)

**Files:** Create `bz_sync/names.py`, `bz_sync/tests/test_names.py`, `bz_sync/config.example.json`

**Interfaces:**
- Consumes: Task2의 `off_by_oid`(`{oidStaff:[dates]}`), `oid_to_name`(`{oidStaff:name}`).
- Produces: `resolve(off_by_oid, oid_to_name, system_accounts, name_map) -> dict[str, list[str]]`
  - oid→이름 치환. 이름 미상 oid는 `"oid:{n}"`로. 시스템계정·`name_map`값이 빈문자열이면 제외. `name_map`으로 근무표명 치환.

- [ ] **Step 1: config 예시** — `bz_sync/config.example.json`:
```json
{
  "firebase_base": "https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app",
  "credentials_path": "bz_sync/credentials.json",
  "branch_stores_path": "bz_sync/branch_stores.json",
  "alert": { "type": "none" },
  "system_accounts": ["대기","대기2","당일취소","전일취소","업무","지원","네이버(신규)","네이버(기존)","결제변경","소멸","매장","환불","워크인","유료","무료"],
  "name_map": {}
}
```

- [ ] **Step 2: 실패 테스트** — `bz_sync/tests/test_names.py`:
```python
from bz_sync.names import resolve

SYS = ["대기", "지원", "당일취소"]

def test_maps_oid_to_name_and_filters_system():
    off = {847079: ["2026-07-01"], 564937: ["2026-07-02"], 860807: ["2026-07-03"]}
    oid2name = {847079: "김효은", 564937: "대기", 860807: "지원"}
    assert resolve(off, oid2name, SYS, {}) == {"김효은": ["2026-07-01"]}

def test_unknown_oid_becomes_placeholder():
    off = {999999: ["2026-07-01"]}
    assert resolve(off, {}, SYS, {}) == {"oid:999999": ["2026-07-01"]}

def test_name_map_rename_and_exclude():
    off = {1: ["2026-07-01"], 2: ["2026-07-02"]}
    oid2name = {1: "김효은(신사)", 2: "제외대상"}
    out = resolve(off, oid2name, SYS, {"김효은(신사)": "김효은", "제외대상": ""})
    assert out == {"김효은": ["2026-07-01"]}
```

- [ ] **Step 3: 실패 확인** — Run `python -m pytest bz_sync/tests/test_names.py -v` → FAIL.

- [ ] **Step 4: 구현** — `bz_sync/names.py`:
```python
"""oidStaff → 근무표 이름 해석: 이름 치환 + 시스템계정/제외 필터."""


def resolve(off_by_oid: dict[int, list[str]], oid_to_name: dict[int, str],
            system_accounts: list[str], name_map: dict[str, str]) -> dict[str, list[str]]:
    sys_set = set(system_accounts)
    out: dict[str, list[str]] = {}
    for oid, dates in off_by_oid.items():
        name = oid_to_name.get(oid) or f"oid:{oid}"
        if name in sys_set:
            continue
        mapped = name_map.get(name, name)
        if mapped == "":
            continue
        out[mapped] = dates
    return out
```

- [ ] **Step 5: 통과 확인** — pytest → PASS(3 passed).

- [ ] **Step 6: Commit**
```bash
git add bz_sync/names.py bz_sync/tests/test_names.py bz_sync/config.example.json
git commit -m "이름 해석: oidStaff→근무표명 + 시스템계정 필터 + 테스트"
```

---

## Task 4: Firebase writer (`fb.py`)

**Files:** Create `bz_sync/fb.py`, `bz_sync/tests/test_fb.py`

**Interfaces:**
- `build_payload(off_by_name: dict[str,list[str]], synced_at: str) -> dict` → `{name:[dates], "_syncedAt":synced_at}`
- `write_branch(base, year:int, month:int, branch:str, payload:dict, put=requests.put) -> int` → PUT `/beautyzzang/{YYYY_MM}/{branch}.json`, status 반환. branch에 `/`·`..` 있으면 ValueError.

- [ ] **Step 1: 실패 테스트** — `bz_sync/tests/test_fb.py`:
```python
import pytest
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
    assert calls["url"] == "https://db.example/beautyzzang/2026_07/01. 신사본점.json"

def test_write_branch_rejects_namespace_escape():
    with pytest.raises(ValueError):
        write_branch("https://db.example", 2026, 7, "../schedule/2026_07/x", {}, put=lambda **k: None)
```

- [ ] **Step 2: 실패 확인** — Run `python -m pytest bz_sync/tests/test_fb.py -v` → FAIL.

- [ ] **Step 3: 구현** — `bz_sync/fb.py`:
```python
"""Firebase RTDB /beautyzzang 네임스페이스 write (공개 write)."""
import requests


def build_payload(off_by_name: dict[str, list[str]], synced_at: str) -> dict:
    payload: dict = dict(off_by_name)
    payload["_syncedAt"] = synced_at
    return payload


def write_branch(base: str, year: int, month: int, branch: str, payload: dict, put=requests.put) -> int:
    if "/" in branch or ".." in branch:
        raise ValueError(f"invalid branch key: {branch!r}")
    url = f"{base}/beautyzzang/{year:04d}_{month:02d}/{branch}.json"
    return put(url, json=payload, timeout=20).status_code
```

- [ ] **Step 4: 통과 확인** — pytest → PASS(3 passed).

- [ ] **Step 5: Commit**
```bash
git add bz_sync/fb.py bz_sync/tests/test_fb.py
git commit -m "Firebase writer: /beautyzzang PUT + 네임스페이스 가드 + 테스트"
```

---

## Task 5: 스크레이퍼 (`scrape.py`)

**Files:** Create `bz_sync/scrape.py`; Modify 루트 `.gitignore`(`bz_sync/credentials.json` — 이미 추가됨, 없으면 추가).

**Interfaces:**
- `login(page, creds: dict) -> None` — 폼 제출로 세션 확보.
- `fetch_branch(page, oid_store: str, year: int, month: int) -> tuple[list, list]` — `(ban_json, rv_json)`. Playwright `page.context.request.post`로 두 엔드포인트 호출(세션 쿠키 자동).

라이브 의존이라 단위테스트 대신 라이브 스모크로 검증. JSON→집계는 이미 Task2에서 검증됨.

- [ ] **Step 1: 구현** — `bz_sync/scrape.py`:
```python
"""뷰티짱 로그인 + 지점별 휴무/담당자 JSON 수집 (Playwright request API, HTML 파싱 없음)."""

LOGIN_URL = "https://hasys.hairzzang.com/"
BASE = "https://hasys.hairzzang.com"
BAN_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationBanList"
RV_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationList"


def login(page, creds: dict) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill("#strShopCode", creds["shop_code"])
    page.fill("#strId", creds["user_id"])
    page.fill("#strPass", creds["password"])
    page.eval_on_selector("#btnSubmit", "el => el.click()")
    page.wait_for_timeout(4000)  # 세션 쿠키 확립


def _last_day(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def fetch_branch(page, oid_store: str, year: int, month: int) -> tuple[list, list]:
    body = {
        "seloidStore": str(oid_store),
        "strDateS": f"{year:04d}-{month:02d}-01",
        "strDateE": f"{year:04d}-{month:02d}-{_last_day(year, month):02d}",
        "viewStaff": "ALL",
    }
    req = page.context.request
    ban = req.post(BAN_URL, form=body).json()
    rv = req.post(RV_URL, form=body).json()
    return ban, rv
```

- [ ] **Step 2: 라이브 스모크(맥미니, 신사점)**
```bash
cd ~/github/cclime-schedule2 && python -c "
import json
from playwright.sync_api import sync_playwright
from bz_sync.scrape import login, fetch_branch
from bz_sync.banparse import parse_offdays, parse_staff_names
from bz_sync.names import resolve
creds = json.load(open('bz_sync/credentials.json'))
cfg = json.load(open('bz_sync/config.json'))
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); login(pg, creds)
    ban, rv = fetch_branch(pg, '301477', 2026, 7)
    off = resolve(parse_offdays(ban), parse_staff_names(rv), cfg['system_accounts'], cfg['name_map'])
    print('신사 휴무 직원수:', len(off), '| 예:', list(off.items())[:2])
    b.close()
"
```
Expected: 예외 없이 직원수>0 + 이름별 휴무일 리스트 출력.

- [ ] **Step 3: Commit**
```bash
git add bz_sync/scrape.py .gitignore
git commit -m "스크레이퍼: 로그인 + 지점별 휴무/담당자 JSON POST 수집"
```

---

## Task 6: 오케스트레이터 + launchd (`sync.py`)

**Files:** Create `bz_sync/sync.py`, `bz_sync/com.cclime.bzsync.plist`

**Interfaces:** `summarize(results: dict[str,str]) -> str`; `run(config, creds, now_iso) -> dict[str,str]`.
당월+익월, 지점 순회, 부분성공(실패지점 write 스킵→이전값 유지), 실패 시 알림.

- [ ] **Step 1: 실패 테스트** — `bz_sync/tests/test_sync.py`:
```python
from bz_sync.sync import summarize

def test_summarize_failures():
    msg = summarize({"01. 신사본점": "ok", "04. 삼성점": "fail:Timeout"})
    assert "1/2 실패" in msg and "04. 삼성점" in msg

def test_summarize_all_ok():
    assert "전체 성공" in summarize({"01. 신사본점": "ok"})
```

- [ ] **Step 2: 실패 확인** — Run `python -m pytest bz_sync/tests/test_sync.py -v` → FAIL.

- [ ] **Step 3: 구현** — `bz_sync/sync.py`:
```python
"""오케스트레이터: 지점 순회 → JSON 수집 → 집계 → Firebase write. 부분성공·실패알림."""
import json
import sys
from playwright.sync_api import sync_playwright

from bz_sync.scrape import login, fetch_branch
from bz_sync.banparse import parse_offdays, parse_staff_names
from bz_sync.names import resolve
from bz_sync.fb import build_payload, write_branch


def summarize(results: dict[str, str]) -> str:
    fails = {b: r for b, r in results.items() if r != "ok"}
    if not fails:
        return f"뷰티짱 동기화 전체 성공 ({len(results)}지점)"
    lines = "\n".join(f"{b}: {r}" for b, r in fails.items())
    return f"뷰티짱 동기화 {len(fails)}/{len(results)} 실패\n{lines}"


def _months(now_iso: str) -> list[tuple[int, int]]:
    y, m = int(now_iso[:4]), int(now_iso[5:7])
    return [(y, m), (y + 1, 1) if m == 12 else (y, m + 1)]


def run(config: dict, creds: dict, now_iso: str) -> dict:
    base = config["firebase_base"]
    stores = json.load(open(config["branch_stores_path"], encoding="utf-8"))
    results: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        login(page, creds)
        for branch, oid in stores.items():
            if branch.startswith("_"):
                continue
            try:
                for (y, m) in _months(now_iso):
                    ban, rv = fetch_branch(page, oid, y, m)
                    off = resolve(parse_offdays(ban), parse_staff_names(rv),
                                  config["system_accounts"], config["name_map"])
                    status = write_branch(base, y, m, branch, build_payload(off, now_iso))
                    if status >= 400:
                        raise RuntimeError(f"firebase {status}")
                results[branch] = "ok"
            except Exception as e:
                results[branch] = f"fail:{type(e).__name__}"
        browser.close()
    return results


def alert(config: dict, message: str) -> None:
    a = config.get("alert", {"type": "none"})
    if a.get("type") == "slack":
        import requests
        requests.post(a["webhook_url"], json={"text": message}, timeout=15)
    # 'none'/'nova'는 stdout 로깅으로 갈음


if __name__ == "__main__":
    import datetime
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "bz_sync/config.json", encoding="utf-8"))
    creds = json.load(open(cfg["credentials_path"], encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    res = run(cfg, creds, now)
    msg = summarize(res)
    print(msg)
    if any(r != "ok" for r in res.values()):
        alert(cfg, msg)
```

- [ ] **Step 4: 통과 확인** — pytest → PASS(2 passed).

- [ ] **Step 5: launchd plist** — `bz_sync/com.cclime.bzsync.plist`(`<HOME>`는 맥미니 실경로로 치환, `~/Library/LaunchAgents/`에 설치):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cclime.bzsync</string>
  <key>WorkingDirectory</key><string><HOME>/github/cclime-schedule2</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/env</string><string>python3</string><string>-m</string><string>bz_sync.sync</string><string>bz_sync/config.json</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/bzsync.log</string>
  <key>StandardErrorPath</key><string>/tmp/bzsync.err</string>
</dict>
</plist>
```
설치: `cp bz_sync/com.cclime.bzsync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.cclime.bzsync.plist`

- [ ] **Step 6: 전체 봇 라이브 스모크(맥미니)** — Run `python -m bz_sync.sync bz_sync/config.json` → "전체 성공"/실패목록. `GET .../beautyzzang/2026_07/01. 신사본점.json`으로 확인.

- [ ] **Step 7: Commit**
```bash
git add bz_sync/sync.py bz_sync/tests/test_sync.py bz_sync/com.cclime.bzsync.plist
git commit -m "오케스트레이터: 지점순회 동기화 + 부분성공 + 실패알림 + launchd"
```

---

## Task 7: 프론트엔드 비교 그리드 (`index.html`)

**Files:** Modify `index.html`(`#sch-table` 블록 근처 line 259, `buildTable()` line 2449~).

**Interfaces:** Firebase `GET {FB_BASE}/beautyzzang/{YYYY_MM}/{branch}.json` → `{name:[YYYY-MM-DD], _syncedAt}`. 기존 전역 `curY,curM,FB_BASE,mergedBranch,#branch-sel` 사용. Produces `#bz-table` 렌더 + 불일치 하이라이트.

- [ ] **Step 1: 컨테이너 추가** — `#sch-table`(`<table id="sch-table">`, line 259) 블록 바로 뒤:
```html
<div id="bz-wrap" style="margin-top:18px;display:none">
  <div id="bz-summary" style="font-size:13px;margin:6px 0;color:#555"></div>
  <table id="bz-table"><thead id="bz-head"></thead><tbody id="bz-body"></tbody></table>
</div>
```

- [ ] **Step 2: 렌더 함수** — `buildTable()` 정의 앞에 추가:
```javascript
async function buildBeautyzzangTable(branch, schOffMap) {
  // schOffMap: {직원명: Set('YYYY-MM-DD')} — 근무표 휴무(비교 기준)
  const wrap = document.getElementById('bz-wrap');
  if (!branch) { wrap.style.display = 'none'; return; }
  const ym = curY + '_' + String(curM).padStart(2, '0');
  let data = null;
  try { data = await (await fetch(`${FB_BASE}/beautyzzang/${ym}/${encodeURIComponent(branch)}.json`)).json(); }
  catch (e) { data = null; }
  wrap.style.display = '';
  const summary = document.getElementById('bz-summary');
  if (!data) {
    summary.textContent = '⚠️ 뷰티짱 동기화 데이터 없음';
    document.getElementById('bz-head').innerHTML = '';
    document.getElementById('bz-body').innerHTML = '';
    return;
  }
  const days = new Date(curY, curM, 0).getDate();
  let hd = '<tr><th>직원(뷰티짱 휴무)</th>';
  for (let d = 1; d <= days; d++) hd += `<th>${d}</th>`;
  document.getElementById('bz-head').innerHTML = hd + '</tr>';
  let mism = 0, body = '';
  for (const name of Object.keys(data)) {
    if (name === '_syncedAt') continue;
    const bzOff = new Set(data[name]);
    const schOff = schOffMap[name] || null;   // 근무표에 없으면 미매칭
    body += `<tr><td>${name}${schOff ? '' : ' <span style="color:#999">(미매칭)</span>'}</td>`;
    for (let d = 1; d <= days; d++) {
      const key = `${curY}-${String(curM).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const inBz = bzOff.has(key), inSch = schOff ? schOff.has(key) : null;
      let cls = '', mark = inBz ? '휴' : '';
      if (schOff) {
        if (inBz && !inSch) { cls = 'bz-mismatch-red'; mism++; }
        else if (!inBz && inSch) { cls = 'bz-mismatch-orange'; mism++; mark = '·'; }
        else if (inBz && inSch) { cls = 'bz-match'; }
      }
      body += `<td class="${cls}">${mark}</td>`;
    }
    body += '</tr>';
  }
  document.getElementById('bz-body').innerHTML = body;
  summary.innerHTML = `뷰티짱 대조: <b style="color:${mism?'#c00':'#080'}">${mism}건 불일치</b> · 마지막 동기화 ${data._syncedAt || '?'}`;
}
```

- [ ] **Step 3: CSS** — `<style>`에 추가:
```css
#bz-table th, #bz-table td { border:1px solid #ddd; text-align:center; font-size:11px; padding:2px 4px; }
.bz-match { background:#e8f5e9; }
.bz-mismatch-red { background:#ffcdd2; font-weight:700; }
.bz-mismatch-orange { background:#ffe0b2; font-weight:700; }
```

- [ ] **Step 4: `buildTable()` 말미 호출** — `buildTable()` 상단에 `const _schOffMap = {};` 선언, emps 렌더 루프에서 각 직원의 상태가 '휴무'/'휴직'인 날짜를 `(_schOffMap[emp.name] ||= new Set()).add('YYYY-MM-DD')`로 수집(기존 셀 상태값 재사용), 함수 마지막 `return` 직전:
```javascript
  buildBeautyzzangTable(branch, _schOffMap);
```

- [ ] **Step 5: 로컬 렌더 확인** — Run `cd ~/github/cclime-schedule2 && python3 -m http.server 8765` → `http://localhost:8765/` 지점(신사본점) 선택 → 근무표 아래 뷰티짱 그리드·불일치 색상·동기화 시각 확인(Task6 데이터 선행).

- [ ] **Step 6: Commit**
```bash
git add index.html
git commit -m "근무표 앱: 뷰티짱 휴무 비교 그리드 + 불일치 하이라이트"
```

---

## Self-Review
- 데이터 소스 JSON 확정 반영(BeautifulSoup·HTML 파서 제거). Task2 = JSON 집계, Task5 = 2 POST.
- 타입 일관: `parse_offdays→{oid:[date]}` + `parse_staff_names→{oid:name}` → `resolve→{name:[date]}` → `build_payload` → `write_branch` → 프론트 `{name:[date]}` 소비. 일관.
- 시스템계정/미매칭/부분금지(n1DayHoliday=0) 처리 명시. 기존 /schedule 불변, creds 로컬.
- 미세 잔여(경미): 근무표 이름 표기와 strStaffName 표기 차이 시 `name_map` 보강(운영 중 조정).
