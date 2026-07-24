"""
⚠️ 위험 스크립트 — 7·8월 외 모든 달을 삭제하고 7·8월을 재생성한다(수기데이터 소실).
자동 실행 금지. 실행하려면 환경변수 CONFIRM_RESET=YES-DELETE-AND-REGENERATE 를 명시해야 한다.

6월 이전 Firebase 스케줄 삭제 후 7월·8월 재생성.
7월은 1~5일(화~일) 전체 출근, 6일(월요일)부터 자동 휴무 배정.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, urllib.request, urllib.parse, re
from init_schedule import (FB_BASE, fb_key, fb_set_branch, fetch_gviz,
                           parse_employees, build_month_schedule)

KEEP = {'2026_07', '2026_08'}

def list_schedule_months():
    url = FB_BASE + '/schedule.json?shallow=true'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode('utf-8'))
    return list(data.keys()) if data else []

def delete_month(month_key):
    path = f'/schedule/{month_key}.json'
    url = FB_BASE + urllib.parse.quote(path, safe='/.=')
    req = urllib.request.Request(url, method='DELETE',
                                 headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()

def write_month(y, m, employees, sched_start_day=1):
    sched = build_month_schedule(y, m, employees, sched_start_day=sched_start_day)
    branches = sorted(set(v['branch'] for v in sched.values()),
                      key=lambda b: int(re.search(r'\d+', b).group()) if re.search(r'\d+', b) else 999)
    for branch in branches:
        cnt = sum(1 for v in sched.values() if v.get('branch') == branch)
        if cnt == 0:
            continue
        fb_set_branch(y, m, branch, sched)
        print(f'  {branch}: {cnt}명 작성 완료')

def main():
    # 0. 안전장치 — 실수 실행 방지. 명시적 동의 환경변수 없으면 아무것도 안 함.
    if os.environ.get('CONFIRM_RESET') != 'YES-DELETE-AND-REGENERATE':
        print('⛔ 안전장치 작동: 이 스크립트는 7·8월 외 모든 달을 삭제하고 7·8월을 재생성합니다.')
        print('   (수기 입력한 근무표가 소실될 수 있습니다.)')
        print('   정말 실행하려면:')
        print('   CONFIRM_RESET=YES-DELETE-AND-REGENERATE python3 reset_schedule.py')
        sys.exit(1)

    # 1. 기존 달 목록 조회
    print('=== Firebase 스케줄 목록 조회 ===')
    months = list_schedule_months()
    print(f'현재 저장된 달: {months}')

    # 2. 7월·8월 제외 삭제
    to_delete = [m for m in months if m not in KEEP]
    if to_delete:
        print(f'\n삭제 대상: {to_delete}')
        for mk in to_delete:
            delete_month(mk)
            print(f'  삭제됨: {mk}')
    else:
        print('삭제할 달 없음')

    # 3. 직원 데이터 로드
    print('\n직원 데이터 로드 중...')
    gviz = fetch_gviz()
    employees = parse_employees(gviz)
    print(f'직원 {len(employees)}명 로드 완료')

    # 4. 7월 재생성 (1~5일 전체 출근, 6일부터 자동 휴무)
    print('\n=== 2026년 7월 재생성 (sched_start_day=6) ===')
    write_month(2026, 7, employees, sched_start_day=6)

    # 5. 8월 재생성 (정상)
    print('\n=== 2026년 8월 재생성 ===')
    write_month(2026, 8, employees, sched_start_day=1)

    print('\n완료!')

if __name__ == '__main__':
    main()
