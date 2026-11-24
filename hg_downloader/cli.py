from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from .core import (DEFAULT_SITE, Cancelled, DownloadError, Downloader, Options,
                   SiteClient, choose_episodes, parse_ref)


def nonnegative(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 10:
        raise argparse.ArgumentTypeError("应为 0 到 10 之间的整数")
    return number


def seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("秒数必须大于 0")
    return number


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="黄果视频下载器 · 粘贴视频页链接即可下载")
    result.add_argument("urls", nargs="*", help="视频页链接或视频 ID，可传多个")
    result.add_argument("--gui", action="store_true", help="打开桌面界面")
    result.add_argument("-i", "--input-file", type=Path, help="UTF-8 文本，每行一个链接，# 开头为注释")
    result.add_argument("-o", "--output", type=Path, default=Path("downloads"), help="保存目录（默认 downloads）")
    group = result.add_mutually_exclusive_group()
    group.add_argument("-e", "--episodes", help="指定集数，例如 1,3,5-8")
    group.add_argument("--all", action="store_true", help="下载全部已发布集数")
    result.add_argument("--stream", choices=("main", "hevc"), default="main", help="main 兼容编码（默认），hevc 节省空间")
    result.add_argument("--list", action="store_true", help="仅列出标题和剧集，不下载")
    result.add_argument("--json", action="store_true", help="以 JSON 输出列表，配合 --list")
    result.add_argument("--sample-seconds", type=seconds, help="只下载开头若干秒，文件名带 sample 标记")
    result.add_argument("--site", default=DEFAULT_SITE, help="输入纯数字 ID 时使用的网站域名")
    result.add_argument("--cookies", help="Netscape cookies.txt 文件，仅用于网站 API")
    result.add_argument("--ffmpeg", help="FFmpeg 可执行文件路径")
    result.add_argument("--ffprobe", help="FFprobe 可执行文件路径")
    result.add_argument("--retries", type=nonnegative, default=2, help="每集失败后的重试次数，默认 2")
    result.add_argument("--overwrite", action="store_true", help="重新下载并替换已有文件")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.gui or (not args.urls and not args.input_file):
        from .gui import run
        run()
        return 0
    if args.json and not args.list:
        parser().error("--json 需要配合 --list 使用")
    urls = list(args.urls)
    if args.input_file:
        try:
            urls += [line.strip() for line in args.input_file.read_text(encoding="utf-8-sig").splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
        except OSError as exc:
            print(f"读取链接列表失败：{exc}", file=sys.stderr)
            return 1
    urls = list(dict.fromkeys(urls))
    if not urls:
        print("链接列表为空。", file=sys.stderr)
        return 1
    client = None
    try:
        client = SiteClient(args.cookies)

        def report(event: dict):
            if event["kind"] == "progress":
                print(f"\r下载 {event['percent']:5.1f}%  {event['seconds']:.0f}s  {event['speed']}   ", end="", flush=True)
            else:
                print("\n" + event.get("message", ""), flush=True)

        options = Options(output=args.output, stream=args.stream, retries=args.retries,
                          overwrite=args.overwrite, sample_seconds=args.sample_seconds,
                          ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
        downloader = None if args.list else Downloader(client, options, report)
        failures = 0
        listings = []
        for url in urls:
            try:
                video = client.video(parse_ref(url, args.site))
                selected = choose_episodes(video, args.episodes, args.all)
                if args.list:
                    listings.append({"id": video.ref.video_id, "title": video.title, "url": video.ref.url,
                                     "episodes": [{"number": ep.number, "title": ep.title,
                                                   "duration": ep.duration, "selected": ep in selected}
                                                  for ep in video.episodes]})
                    if not args.json:
                        print(f"{video.title} [{video.ref.video_id}] · {len(video.episodes)} 集")
                        for ep in video.episodes:
                            print(f"  {ep.number:3d}  {ep.title}  {ep.duration:.0f} 秒")
                    continue
                for ep in selected:
                    try:
                        downloader.download(video, ep)
                    except Cancelled:
                        raise
                    except (DownloadError, OSError) as exc:
                        failures += 1
                        print(f"\n第 {ep.number} 集失败：{exc}", file=sys.stderr)
            except Cancelled:
                raise
            except (DownloadError, OSError) as exc:
                failures += 1
                print(f"\n处理失败：{url}\n{exc}", file=sys.stderr)
        if args.json:
            print(json.dumps(listings, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    except (KeyboardInterrupt, Cancelled):
        if client:
            client.cancel.set()
        print("\n已取消。", file=sys.stderr)
        return 130
    except (DownloadError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
