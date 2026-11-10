import sqlite3, feed

def test_score_streak_rank_growth():
    rows = [("2026-11-01", 12, 10, 0), ("2026-11-03", 5, 20, 2), ("2026-11-04", 3, 60, 4)]
    s, streak, best, growth = feed.score(rows)
    assert (streak, best, growth) == (2, 3, 54)  # 11-01은 끊겨서 연속 2일
    assert s == 2 * 10 + 28 + 5.4

def test_score_without_reactions():  # 주제판 글은 좋아요·댓글이 없다
    s, streak, best, growth = feed.score([("2026-11-01", 4, None, None), ("2026-11-02", 2, None, None)])
    assert (s, streak, growth) == (2 * 10 + 29, 2, None)

def test_keyword_filter_and_report():
    assert feed.matches("아기 이유식", ["아기"]) and not feed.matches("주식", ["아기"]) and feed.matches("아무거나", [])
    con = sqlite3.connect(":memory:")
    con.execute("create table snap(day text, topic text, id text, service text, rank int, author text, title text, url text, likes int, comments int, primary key(day,topic,id))")
    feed.save(con, "2026-11-01", "건강", [{"id": "a", "rank": 9}, {"id": "b", "rank": 1}])
    feed.save(con, "2026-11-02", "건강", [{"id": "a", "rank": 2}])
    feed.save(con, "2026-11-02", "육아", [{"id": "c", "rank": 1, "likes": 5, "comments": 1}])
    r = feed.report(con)
    assert [(x["topic"], x["streak_days"]) for x in r] == [("건강", 2), ("육아", 1)]

if __name__ == "__main__":
    test_score_streak_rank_growth(); test_score_without_reactions(); test_keyword_filter_and_report(); print("ok")
