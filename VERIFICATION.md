# 验证记录

验证日期：2026-11-24（Asia/Shanghai）。

## 自动回归

本次开发运行了 10 项本地回归测试，全部通过。使用临时 HTTP 服务与 FFmpeg
生成的合成 AES-128 HLS，不依赖目标网站：

| 验证项 | 结果 |
|---|---|
| 视频 URL、查询参数、默认集数、集数范围 | 通过 |
| 文件名净化、请求头注入拒绝 | 通过 |
| UAV 页面元数据和分集链接解析 | 通过 |
| UAV Retry-After 秒数和日期解析 | 通过 |
| 加密 HLS 下载、音视频封装、已有文件跳过 | 通过 |
| 元数据 API 失败后 HTML 备用解析、403 拒绝访问 | 通过 |
| 临时 API 失败后重试 | 通过 |
| 服务端要求长时间等待时不立即重试 | 通过 |
| 缺失分片时拒绝发布输出 | 通过 |
| 取消时回收 FFmpeg 并清理临时文件 | 通过 |

另外执行了桌面界面完整流程检查：解析本地视频、默认选择当前集、开始下载、
接收进度和完成事件、恢复按钮状态，最终生成一份有效 MP4。

按 AGENTS.md“每次代码生成的单元测试类在完成任务后自动清除”的要求，
测试代码在最终验证后移除，此处保留覆盖范围与结果。

## 目标站实测

| 项目 | 结果 |
|---|---|
| 视频 ID 14117 元数据 | 获取 3 集，时长分别为 360 / 325 / 479 秒 |
| UAV 派生 HTML 备用解析 | 正确返回 3 集 |
| 第一集 main 样本 | H.264 + AAC，5.087667 秒 |
| 第一集 HEVC 样本 | HEVC + AAC，5.066667 秒 |
| 第二集完整下载 | H.264 + AAC，325.103197 秒，48,041,169 字节 |
| 第二集 HEVC 不可用 | 正确报错，不替换为预览或其他编码 |

完整视频保存在 `downloads/verification/`，不包含在构建包内。

## 可重复执行的快速检查

在项目根目录执行：

```powershell
python -m compileall -q hg_downloader run.py
python run.py 14117 --list --json --all
python run.py 14117 --sample-seconds 5 -o downloads\verification
python run.py 14117 --sample-seconds 5 --stream hevc -o downloads\verification
python run.py 14117 -e 2 -o downloads\verification
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

网站检查需要当前网站可访问；站点接口和内容可能变化。样本按关键帧流复制，
所以可能比指定秒数略长。重复下载会先校验已有文件，再跳过。

## 打包

已验证 wheel 构建成功，并包含派生代码、完整上游 Apache 2.0 许可证和第三方来源说明。
FFmpeg / FFprobe 仍需通过系统 PATH、自定义路径或项目 tools 目录提供。

## GitHub Actions Windows 运行包

2026-11-24 新增 `.github/workflows/build-runtime.yml`，仅接受 `workflow_dispatch`。
目标环境为 `windows-2025`、Python 3.14 x64 和 PyInstaller 6.22.3。

在本机 Windows 10 x64、Python 3.14.4 的隔离构建环境中，直接执行工作流中的
构建与验证脚本，成功生成 `dist/hg-downloader-windows-x64.zip`。
压缩包包含完整的 `HG-Downloader/`，共 996 个条目、13,110,715 字节。

| 验证项 | 结果 |
|---|---|
| 工作流事件、权限及构建产物配置 | 仅手动事件、只读仓库、缺少产物时报错 |
| actionlint 1.7.11、YAML、三段 PowerShell AST | 通过 |
| 工作流原始构建脚本及 CLI `--help` | 通过 |
| ZIP 内 Python DLL、Tkinter、Tcl、说明和完整第三方许可证 | 齐全 |
| 解压后清空 PATH 和 Python 路径运行 CLI | 通过，无需系统 Python |
| 缺少 FFmpeg 及 exe 同级 tools 查找 | 按预期失败或找到本地工具 |
| 冻结 GUI 主窗口创建及正常关闭 | 通过，退出码 0 |
| 现有 10 项离线回归及 compileall | 全部通过 |

初选 PyInstaller 6.22.0 会为 `hide_console` 生成错误的重复引号，已通过实际打包
定位并升级至 6.22.3。文档与许可证在打包后复制，避免 `build/` 内生成的 spec
改变相对数据文件的解析路径。验证没有新增单元测试类。

首次 GitHub 托管构建在运行包 `--help` 检查中失败：冻结解释器选择了 CP1252，
输出中文描述时触发 `UnicodeEncodeError`。以下修复已在本地重新构建验证，
提交后需通过 Actions 的 Run workflow 发起新构建，确认托管执行与 Artifacts 上传。

### Windows 中文编码修复

打包参数增加 `--python-option 'X utf8'`，将 UTF-8 模式写入 exe 内的解释器参数。
检查步骤改为捕获 `--help` 的原始输出字节，严格按 UTF-8 解码并断言中文描述，
避免只依赖本机中文系统代码页。

2026-11-24 验证结果：

- 源码入口在强制 `PYTHONIOENCODING=cp1252` 并重定向输出时，复现相同异常。
- 旧运行包在本机输出 GBK 字节，不能通过新增的 UTF-8 内容校验。
- 原样执行修复后的工作流构建、检查和压缩脚本，全部通过。
- 设置 `PYTHONIOENCODING=cp1252`、`PYTHONUTF8=0` 后，工作流检查仍通过。
- 从 ZIP 解压运行包并清空 PATH，中文帮助和参数错误输出均可严格按 UTF-8 解码；
  帮助退出码为 0，参数错误退出码为 2。
- actionlint、YAML 手动触发约束、三段 PowerShell AST、内嵌 Python 语法检查通过。
- 未修改 Python 业务代码，未新增单元测试类。
