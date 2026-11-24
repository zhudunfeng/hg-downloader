"""Adapted from Alos21750/UAV-Downloader, Apache-2.0.

Upstream: src/uav_downloader/sites/huangguo.py
Commit: 3cb9f07af934373a90ef1de822b5696efb98623c
Derived routines: _retry_after, _initial_data, _fetch_episodes_uncached.
Changes: stdlib HTMLParser instead of BeautifulSoup; mirror-aware URL matching;
return compact episode metadata; remove unrelated crawler infrastructure.
See THIRD_PARTY_NOTICES.md and licenses/UAV-Downloader-Apache-2.0.txt.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlsplit


def retry_after(value):
    """Parse a server cooldown without shortening the requested wait."""
    try:
        if str(value).strip().isdigit():
            return min(int(value), 86400)
        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo is None:
            return None
        return max(0, min(86400, (parsed - datetime.now(timezone.utc)).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_data = False
        self.chunks = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.in_data = attrs.get("id") == "videoInitialData" and attrs.get("type") == "application/json"
        if tag == "a" and "hg-web-play__ep" in attrs.get("class", "").split():
            self.links.append((attrs.get("data-ep-id", ""), attrs.get("href", "")))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False

    def handle_data(self, data):
        if self.in_data:
            self.chunks.append(data)


def page_metadata(html: str, url: str, video_id: str) -> dict:
    """Parse public page JSON and verify episode links belong to this series."""
    if len(html) > 4 * 1024 * 1024:
        raise ValueError("页面超过解析大小上限")
    page = _Page()
    page.feed(html)
    text = "".join(page.chunks)
    if len(text) > 1024 * 1024:
        raise ValueError("视频元数据超过大小上限")
    data = json.loads(text)
    if (not isinstance(data, dict) or str(data.get("id")) != video_id
            or str(data.get("ep")) != "1"):
        raise ValueError("页面视频标识不匹配")
    title = " ".join(str(data.get("title") or "").split())[:1000]
    if not title:
        raise ValueError("页面没有视频标题")
    origin = urlsplit(url)
    episodes, seen = [], set()
    tracking = data.get("trackingEpisodes") or {}
    if not isinstance(tracking, dict):
        tracking = {}
    for number, href in page.links:
        parsed = urlsplit(urljoin(url, href))
        if parsed.scheme != origin.scheme or parsed.netloc != origin.netloc or parsed.query or parsed.fragment:
            continue
        match = re.fullmatch(r"/video/([1-9][0-9]*)(?:/ep-([1-9][0-9]*))?/?", parsed.path)
        if not match or match[1] != video_id or number != (match[2] or "1"):
            continue
        if number in seen:
            continue
        seen.add(number)
        if len(seen) > 1000:
            raise ValueError("剧集数量超过解析上限")
        info = tracking.get(number) or {}
        episodes.append({"ep_num": int(number), "title": f"第{number}集", "status": 1,
                         "duration": info.get("drama_duration", 0) if isinstance(info, dict) else 0})
    if not episodes:
        raise ValueError("页面没有有效的剧集链接")
    return {"id": video_id, "title": title, "episodes": sorted(episodes, key=lambda item: item["ep_num"])}
