#!/usr/bin/env python3
"""
전지점 전체 월 스케줄 초기화 + 구월 데이터 삭제
  - 삭제: 2026년 4월, 5월, 6월
  - 초기화: 2026년 7월, 8월 (전지점)
  - 7월6일(월) 주부터 시작 (이전 주는 생략)
"""
import json, re, math, random, calendar, sys
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
        store_hours  = wt['hours'] + 1
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
    if prev_overflow_off and prefix_days > 0:
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
                prev_all = sorted(d for d in off_map[key] if d < first_pair_off)
                last_off = prev_all[-1] if prev_all else 0
                consec = first_pair_off - last_off - 1
                if consec <= 5: break
                must_by = last_off + 5
                if must_by < 1: break
                cands = [d for d in prefix_range
                         if d >= ed['start_day'] and d <= must_by
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
                random.shuffle(keys)  # 내부 셔플로 누가 어느 쌍 가는지 매번 달라짐
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
                prev_offs = [d for d in off_map[key] if d < w_days[0]]
                last_off = max(prev_offs) if prev_offs else 0
                forced = None
                if last_off > 0:
                    must_by = last_off + 5
                    cands_before = [d for d in avail if d <= must_by]
                    if cands_before:
                        forced = min(cands_before, key=lambda d: flex_off[br].get(d, 0))
                    elif avail:
                        forced = avail[0]

                best, best_score = None, float('inf')
                if forced is not None:
                    rest = [d for d in avail if d != forced and abs(d - forced) > 1]
                    if n_off == 2:
                        for d2 in rest:
                            score = flex_off[br].get(forced, 0) + flex_off[br].get(d2, 0)
                            if score < best_score:
                                best_score, best = score, (forced, d2)
                        if best is None and rest:
                            best = (forced, rest[-1])
                    else:
                        for i in range(len(rest)):
                            for j in range(i+1, len(rest)):
                                d2, d3 = rest[i], rest[j]
                                adj = (1 if abs(d2-d3)==1 else 0)
                                score = (flex_off[br].get(forced,0) + flex_off[br].get(d2,0)
                                         + flex_off[br].get(d3,0)) + adj * 100
                                if score < best_score:
                                    best_score, best = score, (forced, d2, d3)

                if best is None:
                    if n_off == 2:
                        for i in range(len(avail)):
                            for j in range(i+1, len(avail)):
                                d1, d2 = avail[i], avail[j]
                                if abs(d1 - d2) == 1: continue
                                score = flex_off[br].get(d1, 0) + flex_off[br].get(d2, 0)
                                if score < best_score:
                                    best_score, best = score, (d1, d2)
                    else:
                        for i in range(len(avail)):
                            for j in range(i+1, len(avail)):
                                for k in range(j+1, len(avail)):
                                    d1, d2, d3 = avail[i], avail[j], avail[k]
                                    adj = (1 if abs(d1-d2)==1 else 0) + (1 if abs(d2-d3)==1 else 0)
                                    score = (flex_off[br].get(d1,0) + flex_off[br].get(d2,0)
                                             + flex_off[br].get(d3,0)) + adj * 100
                                    if score < best_score:
                                        best_score, best = score, (d1, d2, d3)

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

# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    print("직원 데이터 로드 중...")
    employees = fetch_employees()
    branches = sorted(
        set(merged_branch(e['branch']) for e in employees),
        key=lambda b: int(re.match(r'(\d+)', b).group(1)) if re.match(r'(\d+)', b) else 999
    )
    print(f"  → {len(employees)}명 / {len(branches)}개 지점 로드됨\n")

    # 1. 4~8월 전체 삭제 (구형 키 잔존 방지)
    print("━━ 4~8월 Firebase 데이터 삭제 ━━")
    for y, m in [(2026,4), (2026,5), (2026,6), (2026,7), (2026,8)]:
        url = fb_month_url(y, m)
        try:
            status, _ = http_request(url, method='DELETE')
            print(f"  DELETE {y}년 {m}월 → HTTP {status}")
        except Exception as e:
            print(f"  DELETE {y}년 {m}월 → 오류: {e}")

    # 2. 7월·8월 초기화 (순서대로 — overflow에 휴무일+사이클 상태 포함)
    prev_overflow = None  # 첫 달은 초기값 사용
    for y, m in [(2026,7),(2026,8)]:
        print(f"\n━━ {y}년 {m}월 초기화 ━━")
        all_data, overflow_off = build_month_schedule(employees, y, m, prev_overflow)
        # overflow_off: { key: { off_days:[...], pair_idx:int, weeks_used:int } }
        # off_days를 set으로 변환해서 다음달에 전달
        prev_overflow = {k: {**v, 'off_days': set(v['off_days'])} for k, v in overflow_off.items()}

        # 지점별 분류
        by_branch = {}
        for safe_key, entry in all_data.items():
            if not isinstance(entry, dict) or 'branch' not in entry: continue
            by_branch.setdefault(entry['branch'],{})[safe_key] = entry

        ok = err = skip = 0
        for branch in branches:
            if branch not in by_branch:
                print(f"  {branch}: 직원 없음 (스킵)")
                skip += 1
                continue
            url = fb_branch_url(y, m, branch)
            data = by_branch[branch]
            try:
                status, _ = http_request(url, method='PUT', data=data)
                mark = '✓' if status==200 else f'HTTP{status}'
                print(f"  {branch}: {mark} ({len(data)}명)")
                ok += 1
            except Exception as e:
                print(f"  {branch}: 오류 — {e}")
                err += 1

        print(f"  → 완료 {ok}개 / 오류 {err}개 / 스킵 {skip}개")

    print("\n모든 작업 완료!")

if __name__ == '__main__':
    main()
