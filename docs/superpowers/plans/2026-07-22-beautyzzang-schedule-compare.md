# 뷰티짱 휴무 ↔ 근무표 대조 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 맥미니에서 매일 뷰티짱 휴무를 스크레이프해 Firebase에 올리고, 근무표 앱이 지점별 근무표 아래에 동일 양식의 뷰티짱 휴무 그리드를 붙여 불일치를 하이라이트한다.

**Architecture:** 맥미니의 Python+Playwright 봇이 뷰티짱에 로그인→지점별 월간 휴무 표 파싱→Firebase `/beautyzzang/YYYY_MM/{지점}`에 write. 근무표 정적 앱(`index.html`)이 이 노드를 read해 `buildTable()` 직후 비교 그리드를 렌더. 기존 `/schedule`·`/overflow`는 건드리지 않는다(읽기 전용 대조).

**Tech Stack:** Python 3.11+, Playwright(Python), pytest, BeautifulSoup4(HTML 파싱), Firebase Realtime DB REST(공개 write), 바닐라 JS(`index.html`), launchd(맥미니 스케줄).

## Global Constraints

- 뷰티짱 자격증명은 `bz_sync/credentials.json`(gitignored)에만. repo·로그·출력에 값 노출 금지 — 성공/실패만 로깅.
- 기존 Firebase 노드 `/schedule/**`, `/overflow/**`는 **절대 write 금지**. 신규 네임스페이스 `/beautyzzang/**`만 사용.
- Firebase base: `https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app`
- 지점 키 표기는 근무표와 동일: `01. 신사본점` … `20. 성수점` (앞의 2자리 번호+점명).
- 날짜 표기: 내부 파서는 `day:int`, 저장·비교는 `YYYY-MM-DD` 문자열.
- 스크레이핑은 프레임셋 통째 로딩 금지(`frame_push` long-poll로 멈춤). 로그인 후 콘텐츠 페이지 직접 접근.
- 봇 파일은 `bz_sync/` 하위에 둔다(기존 repo의 flat .py 관례를 따르되 신규 모듈은 폴더로 격리).

---

## File Structure

- `bz_sync/parse.py` — HTML → `{직원명: [day:int]}` (순수 함수, 네트워크 없음)
- `bz_sync/names.py` — 시스템 계정 필터 + 뷰티짱명→근무표명 매핑
- `bz_sync/fb.py` — Firebase `/beautyzzang` read/write (REST)
- `bz_sync/scrape.py` — Playwright 로그인 + 지점 순회 + 월간 휴무 HTML 수집
- `bz_sync/sync.py` — 오케스트레이터(부분성공·실패알림·CLI)
- `bz_sync/config.example.json` — 지점 목록·이름 매핑·시스템계정 목록(커밋됨, 값은 예시)
- `bz_sync/credentials.example.json` — 자격증명 형식 예시(실파일은 gitignore)
- `bz_sync/requirements.txt`
- `bz_sync/RECON.md` — Task 1 산출(정본 소스·엔드포인트·지점전환 문서)
- `bz_sync/tests/fixtures/*.html` — 파서 픽스처
- `bz_sync/tests/test_parse.py`, `test_names.py`, `test_fb.py`
- `bz_sync/com.cclime.bzsync.plist` — launchd 스케줄(맥미니)
- `index.html` — `buildBeautyzzangTable()` 추가 + `buildTable()` 말미에서 호출
- `.gitignore` — `bz_sync/credentials.json` 추가

---

## Task 1: 정찰 스파이크 — 정본 소스·엔드포인트·지점전환 확정 (맥미니)

목적: 열린 항목(정본 휴무 화면, 지점 전환 방식, 실제 HTML 구조)을 실데이터로 확정하고
파서 픽스처를 확보한다. 이 태스크만 뷰티짱 실접속이 필요하며, 이후 태스크는 픽스처로 진행.

**Files:**
- Create: `bz_sync/RECON.md`
- Create: `bz_sync/tests/fixtures/offdays_sinsa_current.html` (신사점 당월 휴무 표 원본 HTML)
- Create: `bz_sync/credentials.example.json`

**Interfaces:**
- Produces: 확정된 "월간 휴무 표" HTML 구조 문서 + 신사점 픽스처 1개. 이후 파서(Task 2)가 이 구조를 파싱.

- [ ] **Step 1: credentials 예시 파일 작성**

`bz_sync/credentials.example.json`:
```json
{ "shop_code": "n0500a001", "user_id": "4868", "password": "<여기에-실비밀번호>" }
```
실제 값이 담긴 `bz_sync/credentials.json`은 맥미니에만 두고 절대 커밋하지 않는다.

- [ ] **Step 2: 정찰 스크립트로 세 후보 화면을 열어 구조 확인**

Playwright(Python)로 로그인 후, 프레임셋을 피해 콘텐츠 페이지를 직접 로드하고 각 후보의
"직원별·날짜별 휴무" 표현 여부를 확인한다. 후보 우선순위:
1. 근태입력 `/staff/diligence/default.aspx?page=Diligence` (직원×날짜 그리드 가능성 — 최우선)
2. 휴무캘린더 `POST /CRM.Regist/Reservation-HolidayCalendar` (날짜셀에 직원명 여부 확인)
3. 예약현황판 `/CRM.Reservation/StatusBoardV2` (당일 단위 — 날짜 순회 필요, 백업)

확인 사항: (a) 어느 화면이 한 번 요청으로 지점의 월간·직원별·날짜별 휴무를 주는가,
(b) 지점 전환이 어떤 요청/파라미터로 이뤄지는가(우상단 지점 선택의 실제 동작),
(c) 표의 DOM 구조(직원명 셀, 날짜 열/셀, 휴무 마커).

- [ ] **Step 3: 신사점 당월 휴무 표 HTML을 픽스처로 저장**

확정한 정본 화면의 표 컨테이너 outerHTML을 `bz_sync/tests/fixtures/offdays_sinsa_current.html`로 저장.
(실직원명이 담기므로 이 픽스처는 로컬 개발용. repo 커밋 시 이름 일부를 익명화해도 무방 — 구조만 유지.)

- [ ] **Step 4: RECON.md에 확정 내용 문서화**

`bz_sync/RECON.md`에 기록: 정본 화면 URL/HTTP 메서드/필요 파라미터, 지점 전환 절차,
표 DOM 구조(선택자), 직원명·휴무 마커 예시, 발견한 시스템 계정 이름들(예: 결제변경·워크인·소멸·당일취소).

- [ ] **Step 5: Commit**

```bash
cd ~/github/cclime-schedule2
git add bz_sync/RECON.md bz_sync/credentials.example.json bz_sync/tests/fixtures/offdays_sinsa_current.html
git commit -m "정찰: 뷰티짱 정본 휴무 소스·지점전환·HTML구조 확정 + 신사점 픽스처"
```

> **주의:** 이후 Task 2의 파서 선택자는 이 픽스처의 실제 구조에 맞춘다. 아래 Task 2는 "직원 행 ×
> 날짜 열" 그리드를 가정한 계약/테스트를 제시한다. 정본 화면이 휴무캘린더(날짜셀 안 직원명) 구조로
> 확정되면 파서 내부만 그 구조에 맞게 바꾸고 함수 시그니처·반환형은 유지한다.

---

## Task 2: 휴무 파서 (`parse.py`)

**Files:**
- Create: `bz_sync/parse.py`
- Create: `bz_sync/tests/test_parse.py`
- Create: `bz_sync/tests/fixtures/offdays_grid_sample.html` (테스트용 소형 합성 픽스처)
- Create: `bz_sync/requirements.txt`

**Interfaces:**
- Produces: `parse_month_offdays(html: str) -> dict[str, list[int]]`
  - 입력: 한 지점·한 달의 휴무 표 HTML.
  - 출력: `{직원명(str): [휴무일(int), ...]}`. 휴무 없는 직원은 빈 리스트. 직원명은 원문 그대로(매핑/필터 전).

- [ ] **Step 1: requirements.txt 작성**

`bz_sync/requirements.txt`:
```
playwright==1.48.0
beautifulsoup4==4.12.3
pytest==8.3.3
requests==2.32.3
```

- [ ] **Step 2: 합성 픽스처 작성 (직원 행 × 날짜 열 그리드)**

`bz_sync/tests/fixtures/offdays_grid_sample.html` — 정본 구조를 대표하는 최소 표.
헤더에 날짜(1..5), 각 행 첫 셀은 직원명, 휴무 셀은 `class="off"`(마커는 RECON에서 확인한 실제 클래스/텍스트로 Task 1 후 교체):
```html
<table id="offgrid">
  <thead><tr><th>담당자</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th></tr></thead>
  <tbody>
    <tr><td class="name">홍길동</td><td></td><td class="off">휴</td><td></td><td></td><td class="off">휴</td></tr>
    <tr><td class="name">김영희</td><td></td><td></td><td></td><td></td><td></td></tr>
    <tr><td class="name">결제변경</td><td class="off">휴</td><td></td><td></td><td></td><td></td></tr>
  </tbody>
</table>
```

- [ ] **Step 3: 실패하는 테스트 작성**

`bz_sync/tests/test_parse.py`:
```python
from pathlib import Path
from bz_sync.parse import parse_month_offdays

FIX = Path(__file__).parent / "fixtures"

def test_extracts_offdays_per_staff():
    html = (FIX / "offdays_grid_sample.html").read_text(encoding="utf-8")
    result = parse_month_offdays(html)
    assert result["홍길동"] == [2, 5]
    assert result["김영희"] == []
    assert result["결제변경"] == [1]

def test_all_staff_present_even_without_offdays():
    html = (FIX / "offdays_grid_sample.html").read_text(encoding="utf-8")
    result = parse_month_offdays(html)
    assert set(result.keys()) == {"홍길동", "김영희", "결제변경"}
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bz_sync.parse'`

- [ ] **Step 5: 파서 구현**

`bz_sync/parse.py`:
```python
"""뷰티짱 월간 휴무 표(HTML) → {직원명: [휴무일수(int)]} 파싱. 네트워크 의존 없음."""
from bs4 import BeautifulSoup


def parse_month_offdays(html: str) -> dict[str, list[int]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="offgrid") or soup.find("table")
    if table is None:
        return {}
    result: dict[str, list[int]] = {}
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        name = cells[0].get_text(strip=True)
        if not name:
            continue
        offdays: list[int] = []
        for idx, td in enumerate(cells[1:], start=1):
            if _is_off(td):
                offdays.append(idx)
        result[name] = offdays
    return result


def _is_off(td) -> bool:
    """휴무 셀 판정. Task 1 RECON에서 확인한 실제 마커에 맞춘다."""
    classes = td.get("class") or []
    if "off" in classes:
        return True
    return td.get_text(strip=True) in {"휴", "휴무", "OFF"}
```
날짜 열이 헤더 순서대로 1일부터라는 전제(그리드). RECON에서 열이 실제 날짜값을 담으면
`enumerate` 대신 헤더의 날짜 텍스트를 읽어 매핑하도록 조정한다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_parse.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add bz_sync/parse.py bz_sync/tests/test_parse.py bz_sync/tests/fixtures/offdays_grid_sample.html bz_sync/requirements.txt
git commit -m "파서: 뷰티짱 월간 휴무 표 → {직원: [휴무일]} + 테스트"
```

---

## Task 3: 이름 필터·매핑 (`names.py`)

**Files:**
- Create: `bz_sync/names.py`
- Create: `bz_sync/tests/test_names.py`
- Create: `bz_sync/config.example.json`

**Interfaces:**
- Consumes: Task 2의 `{직원명: [일]}` (원문 이름).
- Produces:
  - `normalize_offdays(raw: dict[str, list[int]], system_accounts: list[str], name_map: dict[str, str]) -> dict[str, list[int]]`
  - 시스템 계정 제거 + 뷰티짱명→근무표명 치환. 매핑에 없으면 원문 유지.

- [ ] **Step 1: config 예시 작성**

`bz_sync/config.example.json`:
```json
{
  "firebase_base": "https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app",
  "credentials_path": "bz_sync/credentials.json",
  "alert": { "type": "none" },
  "branches": ["01. 신사본점", "04. 삼성점"],
  "system_accounts": ["결제변경", "소멸", "매장", "환불", "워크인", "전일취소", "당일취소", "대기", "유료"],
  "name_map": { "끌리메cs_01": "" }
}
```
`name_map`에서 빈 문자열 값은 "제외"로 취급(시스템 계정과 동일).

- [ ] **Step 2: 실패하는 테스트 작성**

`bz_sync/tests/test_names.py`:
```python
from bz_sync.names import normalize_offdays

SYS = ["결제변경", "당일취소"]
MAP = {"홍길동(신사)": "홍길동", "제외대상": ""}

def test_removes_system_accounts():
    raw = {"홍길동": [2, 5], "결제변경": [1], "당일취소": []}
    out = normalize_offdays(raw, SYS, {})
    assert out == {"홍길동": [2, 5]}

def test_applies_name_map():
    raw = {"홍길동(신사)": [3], "김영희": []}
    out = normalize_offdays(raw, SYS, MAP)
    assert out == {"홍길동": [3], "김영희": []}

def test_map_to_empty_string_excludes():
    raw = {"제외대상": [1], "김영희": [2]}
    out = normalize_offdays(raw, SYS, MAP)
    assert out == {"김영희": [2]}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_names.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bz_sync.names'`

- [ ] **Step 4: 구현**

`bz_sync/names.py`:
```python
"""뷰티짱 담당자명 정규화: 시스템 계정 제거 + 근무표 이름 매핑."""


def normalize_offdays(
    raw: dict[str, list[int]],
    system_accounts: list[str],
    name_map: dict[str, str],
) -> dict[str, list[int]]:
    sys_set = set(system_accounts)
    out: dict[str, list[int]] = {}
    for name, days in raw.items():
        if name in sys_set:
            continue
        mapped = name_map.get(name, name)
        if mapped == "":  # 명시적 제외
            continue
        out[mapped] = days
    return out
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_names.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add bz_sync/names.py bz_sync/tests/test_names.py bz_sync/config.example.json
git commit -m "이름 정규화: 시스템계정 필터 + 근무표명 매핑 + 테스트"
```

---

## Task 4: Firebase writer (`fb.py`)

**Files:**
- Create: `bz_sync/fb.py`
- Create: `bz_sync/tests/test_fb.py`

**Interfaces:**
- Consumes: Task 3의 정규화된 `{직원명: [일]}`, 지점명, 연·월.
- Produces:
  - `build_payload(offdays: dict[str, list[int]], year: int, month: int, synced_at: str) -> dict`
    → `{직원명: ["YYYY-MM-DD", ...], "_syncedAt": synced_at}`
  - `write_branch(base: str, year: int, month: int, branch: str, payload: dict, put=requests.put) -> int`
    → `/beautyzzang/{YYYY_MM}/{branch}.json`에 PUT, HTTP status 반환. `put`은 테스트 주입용.

- [ ] **Step 1: 실패하는 테스트 작성**

`bz_sync/tests/test_fb.py`:
```python
from bz_sync.fb import build_payload, write_branch

def test_build_payload_converts_days_to_dates():
    p = build_payload({"홍길동": [2, 5], "김영희": []}, 2026, 8, "2026-08-01T01:00:00+09:00")
    assert p["홍길동"] == ["2026-08-02", "2026-08-05"]
    assert p["김영희"] == []
    assert p["_syncedAt"] == "2026-08-01T01:00:00+09:00"

def test_write_branch_puts_to_correct_url():
    calls = {}
    class Resp:  # noqa
        status_code = 200
    def fake_put(url, json, timeout):
        calls["url"] = url; calls["json"] = json
        return Resp()
    status = write_branch("https://db.example", 2026, 8, "01. 신사본점",
                          {"홍길동": ["2026-08-02"]}, put=fake_put)
    assert status == 200
    assert calls["url"] == "https://db.example/beautyzzang/2026_08/01. 신사본점.json"
    assert calls["json"] == {"홍길동": ["2026-08-02"]}

def test_write_branch_refuses_schedule_namespace():
    import pytest
    with pytest.raises(ValueError):
        write_branch("https://db.example", 2026, 8, "../schedule/2026_08/01. 신사본점",
                     {}, put=lambda **k: None)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_fb.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bz_sync.fb'`

- [ ] **Step 3: 구현**

`bz_sync/fb.py`:
```python
"""Firebase RTDB /beautyzzang 네임스페이스 write (공개 write)."""
import requests


def build_payload(offdays: dict[str, list[int]], year: int, month: int, synced_at: str) -> dict:
    payload: dict = {}
    for name, days in offdays.items():
        payload[name] = [f"{year:04d}-{month:02d}-{d:02d}" for d in sorted(days)]
    payload["_syncedAt"] = synced_at
    return payload


def write_branch(base: str, year: int, month: int, branch: str, payload: dict, put=requests.put) -> int:
    if "/" in branch or ".." in branch:  # /schedule 등 다른 네임스페이스 침범 방지
        raise ValueError(f"invalid branch key: {branch!r}")
    url = f"{base}/beautyzzang/{year:04d}_{month:02d}/{branch}.json"
    resp = put(url, json=payload, timeout=20)
    return resp.status_code
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_fb.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bz_sync/fb.py bz_sync/tests/test_fb.py
git commit -m "Firebase writer: /beautyzzang PUT + 네임스페이스 가드 + 테스트"
```

---

## Task 5: 스크레이퍼 (`scrape.py`)

라이브 의존이라 순수 단위테스트는 어렵다. 함수를 "세션 확보 / 지점별 HTML 수집"으로 분리하고,
HTML→데이터 변환은 이미 검증된 Task 2 파서에 위임한다. 검증은 라이브 스모크(수동)로 한다.

**Files:**
- Create: `bz_sync/scrape.py`
- Modify: `.gitignore` (루트) — `bz_sync/credentials.json` 추가

**Interfaces:**
- Consumes: credentials dict, 지점 목록, 연·월. 그리고 Task 1 RECON.md의 정본 화면/지점전환 절차.
- Produces:
  - `login(page, creds: dict) -> None` — 폼 제출로 세션 확보.
  - `fetch_branch_offdays_html(page, branch: str, year: int, month: int) -> str` — 지점 전환 후 정본 화면의 휴무 표 outerHTML 반환.

- [ ] **Step 1: .gitignore에 credentials 추가**

루트 `.gitignore`에 다음 줄 추가(파일 없으면 생성):
```
bz_sync/credentials.json
```

- [ ] **Step 2: 스크레이퍼 구현 (RECON 절차 반영)**

`bz_sync/scrape.py`:
```python
"""뷰티짱 로그인 + 지점별 월간 휴무 표 HTML 수집 (Playwright). 프레임셋 통째 로딩 회피."""

LOGIN_URL = "https://hasys.hairzzang.com/"


def login(page, creds: dict) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill("#strShopCode", creds["shop_code"])
    page.fill("#strId", creds["user_id"])
    page.fill("#strPass", creds["password"])
    page.eval_on_selector("#btnSubmit", "el => el.click()")
    page.wait_for_timeout(3000)  # 세션 쿠키 확립 대기


def fetch_branch_offdays_html(page, branch: str, year: int, month: int) -> str:
    """지점 전환 → 정본 휴무 화면(콘텐츠 페이지 직접 접근) → 표 outerHTML.
    URL/파라미터/지점전환/표 선택자는 bz_sync/RECON.md 확정값으로 채운다."""
    switch_branch(page, branch)
    url = _offdays_content_url(year, month)  # RECON에서 확정한 콘텐츠 페이지 URL
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#offgrid", timeout=15000)  # RECON 실제 선택자로 교체
    return page.eval_on_selector("#offgrid", "el => el.outerHTML")


def switch_branch(page, branch: str) -> None:
    """우상단 지점 선택으로 세션 컨텍스트 전환. RECON.md 절차로 구현."""
    raise NotImplementedError("Task 1 RECON.md의 지점 전환 절차로 구현")


def _offdays_content_url(year: int, month: int) -> str:
    """RECON에서 확정한 정본 휴무 콘텐츠 페이지 URL(월 파라미터 포함)."""
    raise NotImplementedError("Task 1 RECON.md의 정본 화면 URL로 구현")
```
> `switch_branch`/`_offdays_content_url`은 Task 1 결과가 있어야 실값이 채워진다. RECON.md를
> 열고 확정 URL·선택자·전환 절차로 두 함수의 본문을 완성한다(시그니처는 유지).

- [ ] **Step 3: 라이브 스모크 (수동, 신사점 1개)**

맥미니에서 실행 확인용 인라인 스니펫:
```bash
cd ~/github/cclime-schedule2
python -c "
import json
from playwright.sync_api import sync_playwright
from bz_sync.scrape import login, fetch_branch_offdays_html
from bz_sync.parse import parse_month_offdays
creds = json.load(open('bz_sync/credentials.json'))
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    login(pg, creds)
    html = fetch_branch_offdays_html(pg, '01. 신사본점', 2026, 8)
    print('직원 수:', len(parse_month_offdays(html)))
    b.close()
"
```
Expected: 예외 없이 "직원 수: N"(N>0) 출력. (자격증명 값은 출력하지 않음.)

- [ ] **Step 4: Commit**

```bash
git add bz_sync/scrape.py .gitignore
git commit -m "스크레이퍼: 뷰티짱 로그인 + 지점별 월간 휴무 HTML 수집"
```

---

## Task 6: 오케스트레이터 + 스케줄 + 실패알림 (`sync.py`)

**Files:**
- Create: `bz_sync/sync.py`
- Create: `bz_sync/com.cclime.bzsync.plist`

**Interfaces:**
- Consumes: Task 2~5 전부(`parse`, `names`, `fb`, `scrape`) + `config.json` + `credentials.json`.
- Produces: `run(config: dict, now_iso: str) -> dict` — `{지점: "ok"|"fail:<이유>"}` 요약 반환.
  당월+익월 처리, 부분성공 허용(실패 지점은 write 스킵→이전 값 유지), 실패 시 알림.

- [ ] **Step 1: 실패하는 테스트 작성 (오케스트레이션 로직만, 라이브 없이)**

`bz_sync/tests/test_sync.py`:
```python
from bz_sync.sync import summarize

def test_summarize_counts_failures():
    results = {"01. 신사본점": "ok", "04. 삼성점": "fail:timeout"}
    msg = summarize(results)
    assert "1/2 실패" in msg
    assert "04. 삼성점" in msg

def test_summarize_all_ok():
    assert "전체 성공" in summarize({"01. 신사본점": "ok"})
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bz_sync.sync'`

- [ ] **Step 3: 구현**

`bz_sync/sync.py`:
```python
"""오케스트레이터: 지점 순회 스크레이프→정규화→Firebase write. 부분성공·실패알림."""
import json
import sys
from playwright.sync_api import sync_playwright

from bz_sync.scrape import login, fetch_branch_offdays_html
from bz_sync.parse import parse_month_offdays
from bz_sync.names import normalize_offdays
from bz_sync.fb import build_payload, write_branch


def summarize(results: dict[str, str]) -> str:
    fails = {b: r for b, r in results.items() if r != "ok"}
    if not fails:
        return f"뷰티짱 동기화 전체 성공 ({len(results)}지점)"
    lines = [f"{b}: {r}" for b, r in fails.items()]
    return f"뷰티짱 동기화 {len(fails)}/{len(results)} 실패\n" + "\n".join(lines)


def _months(now_iso: str) -> list[tuple[int, int]]:
    y, m = int(now_iso[:4]), int(now_iso[5:7])
    nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return [(y, m), nm]


def run(config: dict, now_iso: str) -> dict:
    creds = json.load(open(config["credentials_path"], encoding="utf-8"))
    base = config["firebase_base"]
    results: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        login(page, creds)
        for branch in config["branches"]:
            try:
                for (y, m) in _months(now_iso):
                    html = fetch_branch_offdays_html(page, branch, y, m)
                    raw = parse_month_offdays(html)
                    norm = normalize_offdays(raw, config["system_accounts"], config["name_map"])
                    payload = build_payload(norm, y, m, now_iso)
                    status = write_branch(base, y, m, branch, payload)
                    if status >= 400:
                        raise RuntimeError(f"firebase {status}")
                results[branch] = "ok"
            except Exception as e:  # 부분성공: 이 지점만 스킵
                results[branch] = f"fail:{type(e).__name__}"
        browser.close()
    return results


def alert(config: dict, message: str) -> None:
    """실패 알림. config['alert']['type']: 'none'|'slack'|'nova'. 값 노출 금지."""
    a = config.get("alert", {"type": "none"})
    if a["type"] == "slack":
        import requests
        requests.post(a["webhook_url"], json={"text": message}, timeout=15)
    # 'nova'/'none'은 stdout 로깅으로 갈음(맥미니 노바 연동은 추후)


if __name__ == "__main__":
    import datetime
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "bz_sync/config.json", encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    res = run(cfg, now)
    msg = summarize(res)
    print(msg)
    if any(r != "ok" for r in res.values()):
        alert(cfg, msg)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python -m pytest bz_sync/tests/test_sync.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: launchd plist 작성 (맥미니, 매일 새벽 3시)**

`bz_sync/com.cclime.bzsync.plist` (`<HOME>`은 맥미니 실경로로 치환해 `~/Library/LaunchAgents/`에 설치):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cclime.bzsync</string>
  <key>WorkingDirectory</key><string><HOME>/github/cclime-schedule2</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string><string>python3</string>
    <string>-m</string><string>bz_sync.sync</string>
    <string>bz_sync/config.json</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/bzsync.log</string>
  <key>StandardErrorPath</key><string>/tmp/bzsync.err</string>
</dict>
</plist>
```
설치(맥미니): `cp bz_sync/com.cclime.bzsync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.cclime.bzsync.plist`

- [ ] **Step 6: 전체 봇 라이브 스모크 (수동, 맥미니)**

Run: `cd ~/github/cclime-schedule2 && python -m bz_sync.sync bz_sync/config.json`
Expected: "전체 성공" 또는 실패 지점 목록 출력. Firebase 콘솔/`GET .../beautyzzang/2026_08/01. 신사본점.json`으로 데이터 확인.

- [ ] **Step 7: Commit**

```bash
git add bz_sync/sync.py bz_sync/tests/test_sync.py bz_sync/com.cclime.bzsync.plist
git commit -m "오케스트레이터: 지점순회 동기화 + 부분성공 + 실패알림 + launchd"
```

---

## Task 7: 프론트엔드 — 비교 그리드 + 하이라이트 (`index.html`)

**Files:**
- Modify: `index.html` (근처 `buildTable()` line 2449~; 신규 함수 추가 + 말미 호출)

**Interfaces:**
- Consumes: Firebase `GET {FB_BASE}/beautyzzang/{YYYY_MM}/{branch}.json` → `{직원명:[YYYY-MM-DD],_syncedAt}`.
  기존 전역: `curY`, `curM`, `mergedBranch()`, `FB_BASE`, `#sch-table`, 선택 지점(`#branch-sel`).
- Produces: `#bz-table`에 뷰티짱 휴무 그리드 + 근무표와 불일치 하이라이트.

- [ ] **Step 1: 비교 테이블 컨테이너 추가**

`index.html`에서 `#sch-table`(line 259 `<table id="sch-table">`) 블록 바로 뒤에 뷰티짱 그리드용 컨테이너 삽입:
```html
<div id="bz-wrap" style="margin-top:18px;display:none">
  <div id="bz-summary" style="font-size:13px;margin:6px 0;color:#555"></div>
  <table id="bz-table"><thead id="bz-head"></thead><tbody id="bz-body"></tbody></table>
</div>
```

- [ ] **Step 2: 렌더 함수 추가**

`buildTable()` 함수 정의 앞(예: line 2448 직전)에 추가:
```javascript
async function buildBeautyzzangTable(branch, offMap) {
  // offMap: {직원명: Set('YYYY-MM-DD'), ...} — 근무표 휴무(비교 기준)
  const wrap = document.getElementById('bz-wrap');
  if (!branch) { wrap.style.display = 'none'; return; }
  const ym = curY + '_' + String(curM).padStart(2,'0');
  let data = null;
  try {
    const r = await fetch(`${FB_BASE}/beautyzzang/${ym}/${encodeURIComponent(branch)}.json`);
    data = await r.json();
  } catch (e) { data = null; }
  wrap.style.display = '';
  const summary = document.getElementById('bz-summary');
  if (!data) {
    summary.textContent = '⚠️ 뷰티짱 동기화 데이터 없음';
    document.getElementById('bz-head').innerHTML = '';
    document.getElementById('bz-body').innerHTML = '';
    return;
  }
  const syncedAt = data._syncedAt || '?';
  const days = new Date(curY, curM, 0).getDate();
  // 헤더
  let hd = '<tr><th>직원(뷰티짱 휴무)</th>';
  for (let d=1; d<=days; d++) hd += `<th>${d}</th>`;
  hd += '</tr>';
  document.getElementById('bz-head').innerHTML = hd;
  // 본문 + 불일치 카운트
  let mism = 0, body = '';
  for (const name of Object.keys(data)) {
    if (name === '_syncedAt') continue;
    const bzOff = new Set(data[name]);           // 뷰티짱 휴무일(YYYY-MM-DD)
    const schOff = offMap[name] || null;          // 근무표 휴무일 Set (없으면 미매칭)
    body += `<tr><td>${name}${schOff ? '' : ' <span style="color:#999">(미매칭)</span>'}</td>`;
    for (let d=1; d<=days; d++) {
      const key = `${curY}-${String(curM).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const inBz = bzOff.has(key);
      const inSch = schOff ? schOff.has(key) : null;
      let cls = '', mark = inBz ? '휴' : '';
      if (schOff) {
        if (inBz && !inSch) { cls = 'bz-mismatch-red'; mism++; }        // 뷰티짱만 휴무
        else if (!inBz && inSch) { cls = 'bz-mismatch-orange'; mism++; mark='·'; } // 근무표만 휴무
        else if (inBz && inSch) { cls = 'bz-match'; }
      }
      body += `<td class="${cls}">${mark}</td>`;
    }
    body += '</tr>';
  }
  document.getElementById('bz-body').innerHTML = body;
  summary.innerHTML = `뷰티짱 대조: <b style="color:${mism?'#c00':'#080'}">${mism}건 불일치</b> · 마지막 동기화 ${syncedAt}`;
}
```

- [ ] **Step 3: 셀 색상 CSS 추가**

`<style>` 블록에 추가:
```css
#bz-table th, #bz-table td { border:1px solid #ddd; text-align:center; font-size:11px; padding:2px 4px; }
.bz-match { background:#e8f5e9; }
.bz-mismatch-red { background:#ffcdd2; font-weight:700; }
.bz-mismatch-orange { background:#ffe0b2; font-weight:700; }
```

- [ ] **Step 4: `buildTable()` 말미에서 근무표 휴무 Set 구성 후 호출**

`buildTable()`의 `emps.forEach(...)` 렌더 루프에서 직원별 휴무일을 수집하도록,
함수 상단에 `const _schOffMap = {};` 선언하고 각 직원 셀 계산 시 휴무일을 모은 뒤,
함수 마지막 `return` 직전에 호출:
```javascript
  // (emps 루프 안에서 직원 emp.name의 휴무일을 _schOffMap[emp.name] = Set(['YYYY-MM-DD',...]) 로 채운다)
  buildBeautyzzangTable(branch, _schOffMap);
```
`_schOffMap`은 근무표에서 상태가 '휴무'/'휴직'인 날짜를 `YYYY-MM-DD`로 모은 Set.
(근무표 셀 상태 판정 로직은 기존 emps 루프의 상태값을 재사용 — 상태가 휴무/휴직인 날 추가.)

- [ ] **Step 5: 로컬 렌더 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m http.server 8765`
브라우저 `http://localhost:8765/` → 지점 선택(신사본점) → 근무표 아래 뷰티짱 그리드 표시,
불일치 셀 색상·요약·동기화 시각 확인. (Firebase에 Task 6 데이터가 있어야 표시됨.)

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "근무표 앱: 뷰티짱 휴무 비교 그리드 + 불일치 하이라이트"
```

---

## Self-Review (작성자 점검 결과)

**1. Spec coverage:**
- 정본 소스 확정(spec §2.3, §10.1) → Task 1
- Sync bot(spec §4.1) → Task 5(스크레이프)+Task 6(오케스트레이션)
- 직원명 매핑(spec §4.2) → Task 3
- Firebase 스키마(spec §4.3) → Task 4
- 프론트 대조·하이라이트(spec §4.4) → Task 7
- 에러/신뢰성 부분성공·실패알림(spec §6) → Task 6
- 보안 creds 로컬·비노출(spec §7) → Task 1(예시)·Task 5(gitignore)·전반 로깅 규칙
- 테스트 전략(spec §8) → Task 2/3/4/6 단위 + Task 5/6/7 수동 스모크
- 범위 밖 역방향 쓰기(spec §9) → 계획에 write 없음(대조만) ✔

**2. Placeholder scan:** Task 5의 `switch_branch`/`_offdays_content_url`는 의도적으로
`NotImplementedError`이며, 이는 Task 1 산출(RECON.md)에 의존하는 유일한 항목으로 계획서에 명시.
그 외 실코드·실명령·기대출력 모두 기재. Task 7 Step 4는 기존 상태 판정 로직 재사용을 지시(코드 위치 명시).

**3. Type consistency:** `parse_month_offdays -> {name:[int]}` → `normalize_offdays` 동형 유지 →
`build_payload`에서 [int]→[YYYY-MM-DD] 변환 → `write_branch` 저장 → 프론트에서 동일 키/문자열 소비. 일관.
