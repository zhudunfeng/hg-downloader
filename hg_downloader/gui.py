"""Tk 桌面入口。网络与下载在工作线程执行，控件只在主线程更新。"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from .core import (Cancelled, DownloadError, Downloader, Options, SiteClient,
                   Video, parse_ref)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("HG Downloader · 视频下载器")
        available_height = max(640, root.winfo_screenheight() - 100)
        root.geometry(f"960x{min(920, available_height)}")
        root.minsize(780, min(800, available_height))
        root.configure(bg="#f5f6f8")
        self.events: queue.Queue[dict] = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.video: Video | None = None
        self.parsed_inputs: tuple[str, str] | None = None
        self.url = tk.StringVar()
        self.output = tk.StringVar(value=str(Path("downloads").resolve()))
        self.cookies = tk.StringVar()
        self.stream = tk.StringVar(value="兼容编码 (H.264)")
        self.status = tk.StringVar(value="粘贴视频详情页链接，点击解析剧集。")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f6f8")
        style.configure("TLabel", background="#f5f6f8", foreground="#171717", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Muted.TLabel", foreground="#475569")
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(14, 8))
        style.configure("Accent.TButton", background="#171717", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#404040"), ("disabled", "#e5e5e5")],
                  foreground=[("disabled", "#737373")])
        style.configure("TEntry", padding=7, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", rowheight=32, font=("Microsoft YaHei UI", 10), background="#ffffff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), padding=7)
        style.configure("Horizontal.TProgressbar", background="#a16207", troughcolor="#e8ecf0")

        body = ttk.Frame(root, padding=28)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(8, weight=1)
        ttk.Label(body, text="HG Downloader", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="视频链接 → 选择剧集 → 保存 MP4", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 24))
        ttk.Label(body, text="视频链接").grid(row=2, column=0, sticky="w", padx=(0, 16))
        self.url_entry = ttk.Entry(body, textvariable=self.url)
        self.url_entry.grid(row=2, column=1, sticky="ew")
        self.parse_button = ttk.Button(body, text="解析剧集", style="Accent.TButton", command=self.parse)
        self.parse_button.grid(row=2, column=2, padx=(12, 0))
        ttk.Label(body, text="视频页形如 /video/14117/；支持直接输入视频 ID。", style="Muted.TLabel").grid(row=3, column=1, columnspan=2, sticky="w", pady=(6, 14))
        ttk.Label(body, text="保存目录").grid(row=4, column=0, sticky="w")
        self.output_entry = ttk.Entry(body, textvariable=self.output)
        self.output_entry.grid(row=4, column=1, sticky="ew")
        self.folder_button = ttk.Button(body, text="选择目录", command=self.folder)
        self.folder_button.grid(row=4, column=2, padx=(12, 0))
        ttk.Label(body, text="Cookie 文件").grid(row=5, column=0, sticky="w", pady=10)
        self.cookies_entry = ttk.Entry(body, textvariable=self.cookies)
        self.cookies_entry.grid(row=5, column=1, sticky="ew")
        self.cookie_button = ttk.Button(body, text="选择文件", command=self.cookie_file)
        self.cookie_button.grid(row=5, column=2, padx=(12, 0))
        ttk.Label(body, text="可选；使用 Netscape cookies.txt 格式。", style="Muted.TLabel").grid(row=6, column=1, columnspan=2, sticky="w")

        toolbar = ttk.Frame(body)
        toolbar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(20, 10))
        self.title_label = ttk.Label(toolbar, text="尚未解析视频", font=("Microsoft YaHei UI", 12, "bold"))
        self.title_label.pack(side="left")
        self.stream_box = ttk.Combobox(toolbar, textvariable=self.stream,
                                     values=["兼容编码 (H.264)", "高效编码 (HEVC)"], width=20, state="readonly")
        self.stream_box.pack(side="right")
        table_frame = ttk.Frame(body)
        table_frame.grid(row=8, column=0, columnspan=3, sticky="nsew")
        self.table = ttk.Treeview(table_frame, columns=("number", "title", "duration"), show="headings", height=5, selectmode="extended")
        for key, label, width in [("number", "集数", 70), ("title", "剧集名称", 430), ("duration", "时长", 100)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=60, stretch=key == "title")
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)

        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=3, sticky="new", pady=12)
        self.select_button = ttk.Button(actions, text="全选剧集", command=lambda: self.table.selection_set(self.table.get_children()))
        self.select_button.pack(side="left")
        ttk.Label(actions, text="按住 Ctrl / Shift 多选", style="Muted.TLabel").pack(side="left", padx=12)
        self.download_button = ttk.Button(actions, text="下载所选剧集", style="Accent.TButton", command=self.download, state="disabled")
        self.download_button.pack(side="right")
        self.cancel_button = ttk.Button(actions, text="取消", command=self.stop, state="disabled")
        self.cancel_button.pack(side="right", padx=8)
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.grid(row=10, column=0, columnspan=3, sticky="ew")
        ttk.Label(body, textvariable=self.status, wraplength=790).grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 12))
        self.log = ScrolledText(body, height=5, wrap="word", font=("Microsoft YaHei UI", 9),
                                bg="#ffffff", fg="#475569", relief="flat", padx=10, pady=10, state="disabled")
        self.log.grid(row=12, column=0, columnspan=3, sticky="ew")
        ttk.Button(body, text="打开保存目录", command=self.open_output).grid(row=13, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.url_entry.bind("<Return>", lambda _: self.parse())
        self.url_entry.focus_set()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def folder(self):
        value = filedialog.askdirectory(initialdir=self.output.get() if Path(self.output.get()).is_dir() else None)
        if value:
            self.output.set(value)

    def cookie_file(self):
        value = filedialog.askopenfilename(filetypes=[("Cookie 文本", "*.txt"), ("所有文件", "*.*")])
        if value:
            self.cookies.set(value)

    def set_busy(self, value: bool):
        self.busy = value
        state = "disabled" if value else "normal"
        for widget in (self.parse_button, self.url_entry, self.cookies_entry, self.cookie_button,
                       self.output_entry, self.folder_button, self.select_button):
            widget.configure(state=state)
        self.stream_box.configure(state="disabled" if value else "readonly")
        self.download_button.configure(state="normal" if self.video and not value else "disabled")
        self.cancel_button.configure(state="normal" if value else "disabled")

    def work(self, operation):
        self.cancel.clear()
        self.set_busy(True)

        def target():
            try:
                operation()
            except Cancelled as exc:
                self.events.put({"kind": "message", "message": str(exc)})
            except Exception as exc:
                self.events.put({"kind": "error", "message": str(exc)})
            finally:
                self.events.put({"kind": "idle"})

        threading.Thread(target=target, daemon=True).start()

    def parse(self):
        if self.busy:
            return
        inputs = (self.url.get().strip(), self.cookies.get().strip())
        try:
            ref = parse_ref(inputs[0])
        except DownloadError as exc:
            self.status.set(str(exc))
            return
        self.video = None
        self.parsed_inputs = None
        self.table.delete(*self.table.get_children())
        self.progress["value"] = 0
        self.status.set("正在获取标题和剧集列表…")

        def operation():
            video = SiteClient(inputs[1] or None, cancel=self.cancel).video(ref)
            if self.cancel.is_set():
                raise Cancelled("已取消。")
            self.events.put({"kind": "video", "video": video, "inputs": inputs})
        self.work(operation)

    def download(self):
        if self.busy or not self.video:
            return
        if self.parsed_inputs != (self.url.get().strip(), self.cookies.get().strip()):
            self.status.set("链接或 Cookie 已修改，请重新解析剧集。")
            return
        numbers = {int(key) for key in self.table.selection()}
        episodes = [ep for ep in self.video.episodes if ep.number in numbers]
        if not episodes:
            self.status.set("请先选择要下载的剧集，也可点击“全选剧集”。")
            return
        if not self.output.get().strip():
            self.status.set("请选择保存目录。")
            return
        video = self.video
        cookie_file = self.cookies.get().strip() or None
        options = Options(output=Path(self.output.get()), stream="hevc" if "HEVC" in self.stream.get() else "main")
        self.progress["value"] = 0

        def operation():
            downloader = Downloader(SiteClient(cookie_file, cancel=self.cancel), options, self.events.put)
            failures = 0
            for index, ep in enumerate(episodes, 1):
                if self.cancel.is_set():
                    raise Cancelled("已取消。")
                self.events.put({"kind": "message", "message": f"正在处理 {index}/{len(episodes)} · 第 {ep.number} 集"})
                try:
                    downloader.download(video, ep)
                except Cancelled:
                    raise
                except (DownloadError, OSError) as exc:
                    failures += 1
                    self.events.put({"kind": "error", "message": f"第 {ep.number} 集失败：{exc}"})
            self.events.put({"kind": "message", "message": f"处理完成：{len(episodes) - failures} 集成功或已存在，{failures} 集失败。"})
        self.work(operation)

    def stop(self):
        self.cancel.set()
        self.status.set("正在取消并清理临时文件…")
        self.cancel_button.configure(state="disabled")

    def open_output(self):
        try:
            path = Path(self.output.get()).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as exc:
            self.status.set(f"无法打开目录：{exc}")

    def poll(self):
        for _ in range(150):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event["kind"]
            if kind == "idle":
                self.set_busy(False)
                if self.closing:
                    self.root.destroy()
                    return
            elif kind == "video":
                self.video = event["video"]
                self.parsed_inputs = event["inputs"]
                self.title_label.configure(text=f"{self.video.title} · {len(self.video.episodes)} 集")
                for ep in self.video.episodes:
                    self.table.insert("", "end", iid=str(ep.number), values=(f"{ep.number:02d}", ep.title, f"{ep.duration / 60:.1f} 分钟" if ep.duration else "未知"))
                current = str(self.video.ref.episode)
                if self.table.exists(current):
                    self.table.selection_set(current)
                self.status.set("解析完成。请选择剧集，然后点击下载。")
            elif kind == "progress":
                self.progress["value"] = event["percent"]
                self.status.set(f"当前集 {event['percent']:.1f}% · 已处理 {event['seconds']:.0f} 秒 · {event['speed']}")
            else:
                if kind == "start":
                    self.progress["value"] = 0
                elif kind in ("done", "skipped"):
                    self.progress["value"] = 100
                message = event.get("message", "")
                self.status.set(message[:180])
                self.log.configure(state="normal")
                self.log.insert("end", message + "\n")
                if int(self.log.index("end-1c").split(".")[0]) > 500:
                    self.log.delete("1.0", "100.0")
                self.log.see("end")
                self.log.configure(state="disabled")
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


def run():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
