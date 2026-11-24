# HG Downloader

针对黄果短剧站点的视频下载器。提供中文桌面界面与命令行，默认适配
`https://n59j.aqkmowihz.cc`，也支持相同站点接口的镜像视频链接。

## 启动

需要 Python 3.10+、FFmpeg 和 FFprobe。桌面界面使用 Python 自带的 Tkinter，
无需 `pip install` 依赖。当前开发机器上的三个工具均已检测可用。

Windows 双击 **`start.bat`**，或执行：

```powershell
python run.py
```

1. 打开网站上的某个视频，复制形如 `https://n59j.aqkmowihz.cc/video/14117/` 的链接。
2. 粘贴链接，点击“解析剧集”。也可以直接输入视频 ID。
3. 选择保存目录和集数；Ctrl / Shift 可以多选，“全选剧集”可以下载整部。
4. 点击“下载所选剧集”，完成后点击“打开保存目录”。

首页链接只有站点地址，不指向具体视频，不能直接下载。链接中的统计查询参数会自动去除。
默认只下载链接对应的一集；从 `ep-2` 链接解析时会默认选中第二集。

## 手动构建 Windows 运行包

GitHub Actions 提供 **“手动构建 Windows 运行包”** 工作流，**仅手动触发**。
推送代码、提交 PR 或创建标签都不会自动构建。

1. 将 `.github/workflows/build-runtime.yml` 提交到仓库默认分支；工作流在默认分支存在后，才会显示手动运行入口。
2. 打开仓库 **Actions**，选择 **手动构建 Windows 运行包**。
3. 点击 **Run workflow**，选择需要构建的分支，再点击运行按钮。
4. 构建成功后，打开本次运行记录，在 **Artifacts** 下载 `hg-downloader-windows-x64`。
5. 解压下载的构建产物 ZIP，再解压其中的 `hg-downloader-windows-x64.zip`，保留完整的 `HG-Downloader` 目录。
6. 双击目录内的 `HG-Downloader.exe` 打开桌面界面；运行包自带 Python 和 Tkinter，无需另行安装 Python。

在解压目录中，也可以使用 PowerShell 启动命令行：

```powershell
.\HG-Downloader.exe --help
.\HG-Downloader.exe 14117 --all -o "D:\Videos"
```

运行包仍需要 **FFmpeg 和 FFprobe**。可将 FFmpeg 的 `bin` 目录加入系统 PATH，
或将该目录内的 `ffmpeg.exe`、`ffprobe.exe` 及其依赖 DLL 放入
`HG-Downloader/tools/`，也可以使用 `--ffmpeg`、`--ffprobe` 指定工具位置。
请保留运行包内全部依赖文件，不能只复制 exe。产物默认保留 14 天，过期后可再次手动构建。

## 命令行

```powershell
# 下载链接对应的一集
python run.py "https://n59j.aqkmowihz.cc/video/14117/ep-2/"

# 下载整部
python run.py 14117 --all -o "D:\Videos"

# 指定集数
python run.py 14117 -e "1,3"

# 只查看标题、集数和时长
python run.py 14117 --list
python run.py 14117 --list --json

# 多个视频或链接列表：列表为 UTF-8 文本，一行一个链接或 ID
python run.py 14117 15224 --all
python run.py -i urls.txt --all

# 下载 5 秒测试样本（流复制可能在关键帧处有少量时长偏差）
python run.py 14117 --sample-seconds 5

# 网站实际提供 HEVC 时可选，部分集没有此编码
python run.py 14117 --stream hevc

# 可选：传入自己导出的 Netscape Cookie 文件
python run.py 14117 --cookies cookies.txt

# 自定义工具位置
python run.py 14117 --ffmpeg "D:\FFmpeg\bin\ffmpeg.exe"

# 也支持模块入口
python -m hg_downloader 14117 --list
```

可用 `python run.py --help` 查看全部参数。CLI 批量任务会继续处理其他集，
有任一失败时返回退出码 1；全部成功或已存在时返回 0；取消返回 130。

## 下载行为

- 保存为 MP4，使用流复制，保留站点提供的视频质量和音频。
- 默认 `main` 编码；可手动选 `hevc`。所选编码不可用时会明确报错，避免误下预览流。
- 每集开始及失败重试时重新请求播放地址，携带接口返回的短期 CDN 请求头。
- 普通 HLS AES-128 交由 FFmpeg 处理。支持 MPEG-TS 和 HEVC/fMP4，取决于 FFmpeg 构建。
- 显示当前集进度；取消会终止 FFmpeg 并清理本次临时文件。
- 失败默认重试两次，尊重接口的 `Retry-After`；要求等待超过 30 秒时提示稍后再试。
- 输出先写临时目录，检查分片读取错误、视频轨道和时长，确认通过才发布为最终 MP4。
- 已有文件通过校验后跳过；`--overwrite` 可重新下载，成功前保留旧文件。
- 当前没有分片断点续传；失败或取消后重试会从该集开头重新下载。
- Cookie 按域名交给网站 API，不主动传入 FFmpeg 的媒体请求，也不复制到配置文件。

默认保存路径示例：

```text
downloads/
  视频名称 [14117]/
    14117_E001.mp4
    14117_E002.mp4
    14117_E001.hevc.mp4
    14117_E001.sample-5s.mp4
```

镜像链接以链接自身域名请求 API；纯 ID 使用 `--site` 指定域名。
下载器适配的是公开播放接口，账号权限由网站判断；不实现 DRM、验证码或付费权限绕过。
仅下载自己有权保存的内容。

## FFmpeg 安装与发现

执行下面两条命令检查：

```powershell
ffmpeg -version
ffprobe -version
```

工具查找顺序：命令行显式路径、系统 PATH、项目 `tools/` 目录。
FFprobe 会优先尝试与指定 FFmpeg 同目录的位置。若需要自行安装，可从
[FFmpeg 官方下载入口](https://ffmpeg.org/download.html) 获取合适的构建，
将其 `bin` 加入 PATH 后重新打开终端。项目没有捆绑 FFmpeg 二进制。

## GitHub 代码整合

整合了 [Alos21750/UAV-Downloader](https://github.com/Alos21750/UAV-Downloader)
的黄果页面解析和重试等待时间解析逻辑，固定来源提交为
`3cb9f07af934373a90ef1de822b5696efb98623c`。当视频元数据 API 不可用时，
使用公开页面的 `videoInitialData` 和分集链接作为备用解析。

派生代码在 `hg_downloader/vendor/uav_huangguo.py`，已改用标准库并支持用户提供的镜像。
下载流程、CLI 和中文界面是本项目实现。完整来源和许可证见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

另外查阅了 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的 FFmpeg 调用方式，以及
[N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) 的 HLS 下载说明。

## 验证

运行快速检查：

```powershell
python -m compileall -q hg_downloader run.py
python run.py 14117 --list --json
python run.py 14117 --sample-seconds 5
```

本次开发的 10 项回归测试使用本地 AES-128 HLS，覆盖完整下载、音视频封装、
已有文件跳过、缺失分片拒绝发布、取消清理、API 重试、HTML 备用解析和输入校验，
结果全部通过。按 AGENTS.md 要求，生成的单元测试类已在最终检查后清除；
详细结果见 [VERIFICATION.md](VERIFICATION.md)。

2026-11-24 已在目标站实际验证：获取三集元数据、第三方 HTML 备用解析、
H.264 / HEVC 样本下载，以及第二集完整下载。网站接口可能随更新变化。
本地实测文件放在 `downloads/verification/`，不纳入源码。

## 目录

```text
hg_downloader/
  core.py                    网站 API、下载和文件校验
  cli.py                     命令行与批量入口
  gui.py                     中文桌面界面
  vendor/uav_huangguo.py      复用的第三方解析逻辑
VERIFICATION.md              实测与回归结果
licenses/                   第三方许可证
run.py                      启动入口
start.bat                   Windows 双击启动
```
