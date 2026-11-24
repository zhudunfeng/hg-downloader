"""网站 API 适配与 FFmpeg 下载；仅使用 Python 标准库。"""

from __future__ import annotations

import collections
import http.cookiejar
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .vendor.uav_huangguo import page_metadata, retry_after

# 未指定镜像时，使用当前验证过的视频站点。
DEFAULT_SITE = "https://n59j.aqkmowihz.cc"
# 网站 API 和媒体请求共用的浏览器标识。
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
# Windows 下隐藏 FFmpeg 和 FFprobe 的独立控制台窗口。
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class DownloadError(Exception):
    """可向用户直接展示的错误。"""


class Cancelled(DownloadError):
    """用户取消当前解析或下载任务。"""


class RetryLater(DownloadError):
    """服务端要求较长冷却时间，当前任务不能立即重新取址。"""


def http_url(value: str) -> str:
    """校验无嵌入凭据和控制字符的 HTTP/HTTPS 地址。"""
    try:
        parsed = urllib.parse.urlsplit(value)
        # 拒绝非网页协议、缺失主机、嵌入凭据及非法空白字符。
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or re.search(r"[\x00-\x20\x7f]", value)):
            raise ValueError
        _ = parsed.port
    except ValueError as exc:
        raise DownloadError("请输入有效的 HTTP/HTTPS 网址。") from exc
    return value


def site_origin(value: str) -> str:
    """保留输入网址的协议和域名，供镜像站点请求使用。"""
    parsed = urllib.parse.urlsplit(http_url(value))
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class VideoRef:
    """视频详情页的定位信息，不保存追踪参数。"""

    # 视频所在镜像的协议和域名。
    origin: str
    # 网站分配的视频编号。
    video_id: str
    # 视频页指定的集数，默认第一集。
    episode: int = 1

    @property
    def url(self) -> str:
        """生成可用于请求来源校验的规范详情页链接。"""
        suffix = f"ep-{self.episode}/" if self.episode != 1 else ""
        return f"{self.origin}/video/{self.video_id}/{suffix}"


def parse_ref(value: str, site: str = DEFAULT_SITE) -> VideoRef:
    """解析视频编号或详情页链接，并移除追踪查询和片段。"""
    value = value.strip()
    # 纯数字按视频编号处理，其镜像由 site 参数指定。
    if re.fullmatch(r"[1-9]\d{0,18}", value):
        return VideoRef(site_origin(site), value)
    parsed = urllib.parse.urlsplit(http_url(value))
    match = re.fullmatch(r"/video/([1-9]\d{0,18})(?:/ep-([1-9]\d{0,8}))?/?", parsed.path)
    # 首页和其他路径不包含可供下载的视频定位信息。
    if not match:
        raise DownloadError("请粘贴视频详情页链接（/video/数字/），或直接输入视频 ID。首页不是视频链接。")
    return VideoRef(site_origin(value), match[1], int(match[2] or 1))


@dataclass(frozen=True)
class Episode:
    """可供用户选择的单集元数据。"""

    # 网站公布的正整数集数。
    number: int
    # 剧集名称，用于列表和日志展示。
    title: str
    # 预计时长，单位为秒；零表示未知。
    duration: float = 0


@dataclass
class Video:
    """视频标题及全部已发布剧集。"""

    # 视频详情页定位信息。
    ref: VideoRef
    # 用于界面展示和输出目录命名的视频标题。
    title: str
    # 已验证且按集数排序的剧集列表。
    episodes: list[Episode]


def positive_duration(value: object) -> float:
    """将网站或工具给出的时长转换为有限正数，异常值返回零。"""
    try:
        result = float(str(value))
        return result if math.isfinite(result) and result > 0 else 0
    except (ValueError, TypeError):
        return 0


def choose_episodes(video: Video, selection: str | None = None, all_episodes: bool = False) -> list[Episode]:
    """根据全部下载、集数表达式或详情页默认集数选择剧集。"""
    available = {ep.number: ep for ep in video.episodes}
    # 全集模式优先返回全部已发布剧集。
    if all_episodes:
        return sorted(video.episodes, key=lambda ep: ep.number)
    numbers: set[int] = set()
    # 显式集数支持逗号列表和闭区间，未指定时沿用详情页集数。
    if selection:
        # 逐段解析并合并集数，集合自动去除重复选择。
        for part in selection.replace("，", ",").split(","):
            match = re.fullmatch(r"\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*", part)
            # 不接受空项、零或其他非集数内容。
            if not match:
                raise DownloadError("集数格式应为 1,3,5-8。")
            start, end = int(match[1]), int(match[2] or match[1])
            # 拒绝倒序或过大的范围，防止无效输入占用大量内存。
            if end < start or end - start > 10000:
                raise DownloadError("集数范围无效。")
            numbers.update(range(start, end + 1))
    else:
        numbers.add(video.ref.episode)
    missing = sorted(numbers - available.keys())
    # 任何不存在的指定集数都应明确报错，避免静默漏下。
    if missing:
        raise DownloadError("以下集数不存在或尚未发布：" + ", ".join(map(str, missing)))
    return [available[number] for number in sorted(numbers)]


def safe_name(value: str, max_length: int = 60) -> str:
    """清理跨平台非法文件名字符，并限制名称长度。"""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value).strip(" .")[:max_length].rstrip(" .")
    value = value or "未命名"
    # Windows 保留设备名即使带扩展名也不能直接用作目录。
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", value):
        value = "_" + value
    return value


def log_message(message: str) -> str:
    """为中文业务日志添加 yyyy-MM-dd HH:mm:ss 格式的本地时间。"""
    return f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"


class SiteClient:
    """使用会话 Cookie 调用网站 API，并提供公开页面备用解析。"""

    def __init__(self, cookie_file: str | None = None, timeout: float = 25,
                 cancel: threading.Event | None = None) -> None:
        """初始化会话、单次请求超时秒数和可共享的取消信号。"""
        self.timeout = timeout
        self.cancel = cancel or threading.Event()
        cookies = http.cookiejar.MozillaCookieJar()
        # 只有显式提供文件时才加载用户的 Netscape Cookie。
        if cookie_file:
            try:
                cookies.load(cookie_file, ignore_discard=True, ignore_expires=False)
            except (OSError, http.cookiejar.LoadError) as exc:
                raise DownloadError("无法读取 Cookie 文件，请使用 Netscape cookies.txt 格式。") from exc
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(self, ref: VideoRef, route: str, post: bool = False) -> dict[str, Any]:
        """请求并校验 JSON 数据，按服务器冷却要求执行有限重试。"""
        # 短暂网络故障最多尝试三次，每次等待均可被用户取消。
        for attempt in range(3):
            delay = 1 + attempt
            # 发出每次请求前先响应取消操作。
            if self.cancel.is_set():
                raise Cancelled("已取消。")
            request = urllib.request.Request(
                ref.origin + route, data=b"{}" if post else None,
                headers={"User-Agent": USER_AGENT, "Referer": ref.url,
                         "Origin": ref.origin, "Accept": "application/json", "Content-Type": "application/json"},
            )
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                # 外层响应必须是包含业务状态的对象。
                if not isinstance(payload, dict):
                    raise DownloadError("网站返回的数据格式已变化。")
                status = payload.get("status", 1)
                # 明确拒绝的业务状态不得继续解析或取址。
                if status not in (1, "1"):
                    message = str(payload.get("msg") or payload.get("message") or "访问被拒绝")[:180]
                    raise DownloadError(f"网站未允许本次访问：{message}")
                data = payload.get("data")
                # 下载所需的元数据必须是对象，不能使用登录页等替代内容。
                if not isinstance(data, dict):
                    raise DownloadError("网站没有返回视频数据，可能需要登录或该视频已下架。")
                return data
            except urllib.error.HTTPError as exc:
                exc.close()
                # 权限问题直接交给用户处理，不自动重试。
                if exc.code in (401, 403):
                    raise DownloadError(f"网站返回 HTTP {exc.code}，请检查访问权限或提供有效 Cookie。") from exc
                # 仅重试可恢复状态，最后一次失败后终止请求。
                if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                    raise DownloadError(f"网站返回 HTTP {exc.code}，请检查链接和网站状态。") from exc
                cooldown = retry_after(exc.headers.get("Retry-After"))
                # 有效的 Retry-After 优先于本地重试间隔。
                if cooldown is not None:
                    # 较长冷却向外传播，避免下载重试层立即重新取址。
                    if cooldown > 30:
                        raise RetryLater(f"网站要求等待约 {cooldown:.0f} 秒，请稍后再试。") from exc
                    delay = cooldown
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # 网络故障已耗尽次数时给出中文连接提示。
                if attempt == 2:
                    raise DownloadError(f"无法连接网站：{getattr(exc, 'reason', exc)}") from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise DownloadError("网站返回的不是 JSON，可能是验证页或网站接口已变化。") from exc
            # 等待期间仍允许立即取消。
            if self.cancel.wait(delay):
                raise Cancelled("已取消。")
        raise DownloadError("请求失败。")

    def video(self, ref: VideoRef) -> Video:
        """获取视频标题和已发布剧集，必要时回退到公开页面解析。"""
        try:
            data = self.request(ref, f"/api/videos/{ref.video_id}")
        except DownloadError as exc:
            # UAV-Downloader 的公开 HTML 解析作为元数据接口变更时的备用路径。
            if not any(marker in str(exc) for marker in ("HTTP 404", "HTTP 405", "不是 JSON", "数据格式已变化", "没有返回视频数据")):
                raise
            data = self._page_video(ref)
        episodes: list[Episode] = []
        seen: set[int] = set()
        # 逐集校验类型、状态和重复编号，只保留已发布内容。
        for item in data.get("episodes") or []:
            # 非对象条目没有有效的剧集字段。
            if not isinstance(item, dict):
                continue
            try:
                number = int(item.get("ep_num", 0))
            except (TypeError, ValueError):
                continue
            # 跳过未发布、无效或重复集数。
            if number <= 0 or number in seen or item.get("status", 1) not in (1, "1"):
                continue
            seen.add(number)
            episodes.append(Episode(number, str(item.get("title") or f"第{number}集"),
                                    positive_duration(item.get("duration"))))
        # 没有分集列表时仅允许明确的单视频形式。
        if not episodes:
            # 单视频没有分集列表时，网站使用 video playback 路由。
            if data.get("episode_count") or data.get("episodes"):
                raise DownloadError("该视频暂时没有可下载的已发布剧集。")
            episodes = [Episode(1, "第1集", positive_duration(data.get("duration")))]
        return Video(ref, str(data.get("title") or ref.video_id), sorted(episodes, key=lambda ep: ep.number))

    def _page_video(self, ref: VideoRef) -> dict[str, Any]:
        """读取大小受限的公开详情页，复用上游项目的元数据解析。"""
        # 取消后不再触发备用网页请求。
        if self.cancel.is_set():
            raise Cancelled("已取消。")
        root_url = f"{ref.origin}/video/{ref.video_id}/"
        request = urllib.request.Request(root_url, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(4 * 1024 * 1024 + 1)
            # 限制页面体积，避免异常响应占用过多内存。
            if len(body) > 4 * 1024 * 1024:
                raise ValueError("页面过大")
            return page_metadata(body.decode("utf-8"), root_url, ref.video_id)
        except (OSError, ValueError, UnicodeError) as exc:
            raise DownloadError("API 和公开页面元数据均解析失败，请检查网站是否可访问。") from exc

    def playback(self, ref: VideoRef, episode: Episode, stream: str) -> tuple[str, dict[str, str]]:
        """获取匹配剧集的正片地址及短期 CDN 请求头。"""
        ref = VideoRef(ref.origin, ref.video_id, episode.number)
        route = f"/api/videos/{ref.video_id}/episodes/{episode.number}/playback"
        try:
            data = self.request(ref, route, post=True)
        except DownloadError as exc:
            # 仅第一集的分集路由缺失时，尝试网站的单视频播放路由。
            if "HTTP 404" not in str(exc) or episode.number != 1:
                raise
            data = self.request(ref, f"/api/videos/{ref.video_id}/playback", post=True)
        # 播放响应必须属于当前视频和集数，且清单使用 GET 获取。
        if (str(data.get("id")) != ref.video_id or str(data.get("ep")) != str(episode.number)
                or data.get("manifest_method") != "GET"):
            raise DownloadError("播放接口返回的剧集标识或清单格式不匹配。")
        streams = data.get("streams") or {}
        # 不使用 preview，以免把预览片段当成完整视频。
        media_url = streams.get(stream) if isinstance(streams, dict) else None
        # 没有指定正片流时明确失败，不使用预览替代。
        if not media_url:
            raise DownloadError(f"网站未提供 {stream} 正片流，请更换编码或检查登录权限。")
        http_url(media_url)
        cdn = data.get("cdn") or {}
        headers = {"Referer": ref.url, "User-Agent": USER_AGENT}
        # CDN 开启鉴权时使用播放接口提供的短期请求头。
        if cdn.get("m3u8Enabled") or cdn.get("otherEnabled"):
            key, value = cdn.get("authKey"), cdn.get("authValue")
            # 只有完整的键值对才能组成 CDN 鉴权头。
            if key and value:
                # 登录 Cookie 仅交给网站 API；CDN 请求使用播放接口返回的短期凭据。
                if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", str(key)) or str(key).lower() in {"cookie", "authorization", "host"}:
                    raise DownloadError("网站返回了无效的 CDN 请求头。")
                headers[str(key)] = str(value)
                # 网站提供应用标识时一并传给 CDN。
                if cdn.get("app"):
                    headers["x-cdn-app"] = str(cdn["app"])
        return media_url, headers


@dataclass
class Options:
    """命令行和桌面界面共用的下载配置。"""

    # 保存根目录，默认使用当前目录下的 downloads。
    output: Path = field(default_factory=lambda: Path("downloads"))
    # 正片编码：main 为兼容编码，hevc 为高效编码。
    stream: str = "main"
    # 单集下载失败后的重试次数，默认重试两次。
    retries: int = 2
    # 是否在下载校验成功后替换同名文件，默认保留已有文件。
    overwrite: bool = False
    # 仅保存开头指定秒数；None 表示下载完整正片。
    sample_seconds: float | None = None
    # FFmpeg 路径；None 表示自动查找 PATH 和 tools 目录。
    ffmpeg: str | None = None
    # FFprobe 路径；None 表示优先从 FFmpeg 同目录查找。
    ffprobe: str | None = None
    # FFmpeg 无进度时的最长等待秒数，默认两分钟。
    stall_timeout: float = 120


def find_tool(name: str, override: str | None = None, sibling: str | None = None) -> str:
    """按显式路径、同目录、PATH 和本地 tools 的顺序查找外部工具。"""
    # 用户指定的工具必须存在，不能静默改用其他版本。
    if override:
        resolved = shutil.which(override)
        # shutil.which 同时支持可执行文件名和完整路径。
        if resolved:
            return resolved
        raise DownloadError(f"找不到 {name}：{override}")
    # FFprobe 优先使用与 FFmpeg 一起分发的版本。
    if sibling:
        candidate = Path(sibling).with_name(name + (".exe" if os.name == "nt" else ""))
        # 同目录不存在时继续查找系统 PATH。
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(name)
    # 系统 PATH 没有工具时，再检查项目自带目录。
    if not resolved:
        local = Path(__file__).resolve().parents[1] / "tools" / (name + (".exe" if os.name == "nt" else ""))
        # 允许用户将工具直接放入 tools 目录。
        if local.is_file():
            return str(local)
        raise DownloadError(f"找不到 {name}。请将 FFmpeg 的 bin 目录加入 PATH，或将工具放入项目 tools 目录。")
    return resolved


def header_block(headers: dict[str, str]) -> str:
    """校验请求头并转换为 FFmpeg 要求的 CRLF 文本。"""
    # 所有动态请求头都应阻止换行和空字节注入。
    for key, value in headers.items():
        # 请求头名称只能包含协议允许的字符。
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key) or re.search(r"[\r\n\x00]", value):
            raise DownloadError("请求头格式不合法。")
    return "".join(f"{key}: {value}\r\n" for key, value in headers.items())


def redact(message: str) -> str:
    """隐藏 FFmpeg 诊断网址中的临时签名查询参数。"""
    return re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]+", r"\1?[已隐藏签名]", message)


def probe_media(ffprobe: str, path: Path, expected: float = 0) -> dict[str, Any]:
    """检查输出包含有效视频轨道，并验证其时长没有明显缺失。"""
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name",
             "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, creationflags=NO_WINDOW,
        )
        info = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise DownloadError("无法校验输出视频，请检查 FFprobe 是否可用。") from exc
    # 零字节、损坏文件或无视频轨道均不能认定为成功。
    if result.returncode or not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise DownloadError("输出文件中没有有效的视频轨道。")
    actual = positive_duration(info.get("format", {}).get("duration"))
    # 接受容器的少量时长误差，但拒绝明显缺片的输出。
    if not actual or (expected > 0 and actual < expected - max(0.5, min(3, expected * 0.02))):
        raise DownloadError(f"视频时长校验失败：输出 {actual:.1f} 秒，预期约 {expected:.1f} 秒，可能存在分片缺失。")
    return info


def stop_process(process: subprocess.Popen[str]) -> None:
    """终止仍在运行的子进程并等待回收，超时则强制结束。"""
    # 已经结束的 FFmpeg 无需再次发送终止信号。
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


class Downloader:
    """负责逐集取址、FFmpeg 下载、校验、原子发布及进度事件。"""

    def __init__(self, client: SiteClient, options: Options,
                 event: Callable[[dict[str, Any]], None] | None = None) -> None:
        """绑定网站会话、下载配置和可选的业务事件接收函数。"""
        self.client = client
        self.options = options
        self.cancel = client.cancel
        self.event = event or (lambda data: None)
        self.ffmpeg = find_tool("ffmpeg", options.ffmpeg)
        self.ffprobe = find_tool("ffprobe", options.ffprobe, sibling=self.ffmpeg)

    def emit(self, kind: str, **data: Any) -> None:
        """发送包含事件类型和业务字段的进度或结果通知。"""
        self.event({"kind": kind, **data})

    def download(self, video: Video, episode: Episode) -> Path:
        """下载单集到临时目录，校验通过后发布为最终 MP4。"""
        options = self.options
        directory = options.output.expanduser().resolve() / f"{safe_name(video.title)} [{video.ref.video_id}]"
        directory.mkdir(parents=True, exist_ok=True)
        suffix = f".sample-{options.sample_seconds:g}s" if options.sample_seconds else ""
        codec = ".hevc" if options.stream == "hevc" else ""
        target = directory / f"{video.ref.video_id}_E{episode.number:03d}{codec}{suffix}.mp4"
        expected = min(episode.duration, options.sample_seconds) if options.sample_seconds and episode.duration else (options.sample_seconds or episode.duration)
        # 保留已有文件前也必须校验，避免把损坏文件当成已完成。
        if target.exists() and not options.overwrite:
            # 不把零字节或上次外部产生的损坏文件视为已完成。
            probe_media(self.ffprobe, target, expected)
            self.emit("skipped", message=f"已存在，跳过：{target.name}", path=str(target))
            return target
        self.emit("start", message=f"{video.title} · 第 {episode.number} 集", duration=expected)
        # 每次重试都重新获取短期播放地址，不复用已过期签名。
        for attempt in range(options.retries + 1):
            # 用户取消后不创建新的临时下载任务。
            if self.cancel.is_set():
                raise Cancelled("已取消。")
            # 独立临时目录防止并行运行互相覆盖 .part 文件。
            import tempfile
            with tempfile.TemporaryDirectory(prefix=".hg-", dir=directory) as temporary:
                partial = Path(temporary) / "video.part.mp4"
                try:
                    media_url, headers = self.client.playback(video.ref, episode, options.stream)
                    self._ffmpeg(media_url, headers, partial, expected)
                    # 发布最终文件前再次确认用户没有取消。
                    if self.cancel.is_set():
                        raise Cancelled("已取消。")
                    info = probe_media(self.ffprobe, partial, expected)
                    # 下载期间有其他任务生成同名文件时，默认禁止覆盖。
                    if target.exists() and not options.overwrite:
                        raise DownloadError("目标文件在下载期间已生成，请检查其他下载任务。")
                    # 只有用户显式要求覆盖时，才替换原有完整文件。
                    if options.overwrite:
                        partial.replace(target)
                    else:
                        # 同一文件系统中通过硬链接原子地创建，防止并发覆盖现有文件。
                        os.link(partial, target)
                        partial.unlink()
                    self.emit("done", message=f"已保存：{target}", path=str(target), info=info)
                    return target
                except (Cancelled, RetryLater):
                    raise
                except DownloadError as exc:
                    # 达到配置的重试次数后保留失败原因。
                    if attempt == options.retries:
                        raise
                    self.emit("retry", message=f"下载失败，将重新获取地址重试 ({attempt + 1}/{options.retries})：{exc}")
                    # 重试等待同样允许取消，并由临时目录上下文负责清理。
                    if self.cancel.wait(2 * (attempt + 1)):
                        raise Cancelled("已取消。")
        raise DownloadError("下载失败。")

    def _ffmpeg(self, media_url: str, headers: dict[str, str], partial: Path, expected: float) -> None:
        """执行流复制下载，持续发送进度并拒绝缺失分片的输出。"""
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y", "-xerror",
                   "-rw_timeout", "20000000", "-headers", header_block(headers), "-i", media_url]
        # 样本模式限制保存时长，完整模式不截断正片。
        if self.options.sample_seconds:
            command += ["-t", str(self.options.sample_seconds)]
        command += ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart"]
        # 为 HEVC 写入兼容播放器常用的 MP4 编码标签。
        if self.options.stream == "hevc":
            command += ["-tag:v", "hvc1"]
        command += ["-progress", "pipe:1", "-nostats", "-f", "mp4", str(partial)]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        except OSError as exc:
            raise DownloadError(f"FFmpeg 启动失败：{exc}") from exc
        progress: queue.Queue[str] = queue.Queue()
        errors: collections.deque[str] = collections.deque(maxlen=12)
        missing_segments = threading.Event()

        def read_stdout() -> None:
            """读取 FFmpeg 标准输出，交给下载线程解析进度。"""
            # 独立读取线程持续排空管道，避免 FFmpeg 阻塞。
            for line in process.stdout:
                progress.put(line.strip())

        def read_stderr() -> None:
            """保存有限诊断行，并标记 FFmpeg 跳过或读取失败的分片。"""
            # 仅保存最近诊断，防止长期下载占用过多内存。
            for line in process.stderr:
                errors.append(line.rstrip())
                # HLS 解复用器可能跳过损坏分片后以 0 退出；必须额外检查其警告。
                if re.search(r"failed to open segment|failed to open an initialization section|error when loading first segment|segment .* failed too many times|skipping segment", line, re.I):
                    missing_segments.set()

        readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
        # 同时读取进度和诊断，两条管道互不阻塞。
        for reader in readers:
            reader.start()
        last_activity = time.monotonic()
        state: dict[str, str] = {}
        try:
            while process.poll() is None or not progress.empty():
                # 主下载线程响应取消，并在 finally 中回收子进程。
                if self.cancel.is_set():
                    raise Cancelled("已取消，未完成的临时文件已清理。")
                try:
                    line = progress.get(timeout=0.2)
                except queue.Empty:
                    # 长时间没有进度时终止任务，以便重新获取有效地址。
                    if time.monotonic() - last_activity > self.options.stall_timeout:
                        raise DownloadError("下载长时间无进展，可能是网络中断或播放地址已过期。")
                    continue
                last_activity = time.monotonic()
                key, _, value = line.partition("=")
                state[key] = value
                # FFmpeg 每组进度以 progress 字段结束，此时统一发布快照。
                if key == "progress":
                    elapsed = positive_duration(state.get("out_time_us")) / 1_000_000
                    self.emit("progress", seconds=elapsed, duration=expected,
                              percent=min(99.9, elapsed / expected * 100) if expected else 0,
                              speed=state.get("speed", ""), size=state.get("total_size", "0"))
            process.wait()
        finally:
            stop_process(process)
            # 子进程结束后等待读取线程收尾，再关闭管道。
            for reader in readers:
                reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
        # 返回码为零也可能跳过了分片，必须同时检查诊断标志。
        if process.returncode or missing_segments.is_set():
            detail = redact("\n".join(errors))[-1600:]
            reason = "存在缺失或无法读取的分片" if missing_segments.is_set() else f"退出码 {process.returncode}"
            raise DownloadError(f"FFmpeg 下载失败（{reason}）：\n{detail or '媒体请求失败'}")
