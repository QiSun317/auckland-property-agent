# LangChain Python 数据助手 Worker

这是公网助手的唯一模型入口。浏览器仍保留原有选区卡片、比较、计算器、多轮偏好和离线规则兜底；
Worker 使用 Cloudflare Python Workers、LangChain Core 的 `BaseChatModel`、消息协议和 `StructuredTool`，
根据当前页面随请求发送的项目 suburb 表运行轻量工具 Agent，并调用五个受限工具：

- 精确读取 suburb
- 筛选和排序 suburb
- 聚合项目数值字段
- 解释项目字段与数据范围
- 计算本轮数据工具已返回数值的差额、比率、均值或变化率

Agent 没有联网搜索、代码执行或其他外部数据工具。Gemini 只通过 Worker 原生异步 `fetch` 充当 LangChain ChatModel；
模型结构化回答还会经过第二道取证闸门：引用必须逐项匹配本轮工具结果，
推荐名必须存在于项目表中，显著数字必须能由引用复核。校验失败或额度不可用时，页面继续使用原有本地规则。

为适配 Cloudflare 免费计划的 3 MiB 压缩包限制，`scripts/setup_pyodide_deps.sh` 会在
`pywrangler sync` 后移除未启用的 LangSmith 远程追踪客户端、HTTP 客户端和类型文件，并换成无网络的最小兼容层。
这不会裁掉本项目使用的 LangChain 消息、模型、Runnable 或工具能力；生成的 `python_modules` 不进入 Git。

## 本地校验

```bash
cd ops/worker
npm install
uv sync
npm run check
```

`.dev.vars` 只用于本地生成绑定类型和开发，不会进入 Git。真实 key 只保存为 Cloudflare secret：

```bash
npx wrangler secret put GEMINI_API_KEY
```

## 部署

```bash
npm run deploy
```

部署地址为 `https://auckland-suburb-agent.qisun317.workers.dev`。重新生成页面时传入：

```bash
AKL_AGENT_PROXY=https://auckland-suburb-agent.qisun317.workers.dev \
  python3 ../../scripts/build_map.py
```

入口采用 origin 白名单、每 IP 每分钟 12 次限流、流式请求体/历史长度上限、Agent 模型与工具调用上限，
并开启 Cloudflare 日志和抽样 trace。公开端点仍会消耗绑定 Google 项目的模型额度。
