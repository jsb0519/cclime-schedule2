import json, urllib.request
from datetime import datetime, timezone, timedelta

FB_BASE = 'https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app'
KST = timezone(timedelta(hours=9))

# 백업 대상: 당월 + 익월 + 다다음달 (미래월 수기데이터도 복구 가능하게)
MONTHS_AHEAD = 2


def read_month(y, m):
    req = urllib.request.Request(
        f'{FB_BASE}/schedule/{y}_{m:02d}.json',
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def write_snapshot(path, data):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{FB_BASE}/{path}.json',
        data=body, method='PUT',
        headers={'Content-Type': 'application/json; charset=utf-8'}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def emp_count(data):
    return sum(len(v) for v in data.values() if isinstance(v, dict))


def month_list(now, ahead):
    out = []
    for off in range(ahead + 1):
        mm = now.month + off
        yy = now.year + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        out.append((yy, mm))
    return out


def main():
    now = datetime.now(KST)
    snap_date = now.strftime('%Y-%m-%d')
    print(f'=== 근무표 스냅샷 저장: {snap_date} (당월+{MONTHS_AHEAD}개월) ===')

    saved = 0
    for i, (y, m) in enumerate(month_list(now, MONTHS_AHEAD)):
        try:
            data = read_month(y, m)
        except Exception as e:
            print(f'  {y}_{m:02d}: 읽기 실패 — {e}')
            continue
        if not data:
            print(f'  {y}_{m:02d}: 데이터 없음 (건너뜀)')
            continue

        # 월별 백업 — 미래월도 복구 가능 (핵심 안전망)
        try:
            write_snapshot(f'snapshots_v2/{snap_date}/{y}_{m:02d}', data)
            print(f'  {y}_{m:02d}: /snapshots_v2/{snap_date}/{y}_{m:02d} 저장 '
                  f'({len(data)}개 지점, {emp_count(data)}명)')
            saved += 1
        except Exception as e:
            print(f'  {y}_{m:02d}: v2 저장 실패 — {e}')

        # 당월은 기존 경로에도 저장해 앱의 스냅샷 리더(fbGetSnapshot) 호환 유지
        if i == 0:
            try:
                write_snapshot(f'snapshots/{snap_date}', data)
                print(f'  {y}_{m:02d}: /snapshots/{snap_date} (레거시·앱호환) 저장')
            except Exception as e:
                print(f'  레거시 저장 실패 — {e}')

    if saved == 0:
        print('저장할 데이터 없음')
    else:
        print(f'완료: {saved}개월 백업')


if __name__ == '__main__':
    main()
