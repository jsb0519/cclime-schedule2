import json, re, urllib.request, urllib.parse, calendar, sys
from datetime import date

SHEET_ID = '1kXGHbBBIAIXoNkXbEXzck0oKGF9RYQddhO279HociSo'
GID      = '0'
FB_BASE  = 'https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app'
BELT_ORDER = ['골드','실버','블랙','레드','블루','퍼플','옐로우','화이트','실습생']

def fetch_gviz():
    url = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:json&gid={GID}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode('utf-8')
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    return json.loads(m.group())

def parse_date(cell):
    if not cell: return ''
    src = str(cell.get('f','')) + ' ' + str(cell.get('v',''))
    m = re.search(r'Date\((\d{4}),(\d+),(\d+)\)', src)
    if m: return f"{m.group(1)}-{int(m.group(2))+1:02d}-{int(m.group(3)):02d}"
    m = re.search(r'(\d{4})[.\-\s\/년]+(\d{1,2})[.\-\s\/월]+(\d{1,2})', src)
    if m: return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ''

def parse_employees(data):
    cols = data['table']['cols']
    rows = data['table']['rows']
    iB=iN=iR=iL=iD=iW=iE = -1

    def find_idx(items):
        nonlocal iB,iN,iR,iL,iD,iW,iE
        for i,c in enumerate(items):
            t = str(c.get('label') or c.get('v') or '').strip()
            if t=='지점': iB=i
            elif t=='이름': iN=i
            elif t in ('직무','직급','직무/직급'): iR=i
            elif t in ('벨트','등급','벨트/등급'): iL=i
            elif '입사' in t: iD=i
            elif '근무형태' in t: iW=i
            elif '퇴사' in t or '퇴직' in t: iE=i

    find_idx(cols)
    data_start = 0
    if iB<0 or iN<0:
        for ri in range(min(len(rows),5)):
            cells = [{'label': str((c or {}).get('f') or (c or {}).get('v') or '').strip()}
                     for c in (rows[ri].get('c') or [])]
            iB=iN=iR=iL=iD=iW=iE = -1
            find_idx(cells)
            if iB>=0 and iN>=0: data_start=ri+1; break

    if iB<0: iB=1
    if iN<0: iN=2
    if iR<0: iR=3
    if iL<0: iL=4
    if iD<0: iD=7
    if iW<0: iW=5

    def get_str(row, i):
        if i<0: return ''
        c_list = row.get('c') or []
        if i>=len(c_list): return ''
        c = c_list[i]
        return str((c or {}).get('f') or (c or {}).get('v') or '').strip()

    employees = []
    for row in rows[data_start:]:
        branch = get_str(row, iB)
        name   = get_str(row, iN)
        if not branch or not name: continue
        belt_raw = get_str(row, iL)
        belt = belt_raw if belt_raw in BELT_ORDER else '실습생'
        c_list = row.get('c') or []
        hire_date = parse_date(c_list[iD] if iD>=0 and iD<len(c_list) else None)
        work_type = get_str(row, iW)
        exit_date = ''
        if iE>=0 and iE<len(c_list):
            exit_date = parse_date(c_list[iE])
            if not exit_date:
                raw = get_str(row, iE)
                m2 = re.search(r'(\d{4})[.\-\s\/년]+(\d{1,2})[.\-\s\/월]+(\d{1,2})', raw)
                if m2: exit_date = f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
        employees.append({'branch':branch,'name':name,'role':get_str(row,iR),
                          'belt':belt,'hire_date':hire_date,'work_type':work_type,'exit_date':exit_date})
    return employees

def parse_work_type(s):
    dm = re.search(r'주\s*(\d)\s*일', s or '')
    hm = re.search(r'(\d+)\s*시간', s or '')
    return {'days': int(dm.group(1)) if dm else 5, 'hours': int(hm.group(1)) if hm else 8}

def get_slots(store_hours):
    r = [f'{h:02d}:00' for h in range(10, 21-store_hours+1)]
    return r if r else ['10:00']

def build_month_schedule(y, m, employees):
    dim = calendar.monthrange(y, m)[1]
    ROT = 2
    FW5 = {0:0,1:2,2:2,3:1,4:0,5:0,6:0}
    FW4 = {0:0,1:3,2:2,3:1,4:1,5:0,6:0}
    branch_load = {}  # 지점별 일별 출근 예정 인원
    emp_data = []

    for emp in employees:
        wt = parse_work_type(emp.get('work_type',''))
        store_hours = wt['hours'] + 1
        start_day, end_day = 1, dim
        hire = emp.get('hire_date','')
        if hire and len(hire)>=10:
            hy,hm_,hd = int(hire[:4]),int(hire[5:7]),int(hire[8:10])
            if hy>y or (hy==y and hm_>m): continue
            if hy==y and hm_==m: start_day = hd
        ex = emp.get('exit_date','')
        if ex and len(ex)>=10:
            ey,em_,ed_ = int(ex[:4]),int(ex[5:7]),int(ex[8:10])
            if ey<y or (ey==y and em_<m): continue
            if ey==y and em_==m: end_day = ed_

        key = emp['branch']+'||'+emp['name']
        avail = list(range(start_day, end_day+1))
        branch = emp['branch']
        if branch not in branch_load:
            branch_load[branch] = {d: 0 for d in range(1, dim+1)}
        for d in avail: branch_load[branch][d] += 1
        slots = get_slots(store_hours)
        py_dow = date(y, m, start_day).weekday()
        js_dow = (py_dow+1) % 7
        is_hire_month = bool(hire and len(hire)>=10 and int(hire[:4])==y and int(hire[5:7])==m)
        emp_data.append({'key':key,'emp':emp,'start_day':start_day,'end_day':end_day,
                         'avail':avail,'dpw':wt['days'],'sh':store_hours,
                         'slots':slots,'hire_dow':js_dow,'is_hire_month':is_hire_month,
                         'branch':branch})

    # 주 목록 (일요일 기준)
    weeks, wd = [], []
    for d in range(1, dim+1):
        wd.append(d)
        if date(y,m,d).weekday()==6 or d==dim: weeks.append(list(wd)); wd=[]

    off_map = {e['key']:set() for e in emp_data}
    for w_days in weeks:
        w_emp = []
        for ed in emp_data:
            avail = [d for d in w_days if ed['start_day']<=d<=ed['end_day']]
            if not avail: continue
            is_hire_week = ed['is_hire_month'] and w_days[0]<=ed['start_day']<=w_days[-1]
            if is_hire_week:
                tbl = FW4 if ed['dpw']<=4 else FW5
                n_off = min(tbl.get(ed['hire_dow'],0), len(avail))
            else:
                n_off = round(len(avail)*(7-ed['dpw'])/7)
            w_emp.append({'key':ed['key'],'avail':avail,'n_off':n_off,
                          'sd':ed['start_day'],'ed':ed['end_day'],'ihm':ed['is_hire_month'],
                          'branch':ed['branch']})
        w_emp.sort(key=lambda x:-x['n_off'])
        for we in w_emp:
            if not we['n_off']: continue
            no_off = set()
            if we['ihm']: sd=we['sd']; no_off={sd,sd+1,sd+2}
            if we['ed']<dim: no_off.add(we['ed'])
            # 매주 수요일은 전체 출근일 — 휴무 배정 불가
            no_off |= {d for d in we['avail'] if date(y, m, d).weekday() == 2}
            cands = [d for d in we['avail'] if d not in no_off]
            # 지점 내 출근 인원이 많은 날부터 휴무 배정 → 출근 인원 평균화 (최우선)
            b = we['branch']
            cands.sort(key=lambda d: -branch_load[b].get(d, 0))
            for d in cands[:we['n_off']]:
                off_map[we['key']].add(d); branch_load[b][d]-=1

    belt_idx = lambda b: BELT_ORDER.index(b) if b in BELT_ORDER else 8
    branch_list = {}
    for ed in emp_data:
        b=ed['emp']['branch']
        if b not in branch_list: branch_list[b]=[]
        branch_list[b].append({'key':ed['key'],'belt':ed['emp'].get('belt','화이트')})
    for arr in branch_list.values(): arr.sort(key=lambda x:belt_idx(x['belt']))
    base_off = {}
    for arr in branch_list.values():
        for pos,item in enumerate(arr): base_off[item['key']]=pos

    starts = {ed['key']:{} for ed in emp_data}
    for d in range(1, dim+1):
        by_b = {}
        for ed in emp_data:
            if d<ed['start_day'] or d>ed['end_day'] or d in off_map[ed['key']]: continue
            b=ed['emp']['branch']
            if b not in by_b: by_b[b]=[]
            by_b[b].append({'key':ed['key'],'slots':ed['slots'],'belt':ed['emp'].get('belt','화이트')})
        rot=(d-1)//ROT
        for workers in by_b.values():
            workers.sort(key=lambda x:belt_idx(x['belt']))
            for pos,w in enumerate(workers):
                starts[w['key']][str(d)]=w['slots'][(pos+rot)%len(w['slots'])]

    result = {}
    for ed in emp_data:
        key=ed['key']; emp=ed['emp']
        result[key]={'name':emp['name'],'branch':emp['branch'],'belt':emp.get('belt','화이트'),
                     'hire_date':emp.get('hire_date',''),'exit_date':emp.get('exit_date',''),
                     'work_type':emp.get('work_type',''),'shift_hours':ed['sh'],
                     'shift_slots':ed['slots'],'shift_base_offset':base_off.get(key,0),
                     'rotation_interval':ROT,'shift_starts':starts.get(key,{}),
                     'off_days':sorted(off_map[key]),'day_types':{}}
    return result

def fb_key(s): return re.sub(r'[.#$\[\]/ ]', '_', s)

def fb_get_branch(y, m, branch):
    """Firebase에서 해당 지점/월 데이터 읽기. 없으면 None 반환."""
    path = f'/schedule/{y}_{m:02d}/{fb_key(branch)}.json'
    url = FB_BASE + urllib.parse.quote(path, safe='/.=')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read().decode('utf-8')
    raw = json.loads(data)
    if not raw: return None
    # Firebase 키(특수문자→_)에서 원본 키(branch||name) 복원
    result = {}
    for v in raw.values():
        if isinstance(v, dict) and v.get('branch') and v.get('name'):
            result[v['branch'] + '||' + v['name']] = v
    return result if result else None

def fb_set_branch(y, m, branch, sched):
    branch_data = {fb_key(k):v for k,v in sched.items() if v.get('branch')==branch}
    path = f'/schedule/{y}_{m:02d}/{fb_key(branch)}.json'
    url = FB_BASE + urllib.parse.quote(path, safe='/.=')
    body = json.dumps(branch_data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='PUT',
                                  headers={'Content-Type':'application/json; charset=utf-8'})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()

def target_months(today):
    """당월 + 다음 2개월 반환."""
    result = []
    for offset in range(3):
        m = today.month + offset
        y = today.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        result.append((y, m))
    return result

def main():
    force = '--force' in sys.argv
    today = date.today()
    months = target_months(today)
    mode_label = ' [강제 재생성]' if force else ''
    print(f'=== 전체 지점 근무표 자동 초기화{mode_label} ({months[0][0]}/{months[0][1]}월 ~ {months[-1][0]}/{months[-1][1]}월) ===\n')

    print('직원 데이터 로드 중...')
    gviz = fetch_gviz()
    employees = parse_employees(gviz)
    print(f'직원 {len(employees)}명 로드 완료')

    branches = sorted(set(e['branch'] for e in employees),
                      key=lambda b: int(re.search(r'\d+',b).group()) if re.search(r'\d+',b) else 999)
    print(f'지점 수: {len(branches)}개\n')

    for y, m in months:
        print(f'── {y}년 {m}월 ──')
        sched = build_month_schedule(y, m, employees)
        skipped = created = added = 0
        for branch in branches:
            cnt = sum(1 for v in sched.values() if v.get('branch')==branch)
            if cnt == 0: continue
            try:
                existing = fb_get_branch(y, m, branch)
                if existing and not force:
                    # 신규 입사자 감지
                    missing = {k: v for k, v in sched.items()
                               if v.get('branch') == branch and k not in existing}
                    if missing:
                        merged = {**{fb_key(k): v for k, v in existing.items()},
                                  **{fb_key(k): v for k, v in missing.items()}}
                        path = f'/schedule/{y}_{m:02d}/{fb_key(branch)}.json'
                        url = FB_BASE + urllib.parse.quote(path, safe='/.=')
                        body = json.dumps(merged, ensure_ascii=False).encode('utf-8')
                        req = urllib.request.Request(url, data=body, method='PUT',
                                                     headers={'Content-Type':'application/json; charset=utf-8'})
                        with urllib.request.urlopen(req, timeout=15) as r: r.read()
                        print(f'  [{branch}] 신규 {len(missing)}명 추가 ✓')
                        added += 1
                    else:
                        print(f'  [{branch}] 이미 존재, 건너뜀')
                        skipped += 1
                else:
                    fb_set_branch(y, m, branch, sched)
                    label = '재생성' if (existing and force) else '생성'
                    print(f'  [{branch}] {cnt}명 {label} 완료 ✓')
                    created += 1
            except Exception as e:
                print(f'  [{branch}] 오류: {e}')
        print(f'  → 신규생성/재생성 {created}개, 신규입사자추가 {added}개, 건너뜀 {skipped}개\n')

    print('완료!')

if __name__ == '__main__':
    main()
