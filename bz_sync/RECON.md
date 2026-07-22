# 뷰티짱 정찰 결과 (Task 1) — 2026-07-22 (JSON API 확정, HTML 스크레이핑 불필요)

라이브 접속(본사 그룹계정)으로 데이터 소스를 **JSON API로 완전 확정**. 자격증명 값은 본 문서·로그·코드에 기록 안 함.

## 결론 (핵심)
뷰티짱 휴무 데이터는 **예약현황판(StatusBoardV2)의 AJAX JSON 엔드포인트**로 깔끔하게 나온다.
HTML 파싱·프레임셋 로딩·BeautifulSoup **전부 불필요**. 세션 쿠키만 있으면 same-origin POST 2개로 끝.

## 로그인
- URL `https://hasys.hairzzang.com/` (ASP.NET WebForms). 필드 `#strShopCode`/`#strId`/`#strPass`, 제출 `doLoginCheck()` 또는 `#btnSubmit`.
- 세션 쿠키 기반. 로그인 후 same-origin fetch/POST에 쿠키 자동 적용됨(라이브로 확인).

## 지점 컨텍스트 / 전환
- 로그인 시 컨텍스트 = **끌리메(본사)** — 본사엔 디자이너 없어 스케줄/휴무 화면이 전부 빔.
- 상단 **예약** 메뉴 → 예약현황판(StatusBoardV2) 안의 `<select id="seloidStore">`(21개, 20지점+본사)로 지점 선택.
- **중요:** BanList/ReservationList AJAX는 `seloidStore` 파라미터로 지점을 직접 받는다 → 화면에서 select를 바꿀 필요조차 없이 **POST body에 oidStore를 넣으면 됨.**
- 근무표 지점키 → oidStore 매핑은 `bz_sync/branch_stores.json`에 저장(20지점 전부 실측). 예: `01. 신사본점`=301477.

## 데이터 소스 (확정) — 지점당 월 1회 호출로 전월치 확보
### 1) 휴무(정본): `POST /CRM.reservation/StatusBoardV2-AjaxReservationBanList`
- body: `seloidStore={oid}&strDateS={YYYY-MM-DD}&strDateE={YYYY-MM-DD}&viewStaff=ALL`
- **strDateS~strDateE 날짜 범위 지원** → 한 달 범위 한 번에(신사점 7월 = 285건 확인).
- 응답: JSON 배열. 주요 필드:
  - `oidStaff`(int) — 담당자 ID
  - `strDate`("YYYY-MM-DD")
  - `n1DayHoliday`(1=종일 휴무, 0=시간대 부분금지) ← **종일 휴무만 = `n1DayHoliday===1`**
  - `n1BanGubun`("rv_staffconfig_holiday"=정기휴무 / "rv_ban"=예약금지)
  - `strBanReason`("담당자 휴무","휴무","병가","기타"…), `strTimeS`/`strTimeE`
- 실측 픽스처: `bz_sync/tests/fixtures/banlist_sinsa_2026_07.json`
- **파서 규칙:** `n1DayHoliday===1`인 항목만 종일 휴무로 집계 → `{oidStaff: set(strDate)}`.
  (n1DayHoliday=0 부분금지는 반차 후보나, 1차 범위에선 제외.)

### 2) oidStaff → 담당자명: `POST /CRM.reservation/StatusBoardV2-AjaxReservationList`
- 같은 body. 응답 JSON 객체에 `oidStaff` + **`strStaffName`** 포함 → oidStaff→이름 맵 구성.
- 실측: 신사 디자이너 예 847079=김효은, 857465=박세영, 858195=조향화, 860071=전혜원, 866628=기영원, 869936=강은채, 870040=박예진.
- 시스템/비디자이너 계정(제외 대상): 대기, 대기2, 당일취소, 전일취소, 업무, 지원, 네이버(신규), 네이버(기존), 결제변경, 소멸, 매장, 환불, 워크인, 유료, 무료 등.
- 실측 픽스처: `bz_sync/tests/fixtures/reservationlist_staffnames_sinsa.json`
- 주의: ReservationList 응답이 큼(신사 7월 152KB). 이름맵은 지점당 월 1회면 충분.
- 810013(31일 전일 휴무, rv_staffconfig_holiday)는 rv 맵에 없음 → 퇴사/비활성 추정. **근무표에 없는 이름/전일휴무 계정은 대조에서 미매칭 처리.**

## 봇 메커니즘 (확정)
Playwright로 로그인해 세션 확보 → Playwright `context.request.post()`(또는 로그인 후 쿠키를 꺼내 Python `requests`)로
지점별 위 2개 엔드포인트에 POST. **프레임셋·IE모드·long-poll frame_push 전부 회피됨**(그 함정은 화면 로딩에서만 발생).
Playwright evaluate 안 same-origin `fetch()`로도 정상 동작 확인함.

## 부적합으로 판정한 소스 (기록)
- 근태입력(page=Diligence): 일별 출퇴근 입력표, 월그리드 아님.
- 근태현황(ListByDiligence): 담당자별 월 집계(휴무일수 개수만), 날짜별 아님.
- 휴무캘린더(page=calendar): `div.day_View[date]` 달력이나 **로그인 shop(본사) 컨텍스트 고정** — seloidStore로 안 바뀜. 지점별 조회 불가라 탈락.

## 남은 확인(구현 중, 경미)
- `n1BanGubun`/`strBanReason` 값별 의미 확정 시 반차·연차 세분화 가능(1차는 종일휴무만).
- 디자이너가 그 달 예약이 0건이면 ReservationList에 이름이 안 나올 수 있음 → 근무표 이름을 기준축으로 두고 oidStaff 맵은 보강용.
