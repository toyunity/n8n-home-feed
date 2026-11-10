# 네이버 홈판 인기 게시물 수집 자동화 (n8n + Python + 구글 시트)

주제별로 네이버 모바일 홈피드(홈판)에 잘 뜨는 게시물을 매일 모아 점수를 매기고 구글 시트에 정리하는 자동화 예제입니다.
n8n이 일정과 흐름·오류 알림을 맡고, 수집·점수 계산·시트 기록은 파이썬이 맡습니다.

> 기본 실행은 **가상 샘플 데이터**(`collector/sample/`, 제목 앞에 `[샘플]`)로 동작합니다.
> 네이버 robots.txt는 메인 주소(`/`) 외 수집을 허용하지 않으므로, 실제 수집은 `LIVE_MODE=1`로 직접 켠 경우에만 동작하며 사용 책임은 실행하는 쪽에 있습니다.

## 구조

```
[n8n] 매일 08시 / 수동 실행
   └─ HTTP → [Python 수집기] POST /collect   비로그인 브라우저(Playwright)로 홈판 카드 수집 → SQLite에 날짜별 저장
   └─ 0건인가? ── 예 → 실패 처리(Stop and Error) ─┐
   └─ 아니오 → POST /publish   점수 계산 → 구글 시트 '결과_날짜' 탭 (시트 미연결 시 CSV)
[n8n] 오류 워크플로 ◀──────────────────────────────┘ 어느 노드에서 멈췄는지 '로그' 탭에 기록
```

| 파일 | 역할 |
|---|---|
| `workflows/homefeed-main.json` | 메인 워크플로 (일정, 수집 호출, 0건 검사, 기록) |
| `workflows/homefeed-error.json` | 오류 워크플로 (실패 단계·메시지를 로그로) |
| `collector/feed.py` | 수집(`collect_live`), 저장, 점수 계산(`score`) |
| `collector/sheets.py` | 구글 시트 읽기/쓰기 (gspread, 서비스 계정) |
| `collector/app.py` | n8n이 부르는 HTTP 서버 (표준 라이브러리) |

## '잘 뜬다'의 기준

하루치만으로는 판단이 어려워 날짜별 스냅샷을 쌓아 비교합니다.

```
점수 = 연속 노출일 × 10 + (31 − 최고 순위) + (좋아요+댓글 증가량) ÷ 10
```

## 실행 방법

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec n8n n8n import:workflow --separate --input=/workflows
docker compose exec n8n n8n publish:workflow --id=homefeedMain0001
docker compose exec n8n n8n publish:workflow --id=homefeedError001
docker compose restart n8n
```

http://localhost:5678 에서 워크플로를 열고 '수동 실행'으로 바로 돌려 볼 수 있습니다.
결과는 시트(연결 시) 또는 `collector/data/결과_날짜.csv`, 실행 기록은 `collector/data/run.log`에 남습니다.

## 자주 바꾸는 곳

| 바꾸고 싶은 것 | 고칠 곳 |
|---|---|
| 주제·키워드 | 구글 시트 '설정' 탭 (A열 주제, B열 쉼표 구분 키워드). 시트 미연결 시 `collector/config/keywords.json` |
| 실행 시각 | n8n '매일 08시' 노드 |
| 샘플 ↔ 실제 수집 | `.env`의 `LIVE_MODE=1`, `COLLECT_MODE=live` |
| 구글 시트 연결 | `.env`의 `GOOGLE_SHEET_ID`, `secrets/service-account.json` (서비스 계정을 시트에 편집자로 공유) |
| 스크롤 횟수·요청 간격 | `collector/feed.py`의 `collect_live(scrolls, delay_ms)` |
| 화면 구조가 바뀌었을 때 | `collector/feed.py`의 `EXTRACT_JS` 한 곳 |
| 오류 알림을 슬랙·텔레그램으로 | 오류 워크플로의 '로그 탭에 기록' 뒤에 노드 추가 |

## 막힐 수 있는 부분과 대응

| 문제 | 대응 |
|---|---|
| 홈판이 계정마다 다르게 보임 | 매번 새 브라우저 컨텍스트, 비로그인 기준으로 고정 |
| 화면 구조 변경 | 0건 수집도 실패로 처리해 즉시 알림 |
| 접속 차단 | 스크롤 간격 1.5초, 재시도 최대 2회, 403·429·캡차 감지 시 재시도 없이 중단하고 기록 |
| 시트 API 오류 | 로그는 파일에 먼저 쓰고 시트는 그다음 |

## 테스트

```bash
cd collector && python3 test_feed.py
```

## 라이선스

MIT
