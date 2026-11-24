# GitHub Actions 手动构建运行包

## Goal

为当前 Python 桌面下载器增加 GitHub Actions，使用户可以手动构建并下载 Windows x64 运行包。

## Requirements

- 仅允许 `workflow_dispatch` 手动触发，不配置 push、pull_request、定时或发布触发。
- 复用 `run.py` 和现有 GUI/CLI，生成无需安装 Python 的 Windows 运行包。
- 保持 FFmpeg / FFprobe 由用户外部提供的现有约定，随包提供说明和第三方许可证。
- 上传构建产物到本次 Actions 的 Artifacts，缺少预期产物时明确失败。
- 每个新增配置参数都有中文解释，关键构建步骤输出中文日志。
- 更新 README，说明手动触发、下载和运行方式及外部工具要求。
- 不修改数据库实体，不保留本次生成的临时测试类。

## Acceptance Criteria

- [x] 工作流只有 workflow_dispatch 事件。
- [x] PyInstaller 打包可执行文件及 Python/Tkinter 运行依赖。
- [x] 运行包包含说明、来源记录和完整第三方许可证。
- [x] 工作流语法及构建相关静态检查通过。
- [x] 本地打包和运行冒烟检查通过，或明确记录无法验证的限制。
- [x] README 提供完整手动操作步骤。

## Technical Approach

使用 Windows runner、Python 3.14 x64 和固定版本 PyInstaller 6.22.3，从 `run.py` 创建 onedir 包。通过 `--console --hide-console hide-early` 同时保留终端输出和双击 GUI 体验；通过 `--contents-directory .` 让现有 `tools/` 查找位置与 exe 同级，无需修改业务代码。压缩为 `hg-downloader-windows-x64.zip` 并上传 Artifacts。

## Research References

- [research/runtime-build.md](research/runtime-build.md)：官方 Actions 版本、手动触发约束和 PyInstaller 运行路径契约。

## Decision

用户已明确授权为当前项目编写构建运行包的 Actions，并进一步确认必须手动触发。沿用已有 Windows 入口和外部 FFmpeg 契约，不需要额外产品决策。

## Out of Scope

- 自动触发、GitHub Releases、Docker、macOS/Linux 运行包。
- 下载业务逻辑重构、数据库变更、捆绑 FFmpeg。

## Technical Notes

- 当前为标准库 Python 项目，`pyproject.toml` 要求 Python >= 3.10。
- `run.py` 为统一入口，`start.bat` 表明现有主要使用场景为 Windows。
- `.trellis/workflow.md` 要求实现、研究和检查代理；按其流程推进。

## Verification

- Windows 10 x64、Python 3.14.4、PyInstaller 6.22.3：直接提取工作流原始构建/验证脚本执行，打包及压缩成功。
- ZIP 内 996 个条目、13,110,715 字节；核实 exe、Python DLL、Tkinter、Tcl 数据、说明和许可证齐全。
- 从 ZIP 解压到独立目录，清空 PATH 和 Python 环境路径后，`--help` 仍成功。
- 缺少 FFmpeg 时返回失败；临时工具占位验证同级 tools 查找正常，占位已清除。
- 实际启动冻结 GUI，核实主窗口标题后正常关闭，退出码 0。
- actionlint 1.7.11、YAML 手动事件断言、全部 3 段 PowerShell AST、compileall、git diff --check 通过。
- 现有 10 项离线回归测试全部通过；没有新增或保留本次生成的单元测试类。
- 尚未提交推送，GitHub 托管 runner 执行及 Artifacts 上传需要首次手动运行验证。
