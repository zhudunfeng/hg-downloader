"""离线回归：本地 API、AES-128 HLS、输出校验、取消、错误与第三方备用解析。"""

import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from hg_downloader.core import (
    Cancelled, DownloadError, Downloader, Episode, Options, SiteClient, Video,
    choose_episodes, header_block, parse_ref, probe_media, safe_name,
)
from hg_downloader.vendor.uav_huangguo import page_metadata, retry_after


def page_html(video_id="42"):
    data = {"id": video_id, "ep": 1, "title": "测试剧集", "trackingEpisodes": {"1": {"drama_duration": 3}}}
    return '<script id="videoInitialData" type="application/json">' + json.dumps(data) + '</script>' + '''
    <a class="hg-web-play__ep" data-ep-id="1" href="/video/42/">01</a>
    <a class="hg-web-play__ep" data-ep-id="2" href="/video/42/ep-2/">02</a>
    <a class="hg-web-play__ep" data-ep-id="2" href="/video/42/ep-2/">重复</a>
    <a class="hg-web-play__ep" data-ep-id="3" href="https://other.example/video/42/ep-3/">外部</a>
    <a class="hg-web-play__ep" data-ep-id="4" href="/video/99/ep-4/">其他视频</a>
    <a class="hg-web-play__ep" data-ep-id="9" href="/video/42/ep-5/">不匹配</a>
    '''


class ParsingTests(unittest.TestCase):
    def test_link_and_episode_selection(self):
        ref = parse_ref("https://mirror.example/video/42/ep-2/?_gl=tracking#player")
        self.assertEqual((ref.video_id, ref.episode, ref.url), ("42", 2, "https://mirror.example/video/42/ep-2/"))
        video = Video(ref, "test", [Episode(n, str(n)) for n in range(1, 6)])
        self.assertEqual([e.number for e in choose_episodes(video)], [2])
        self.assertEqual([e.number for e in choose_episodes(video, "1,3-5,3")], [1, 3, 4, 5])
        with self.assertRaises(DownloadError):
            choose_episodes(video, "1,7")
        for url in ["https://mirror.example/", "https://u:p@mirror.example/video/42/", "file:///video/42/", "https://mirror.example/video/0/"]:
            with self.subTest(url=url), self.assertRaises(DownloadError):
                parse_ref(url)

    def test_paths_and_headers(self):
        self.assertEqual(safe_name("../bad:title?"), "_bad_title_")
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertEqual(header_block({"x-test": "ok"}), "x-test: ok\r\n")
        with self.assertRaises(DownloadError):
            header_block({"x-test": "ok\r\nCookie: injected"})

    def test_upstream_page_fallback(self):
        data = page_metadata(page_html(), "https://mirror.example/video/42/", "42")
        self.assertEqual(data["title"], "测试剧集")
        self.assertEqual([ep["ep_num"] for ep in data["episodes"]], [1, 2])
        self.assertEqual(data["episodes"][0]["duration"], 3)
        with self.assertRaises(ValueError):
            page_metadata(page_html("99"), "https://mirror.example/video/42/", "42")

    def test_upstream_retry_after(self):
        self.assertEqual(retry_after("12"), 12)
        self.assertIsNone(retry_after("not-a-date"))
        future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=20))
        self.assertTrue(18 <= retry_after(future) <= 20)


class ServerHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body, content_type="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        state = self.server.test_state
        path = urlsplit(self.path).path
        if path == "/api/videos/42":
            if state.get("fallback"):
                return self.respond(404, b"{}")
            if state.get("forbidden"):
                return self.respond(403, b"{}")
            data = {"title": "测试剧集", "id": 42, "episodes": [{"ep_num": 1, "title": "第一集", "duration": 3, "status": 1}]}
            return self.respond(200, json.dumps({"status": 1, "data": data}).encode())
        if path == "/video/42/":
            return self.respond(200, page_html().encode(), "text/html; charset=utf-8")
        if path == "/slow.m3u8":
            state["manifest_requested"].set()
            state["release_manifest"].wait(5)
            path = "/fixture.m3u8"
        if path == "/fixture.m3u8":
            if self.headers.get("x-cdn-auth") != "test-auth":
                return self.respond(403, b"missing header")
            body = (self.server.fixture_dir / "fixture.m3u8").read_bytes()
            if state.get("broken"):
                body = body.replace(b"segment0.ts", b"missing0.ts")
            return self.respond(200, body, "application/vnd.apple.mpegurl")
        file = self.server.fixture_dir / path.lstrip("/")
        if file.name == path.lstrip("/") and file.is_file():
            return self.respond(200, file.read_bytes(), "application/octet-stream")
        return self.respond(404, b"not found", "text/plain")

    def do_POST(self):
        state = self.server.test_state
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/api/videos/42/episodes/1/playback":
            return self.respond(404, b"{}")
        count = state.get("playback_calls", 0) + 1
        state["playback_calls"] = count
        if state.get("cooldown"):
            return self.respond(429, b"{}", extra={"Retry-After": "60"})
        if state.get("api_expired") and count == 1:
            return self.respond(500, b"{}", extra={"Retry-After": "0"})
        name = "slow.m3u8" if state.get("slow") else "fixture.m3u8"
        data = {"id": "42", "ep": 1, "manifest_method": "GET",
                "cdn": {"m3u8Enabled": True, "authKey": "x-cdn-auth", "authValue": "test-auth", "app": "150"},
                "streams": {"main": f"{self.server.origin}/{name}"}}
        return self.respond(200, json.dumps({"status": 1, "data": data}).encode())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 FFmpeg / FFprobe")
class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = cls.root / "fixture"
        cls.fixture.mkdir()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ServerHandler)
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"
        cls.server.origin = cls.origin
        cls.server.fixture_dir = cls.fixture
        cls.server.test_state = {}
        key = cls.fixture / "key.bin"
        key.write_bytes(bytes(range(16)))
        key_info = cls.fixture / "key-info.txt"
        key_info.write_text(f"{cls.origin}/key.bin\n{key.as_posix()}\n00000000000000000000000000000001\n")
        # 真正生成带密钥的 HLS，覆盖下载、解密、音视频封装全过程。
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "3",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "10", "-c:a", "aac",
            "-f", "hls", "-hls_time", "1", "-hls_list_size", "0", "-hls_key_info_file", str(key_info),
            "-hls_segment_filename", str(cls.fixture / "segment%d.ts"), str(cls.fixture / "fixture.m3u8"),
        ], check=True, capture_output=True, timeout=25)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def setUp(self):
        self.server.test_state = {}
        self.client = SiteClient()
        self.ref = parse_ref(f"{self.origin}/video/42/")
        self.out = Path(tempfile.mkdtemp(dir=self.root))

    def downloader(self, events=None):
        return Downloader(self.client, Options(output=self.out, retries=0), events.append if events is not None else None)

    def test_encrypted_download_and_existing_file(self):
        events = []
        video = self.client.video(self.ref)
        downloader = self.downloader(events)
        result = downloader.download(video, video.episodes[0])
        info = probe_media(downloader.ffprobe, result, 3)
        self.assertEqual({s["codec_type"] for s in info["streams"]}, {"video", "audio"})
        self.assertTrue(result.stat().st_size > 1000)
        calls = self.server.test_state["playback_calls"]
        self.assertEqual(downloader.download(video, video.episodes[0]), result)
        self.assertEqual(self.server.test_state["playback_calls"], calls)
        self.assertEqual(events[-1]["kind"], "skipped")
        self.assertFalse(list(self.out.rglob(".hg-*")))

    def test_api_fallback_and_access_refusal(self):
        self.server.test_state["fallback"] = True
        video = self.client.video(self.ref)
        self.assertEqual([ep.number for ep in video.episodes], [1, 2])
        self.server.test_state = {"forbidden": True}
        with self.assertRaisesRegex(DownloadError, "403"):
            self.client.video(self.ref)

    def test_transient_api_retry(self):
        self.server.test_state["api_expired"] = True
        self.client.playback(self.ref, Episode(1, "first"), "main")
        self.assertEqual(self.server.test_state["playback_calls"], 2)

    def test_server_cooldown_is_not_retried_by_download_loop(self):
        video = self.client.video(self.ref)
        self.server.test_state["cooldown"] = True
        downloader = Downloader(self.client, Options(output=self.out, retries=2))
        with self.assertRaisesRegex(DownloadError, "60"):
            downloader.download(video, video.episodes[0])
        self.assertEqual(self.server.test_state["playback_calls"], 1)

    def test_broken_segments_never_published(self):
        video = self.client.video(self.ref)
        self.server.test_state["broken"] = True
        with self.assertRaises(DownloadError):
            self.downloader().download(video, video.episodes[0])
        self.assertFalse(list(self.out.rglob("*.mp4")))
        self.assertFalse(list(self.out.rglob(".hg-*")))

    def test_cancel_reaps_process_and_cleans_partial(self):
        video = self.client.video(self.ref)
        self.server.test_state.update(slow=True, manifest_requested=threading.Event(), release_manifest=threading.Event())
        result = []

        def target():
            try:
                self.downloader().download(video, video.episodes[0])
            except Exception as exc:
                result.append(exc)

        worker = threading.Thread(target=target)
        worker.start()
        self.assertTrue(self.server.test_state["manifest_requested"].wait(5))
        self.client.cancel.set()
        worker.join(timeout=6)
        self.server.test_state["release_manifest"].set()
        self.assertFalse(worker.is_alive())
        self.assertTrue(result and isinstance(result[0], Cancelled))
        self.assertFalse(list(self.out.rglob("*.mp4")))
        self.assertFalse(list(self.out.rglob(".hg-*")))


if __name__ == "__main__":
    unittest.main()
