<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

Use the `/trellis:start` command when starting a new session to:
- Initialize your developer identity
- Understand current project context
- Read relevant guidelines

Use `@/.trellis/` to learn:
- Development workflow (`workflow.md`)
- Project structure guidelines (`spec/`)
- Developer workspace (`workspace/`)

If you're using Codex, project-scoped helpers may also live in:
- `.agents/skills/` for reusable Trellis skills
- `.codex/agents/` for optional custom subagents

Keep this managed block so 'trellis update' can refresh the instructions.

<!-- TRELLIS:END -->



<!-- USER:START -->
- 所有方法上都需要有中文方法注释
- 实体字段上方需要有中文字段注释
- 业务逻辑关键方法需要有中文行注释
- 业务关键之处自动输出中文日志记录
- 异常内容信息需要是中文
- 方法入参出参需要有类型
- 每一个配置参数上必须存在中文解释
- 代码检索尽量使用codegraph cli或codegraph mcp
- 日期格式化使用 `yyyy-MM-dd HH:mm:ss`格式
- if 判断条件需要有中文注释,且必须跟大括号，保持代码可读性
- for 循环需要有中文注释,且必须跟大括号，保持代码可读性
- 当存在trellis时，使用trellis推进，计划自动创建任务并生成prd
- 每次代码生成的单元测试类在完成任务后自动清除
- 代码保证正确且精简，不要过度设计，尽量复用已存在的数据库实体，避免重复造轮子，必须新增或修改的数据库实体需要经过我的同意
<!-- USER:END -->