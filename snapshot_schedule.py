import json, urllib.request
from datetime import datetime, timezone, timedelta

FB_BASE = 'https://cclime-schedule-cb047-default-rtdb.asia-southeast1.firebasedatabase.app'
KST = timezone(timedelta(hours=9))

def main():
    now_kst = datetime.now(KST)
    y, m = now_kst.year, now_kst.month
    snap_date = now_kst.strftime('%Y-%m-%d')

    print(f'=== 근무표 스냅샷 저장: {snap_date} ({y}년 {m}월) ===')

    # 현재 월 전체 읽기
    req = urllib.request.Request(
        f'{FB_BASE}/schedule/{y}_{m:02d}.json',
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f'Firebase 읽기 실패: {e}'); return

    if not data:
        print('저장할 데이터 없음'); return

    # 스냅샷 저장
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req2 = urllib.request.Request(
        f'{FB_BASE}/snapshots/{snap_date}.json',
        data=body, method='PUT',
        headers={'Content-Type': 'application/json; charset=utf-8'}
    )
    try:
        with urllib.request.urlopen(req2, timeout=30) as r:
            r.read()
        emp_count = sum(len(v) for v in data.values() if isinstance(v, dict))
        print(f'저장 완료: /snapshots/{snap_date}/ ({len(data)}개 지점, {emp_count}명)')
    except Exception as e:
        print(f'Firebase 쓰기 실패: {e}')

if __name__ == '__main__':
    main()
