---
name: ship
description: Ship functional changes in the auckland-property-agent repository to origin/main and every affected live target, while checking for reusable code first and verifying the public result. Use for any requested code or feature change in this repository, and when the user says 上线、发布、推上去、push、deploy, or make it live.
---

# Ship Auckland Property Agent changes

全程用中文向用户汇报。这个项目的完成标准不是“本地改完”，而是相关验证通过、源码已同步到远程 `main`、受影响的线上目标已重新发布并验证。

## 修改前

1. 用 `git status --short --branch` 记录已有改动。把它们视为用户资产；不要覆盖、暂存或提交与当前任务无关的文件。
2. 先用 `rg` 搜索现有实现、工具函数、组件、脚本和配置。优先扩展已有抽象；只有职责确实不同才新增实现。
3. 确认本次任务的文件集合。若工作区已有无关改动，不要直接运行会 `git add -A` 的发布脚本；先把当前任务隔离到干净工作树，或只提交明确属于当前任务的路径。

## 实现与验证

- 保持改动聚焦，复用项目现有的数据契约、构建链路和测试闸门。
- 运行与风险相称的测试。网页发布必须先构建，再对实际生成的 `heatmap.html` 跑闸门测试。
- 测试失败时停止发布；不要为了变绿而削弱已有用例。若产品行为有意改变并需要更新用例，向用户说明原因。

## 发布

用户已把“功能修改后直接推送远程 `main` 并重新发布”记录为本项目的固定工作流。执行本技能覆盖的任务时，常规 push 和 deploy 不需要再次进行对话确认；仍需遵守平台弹出的权限审批，并在存在冲突、破坏性操作或无法隔离的无关改动时停止。

复用仓库现有发布实现，不再维护第二份脚本：

```bash
.claude/skills/ship/scripts/ship.sh "Describe the user-visible result"
```

该脚本会用线上代理地址构建页面、检查代理配置、对生成页面运行闸门、提交并推送源码、调用 `ops/publish.sh` 发布 GitHub Pages，并比较线上与本地页面的 SHA-256。提交信息要描述用户可见的结果，不要写笼统的 `Update` 或 `Fix bug`。

按改动目标处理：

- `scripts/`、页面模板、数据或评测变化：运行完整发布脚本。
- `ops/worker/` 变化：先按当前 Wrangler 规范部署 `auckland-suburb-agent`，再运行页面发布脚本；Worker 与页面是两个独立目标。
- 仅技能或文档变化、且不改变任何运行产物：只验证并推送源码 `main`，不要制造内容完全相同的网站发布提交。

发布脚本会暂存整个工作树。存在无关改动时，必须先隔离当前任务，确保构建、提交、推送和线上哈希都对应同一份源码；不要把用户的半成品顺带发布。

## 完成条件

- 远程源码 `main` 包含本次改动。
- 所有受影响的线上目标已重新发布。
- 网页变化已通过哈希校验；可交互变化还要在真实浏览器中检查关键路径。
- 最终用中文说明改了什么、复用了什么、验证结果，并附线上地址：<https://QiSun317.github.io/auckland-house-heatmap/>。
