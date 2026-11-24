# 修复 Windows 运行包中文帮助编码异常

## Goal

修复 GitHub Actions Windows runner 使用 CP1252 编码输出中文帮助时发生的 UnicodeEncodeError，使手动运行包构建通过。

## Requirements

- 在冻结可执行文件中正确配置 UTF-8，不能只依赖构建进程环境变量。
- 保留 workflow_dispatch 作为唯一触发事件。
- 复用现有入口、打包方式与工具版本，最小化修复。
- 运行帮助检查必须覆盖重定向输出，并验证中文帮助内容。
- 新增配置附中文说明，不修改数据库实体，不保留临时测试类。

## Acceptance Criteria

- [x] 本地复现 CP1252 中文帮助输出失败。
- [x] 修复后的冻结程序在重定向输出时使用 UTF-8，中文帮助完整且退出码为 0。
- [x] 工作流语法、PowerShell 脚本及手动触发约束通过。
- [x] 保存根因和回归验证记录。

## Technical Approach

通过 PyInstaller `--python-option 'X utf8'` 写入冻结解释器的 UTF-8 预初始化参数；在现有验证步骤中捕获子进程输出字节，严格按 UTF-8 解码并断言包含中文帮助说明。

## Research References

- [research/utf8-runtime.md](research/utf8-runtime.md)：官方文档、PyInstaller 6.22.3 源码和冻结解释器环境变量限制。

## Out of Scope

- 自动触发、工具升级、下载业务重构和数据库变更。

## Technical Notes

- 用户提供的 GitHub 日志在 `argparse.print_help` 写入 cp1252 时失败。
- 当前包使用 PyInstaller 6.22.3、Python 3.14、console bootloader。
- 上次本地中文 Windows 验证只检查正常执行，未覆盖英文代码页。

## Verification

- 强制 CP1252 重定向源码帮助输出，复现 argparse UnicodeEncodeError。
- 旧冻结 exe 在中文 Windows 输出 GBK，新增严格 UTF-8 校验会拒绝。
- 直接执行修复后工作流原始构建和验证脚本，重新生成 ZIP 成功。
- 外层设置 PYTHONIOENCODING=cp1252、PYTHONUTF8=0，完整验证脚本通过。
- ZIP 解压后清空 PATH，冻结 stdout/stderr 中文均严格 UTF-8；帮助退出 0，参数错误退出 2。
- actionlint、YAML、PowerShell AST、内嵌 Python 编译和 git diff --check 通过。
- 没有新增 Python 业务方法或单元测试类。

## Bug Analysis

- 根因：隐含的本地代码页假设与跨环境测试缺口；冻结解释器默认使用 runner 的 CP1252。
- 之前漏检原因：中文本机 GBK 能表示帮助文本，交互式成功和退出码无法证明输出编码。
- 修复机制：在解释器预初始化阶段嵌入 X utf8，覆盖帮助与错误输出，不依赖构建环境变量。
- 回归机制：始终捕获原始字节、严格 UTF-8 解码并检查预期中文；已写入运行包契约。
- 远程验证：尚未推送，提交后发起新的手动运行；重跑旧提交不会包含修复。
