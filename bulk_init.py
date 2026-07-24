#!/usr/bin/env python3
"""
전지점 전체 월 스케줄 초기화 + 구월 데이터 삭제
  - 삭제: 2026년 4월, 5월, 6월
  - 초기화: 2026년 7월, 8월 (전지점)
  - 7월6일(월) 주부터 시작 (이전 주는 생략)
"""
import json, re, math, calendar, sys
import urllib.request, urllib.parse
from datetime import date

# ── 상수 ─────────────────────────────────────────────────────────────
SHEET_ID  = '1lL4P4yEXhBl-PCk8ErBDQerSHDPJBDErBYBrNQG4gOQ'
GID       = '0'
FB_BASE   = 'https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app'

BELT_ORDER = ['골드','실버','블랙','레드','블루','퍼플','옐로우','화이트','실습생']
BELT_HOURS = {'골드':10,'실버':10,'블랙':10,'레드':9,'블루':9,'퍼플':8,'옐로우':8,'화이트':8,'실습생':8}
ROT_INTERVAL = 2
FW5 = {0:0,1:2,2:2,3:1,4:0,5:0,6:0}
FW4 = {0:0,1:3,2:2,3:1,4:1,5:0,6:0}
BRANCH_MERGE = {
    '02. 강남사옥점': '02. 강남사옥점 03. 강남구청점',
    '03. 강남구청점': '02. 강남사옥점 03. 강남구청점',
}
def merged_branch(b): return BRANCH_MERGE.get(b, b)

# ── 헬퍼 ─────────────────────────────────────────────────────────────
def fb_safe(s):
    return re.sub(r'[\.#\$\[\]/]', '_', s)

# JS buildMonthSchedule()의 seeded PRNG(mulberry32)를 그대로 포팅.
# 브라우저 "근무표 원본 확인" 재계산 결과와 비트 단위로 동일해야 함.
def mulberry32(seed):
    state = seed & 0xFFFFFFFF
    def rng():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rng

def seeded_shuffle(arr, rng):
    for i in range(len(arr) - 1, 0, -1):
        j = math.floor(rng() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]

def fb_branch_url(y, m, branch):
    key = urllib.parse.quote(fb_safe(branch), safe='')
    return f"{FB_BASE}/schedule/{y}_{str(m).zfill(2)}/{key}.json"

def fb_month_url(y, m):
    return f"{FB_BASE}/schedule/{y}_{str(m).zfill(2)}.json"

def http_request(url, method='GET', data=None):
    req = urllib.request.Request(url, method=method)
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
        req.data = body
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode('utf-8')

def parse_work_type(s):
    s = s or ''
    dm = re.search(r'주\s*(\d)\s*일', s)
    hm = re.search(r'(\d+)\s*시간', s)
    return {'days': int(dm.group(1)) if dm else 5,
            'hours': int(hm.group(1)) if hm else 8}

def get_slots(store_hours):
    if store_hours == 11.5:
        return ['09:30']  # 10시간 근무형태: 09:30~21:00 (11h30m 상주) — JS getSlots와 동일
    r = [f"{str(h).zfill(2)}:00" for h in range(10, 21 - store_hours + 1)]
    return r if r else ['10:00']

def belt_idx(b):
    return BELT_ORDER.index(b) if b in BELT_ORDER else len(BELT_ORDER)

# ── 구글시트 직원 데이터 ─────────────────────────────────────────────
def fetch_employees():
    import time
    ts = int(time.time() * 1000)
    url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
           f"/gviz/tq?tqx=out:json&gid={GID}&_{ts}")
    _, text = http_request(url)
    m = re.search(r'\((\{.*\})\)', text, re.DOTALL)
    if not m:
        raise ValueError("GViz 응답 파싱 실패")
    resp = json.loads(m.group(1))
    if resp.get('status') != 'ok':
        raise ValueError(f"GViz 오류: {resp.get('errors')}")

    cols = resp['table']['cols']
    rows = resp['table']['rows']

    iB=iN=iR=iL=iD=iW=iE = -1
    def find_idx(arr):
        nonlocal iB,iN,iR,iL,iD,iW,iE
        for i,c in enumerate(arr):
            t = str(c.get('label') or c.get('v') or c.get('f') or '').strip()
            if t=='지점': iB=i
            elif t=='이름': iN=i
            elif t in('직무','직급'): iR=i
            elif t in('벨트','등급'): iL=i
            elif '입사' in t: iD=i
            elif '근무형태' in t: iW=i
            elif '퇴사' in t or '퇴직' in t: iE=i

    find_idx(cols)
    saved = (iB,iN,iR,iL,iD,iW,iE)
    data_start = 0
    if iB<0 or iN<0:
        for ri, row in enumerate(rows[:5]):
            cells=[{'label':str((c or {}).get('f') or (c or {}).get('v') or '').strip()}
                   for c in (row.get('c') or [])]
            iB=iN=iR=iL=iD=iW=iE=-1
            find_idx(cells)
            if iB>=0 and iN>=0: data_start=ri+1; break
        sv=saved
        if iB<0:iB=sv[0]
        if iN<0:iN=sv[1]
        if iR<0:iR=sv[2]
        if iL<0:iL=sv[3]
        if iD<0:iD=sv[4]
        if iW<0:iW=sv[5]
        if iE<0:iE=sv[6]

    if iB<0:iB=1
    if iN<0:iN=2
    if iR<0:iR=3
    if iL<0:iL=4
    if iD<0:iD=7
    if iW<0:iW=5
    if iE<0:
        for i,c in enumerate(cols):
            if iE<0 and c.get('type') in('date','datetime') and i>iD: iE=i
        if iE<0: iE=9

    def get_str(row, i):
        cs = row.get('c') or []
        if i<0 or i>=len(cs) or not cs[i]: return ''
        return str(cs[i].get('f') or cs[i].get('v') or '').strip()

    def parse_date(cell):
        if not cell: return ''
        src = str(cell.get('f') or '') + ' ' + str(cell.get('v') or '')
        m2 = re.search(r'Date\((\d{4}),(\d{1,2}),(\d{1,2})\)', src)
        if m2:
            return f"{m2.group(1)}-{str(int(m2.group(2))+1).zfill(2)}-{m2.group(3).zfill(2)}"
        m3 = re.search(r'(\d{4})[.\-\s/년]+(\d{1,2})[.\-\s/월]+(\d{1,2})', src)
        if m3:
            return f"{m3.group(1)}-{m3.group(2).zfill(2)}-{m3.group(3).zfill(2)}"
        return ''

    def safe_cell(row, i):
        cs = row.get('c') or []
        return cs[i] if i>=0 and i<len(cs) else None

    employees = []
    for row in rows[data_start:]:
        branch = get_str(row, iB)
        name   = get_str(row, iN)
        if not branch or not name: continue
        belt_raw  = get_str(row, iL)
        belt      = belt_raw if belt_raw in BELT_ORDER else '실습생'
        hire_date = parse_date(safe_cell(row, iD))
        work_type = get_str(row, iW)
        exit_date = parse_date(safe_cell(row, iE))
        if not exit_date:
            raw = get_str(row, iE)
            m4 = re.search(r'(\d{4})[.\-\s/년]+(\d{1,2})[.\-\s/월]+(\d{1,2})', raw)
            if m4: exit_date = f"{m4.group(1)}-{m4.group(2).zfill(2)}-{m4.group(3).zfill(2)}"
        employees.append({'branch':branch,'name':name,'belt':belt,
                          'hire_date':hire_date,'work_type':work_type,'exit_date':exit_date})
    return employees

# ── 스케줄 생성 (JS buildMonthSchedule 재현) ─────────────────────────
def build_month_schedule(employees, y, m, prev_overflow_off=None):
    rng = mulberry32(y * 100 + m)  # 동일 연월은 항상 동일 결과 보장 (JS와 동일 PRNG)
    days_in_month = calendar.monthrange(y, m)[1]

    # 월 경계 주 처리: 첫 월요일 / 마지막 주 일요일까지 연장
    from datetime import timedelta as _td
    first_dow_py = date(y, m, 1).weekday()  # 0=월,...,6=일
    last_dow_py  = date(y, m, days_in_month).weekday()
    # 첫 월요일 (1-based day of month)
    if first_dow_py == 0:
        first_monday = 1
    else:
        first_monday = 1 + (7 - first_dow_py)
    # 마지막 주를 일요일까지 늘리는 날수 (다음달 초)
    extra_days = 0 if last_dow_py == 6 else (6 - last_dow_py)
    prefix_days = first_monday - 1

    emp_data = []

    for emp in employees:
        wt = parse_work_type(emp.get('work_type',''))
        store_hours  = 11.5 if wt['hours'] == 10 else wt['hours'] + 1  # 10시간 근무 → 11.5h(09:30~21:00), 그 외 +1 휴게 — JS와 동일
        days_per_week = wt['days']

        start_day = 1
        hd = emp.get('hire_date','')
        if hd and len(hd)>=10:
            hy,hm2,hdd = int(hd[:4]),int(hd[5:7]),int(hd[8:10])
            if hy>y or (hy==y and hm2>m): continue
            if hy==y and hm2==m: start_day=hdd

        end_day = days_in_month
        ed = emp.get('exit_date','')
        if ed and len(ed)>=10:
            ey,em2,edd = int(ed[:4]),int(ed[5:7]),int(ed[8:10])
            if ey<y or (ey==y and em2<m): continue
            if ey==y and em2==m: end_day=edd

        ext_end_day = (days_in_month + extra_days) if end_day == days_in_month else end_day

        mbranch = merged_branch(emp['branch'])
        key = mbranch + '||' + emp['name']
        avail_days = list(range(start_day, end_day+1))
        slots = get_slots(store_hours)
        # JS getDay(): 0=Sun…6=Sat  ← Python weekday()+1 mod 7
        hire_dow_js = (date(y,m,start_day).weekday()+1) % 7
        is_hire_month = bool(hd and len(hd)>=10
                             and int(hd[:4])==y and int(hd[5:7])==m)
        emp_data.append({'key':key,'emp':{**emp,'branch':mbranch},'start_day':start_day,'end_day':end_day,
                         'ext_end_day':ext_end_day,'avail_days':avail_days,'days_per_week':days_per_week,
                         'store_hours':store_hours,'slots':slots,
                         'hire_dow':hire_dow_js,'is_hire_month':is_hire_month})

    # 날짜 d (넘침 가능)의 요일 계산 헬퍼 (Python weekday: 0=월,...,6=일)
    def day_weekday(d):
        return (date(y, m, 1) + _td(days=d-1)).weekday()

    # 주 목록: firstMonday부터 7일 단위 블록 (마지막 주는 다음달 초까지 연장)
    weeks = []
    d = first_monday
    while d <= days_in_month + extra_days:
        weeks.append(list(range(d, d+7)))
        d += 7

    # 3그룹 초기 배정: 지점 내 벨트→이름 순 정렬 후 idx%3
    #   0=월화(py:0,1), 1=목금(py:3,4), 2=토일(py:5,6)
    PAIR_WDAYS = [(0,1),(3,4),(5,6)]
    emp_group = {}
    branch_sorted = {}
    for ed in emp_data:
        br = ed['emp']['branch']
        branch_sorted.setdefault(br, []).append(
            {'key': ed['key'], 'belt': ed['emp'].get('belt','화이트'), 'name': ed['emp']['name']})
    for arr in branch_sorted.values():
        arr.sort(key=lambda x: (belt_idx(x['belt']), x['name']))
        for i, item in enumerate(arr):
            emp_group[item['key']] = i % 3

    # 직원별 사이클 상태: pair_idx, weeks_used
    emp_state = {}
    for ed in emp_data:
        key = ed['key']
        prev = prev_overflow_off.get(key) if prev_overflow_off else None
        if isinstance(prev, dict) and prev.get('pair_idx') is not None:
            emp_state[key] = {'pair_idx': prev['pair_idx'], 'weeks_used': prev.get('weeks_used', 0)}
        else:
            emp_state[key] = {'pair_idx': emp_group.get(key, 0), 'weeks_used': 0}

    off_map = {ed['key']:set() for ed in emp_data}
    # 이전 달 마지막 주 overflow 휴무 선반영
    # last_off_day 음수 변환은 prefix_days=0(달이 월요일로 시작)이어도 항상 반영해야 함 —
    # 그렇지 않으면 전월 마지막 휴무 이후 연속 출근일수를 알 수 없어 5일 제한이 깨짐 (JS와 동일)
    if prev_overflow_off:
        prev_m = m - 1 if m > 1 else 12
        prev_y = y if m > 1 else y - 1
        days_in_prev = calendar.monthrange(prev_y, prev_m)[1]
        for k, v in prev_overflow_off.items():
            if k not in off_map: continue
            days = v if isinstance(v, (set, list)) else v.get('off_days', [])
            off_map[k].update(days)
            # 이전 달 마지막 휴무일을 음수로 변환해 연속 출근 제한에 활용
            if isinstance(v, dict):
                lod = v.get('last_off_day', 0)
                if lod > 0:
                    off_map[k].add(lod - days_in_prev)

    # prefix_days 연속 제한: 달 초 첫 월요일 이전 공백 기간에 연속 초과 방지
    # 연속 판정 범위: 마지막 휴무 ~ 첫 쌍 정규 휴무일 (월화=firstMonday, 목금=+3, 토일=+5)
    # 지점별 균등화: 같은 날에 여러 직원이 집중되지 않도록 적게 배정된 날 우선
    PAIR_FIRST_OFF_OFFSETS = [0, 3, 5]
    if prefix_days > 0:
        prefix_range = list(range(1, first_monday))
        prefix_br_count = {}  # 지점별 날짜 배정 카운트
        for ed in emp_data:
            key = ed['key']
            if ed['start_day'] >= first_monday: continue
            br = ed['emp']['branch']
            if br not in prefix_br_count:
                prefix_br_count[br] = {d: 0 for d in prefix_range}
            pair_idx = emp_state[key]['pair_idx']
            first_pair_off = first_monday + PAIR_FIRST_OFF_OFFSETS[pair_idx]
            while True:
                all_offs = sorted(d for d in off_map[key] if d < first_pair_off)
                if not all_offs:
                    max_gap, gap_start = first_pair_off - 1, 0
                else:
                    pairs_seq = list(zip(all_offs[:-1], all_offs[1:])) + [(all_offs[-1], first_pair_off)]
                    max_gap, gap_start = 0, 0
                    for a, b in pairs_seq:
                        g = b - a - 1
                        if g > max_gap:
                            max_gap, gap_start = g, a
                if max_gap <= 5: break
                must_by = gap_start + 5
                cands = [d for d in prefix_range
                         if d >= ed['start_day'] and gap_start < d <= must_by
                         and day_weekday(d) != 2
                         and d not in off_map[key]]
                if not cands: break
                best_d = min(cands, key=lambda d: prefix_br_count[br].get(d, 0))
                off_map[key].add(best_d)
                prefix_br_count[br][best_d] = prefix_br_count[br].get(best_d, 0) + 1

    # ══ PHASE 1: 3주 고정쌍 + 1주 Flex 휴무 배정 ══
    # 3주: 현재 쌍(월화/목금/토일) 고정 (주5일=2일, 주4일=쌍2일+추가1일)
    # 4주(flex): 주5일=비연속2일, 주4일=비연속3일 배정 (3일 연속 방지)
    # flex 이후 지점 내 균등 배분으로 다음 쌍 결정 (몰림 방지)
    #   → 현재 쌍별로 짝수번째=(p+1)%3, 홀수번째=(p+2)%3 교대 배정 후 내부 셔플
    extra_off_by_br = {}  # 정규 주 주4일제 추가 휴무 균등화용 (월 전체 누적)
    for w_days in weeks:
        flex_off = {}  # 이번 주 flex 지점별 날짜 카운트

        # ─── flex 주 사전 계산: 지점별 다음 쌍 균등 배분 ───
        flex_next_pair = {}
        flex_by_br = {}
        for ed in emp_data:
            key = ed['key']
            state = emp_state[key]
            is_hw = (ed['is_hire_month']
                     and ed['start_day'] >= w_days[0]
                     and ed['start_day'] <= w_days[-1])
            if not is_hw and state['weeks_used'] == 3:
                br = ed['emp']['branch']
                flex_by_br.setdefault(br, []).append({'key': key, 'p': state['pair_idx']})
        for arr in flex_by_br.values():
            by_p = {0: [], 1: [], 2: []}
            for item in arr:
                by_p[item['p']].append(item['key'])
            for p, keys in by_p.items():
                seeded_shuffle(keys, rng)  # 내부 셔플 — JS seededShuffle과 동일 결과 보장
                for i, key in enumerate(keys):
                    flex_next_pair[key] = (p + 1 + (i % 2)) % 3

        for ed in emp_data:
            key = ed['key']
            state = emp_state[key]
            br = ed['emp']['branch']
            is_hire_week = (ed['is_hire_month']
                            and ed['start_day'] >= w_days[0]
                            and ed['start_day'] <= w_days[-1])

            if is_hire_week:
                # 입사 주: 상태 유지, 기존 로직
                table = FW4 if ed['days_per_week'] <= 4 else FW5
                n_off = table.get(ed['hire_dow'], 0)
                cands = [d for d in w_days
                         if d > ed['start_day'] + 2 and d <= ed['ext_end_day']
                         and day_weekday(d) != 2 and d not in off_map[key]]
                for d in cands[:n_off]:
                    off_map[key].add(d)

            elif state['weeks_used'] < 3:
                # 정규 주: 현재 쌍 배정
                wd1, wd2 = PAIR_WDAYS[state['pair_idx']]
                for d in w_days:
                    if d < ed['start_day'] or d > ed['ext_end_day']: continue
                    if (day_weekday(d) == wd1 or day_weekday(d) == wd2) and d not in off_map[key]:
                        off_map[key].add(d)
                # 주4일제: 쌍 이외 추가 1일 배정 (수요일·쌍 요일 제외, 지점 내 균등)
                if ed['days_per_week'] <= 4:
                    if br not in extra_off_by_br:
                        extra_off_by_br[br] = {}
                    extra_cands = [d for d in w_days
                                   if ed['start_day'] <= d <= ed['ext_end_day']
                                   and day_weekday(d) not in {2, wd1, wd2}
                                   and d not in off_map[key]]
                    if extra_cands:
                        best_d = min(extra_cands, key=lambda d: extra_off_by_br[br].get(d, 0))
                        off_map[key].add(best_d)
                        extra_off_by_br[br][best_d] = extra_off_by_br[br].get(best_d, 0) + 1
                state['weeks_used'] += 1

            else:
                # Flex 주: 비연속 2일 개별 배정 후 다음 쌍으로 교체
                # 다음 쌍은 사전 균등 배분값 사용 (지점 편차 방지)
                next_pair = flex_next_pair.get(key, (state['pair_idx'] + 1) % 3)

                # 금지 요일: 수요일(2) + 3일 연속 경계 방지
                # prev=토일(2) → 이번 주 월(0): 토·일·월 3연속
                # next=월화(0) → 이번 주 일(6): 일·월·화 3연속
                forbidden_py = {2}  # Wednesday
                if state['pair_idx'] == 2: forbidden_py.add(0)  # Mon
                if next_pair == 0:         forbidden_py.add(6)  # Sun

                avail = [d for d in w_days
                         if ed['start_day'] <= d <= ed['ext_end_day']
                         and day_weekday(d) not in forbidden_py
                         and d not in off_map[key]]

                if br not in flex_off:
                    flex_off[br] = {d: 0 for d in w_days}

                n_off = 3 if ed['days_per_week'] <= 4 else 2

                # 연속 출근 5일 제한: 마지막 휴무 이후 5일 이내에 반드시 1일 포함
                # (월 경계에서 직전 주가 prefix 보정으로 인해 마지막 휴무가 아직 없는 경우도
                #  last_off=0으로 취급해 동일하게 강제 — JS와 동일 로직)
                prev_offs = [d for d in off_map[key] if d < w_days[0]]
                last_off = max(prev_offs) if prev_offs else 0
                forced = None
                must_by = last_off + 5
                cands_before = [d for d in avail if d <= must_by]
                if cands_before:
                    forced = min(cands_before, key=lambda d: flex_off[br].get(d, 0))
                elif avail:
                    forced = avail[0]

                # 다음 정규 쌍 첫 휴무까지 연속 제한: flex 마지막 날이 충분히 늦어야 함
                next_pair_first_off = w_days[-1] + 1 + PAIR_FIRST_OFF_OFFSETS[next_pair]
                must_late_from = next_pair_first_off - 6

                def _flex_select(cands_pool, n, req_forced, late_from, flex_cnt):
                    """강제 조건(req_forced)과 후반 강제(late_from) 만족하는 최적 조합 반환."""
                    best, best_score = None, float('inf')
                    if req_forced is not None:
                        rest = [d for d in cands_pool if d != req_forced and abs(d - req_forced) > 1]
                        if n == 2:
                            for d2 in rest:
                                if max(req_forced, d2) < late_from: continue
                                s = flex_cnt.get(req_forced, 0) + flex_cnt.get(d2, 0)
                                if s < best_score: best_score, best = s, (req_forced, d2)
                            if best is None:
                                for d2 in rest:
                                    s = flex_cnt.get(req_forced, 0) + flex_cnt.get(d2, 0)
                                    if s < best_score: best_score, best = s, (req_forced, d2)
                            if best is None and rest:
                                best = (req_forced, rest[-1])
                        else:
                            for i in range(len(rest)):
                                for j in range(i+1, len(rest)):
                                    d2, d3 = rest[i], rest[j]
                                    if max(req_forced, d2, d3) < late_from: continue
                                    adj = 1 if abs(d2-d3)==1 else 0
                                    s = (flex_cnt.get(req_forced,0)+flex_cnt.get(d2,0)+flex_cnt.get(d3,0))+adj*100
                                    if s < best_score: best_score, best = s, (req_forced, d2, d3)
                            if best is None:
                                for i in range(len(rest)):
                                    for j in range(i+1, len(rest)):
                                        d2, d3 = rest[i], rest[j]
                                        adj = 1 if abs(d2-d3)==1 else 0
                                        s = (flex_cnt.get(req_forced,0)+flex_cnt.get(d2,0)+flex_cnt.get(d3,0))+adj*100
                                        if s < best_score: best_score, best = s, (req_forced, d2, d3)
                    if best is None:
                        if n == 2:
                            for i in range(len(cands_pool)):
                                for j in range(i+1, len(cands_pool)):
                                    d1, d2 = cands_pool[i], cands_pool[j]
                                    if abs(d1-d2) == 1: continue
                                    if max(d1, d2) < late_from: continue
                                    s = flex_cnt.get(d1,0) + flex_cnt.get(d2,0)
                                    if s < best_score: best_score, best = s, (d1, d2)
                            if best is None:
                                for i in range(len(cands_pool)):
                                    for j in range(i+1, len(cands_pool)):
                                        d1, d2 = cands_pool[i], cands_pool[j]
                                        if abs(d1-d2) == 1: continue
                                        s = flex_cnt.get(d1,0) + flex_cnt.get(d2,0)
                                        if s < best_score: best_score, best = s, (d1, d2)
                        else:
                            for i in range(len(cands_pool)):
                                for j in range(i+1, len(cands_pool)):
                                    for k in range(j+1, len(cands_pool)):
                                        d1, d2, d3 = cands_pool[i], cands_pool[j], cands_pool[k]
                                        if max(d1, d2, d3) < late_from: continue
                                        adj = (1 if abs(d1-d2)==1 else 0)+(1 if abs(d2-d3)==1 else 0)
                                        s = (flex_cnt.get(d1,0)+flex_cnt.get(d2,0)+flex_cnt.get(d3,0))+adj*100
                                        if s < best_score: best_score, best = s, (d1, d2, d3)
                            if best is None:
                                for i in range(len(cands_pool)):
                                    for j in range(i+1, len(cands_pool)):
                                        for k in range(j+1, len(cands_pool)):
                                            d1, d2, d3 = cands_pool[i], cands_pool[j], cands_pool[k]
                                            adj = (1 if abs(d1-d2)==1 else 0)+(1 if abs(d2-d3)==1 else 0)
                                            s = (flex_cnt.get(d1,0)+flex_cnt.get(d2,0)+flex_cnt.get(d3,0))+adj*100
                                            if s < best_score: best_score, best = s, (d1, d2, d3)
                    return best

                best = _flex_select(avail, n_off, forced, must_late_from, flex_off[br])

                if best:
                    for d in best:
                        off_map[key].add(d)
                        flex_off[br][d] = flex_off[br].get(d, 0) + 1

                state['pair_idx']   = next_pair
                state['weeks_used'] = 0

    # Phase 2 — 출근 시간 배정
    branch_emp_list = {}
    for ed in emp_data:
        br = ed['emp']['branch']
        branch_emp_list.setdefault(br,[]).append(
            {'key':ed['key'],'belt':ed['emp'].get('belt','화이트')})
    for arr in branch_emp_list.values():
        arr.sort(key=lambda x: belt_idx(x['belt']))

    base_offset_map = {}
    for arr in branch_emp_list.values():
        for pos, item in enumerate(arr):
            base_offset_map[item['key']] = pos

    starts_by_key_day = {ed['key']:{} for ed in emp_data}
    for d in range(1, days_in_month+1):
        by_branch = {}
        for ed in emp_data:
            if d<ed['start_day'] or d>ed['end_day']: continue
            if d in off_map[ed['key']]: continue
            by_branch.setdefault(ed['emp']['branch'],[]).append(
                {'key':ed['key'],'slots':ed['slots'],'belt':ed['emp'].get('belt','화이트')})
        rot = math.floor((d-1)/ROT_INTERVAL)
        for workers in by_branch.values():
            workers.sort(key=lambda x: belt_idx(x['belt']))
            for pos, w in enumerate(workers):
                starts_by_key_day[w['key']][str(d)] = w['slots'][(pos+rot)%len(w['slots'])]

    # overflow: 다음달 초 휴무일 + 직원 사이클 상태 (항상 저장)
    overflow_off = {}
    for ed in emp_data:
        k = ed['key']
        state = emp_state[k]
        over = [d - days_in_month for d in off_map[k] if d > days_in_month] if extra_days > 0 else []
        last_day_off = max((d for d in off_map[k] if 1 <= d <= days_in_month), default=0)
        overflow_off[k] = {'off_days': over, 'last_off_day': last_day_off, 'pair_idx': state['pair_idx'], 'weeks_used': state['weeks_used']}

    result = {}
    for ed in emp_data:
        key = ed['key']
        safe_key = fb_safe(key)
        result[safe_key] = {
            'name': ed['emp']['name'], 'branch': ed['emp']['branch'],
            'belt': ed['emp'].get('belt','화이트'),
            'hire_date': ed['emp'].get('hire_date',''),
            'exit_date': ed['emp'].get('exit_date',''),
            'work_type': ed['emp'].get('work_type',''),
            'shift_hours': ed['store_hours'], 'shift_slots': ed['slots'],
            'shift_base_offset': base_offset_map.get(key,0),
            'rotation_interval': ROT_INTERVAL,
            'shift_starts': starts_by_key_day.get(key,{}),
            'off_days': sorted(d for d in off_map[key] if (first_monday if (y == 2026 and m == 7) else 1) <= d <= days_in_month),
            'day_types': {}
        }
    return result, overflow_off

# ── overflow Firebase 저장/로드 ──────────────────────────────────────
def fb_overflow_url(y, m):
    return f"{FB_BASE}/overflow/{y}_{str(m).zfill(2)}.json"

def load_overflow(y, m):
    """Firebase에서 이전 달 overflow 로드. 없으면 None 반환."""
    try:
        _, text = http_request(fb_overflow_url(y, m))
        data = json.loads(text)
        if not data:
            return None
        result = {}
        for safe_k, v in data.items():
            orig_k = v.pop('_key', safe_k)  # 저장 시 보존한 원본 키 복원
            result[orig_k] = {**v, 'off_days': set(v.get('off_days', []))}
        return result
    except Exception as e:
        print(f"  ⚠ overflow {y}/{m:02d} 로드 실패: {e}")
        return None

def save_overflow(y, m, overflow_off):
    """현재 달 overflow를 Firebase에 저장. key의 특수문자를 fb_safe로 변환."""
    data = {}
    for k, v in overflow_off.items():
        data[fb_safe(k)] = {'_key': k, **v, 'off_days': sorted(v['off_days'])}
    try:
        status, _ = http_request(fb_overflow_url(y, m), method='PUT', data=data)
        return status == 200
    except Exception as e:
        print(f"  ⚠ overflow {y}/{m:02d} 저장 실패: {e}")
        return False

# ── 지점 조회 (비파괴 판정용) ────────────────────────────────────────
def fb_get_branch(y, m, branch):
    """지점 데이터 조회.
    - 200 + 실제 데이터 → dict 반환
    - 200 + null/빈값   → None (확인된 빈 지점)
    - 그 외(HTTP 오류 등) → 예외 발생 (호출부에서 '쓰지 않고 건너뜀'으로 처리)
    """
    status, text = http_request(fb_branch_url(y, m, branch), method='GET')
    if status != 200:
        raise RuntimeError(f'조회 실패 HTTP {status}')
    text = (text or '').strip()
    if not text or text == 'null':
        return None
    return json.loads(text)

# ── 단일 월 생성 및 업로드 ─────────────────────────────────────────
def run_month(y, m, employees, branches, prev_overflow=None, destructive=False):
    """특정 달 근무표 생성·업로드. overflow_off 반환.

    destructive=False(기본, 스케줄 실행): 수기데이터 보존.
      기존 지점은 절대 덮어쓰지 않고, 빈 지점만 생성 + 기존 지점엔 신규 입사자만 병합.
    destructive=True(--rebuild 전용): 월 전체 삭제 후 재생성(로테이션 체인 재구축).
    """
    if prev_overflow is None:
        prev_y, prev_m = (y, m-1) if m > 1 else (y-1, 12)
        print(f"  이전 overflow 로드 중 ({prev_y}/{prev_m:02d})...", end=' ')
        prev_overflow = load_overflow(prev_y, prev_m)
        print(f"{len(prev_overflow)}명" if prev_overflow else "없음 (초기값 사용)")

    print(f"\n━━ {y}년 {m}월 근무표 {'재구축(파괴)' if destructive else '생성(비파괴)'} ━━")

    if destructive:
        # 명시적 재구축 시에만 월 전체 삭제
        try:
            status, _ = http_request(fb_month_url(y, m), method='DELETE')
            print(f"  [재구축] 기존 데이터 삭제 → HTTP {status}")
        except Exception as e:
            print(f"  삭제 실패: {e}")

    all_data, overflow_off = build_month_schedule(employees, y, m, prev_overflow)

    # overflow 저장
    ok_ov = save_overflow(y, m, overflow_off)
    print(f"  overflow 저장 → {'완료' if ok_ov else '실패'}")

    # 지점별 업로드
    by_branch = {}
    for safe_key, entry in all_data.items():
        if isinstance(entry, dict) and 'branch' in entry:
            by_branch.setdefault(entry['branch'], {})[safe_key] = entry

    ok = err = skip = add = 0
    for branch in branches:
        if branch not in by_branch:
            skip += 1; continue
        url = fb_branch_url(y, m, branch)
        fresh = by_branch[branch]
        try:
            if not destructive:
                existing = fb_get_branch(y, m, branch)  # 오류 시 예외 → 아래 except에서 안전하게 건너뜀
                if existing:
                    # 기존 지점: 수기데이터 절대 보존. 이름 기준으로 신규 입사자만 병합.
                    existing_names = set(v.get('name') for v in existing.values()
                                         if isinstance(v, dict) and v.get('name'))
                    missing = {k: v for k, v in fresh.items()
                               if isinstance(v, dict) and v.get('name') not in existing_names}
                    if missing:
                        merged = {**existing, **missing}
                        http_request(url, method='PUT', data=merged)
                        print(f"  {branch}: 신규 {len(missing)}명 추가 ✓ (기존 {len(existing)}명 보존)")
                        add += 1
                    else:
                        print(f"  {branch}: 이미 존재, 건너뜀 (보존)")
                        skip += 1
                    continue
                # existing is None → 확인된 빈 지점 → 아래에서 생성
            # destructive 또는 빈 지점 → 신규 생성
            status, _ = http_request(url, method='PUT', data=fresh)
            mark = '✓' if status == 200 else f'HTTP{status}'
            print(f"  {branch}: 생성 {mark} ({len(fresh)}명)")
            ok += 1
        except Exception as e:
            # 조회/쓰기 오류 시 절대 덮어쓰지 않고 건너뜀 (데이터 보호 최우선)
            print(f"  {branch}: 오류 — {e} (건너뜀, 덮어쓰기 안 함)")
            err += 1

    print(f"  → 생성 {ok} / 신규추가 {add} / 건너뜀 {skip} / 오류 {err}")
    return overflow_off

# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    import sys
    from datetime import datetime, timezone, timedelta

    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    args = sys.argv[1:]

    print("직원 데이터 로드 중...")
    employees = fetch_employees()
    branches = sorted(
        set(merged_branch(e['branch']) for e in employees),
        key=lambda b: int(re.match(r'(\d+)', b).group(1)) if re.match(r'(\d+)', b) else 999
    )
    print(f"  → {len(employees)}명 / {len(branches)}개 지점 로드됨")

    # --rebuild [start_y start_m [end_y end_m]]: 지정 달부터 체인 재구축
    if args and args[0] == '--rebuild':
        start_y = int(args[1]) if len(args) > 1 else 2026
        start_m = int(args[2]) if len(args) > 2 else 7
        end_y   = int(args[3]) if len(args) > 3 else now.year
        end_m   = int(args[4]) if len(args) > 4 else now.month
        print(f"\n재구축 모드: {start_y}/{start_m:02d} → {end_y}/{end_m:02d}\n")
        y, m = start_y, start_m
        prev_overflow = None
        while (y, m) <= (end_y, end_m):
            overflow_off = run_month(y, m, employees, branches, prev_overflow, destructive=True)
            prev_overflow = {k: {**v, 'off_days': set(v['off_days'])} for k, v in overflow_off.items()}
            m += 1
            if m > 12: y += 1; m = 1
        print("\n재구축 완료!")
        return

    # 일반 모드: python3 bulk_init.py [y m]
    if len(args) >= 2:
        y, m = int(args[0]), int(args[1])
        print(f"  지정 연월: {y}년 {m}월")
    else:
        # 매달 1일 실행 시 익월 근무표 생성
        y = now.year + (1 if now.month == 12 else 0)
        m = 1 if now.month == 12 else now.month + 1
        print(f"  대상 연월: {y}년 {m}월 (익월 자동 생성)")

    run_month(y, m, employees, branches)
    print("\n완료!")

if __name__ == '__main__':
    main()
