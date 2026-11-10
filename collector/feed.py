"""네이버 모바일 홈판 수집·저장·점수 계산.

주제마다 홈판의 '주제판'(경제, 건강 등)을 열어 노출된 게시물을 읽는다.
주제판이 없는 주제(예: 육아)는 여러 판을 묶어 읽고 제목 키워드로 걸러 낸다. HOME = 추천 홈피드.
"""
import json, sqlite3, time, datetime as dt
from pathlib import Path

DB = Path(__file__).parent / "data" / "feed.db"
SAMPLE = Path(__file__).parent / "sample"

# 추천 홈피드 카드. 좋아요·댓글 수가 화면에 있다.
HOME_JS = """() => [...document.querySelectorAll('.chf_feed_card')].map(c => {
  const like = c.querySelector('.chf_btn_like');
  let p = {}; try { p = JSON.parse(like?.dataset.nlogParams || '{}') } catch (e) {}
  const nums = (c.querySelector('.chf_feed_activity')?.innerText || '').match(/\\d[\\d,]*/g) || [];
  const link = c.querySelector('.chf_feed_info a, a.chf_link_thumb');
  return { id: p.content_id, service: p.wvb_service,
    author: c.querySelector('.chf_name')?.innerText?.trim(),
    title: c.querySelector('.chf_feed_info')?.innerText?.trim() || '',
    url: link?.href, likes: +(nums[0] || '0').replace(/,/g, ''), comments: +(nums[1] || '0').replace(/,/g, '') }
}).filter(x => x.id)"""

# 주제판 카드. 제목·작성자·링크는 있지만 좋아요·댓글 수는 화면에 없다.
PANEL_JS = """(code) => {
  const root = document.querySelector(`[data-panel-code="${code}"]`);
  if (!root) return [];
  const seen = new Set(), out = [];
  for (const e of root.querySelectorAll('[data-nlog-params*="content_id"]')) {
    if (e.closest('[id*="AdSlot"],[id*="AdTemplate"]')) continue;          // 광고 제외
    const title = e.querySelector('[class*="_text_title"]')?.textContent?.trim();
    let p = {}; try { p = JSON.parse(e.dataset.nlogParams) } catch (x) {}
    if (!title || !p.content_id || seen.has(p.content_id)) continue;
    seen.add(p.content_id);
    out.push({ id: p.content_id, service: p.wvb_service || p.feers_item_type, title,
      author: e.querySelector('[class*="channel_name"]')?.textContent?.trim(),
      url: e.querySelector('a')?.href, likes: null, comments: null });
  }
  return out }"""


class Blocked(Exception):
    pass


def db():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""create table if not exists snap(day text, topic text, id text, service text, rank int, author text,
                   title text, url text, likes int, comments int, primary key(day, topic, id))""")
    return con


def matches(title, keywords):
    """키워드가 비어 있으면 전부 통과, 있으면 제목에 하나라도 들어간 글만."""
    return not keywords or any(k in (title or "") for k in keywords)


def collect_live(topics, scrolls=3, delay_ms=1500, retries=2):
    """topics = [{"topic": "재테크", "code": "DATA", "keywords": []},
                 {"topic": "육아", "code": "LIVINGHOME,LECTURE,LIVING", "keywords": ["육아", ...]}]
    비로그인 새 브라우저로 주제판을 차례로 열어 읽는다. 요청 간격·재시도 상한·차단 감지 포함."""
    from playwright.sync_api import sync_playwright
    for attempt in range(retries + 1):
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                ctx = b.new_context(**p.devices["iPhone 13"], locale="ko-KR")  # 새 컨텍스트 = 개인화 없음
                pg = ctx.new_page()
                res = pg.goto("https://m.naver.com/", wait_until="networkidle", timeout=30000)
                if res is None or res.status in (403, 429) or "captcha" in pg.url.lower():
                    raise Blocked(f"차단 의심: status={res and res.status} url={pg.url}")
                result = {}
                for t in topics:
                    items, seen = [], set()
                    for code in [c.strip() for c in t["code"].split(",") if c.strip()]:  # 판 코드는 여러 개 가능
                        if code == "HOME":
                            pg.evaluate("() => document.querySelector(`.nav_item[data-code='SEARCH'] a`)?.click()")
                        else:  # 상단 주제 탭을 눌러 해당 판을 연다
                            pg.evaluate("(c) => document.querySelector(`.nav_item[data-code='${c}'] a`).click()", code)
                        pg.wait_for_timeout(delay_ms * 2)
                        for _ in range(scrolls):
                            pg.mouse.wheel(0, 2500)
                            pg.wait_for_timeout(delay_ms)
                        raw = pg.evaluate(HOME_JS) if code == "HOME" else pg.evaluate(PANEL_JS, code)
                        for x in raw:
                            if x["id"] not in seen and matches(x.get("title"), t.get("keywords")):
                                seen.add(x["id"])
                                items.append(x)
                    for i, x in enumerate(items, 1):
                        x["rank"] = i  # 주제 안에서 위에서부터의 노출 순서
                    result[t["topic"]] = items
                b.close()
                return result
        except Blocked:
            raise  # 차단이면 재시도하지 않고 바로 멈춘다
        except Exception:
            if attempt == retries:
                raise
            time.sleep(5 * (attempt + 1))


def save(con, day, topic, items):
    for it in items:
        con.execute("insert or replace into snap values (?,?,?,?,?,?,?,?,?,?)",
                    (day, topic, it["id"], it.get("service"), it["rank"], it.get("author"), it.get("title", ""),
                     it.get("url"), it.get("likes"), it.get("comments")))
    con.commit()


def load_sample(con, topics):
    """샘플 모드: sample/day*.json(가상 데이터)을 날짜별로 넣는다. 반환: 마지막 날 주제별 건수."""
    wanted = {t["topic"] for t in topics}
    counts = {}
    for f in sorted(SAMPLE.glob("day*.json")):
        d = json.loads(f.read_text())
        counts = {}
        for topic, items in d["topics"].items():
            if topic in wanted:
                save(con, d["day"], topic, items)
                counts[topic] = len(items)
    return counts


def score(rows):
    """rows: 한 게시물의 날짜순 스냅샷 [(day, rank, likes, comments), ...]

    점수 = 연속 노출일 × 10 + (31 - 최고 순위, 최소 0) + 반응 증가량 ÷ 10
    반응 수(좋아요+댓글)가 없는 주제판 글은 반응 증가량을 0으로 본다.
    """
    days = [dt.date.fromisoformat(r[0]) for r in rows]
    streak = 1
    for a, b in zip(days[::-1], days[-2::-1]):  # 마지막 날부터 거꾸로 연속 일수
        if (a - b).days != 1:
            break
        streak += 1
    best = min(r[1] for r in rows)
    known = [(r[2] or 0) + (r[3] or 0) for r in rows if r[2] is not None]
    growth = known[-1] - known[0] if len(known) > 1 else None
    return round(streak * 10 + max(0, 31 - best) + max(0, growth or 0) / 10, 1), streak, best, growth


def report(con, per_topic=20):
    latest = con.execute("select max(day) from snap").fetchone()[0]
    out = []
    for (topic,) in con.execute("select distinct topic from snap where day=?", (latest,)).fetchall():
        rows_t = []
        for (pid,) in con.execute("select id from snap where day=? and topic=?", (latest, topic)).fetchall():
            hist = con.execute("select day, rank, likes, comments from snap where topic=? and id=? order by day",
                               (topic, pid)).fetchall()
            s, streak, best, growth = score(hist)
            rank, author, title, url, likes, comments, service = con.execute(
                "select rank, author, title, url, likes, comments, service from snap where day=? and topic=? and id=?",
                (latest, topic, pid)).fetchone()
            rows_t.append(dict(day=latest, topic=topic, score=s, streak_days=streak, best_rank=best, rank=rank,
                               growth="" if growth is None else growth, likes="" if likes is None else likes,
                               comments="" if comments is None else comments, service=service,
                               author=author, title=title, url=url))
        out += sorted(rows_t, key=lambda r: -r["score"])[:per_topic]
    return out
