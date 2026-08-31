# LangChain Python 数据助手 Worker

这是公网助手的唯一模型入口。浏览器仍保留原有选区卡片、比较、计算器、多轮偏好和离线规则兜底；
Worker 使用 Cloudflare Python Workers、LangChain Core 的 `BaseChatModel`、消息协议和 `StructuredTool`，
根据当前页面随请求发送的项目 suburb 表，以及项目上传到 Vectorize 的规划条款，运行轻量工具 Agent，
并调用七个受限工具：

- 精确读取 suburb
- 筛选和排序 suburb
- 聚合项目数值字段
- 解释项目字段与数据范围
- 计算本轮数据工具已返回数值的差额、比率、均值或变化率
- 解释项目支持的 Unitary Plan 规划区范围，并拒绝从 suburb 猜单个地块的规划区
- 用 Workers AI 的 BGE-M3 对明确规划区的问题编码，再在 Vectorize 里先按适用章节过滤、后做相似度检索

Agent 没有联网搜索、代码执行或其他外部数据工具。Gemini 只通过 Worker 原生异步 `fetch` 充当 LangChain ChatModel；
模型结构化回答还会经过第二道取证闸门：引用必须逐项匹配本轮工具结果，
推荐名必须存在于项目表中，显著数字必须能由引用复核。校验失败或额度不可用时，页面继续使用原有本地规则。

为适配 Cloudflare 免费计划的 3 MiB 压缩包限制，`scripts/setup_pyodide_deps.sh` 会在
`pywrangler sync` 后移除未启用的 LangSmith 远程追踪客户端、HTTP 客户端和类型文件，并换成无网络的最小兼容层。
这不会裁掉本项目使用的 LangChain 消息、模型、Runnable 或工具能力；生成的 `python_modules` 不进入 Git。

规划检索使用 `AI` 和 `PLAN_INDEX` 两个原生绑定。索引名为 `auckland-unitary-plan`，
存放 776 条 BGE-M3 1024 维条款向量；`chapter` 元数据索引必须先于向量建立，
这样 Mixed Housing Urban（zone 60）之类的问题只可能从 `H5 + E36 + E38` 中召回。
当前问题若只说 Remuera 等 suburb，工具只会要求用户提供房产的精确规划区，不会使用“该 suburb 最常见分区”代替。

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

规划条款更新后，先从项目 DuckDB 生成并复核上传文件，再幂等更新 Vectorize：

```bash
python3 ../../scripts/export_plan_vectorize.py
npx wrangler vectorize upsert auckland-unitary-plan \
  --file=../../build/plan-vectors-bge-m3.ndjson --batch-size=500
```

部署地址为 `https://auckland-suburb-agent.qisun317.workers.dev`。重新生成页面时传入：

```bash
AKL_AGENT_PROXY=https://auckland-suburb-agent.qisun317.workers.dev \
  python3 ../../scripts/build_map.py
```

入口采用 origin 白名单、每 IP 每分钟 12 次限流、流式请求体/历史长度上限、Agent 模型与工具调用上限，
并开启 Cloudflare 日志和抽样 trace。公开端点仍会消耗绑定 Google 项目的模型额度。
