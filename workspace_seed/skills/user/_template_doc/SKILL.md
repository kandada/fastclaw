---
name: _template_doc
description: 文档型技能模板（无脚本）- 用一句话说明能力与触发时机，修改这里
---

## When to use
描述何时应该使用本技能（触发场景 / 关键词 / 用户意图）。

## Workflow
按步骤给出可执行的操作指引，模型会读取本文件后用 run_shell 自行执行：
1. 第一步：例如 `run_shell("...")`
2. 第二步：...
3. 第三步：...

## Constraints
- 需要遵守的约束、注意事项、边界条件

## References
同目录下可按需读取的资源（模型会自动看到资源清单，用 run_shell 读取）：
- reference.md：详细规范说明
- scripts/example.sh：可复用脚本

## Examples
- 用户："帮我做 X" → 依次执行 Workflow 步骤，产出 Y
