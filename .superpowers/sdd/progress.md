# 뷰티짱 대조 — 진행 원장

- 계획: docs/superpowers/plans/2026-07-22-beautyzzang-schedule-compare.md (JSON API 확정판)
- 브랜치: feature/beautyzzang-compare (base b03140b)

## 태스크 상태
- Task 1 (정찰): **완료** — 데이터소스 JSON API 확정. RECON.md, branch_stores.json, 픽스처 2종.
- Task 2 (banparse.py): 대기 (착수)
- Task 3 (names.py): 대기
- Task 4 (fb.py): 대기
- Task 5 (scrape.py): 대기 (라이브 스모크는 맥미니)
- Task 6 (sync.py+launchd): 대기 (라이브 스모크는 맥미니)
- Task 7 (index.html 프론트): 대기

## 핵심 확정 사실 (Task1)
- 휴무: POST /CRM.reservation/StatusBoardV2-AjaxReservationBanList, body seloidStore/strDateS/strDateE/viewStaff=ALL, 종일=n1DayHoliday==1. 날짜범위=월1회.
- 이름: POST /CRM.reservation/StatusBoardV2-AjaxReservationList → oidStaff+strStaffName.
- 지점→oidStore: branch_stores.json (신사=301477).
- HTML 파싱 불필요. Playwright 로그인→context.request.post.
