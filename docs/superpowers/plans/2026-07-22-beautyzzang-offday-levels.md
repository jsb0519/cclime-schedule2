# 뷰티짱 근무 외 상태 전체 + 반차 3단계 대조 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 근무표의 근무 외 상태 전체(휴무·연차·대휴·교육·휴직)와 반차(부분금지)를 뷰티짱과 3단계 레벨로 대조한다.

**Architecture:** 봇(`bz_sync/`, Python)이 뷰티짱 BanList에서 종일휴무(`off`)와 부분금지(`half`)를 분리 수집해 Firebase에 `{name:{off,half}}` 구조로 쓰고, 근무표 앱(`index.html`, 순수 JS)이 근무표 상태를 종일(2)/반일(1)/근무(0) 레벨로 매겨 뷰티짱 레벨과 비교·색상 하이라이트한다.

**Tech Stack:** Python 3.9(system, `--user` deps) + pytest, Playwright(스크레이핑), Firebase RTDB(REST), 바닐라 JS(index.html).

## Global Constraints

- 지점 Firebase 키 규칙은 `fb_key`(봇)·`fbBranchKey`(앱) 동일: `. # $ [ ] /` → `_`. 변경 금지.
- 시크릿(credentials.json) 절대 커밋·출력 금지. `bz_sync/credentials.json`은 gitignore.
- 봇 실행(로그인/스크레이핑)은 Claude가 못 돌림 → **재동기화는 사람이 직접**.
- 기존 오프라인 테스트 회귀 통과 유지(`python3 -m pytest bz_sync/tests`).
- 색 규칙 고정: 뷰티짱 레벨 < 근무표 레벨 → 주황(`bz-mismatch-orange`), > → 빨강(`bz-mismatch-red`), = → 무표시.
- 레벨 매핑 고정: 종일=2(휴무·연차·대휴·교육·휴직 / `n1DayHoliday=1`), 반일=1(오전·오후반차 / `n1DayHoliday=0`), 근무=0.

---

### Task 1: 봇 파서 — 종일/부분 분리 (`parse_bans`)

**Files:**
- Modify: `bz_sync/banparse.py:4-15` (`parse_offdays` → `parse_bans`)
- Test: `bz_sync/tests/test_banparse.py:7-20`
- Fixture(기존 재사용): `bz_sync/tests/fixtures/banlist_sinsa_2026_07.json` (oid 860807 = `n1DayHoliday=0`, `strDate=2026-07-22` 이미 존재)

**Interfaces:**
- Produces: `parse_bans(ban: list[dict]) -> dict[int, dict[str, list[str]]]`.
  반환 각 oid는 `{"off": sorted[YYYY-MM-DD], "half": sorted[YYYY-MM-DD]}` (두 키 항상 존재, 빈 리스트 가능).
  `n1DayHoliday==1`→off, `==0`→half. 같은 날 중복 dedupe. oid/strDate 없으면 skip.
- `parse_staff_names`는 변경 없음(그대로 export 유지).

- [ ] **Step 1: 실패 테스트 작성** — `bz_sync/tests/test_banparse.py`의 `test_parse_offdays_fullday_only`, `test_parse_offdays_dedup_sorted`를 아래로 교체하고 import 갱신.

```python
import json
from pathlib import Path
from bz_sync.banparse import parse_bans, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_bans_splits_full_and_half():
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    rec = parse_bans(ban)
    assert rec[847079] == {"off": ["2026-07-01", "2026-07-06"], "half": []}   # 종일휴무
    assert rec[857465] == {"off": ["2026-07-04", "2026-07-05"], "half": []}
    assert rec[860807] == {"off": [], "half": ["2026-07-22"]}                  # 부분금지 → half

def test_parse_bans_dedup_sorted():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0},
    ]
    assert parse_bans(ban) == {1: {"off": ["2026-07-02", "2026-07-05"], "half": ["2026-07-10"]}}
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests/test_banparse.py -q`
Expected: FAIL (`ImportError: cannot import name 'parse_bans'`).

- [ ] **Step 3: 최소 구현** — `bz_sync/banparse.py`의 `parse_offdays`(4-15행)를 아래로 교체.

```python
def parse_bans(ban: list[dict]) -> dict[int, dict[str, list[str]]]:
    """BanList JSON → {oidStaff: {"off":[YYYY-MM-DD], "half":[YYYY-MM-DD]}}.
    n1DayHoliday==1 → 종일휴무(off), ==0 → 시간대 부분금지(half). 같은 날 중복은 dedupe."""
    off: dict[int, set[str]] = {}
    half: dict[int, set[str]] = {}
    for row in ban:
        oid = row.get("oidStaff")
        date = row.get("strDate")
        if oid is None or not date:
            continue
        flag = row.get("n1DayHoliday")
        if flag == 1:
            off.setdefault(int(oid), set()).add(date[:10])
        elif flag == 0:
            half.setdefault(int(oid), set()).add(date[:10])
    oids = set(off) | set(half)
    return {oid: {"off": sorted(off.get(oid, set())),
                  "half": sorted(half.get(oid, set()))} for oid in oids}
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests/test_banparse.py -q`
Expected: PASS (3 passed — 위 2개 + `test_parse_staff_names`).

- [ ] **Step 5: 커밋**

```bash
cd ~/github/cclime-schedule2
git add bz_sync/banparse.py bz_sync/tests/test_banparse.py
git commit -m "뷰티짱 봇: parse_bans로 종일휴무/부분금지 분리 수집"
```

---

### Task 2: 봇 이름해석 — 중첩 구조 (`resolve_bans`)

**Files:**
- Modify: `bz_sync/names.py:4-16` (`resolve` → `resolve_bans`)
- Test: `bz_sync/tests/test_names.py` (전체 교체)

**Interfaces:**
- Consumes: `parse_bans` 출력 `{oid: {"off":[...], "half":[...]}}` (Task 1).
- Produces: `resolve_bans(bans_by_oid, oid_to_name, system_accounts, name_map) -> dict[str, dict[str, list[str]]]`.
  oid→이름(없으면 `oid:{oid}`), system_accounts 제외, name_map 치환(빈문자열이면 제외).
  동명이인(같은 매핑명) 시 off·half 각각 합집합. 값은 `{"off": sorted, "half": sorted}`.

- [ ] **Step 1: 실패 테스트 작성** — `bz_sync/tests/test_names.py` 전체를 아래로 교체.

```python
from bz_sync.names import resolve_bans

SYS = ["대기", "지원", "당일취소"]

def test_maps_oid_and_filters_system():
    bans = {847079: {"off": ["2026-07-01"], "half": []},
            564937: {"off": ["2026-07-02"], "half": []},      # 시스템계정 → 제외
            860807: {"off": [], "half": ["2026-07-22"]}}
    oid2name = {847079: "김효은", 564937: "대기", 860807: "박세영"}
    assert resolve_bans(bans, oid2name, SYS, {}) == {
        "김효은": {"off": ["2026-07-01"], "half": []},
        "박세영": {"off": [], "half": ["2026-07-22"]},
    }

def test_unknown_oid_becomes_placeholder():
    bans = {999999: {"off": ["2026-07-01"], "half": []}}
    assert resolve_bans(bans, {}, SYS, {}) == {"oid:999999": {"off": ["2026-07-01"], "half": []}}

def test_name_map_rename_exclude_and_merge_dup():
    bans = {1: {"off": ["2026-07-01"], "half": []},
            2: {"off": [], "half": ["2026-07-03"]},           # 2도 김효은으로 매핑 → 합집합
            3: {"off": ["2026-07-09"], "half": []}}            # 제외대상
    oid2name = {1: "김효은(신사)", 2: "김효은(신사)", 3: "제외대상"}
    out = resolve_bans(bans, oid2name, SYS, {"김효은(신사)": "김효은", "제외대상": ""})
    assert out == {"김효은": {"off": ["2026-07-01"], "half": ["2026-07-03"]}}
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests/test_names.py -q`
Expected: FAIL (`ImportError: cannot import name 'resolve_bans'`).

- [ ] **Step 3: 최소 구현** — `bz_sync/names.py`의 `resolve`(4-16행)를 아래로 교체.

```python
def resolve_bans(bans_by_oid: dict[int, dict[str, list[str]]], oid_to_name: dict[int, str],
                 system_accounts: list[str], name_map: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    """oidStaff→근무표 이름 해석 + 시스템계정/제외 필터. off·half 중첩 구조 보존, 동명이인 합집합."""
    sys_set = set(system_accounts)
    acc: dict[str, dict[str, set]] = {}
    for oid, rec in bans_by_oid.items():
        name = oid_to_name.get(oid) or f"oid:{oid}"
        if name in sys_set:
            continue
        mapped = name_map.get(name, name)
        if mapped == "":
            continue
        slot = acc.setdefault(mapped, {"off": set(), "half": set()})
        slot["off"].update(rec.get("off", []))
        slot["half"].update(rec.get("half", []))
    return {name: {"off": sorted(v["off"]), "half": sorted(v["half"])} for name, v in acc.items()}
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests/test_names.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: 커밋**

```bash
cd ~/github/cclime-schedule2
git add bz_sync/names.py bz_sync/tests/test_names.py
git commit -m "뷰티짱 봇: resolve_bans로 off/half 중첩 이름해석 + 동명이인 합집합"
```

---

### Task 3: 봇 페이로드 + 오케스트레이터 배선 (`build_payload`, `sync.py`)

**Files:**
- Modify: `bz_sync/fb.py:11-14` (`build_payload` 시그니처/문서만; 로직은 passthrough라 유지)
- Modify: `bz_sync/sync.py:5-8`(import), `bz_sync/sync.py:42-45`(파이프 배선)
- Test: `bz_sync/tests/test_fb.py:3-6` (`test_build_payload_passthrough_dates` 교체)

**Interfaces:**
- Consumes: `resolve_bans` 출력 `{name: {"off":[...], "half":[...]}}` (Task 2).
- Produces: `build_payload(bans_by_name: dict[str, dict], synced_at: str) -> dict` — 입력 dict 얕은 복사 + `_syncedAt` 부가. (Firebase 노드 = `{name:{off,half}, _syncedAt}`)

- [ ] **Step 1: 실패 테스트 작성** — `bz_sync/tests/test_fb.py`의 `test_build_payload_passthrough_dates`(3-6행)를 아래로 교체. (`test_write_branch_*` 2개는 그대로 둠)

```python
def test_build_payload_nested_and_synced_at():
    p = build_payload({"김효은": {"off": ["2026-07-01"], "half": ["2026-07-22"]}}, "2026-07-22T03:00:00+09:00")
    assert p["김효은"] == {"off": ["2026-07-01"], "half": ["2026-07-22"]}
    assert p["_syncedAt"] == "2026-07-22T03:00:00+09:00"
```

- [ ] **Step 2: 실패 확인 (전체 스위트)**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests -q`
Expected: FAIL — Task 1·2에서 `parse_offdays`/`resolve`를 없앴는데 `bz_sync/sync.py`가 아직 옛 이름을 import → `test_sync.py` 수집 단계에서 `ImportError`. (이 배선 오류를 Step 3에서 고친다. `build_payload` 자체는 passthrough라 로직 변경은 없고 시그니처/문서만 갱신.)

- [ ] **Step 3: 구현** — `bz_sync/fb.py`의 `build_payload`(11-14행)를 시그니처·문서만 갱신(로직 동일).

```python
def build_payload(bans_by_name: dict[str, dict], synced_at: str) -> dict:
    """{name: {"off":[...], "half":[...]}} + _syncedAt 를 Firebase 노드 페이로드로."""
    payload: dict = dict(bans_by_name)
    payload["_syncedAt"] = synced_at
    return payload
```

그리고 `bz_sync/sync.py` import(5-8행) 및 파이프 배선(42-45행)을 교체:

```python
# 5-8행: import 교체
from bz_sync.scrape import login, fetch_branch
from bz_sync.banparse import parse_bans, parse_staff_names
from bz_sync.names import resolve_bans
from bz_sync.fb import build_payload, write_branch
```

```python
# 42-45행: 배선 교체 (try 블록 내부)
                    ban, rv = fetch_branch(page, oid, y, m)
                    bans = resolve_bans(parse_bans(ban), parse_staff_names(rv),
                                        config["system_accounts"], config["name_map"])
                    status = write_branch(base, y, m, branch, build_payload(bans, now_iso))
```

- [ ] **Step 4: 전체 봇 테스트 통과 확인**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests -q`
Expected: PASS (전체 통과 — banparse 3 + names 3 + fb 3 + sync 3 + scrape 등 기존). import 깨짐 없어야 함.

- [ ] **Step 5: 커밋**

```bash
cd ~/github/cclime-schedule2
git add bz_sync/fb.py bz_sync/sync.py bz_sync/tests/test_fb.py
git commit -m "뷰티짱 봇: build_payload/sync를 off·half 중첩 구조로 배선"
```

---

### Task 4: 앱 — 근무표 레벨 분리 + 매칭 이름 집합 (`buildTable`)

**Files:**
- Modify: `index.html:2540` (`_schOffMap` 선언 + `_schNames` 추가)
- Modify: `index.html:2605` (forEach 루프 진입부에 `_schNames.add`)
- Modify: `index.html:2659-2663` (dtype → full/half Set 분리)
- Modify: `index.html:2690` (`buildBeautyzzangTable` 호출 인자 추가)

**Interfaces:**
- Produces: `_schOffMap = {name: {full:Set<YYYY-MM-DD>, half:Set}}`, `_schNames = Set<name>`.
  `buildBeautyzzangTable(branch, _schOffMap, _schNames)` 로 전달(Task 5가 소비).
- Note: index.html은 단위 테스트 프레임워크가 없음 → Task 6 완료 후 Playwright 육안 검증(Task 7).

- [ ] **Step 1: `_schOffMap`/`_schNames` 선언** — `index.html:2540` 을 교체.

```javascript
  const _schOffMap = {};        // {name: {full:Set, half:Set}} — 근무표 오프(레벨 분리)
  const _schNames  = new Set(); // 근무표에 존재하는 모든 직원(오프 유무 무관) — 미매칭 판정용
```

- [ ] **Step 2: 매칭 이름 수집** — `index.html:2605`(`emps.forEach(emp => {`) 바로 다음 줄에 삽입.

```javascript
  emps.forEach(emp => {
    _schNames.add(emp.name);
    const key = mergedBranch(emp.branch) + '||' + emp.name;
```

- [ ] **Step 3: dtype 레벨 분리** — `index.html:2659-2663` (`const dtype = …` ~ 닫는 `}`) 을 교체.

기존:
```javascript
        const dtype = (sd.day_types && sd.day_types[String(d)]) || (offs.includes(d) ? '휴무' : null);
        if (dtype) {
          if (dtype === '휴무' || dtype === '휴직') {
            (_schOffMap[emp.name] ||= new Set()).add(`${curY}-${String(curM).padStart(2,'0')}-${String(d).padStart(2,'0')}`);
          }
          offCnt++;
```

교체:
```javascript
        const dtype = (sd.day_types && sd.day_types[String(d)]) || (offs.includes(d) ? '휴무' : null);
        if (dtype) {
          const dstr = `${curY}-${String(curM).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
          const rec = (_schOffMap[emp.name] ||= { full: new Set(), half: new Set() });
          if (dtype === '오전반차' || dtype === '오후반차') rec.half.add(dstr);
          else rec.full.add(dstr);   // 휴무·연차·대휴·교육·휴직 등 종일 비근무 = 레벨2
          offCnt++;
```

- [ ] **Step 4: 호출 인자 추가** — `index.html:2690` 을 교체.

```javascript
  buildBeautyzzangTable(branch, _schOffMap, _schNames);
```

- [ ] **Step 5: 문법 확인 후 커밋** (렌더는 Task 5·6 후 동작)

```bash
cd ~/github/cclime-schedule2
node --check index.html 2>/dev/null || echo "(HTML 파일이라 node --check 불가 — Task 6 후 Playwright로 검증)"
git add index.html
git commit -m "뷰티짱 앱: 근무표 오프를 full/half 레벨로 분리 + 매칭 이름집합"
```

---

### Task 5: 앱 — 뷰티짱 노드 리더/병합 (`{off,half}` 구조)

**Files:**
- Modify: `index.html:2457` (`buildBeautyzzangTable` 시그니처)
- Modify: `index.html:2476-2493` (노드 병합 로직)

**Interfaces:**
- Consumes: `_schOffMap`, `_schNames` (Task 4). Firebase 노드값 `{name:{off:[],half:[]}, _syncedAt}`.
- Produces: `data[name] = {off:Set, half:Set}` (병합·dedupe 완료), `data._syncedAt` 문자열.
  구형 flat 배열 노드는 `{off:배열, half:[]}`로 방어 해석.

- [ ] **Step 1: 시그니처 변경** — `index.html:2457` 교체.

```javascript
async function buildBeautyzzangTable(branch, schOffMap, schNames) {
```

- [ ] **Step 2: 병합 로직 교체** — `index.html:2476-2493` (`data = {};` ~ `_syncedAt` 계산 끝) 을 교체.

기존 블록(참고):
```javascript
    data = {};
    for (const node of validNodes) {
      for (const [k, v] of Object.entries(node)) {
        if (k === '_syncedAt') continue;
        if (!data[k]) {
          data[k] = [...v];
        } else {
          const existing = new Set(data[k]);
          for (const d of v) existing.add(d);
          data[k] = [...existing];
        }
      }
    }
    const syncTimes = validNodes.map(n => n._syncedAt).filter(Boolean);
    data._syncedAt = syncTimes.length ? syncTimes.reduce((a, b) => a > b ? a : b) : undefined;
```

교체:
```javascript
    data = {};
    for (const node of validNodes) {
      for (const [k, v] of Object.entries(node)) {
        if (k === '_syncedAt') continue;
        // 신형 {off,half} / 구형 flat 배열(=전부 off) 모두 방어 해석
        const rec = Array.isArray(v) ? { off: v, half: [] }
                                     : { off: (v && v.off) || [], half: (v && v.half) || [] };
        if (!data[k]) {
          data[k] = { off: new Set(rec.off), half: new Set(rec.half) };
        } else {
          rec.off.forEach(d => data[k].off.add(d));
          rec.half.forEach(d => data[k].half.add(d));
        }
      }
    }
    const syncTimes = validNodes.map(n => n._syncedAt).filter(Boolean);
    data._syncedAt = syncTimes.length ? syncTimes.reduce((a, b) => a > b ? a : b) : undefined;
```

- [ ] **Step 3: 커밋** (렌더는 Task 6 후 동작)

```bash
cd ~/github/cclime-schedule2
git add index.html
git commit -m "뷰티짱 앱: 노드 리더를 off/half Set 병합 + 구형배열 방어"
```

---

### Task 6: 앱 — 3레벨 판정/렌더 + 범례

**Files:**
- Modify: `index.html:2503-2527` (헤더·바디 렌더 + 판정 + 요약)

**Interfaces:**
- Consumes: `data[name] = {off:Set, half:Set}`, `schOffMap[name] = {full:Set, half:Set}|undefined`, `schNames:Set` (Task 4·5).
- 색 규칙: `bzLv < schLv`→주황, `bzLv > schLv`→빨강, 같으면 무표시(레벨>0이면 `bz-match`).

- [ ] **Step 1: 렌더/판정 블록 교체** — `index.html:2503-2527` (`const days = …` ~ `summary.innerHTML = …`) 을 교체.

```javascript
  const days = new Date(curY, curM, 0).getDate();
  let hd = '<tr><th>직원(뷰티짱 휴무)</th>';
  for (let d = 1; d <= days; d++) hd += `<th>${d}</th>`;
  document.getElementById('bz-head').innerHTML = hd + '</tr>';
  let mism = 0, body = '';
  for (const name of Object.keys(data)) {
    if (name === '_syncedAt') continue;
    const bzOff = data[name].off, bzHalf = data[name].half;   // Sets
    const matched = schNames.has(name);
    const schRec = schOffMap[name] || null;                    // {full:Set, half:Set} | null
    body += `<tr><td>${name}${matched ? '' : ' <span style="color:#999">(미매칭)</span>'}</td>`;
    for (let d = 1; d <= days; d++) {
      const key = `${curY}-${String(curM).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const bzLv = bzOff.has(key) ? 2 : (bzHalf.has(key) ? 1 : 0);
      let cls = '', mark = bzLv === 2 ? '휴' : (bzLv === 1 ? '반' : '');
      if (matched) {
        const schLv = schRec ? (schRec.full.has(key) ? 2 : (schRec.half.has(key) ? 1 : 0)) : 0;
        if (bzLv < schLv) { cls = 'bz-mismatch-orange'; mism++; if (!mark) mark = '·'; }
        else if (bzLv > schLv) { cls = 'bz-mismatch-red'; mism++; }
        else if (bzLv > 0) { cls = 'bz-match'; }
      }
      body += `<td class="${cls}">${mark}</td>`;
    }
    body += '</tr>';
  }
  document.getElementById('bz-body').innerHTML = body;
  summary.innerHTML = `뷰티짱 대조: <b style="color:${mism?'#c00':'#080'}">${mism}건 불일치</b>`
    + ` · <span style="font-size:11px;color:#888">휴=종일·반=부분 · 🟠근무표 오프 미반영 · 🔴뷰티짱 과다차단</span>`
    + ` · 마지막 동기화 ${data._syncedAt || '?'}`;
```

- [ ] **Step 2: 커밋**

```bash
cd ~/github/cclime-schedule2
git add index.html
git commit -m "뷰티짱 앱: 3레벨(종일/반일/근무) 대조 판정 + 반 마크 + 범례"
```

---

### Task 7: 검증 — 봇 테스트 전체 + 앱 Playwright + 재동기화 안내

**Files:** (검증 전용, 코드 변경 없음)

- [ ] **Step 1: 봇 오프라인 테스트 전체 통과**

Run: `cd ~/github/cclime-schedule2 && python3 -m pytest bz_sync/tests -q`
Expected: PASS (전체). 실패 시 해당 Task로 되돌아가 수정.

- [ ] **Step 2: 앱 로컬 렌더 검증 (Playwright, 구조 방어 확인 — 재동기화 前)**

로컬 서버: `cd ~/github/cclime-schedule2 && python3 -m http.server 8777 &`
Playwright로 `http://localhost:8777/index.html` 로드 → `sessionStorage.site_auth='master'` 후 reload → 근무표 탭 → 지점 `01. 신사본점` 및 병합지점 `02. 강남사옥점 03. 강남구청점` 선택.
Expected: 콘솔 에러 없음(favicon 404 무관). 재동기화 前이라 뷰티짱 노드는 구형 flat 배열 → 방어 해석으로 `휴` 마크·기존 대조가 깨지지 않고 렌더. 서버 종료: `pkill -f "http.server 8777"`.

- [ ] **Step 3: 병합 후 재동기화 (사람이 직접 — Claude 실행 막힘)**

배포(main 병합) 후 사람이:
`cd ~/github/cclime-schedule2 && python3 -u -m bz_sync.sync bz_sync/config.json 2>&1 | tee /tmp/bzsync_resync2.log`
Expected: `뷰티짱 동기화 전체 성공 (20지점)`.

- [ ] **Step 4: 재동기화 후 구조·렌더 재확인**

Firebase 검증: `curl -s ".../beautyzzang/2026_07/01_%20신사본점.json"` 값이 `{name:{off:[],half:[]}}` 중첩 구조 + `_syncedAt` 신선.
Playwright: 강남 병합지점에서 `반` 마크가 부분금지 날짜에 뜨고, 연차·대휴 등 종일 비근무가 뷰티짱 종일휴무와 일치(무표시)로 나오는지 육안 확인.

- [ ] **Step 5: 최종 커밋(진행원장/핸드오프 갱신은 세션 마무리에서)**

```bash
cd ~/github/cclime-schedule2 && git log --oneline -8
```

---

## 실행 순서 / 의존성

- Task 1 → 2 → 3 (봇, 순차: 각자 이전 반환구조 소비).
- Task 4 → 5 → 6 (앱, 순차: 인터페이스 의존). 봇(1-3)과 앱(4-6)은 서로 독립이라 병렬 가능하나, Firebase 구조 계약(`{off,half}`)만 일치하면 됨.
- Task 7 은 전체 후. Step 3(재동기화)은 배포 후 사람이.
