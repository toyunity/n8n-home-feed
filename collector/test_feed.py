import sqlite3, feed

def test_score_streak_rank_growth():
    rows = [("2026-11-01", 12, 10, 0), ("2026-11-03", 5, 20, 2), ("2026-11-04", 3, 60, 4)]
    s, streak, best, growth = feed.score(rows)
    assert (streak, best, growth) == (2, 3, 54)  # 11-01은 끊겨서 연속 2일
    assert s == 2 * 10 + 28 + 5.4

def test_topic_and_report(tmp_path=None):
    con = sqlite3.connect(":memory:")
    con.execute("create table snap(day text, id text, service text, rank int, author text, title text, url text, likes int, comments int, topic text, primary key(day,id))")
    kw = {"맛집": ["맛집", "카페"]}
    assert feed.topic_of("성수 카페 투어", kw) == "맛집" and feed.topic_of("주식", kw) == "기타"
    feed.save(con, "2026-11-01", [{"id": "a", "rank": 9, "title": "카페"}, {"id": "b", "rank": 1}], kw)
    feed.save(con, "2026-11-02", [{"id": "a", "rank": 2, "title": "카페", "likes": 30}], kw)
    r = feed.report(con)
    assert [x["streak_days"] for x in r] == [2] and r[0]["topic"] == "맛집"

if __name__ == "__main__":
    test_score_streak_rank_growth(); test_topic_and_report(); print("ok")
