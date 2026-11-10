"""홈판 수집·저장·점수 계산. 표준 라이브러리 + Playwright만 사용."""
import json, sqlite3, time, datetime as dt
from pathlib import Path

DB = Path(__file__).parent / "data" / "feed.db"
SAMPLE = Path(__file__).parent / "sample"

# 브라우저 안에서 피드 카드를 읽는 스크립트. 화면 구조가 바뀌면 여기만 고치면 된다.
EXTRACT_JS = """() => [...document.querySelectorAll('.chf_feed_card')].map((c, i) => {
  const like = c.querySelector('.chf_btn_like');
  let p = {}; try { p = JSON.parse(like?.dataset.nlogParams || '{}') } catch (e) {}
  const nums = (c.querySelector('.chf_feed_activity')?.innerText || '').match(/\\d[\\d,]*/g) || [];
  const link = c.querySelector('.chf_feed_info a, a.chf_link_thumb');
  return { id: p.content_id, service: p.wvb_service, rank: i + 1,
    author: c.querySelector('.chf_name')?.innerText?.trim(),
    title: c.querySelector('.chf_feed_info')?.innerText?.trim() || '',
    url: link?.href, likes: +(nums[0] || '0').replace(/,/g, ''), comments: +(nums[1] || '0').replace(/,/g, '') }
}).filter(x => x.id)"""


class Blocked(Exception):
    pass


def db():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""create table if not exists snap(day text, id text, service text, rank int, author text,
                   title text, url text, likes int, comments int, topic text, primary key(day, id))""")
    con.execute("create table if not exists log(at text, level text, message text)")
    return con


def topic_of(title, keywords):
    """keywords = {"주제": ["키워드", ...]} → 제목에 처음 걸리는 주제, 없으면 '기타'."""
    for topic, words in keywords.items():
        if any(w in title for w in words):
            return topic
    return "기타"


def collect_live(scrolls=4, delay_ms=1500, retries=2):
    """비로그인 모바일 홈에서 피드를 읽는다. 요청 간격·재시도 상한·차단 감지 포함."""
    from playwright.sync_api import sync_playwright
    last = None
    for attempt in range(retries + 1):
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                ctx = b.new_context(**p.devices["iPhone 13"], locale="ko-KR")  # 새 컨텍스트 = 개인화 없음
                pg = ctx.new_page()
                res = pg.goto("https://m.naver.com/", wait_until="networkidle", timeout=30000)
                if res is None or res.status in (403, 429) or "captcha" in pg.url.lower():
                    raise Blocked(f"차단 의심: status={res and res.status} url={pg.url}")
                for _ in range(scrolls):
                    pg.mouse.wheel(0, 3000)
                    pg.wait_for_timeout(delay_ms)
                items = pg.evaluate(EXTRACT_JS)
                b.close()
                return items
        except Blocked:
            raise  # 차단이면 재시도하지 않고 바로 멈춘다
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise last


def save(con, day, items, keywords):
    for it in items:
        con.execute("insert or replace into snap values (?,?,?,?,?,?,?,?,?,?)",
                    (day, it["id"], it.get("service"), it["rank"], it.get("author"), it.get("title", ""),
                     it.get("url"), it.get("likes", 0), it.get("comments", 0), topic_of(it.get("title", ""), keywords)))
    con.commit()


def load_sample(con, keywords):
    """샘플 모드: sample/*.json(가상 데이터)을 날짜별 스냅샷으로 넣는다."""
    n = 0
    for f in sorted(SAMPLE.glob("day*.json")):
        d = json.loads(f.read_text())
        save(con, d["day"], d["items"], keywords)
        n = len(d["items"])
    return n  # 마지막 날 건수


def score(rows):
    """rows: 한 게시물의 날짜순 스냅샷 [(day, rank, likes, comments), ...]

    점수 = 연속 노출일 × 10 + (31 - 최고 순위, 최소 0) + 반응 증가량(좋아요+댓글) ÷ 10
    """
    days = [dt.date.fromisoformat(r[0]) for r in rows]
    streak = 1
    for a, b in zip(days[::-1], days[-2::-1]):  # 마지막 날부터 거꾸로 연속 일수
        if (a - b).days != 1:
            break
        streak += 1
    best = min(r[1] for r in rows)
    growth = (rows[-1][2] + rows[-1][3]) - (rows[0][2] + rows[0][3])
    return round(streak * 10 + max(0, 31 - best) + max(0, growth) / 10, 1), streak, best, growth


def report(con, limit=20):
    latest = con.execute("select max(day) from snap").fetchone()[0]
    out = []
    for (pid,) in con.execute("select id from snap where day=?", (latest,)).fetchall():
        rows = con.execute("select day, rank, likes, comments from snap where id=? order by day", (pid,)).fetchall()
        s, streak, best, growth = score(rows)
        day, rank, author, title, url, likes, comments, topic, service = con.execute(
            "select day, rank, author, title, url, likes, comments, topic, service from snap where id=? and day=?",
            (pid, latest)).fetchone()
        out.append(dict(day=day, topic=topic, score=s, streak_days=streak, best_rank=best, rank=rank,
                        growth=growth, likes=likes, comments=comments, service=service,
                        author=author, title=title, url=url))
    return sorted(out, key=lambda r: -r["score"])[:limit]
