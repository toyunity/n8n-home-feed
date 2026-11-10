"""n8n이 HTTP Request 노드로 부르는 수집 서버 (표준 라이브러리 http.server).

POST /collect  {"mode": "sample"|"live"}  → 주제별 수집·저장, {"count": n, "by_topic": {...}, "empty_topics": [...]}
POST /publish                             → 점수 계산 후 시트(또는 CSV)에 기록, 결과 행 반환
POST /log      {"stage": "...", "message": "..."} → 오류 기록 (n8n 오류 워크플로가 호출)
GET  /health
"""
import json, os, datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import feed, sheets

LIVE_ALLOWED = os.getenv("LIVE_MODE") == "1"  # 실제 수집은 명시적으로 켠 경우에만


class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "live": LIVE_ALLOWED, "sheet": bool(sheets._book())})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or "{}")
        con = feed.db()
        try:
            if self.path == "/collect":
                return self._send(200, self.collect(con, body.get("mode", "sample")))
            if self.path == "/publish":
                rows = feed.report(con, per_topic=int(body.get("per_topic", 20)))
                where = sheets.write_report(rows[0]["day"], rows) if rows else "없음"
                sheets.log("publish", f"{len(rows)}건 기록 → {where}")
                return self._send(200, {"count": len(rows), "where": where, "rows": rows})
            if self.path == "/log":
                sheets.log(body.get("stage", "n8n"), body.get("message", ""), "error")
                return self._send(200, {"ok": True})
        except (BrokenPipeError, ConnectionResetError):
            pass  # 호출한 쪽이 응답 전에 끊음 (기록은 이미 끝남)
        except feed.Blocked as e:
            sheets.log("collect", str(e), "error")
            return self._send(503, {"error": str(e), "blocked": True})
        except Exception as e:
            sheets.log(self.path.strip("/"), repr(e), "error")
            return self._send(500, {"error": repr(e)})
        self._send(404, {"error": "not found"})

    def collect(self, con, mode):
        topics = sheets.topics()
        if mode == "live":
            if not LIVE_ALLOWED:
                raise RuntimeError("LIVE_MODE=1 환경 변수가 없어 실제 수집을 하지 않습니다")
            day = dt.date.today().isoformat()
            by_topic = {}
            for topic, items in feed.collect_live(topics).items():
                feed.save(con, day, topic, items)
                by_topic[topic] = len(items)
        else:
            by_topic = feed.load_sample(con, topics)
        # 주제 하나라도 0건이면 화면 구조 변경·차단을 의심한다 (n8n이 실패로 처리)
        empty = [t["topic"] for t in topics if not by_topic.get(t["topic"])]
        sheets.log("collect", f"{mode} 모드 " + ", ".join(f"{k} {v}건" for k, v in by_topic.items())
                   + (f" / 0건: {', '.join(empty)}" if empty else ""), "error" if empty else "info")
        return {"count": sum(by_topic.values()), "by_topic": by_topic, "empty_topics": empty, "mode": mode}


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
