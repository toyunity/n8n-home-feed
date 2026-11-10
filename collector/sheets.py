"""구글 시트 입출력. 자격 증명이 없으면 같은 내용을 data/ 폴더의 CSV·로그 파일로 남긴다.

시트 구성
- 설정: A열 주제, B열 판 코드(DATA·HEALTH·HOME 등), C열 키워드(쉼표 구분, 비우면 전체)  ← 의뢰인이 직접 고치는 곳
- 결과_YYYY-MM-DD: 그날 점수순 결과 (주제 열 포함)
- 로그: 실행 시각, 단계, 결과/오류 메시지
"""
import csv, json, os, datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data"
CONFIG = Path(__file__).parent / "config" / "topics.json"
COLUMNS = ["day", "topic", "score", "streak_days", "best_rank", "rank", "growth",
           "likes", "comments", "service", "author", "title", "url"]
HEADER = ["날짜", "주제", "점수", "연속노출일", "최고순위", "오늘순위", "반응증가",
          "좋아요", "댓글", "서비스", "작성자", "제목", "링크"]


def _book():
    sid, key = os.getenv("GOOGLE_SHEET_ID"), os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not (sid and key and Path(key).exists()):
        return None
    import gspread
    return gspread.service_account(filename=key).open_by_key(sid)


def _tab(book, title, cols=13):
    import gspread
    try:
        return book.worksheet(title)
    except gspread.WorksheetNotFound:
        return book.add_worksheet(title, rows=200, cols=cols)


def topics():
    """[{"topic": 주제, "code": 판 코드, "keywords": [...]}, ...]"""
    book = _book()
    if book:
        rows = _tab(book, "설정", 3).get_all_values()[1:]  # 첫 줄은 머리글
        return [{"topic": r[0].strip(), "code": r[1].strip().upper(),
                 "keywords": [w.strip() for w in (r[2] if len(r) > 2 else "").split(",") if w.strip()]}
                for r in rows if len(r) > 1 and r[0].strip() and r[1].strip()]
    return json.loads(CONFIG.read_text())["topics"]


def write_report(day, rows):
    values = [HEADER] + [[r[c] for c in COLUMNS] for r in rows]
    book = _book()
    if book:
        ws = _tab(book, f"결과_{day}")
        ws.clear()
        ws.update(values, "A1")
        return f"sheet:{ws.title}"
    DATA.mkdir(exist_ok=True)
    out = DATA / f"결과_{day}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
        csv.writer(f).writerows(values)
    return f"csv:{out.name}"


def log(stage, message, level="info"):
    row = [dt.datetime.now().isoformat(timespec="seconds"), level, stage, message]
    DATA.mkdir(exist_ok=True)
    with (DATA / "run.log").open("a", encoding="utf-8") as f:  # 시트가 실패해도 파일 로그는 남는다
        f.write("\t".join(row) + "\n")
    try:
        book = _book()
        if book:
            _tab(book, "로그", 4).append_row(row)
    except Exception as e:
        with (DATA / "run.log").open("a", encoding="utf-8") as f:
            f.write(f"{row[0]}\terror\tlog\t시트 로그 기록 실패: {e}\n")
