from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote
import urllib.request
import html
import re
import tempfile
import subprocess
import os

PORT = int(os.environ.get("PORT", "8000"))

def write_json(handler, status, payload: str):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(payload.encode("utf-8"))

def is_safe_src(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        # 1) 원본 오디오 URL 추출
        if parsed.path == "/extract":
            qs = parse_qs(parsed.query)
            link = qs.get("link", [""])[0].strip()
            if not link:
                write_json(self, 400, '{"error":"link param required"}'); return
            try:
                iframe = re.search(r"src=['\"](.*?)['\"]", link, re.I)
                if iframe: link = iframe.group(1)

                m_vr = re.search(r"[0-9a-f]{32,}", link, re.I)
                if not m_vr:
                    write_json(self, 400, '{"error":"vr hash not found"}'); return
                vr = m_vr.group(0)

                player_url = f"https://m.dcinside.com/voice/player?vr={vr}&vr_open=1"
                req = urllib.request.Request(
                    player_url,
                    headers={
                        "User-Agent": UA,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "ko,en;q=0.9",
                        "Referer": "https://m.dcinside.com/",
                        "Cache-Control": "no-cache",
                    }
                )
                with urllib.request.urlopen(req) as r:
                    page = r.read().decode("utf-8", errors="replace")
                page = html.unescape(page)

                audio_url = None
                m1 = re.search(r"https://vr\.dcinside\.com/viewvoice\.php\?[^\"'<> ]+", page, re.I)
                if m1:
                    audio_url = m1.group(0)
                else:
                    for pat in [
                        r"<audio[^>]+src=['\"]([^'^\"]+)['\"]",
                        r"<source[^>]+src=['\"]([^'^\"]+)['\"]",
                        r"data-src=['\"]([^'^\"]+)['\"]",
                        r"['\"](https?:\/\/vr\.dcinside\.com\/viewvoice\.php\?[^\"'<> ]+)['\"]",
                    ]:
                        mm = re.search(pat, page, re.I)
                        if mm:
                            audio_url = mm.group(1); break

                if not audio_url:
                    write_json(self, 404, '{"error":"audio url not found"}'); return

                mp3_url = f"/to-mp3?src={quote(audio_url, safe='')}"
                write_json(self, 200, f'{{"ok":true,"audioUrl":"{audio_url}","mp3Url":"{mp3_url}"}}')
            except Exception as e:
                write_json(self, 500, f'{{"error":"{str(e)}"}}')
            return

        # 2) MP3 변환 다운로드
        if parsed.path == "/to-mp3":
            qs = parse_qs(parsed.query)
            src = qs.get("src", [""])[0].strip()
            if not src or not is_safe_src(src):
                self.send_response(400); self.end_headers(); self.wfile.write(b"Bad src"); return
            headers = "User-Agent: " + UA + "\r\nReferer: https://m.dcinside.com/\r\n"
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    tmp_path = tmp.name
                cmd = [
                    "ffmpeg", "-headers", headers, "-i", src,
                    "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    "-y", tmp_path
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                size = os.path.getsize(tmp_path)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Disposition", 'attachment; filename="voice.mp3"')
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with open(tmp_path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk: break
                        self.wfile.write(chunk)
            except FileNotFoundError:
                self.send_response(500); self.end_headers()
                self.wfile.write(b"ffmpeg not found on server")
            except subprocess.CalledProcessError as e:
                self.send_response(502); self.end_headers()
                self.wfile.write(f"ffmpeg failed: {e}".encode("utf-8"))
            except Exception as e:
                self.send_response(500); self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except: pass
            return

        # 3) 정적 파일
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/robots.txt":
            return self._serve_file("robots.txt", "text/plain; charset=utf-8")
        if path == "/sitemap.xml":
            return self._serve_file("sitemap.xml", "application/xml; charset=utf-8")
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return

        self.send_response(404); self.end_headers()

    def _serve_file(self, fname, ctype):
        try:
            with open(fname, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        except:
            self.send_response(404); self.end_headers()

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

if __name__ == "__main__":
    print(f"➡ Server running at 0.0.0.0:{PORT}")
    with HTTPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()