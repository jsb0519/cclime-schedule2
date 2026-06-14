#!/usr/bin/env python3
"""
전지점 전체 월 스케줄 초기화 + 4월/5월 삭제
  - 삭제: 2026년 4월, 5월
  - 초기화: 2026년 6월, 7월, 8월 (전지점)
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
    branch_load = {}

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

        # 월말까지 재직이면 다음달 초 넘침 날짜까지 확장
        ext_end_day = (days_in_month + extra_days) if end_day == days_in_month else end_day

        mbranch = merged_branch(emp['branch'])
        key = mbranch + '||' + emp['name']
        avail_days = list(range(start_day, end_day+1))

        br = mbranch
        if br not in branch_load:
            branch_load[br] = {d:0 for d in range(1, days_in_month + extra_days + 1)}
        for d in avail_days:
            branch_load[br][d] += 1
        # 넘침 날짜 출근 인원 반영
        if end_day == days_in_month:
            for d in range(days_in_month + 1, days_in_month + extra_days + 1):
                branch_load[br][d] += 1

        slots = get_slots(store_hours)
        # JS getDay(): 0=Sun…6=Sat  ← Python weekday()+1 mod 7
        hire_dow_js = (date(y,m,start_day).weekday()+1) % 7
        is_hire_month = bool(hd and len(hd)>=10
                             and int(hd[:4])==y and int(hd[5:7])==m)
        emp_data.append({'key':key,'emp':{**emp,'branch':mbranch},'start_day':start_day,'end_day':end_day,
                         'ext_end_day':ext_end_day,'avail_days':avail_days,'days_per_week':days_per_week,
                         'store_hours':store_hours,'slots':slots,
                         'hire_dow':hire_dow_js,'is_hire_month':is_hire_month})

    # 주 목록: first_monday부터 시작, 마지막 주는 다음달 초까지 연장해 일요일 마감
    # Python: weekday()==6 이 일요일
    weeks, wd = [], []
    for d in range(first_monday, days_in_month + extra_days + 1):
        wd.append(d)
        actual_date = date(y, m, 1) + _td(days=d-1)
        if actual_date.weekday() == 6:
            weeks.append(list(wd)); wd = []
    if wd:
        weeks.append(list(wd))

    off_map = {ed['key']:set() for ed in emp_data}
    # 이전 달 마지막 주에서 넘어온 이 달 초 휴무일 선반영
    if prev_overflow_off and prefix_days > 0:
        for k, days in prev_overflow_off.items():
            if k in off_map:
                off_map[k].update(days)
    m_off_cnt = {br:{d:0 for d in range(1, days_in_month + extra_days + 1)} for br in branch_load}

    # 궤도 배정: 지점별 직원을 0=월화, 1=목금, 2=토일 그룹으로 균등 분배
    # Python weekday(): 0=월,1=화,2=수,3=목,4=금,5=토,6=일
    TRAJ_WDAYS = [(0,1),(3,4),(5,6)]  # [(월화),(목금),(토일)]
    emp_traj = {}
    b_emps_by_branch = {}
    for ed in emp_data:
        br = ed['emp']['branch']
        b_emps_by_branch.setdefault(br,[]).append(ed)
    for arr in b_emps_by_branch.values():
        arr.sort(key=lambda e: (belt_idx(e['emp'].get('belt','화이트')), e['emp']['name']))
        for i, ed in enumerate(arr):
            emp_traj[ed['key']] = (i + m) % 3

    # 날짜 d (넘침 가능)의 요일 계산 헬퍼 (Python weekday: 0=월,...,6=일)
    def day_weekday(d):
        return (date(y, m, 1) + _td(days=d-1)).weekday()

    def find_traj_pair(traj, w_days, c_set):
        wd1, wd2 = TRAJ_WDAYS[traj]
        d1 = next((d for d in w_days if day_weekday(d)==wd1 and d in c_set), None)
        d2 = next((d for d in w_days if day_weekday(d)==wd2 and d in c_set), None)
        return [d1,d2] if d1 and d2 else None

    for w_days in weeks:
        w_emp = []
        for ed in emp_data:
            available = [d for d in w_days if ed['start_day']<=d<=ed['ext_end_day']]
            if not available: continue
            off_per_week = 7 - ed['days_per_week']
            is_hire_week = (ed['is_hire_month']
                            and ed['start_day']>=w_days[0]
                            and ed['start_day']<=w_days[-1])
            if is_hire_week:
                table = FW4 if ed['days_per_week']<=4 else FW5
                n_off = min(table.get(ed['hire_dow'],0), len(available))
            else:
                n_off = round(len(available)*off_per_week/7)
            w_emp.append({'key':ed['key'],'available':available,'n_off':n_off,
                          'start_day':ed['start_day'],'end_day':ed['end_day'],
                          'is_hire_month':ed['is_hire_month'],'branch':ed['emp']['branch']})

        w_emp.sort(key=lambda x: (-x['n_off'], random.random()))

        for we in w_emp:
            if not we['n_off']: continue
            no_off = set()
            if we['is_hire_month']:
                no_off.update([we['start_day'], we['start_day']+1, we['start_day']+2])
            if we['end_day'] < days_in_month:
                no_off.add(we['end_day'])
            for d in we['available']:
                if day_weekday(d)==2: no_off.add(d)
            candidates = [d for d in we['available'] if d not in no_off]

            load = branch_load.get(we['branch'], {})
            n_off = we['n_off']
            candidates.sort(key=lambda d: (-load.get(d,0), random.random()))
            moc = m_off_cnt.get(we['branch'], {})

            def max_run(new_days):
                all_off = off_map[we['key']] | set(new_days)
                mx = 0
                for d in all_off:
                    if (d-1) not in all_off:
                        r = 0
                        while (d+r) in all_off: r += 1
                        if r > mx: mx = r
                return mx

            # 이전달 overflow 정보 없이 월초 prefix 날짜를 처리할 경우 역산 범위 제한
            trailing_lb = (first_monday if (prev_overflow_off is None
                           and prefix_days > 0 and w_days[0] == first_monday)
                           else we['start_day'])
            prev_trailing = 0
            d = w_days[0] - 1
            while d >= trailing_lb and d not in off_map[we['key']]:
                prev_trailing += 1
                d -= 1

            def ok_leading(first_day):
                return (prev_trailing + (first_day - w_days[0])) <= 6

            c_set = set(candidates)
            picked = []
            if n_off >= 2 and len(candidates) >= 2:
                # ① 궤도 선호 쌍 (okLeading·maxRun 통과 시)
                pair = find_traj_pair(emp_traj.get(we['key'],0), w_days, c_set)
                if pair and (max_run(pair) >= 4 or not ok_leading(pair[0])):
                    pair = None
                if not pair:
                    # ② mOffCnt 기반 균등화 (okLeading 하드 필터)
                    pairs = [[d, d+1] for d in candidates
                             if (d+1) in c_set and max_run([d,d+1]) < 4 and ok_leading(d)]
                    pairs.sort(key=lambda p: moc.get(p[0],0)+moc.get(p[1],0))
                    pair = pairs[0] if pairs else None
                if pair:
                    picked = list(pair)
                    if n_off > 2:
                        rem = [d for d in candidates if d not in picked]
                        picked += rem[:n_off-2]
                else:
                    safe = [d for d in candidates if max_run([d]) < 4 and ok_leading(d)]
                    if not safe:
                        safe = [d for d in candidates if max_run([d]) < 4]
                    picked = (safe if safe else candidates)[:min(n_off, len(candidates))]
            else:
                safe = [d for d in candidates if max_run([d]) < 4 and ok_leading(d)]
                if not safe:
                    safe = [d for d in candidates if max_run([d]) < 4]
                picked = (safe if safe else candidates)[:min(n_off, len(candidates))]

            for d in picked:
                off_map[we['key']].add(d)
                branch_load[we['branch']][d] -= 1
                m_off_cnt[we['branch']][d] += 1

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

    # 다음달 초 넘침 휴무 수집 (다음달 build_month_schedule에 prev_overflow_off로 전달)
    overflow_off = {}
    if extra_days > 0:
        for ed in emp_data:
            k = ed['key']
            over = [d - days_in_month for d in off_map[k] if d > days_in_month]
            if over:
                overflow_off[k] = over

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
            'off_days': sorted(d for d in off_map[key] if d <= days_in_month),
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

    # 1. 4월, 5월 삭제
    print("━━ 4월·5월 Firebase 데이터 삭제 ━━")
    for y, m in [(2026,4), (2026,5)]:
        url = fb_month_url(y, m)
        try:
            status, _ = http_request(url, method='DELETE')
            print(f"  DELETE {y}년 {m}월 → HTTP {status}")
        except Exception as e:
            print(f"  DELETE {y}년 {m}월 → 오류: {e}")

    # 2. 6월·7월·8월 초기화 (순서대로 — 이전달 넘침 휴무를 다음달에 전달)
    prev_overflow = {}  # 이전달 넘침 휴무 (key → [day, ...])
    for y, m in [(2026,6),(2026,7),(2026,8)]:
        print(f"\n━━ {y}년 {m}월 초기화 ━━")
        # prev_overflow의 키는 '브랜치||이름' 형식, Set으로 변환해 전달
        po = {k: set(days) for k, days in prev_overflow.items()} if prev_overflow else None
        all_data, overflow_off = build_month_schedule(employees, y, m, po)
        prev_overflow = overflow_off  # 다음달에 전달

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
