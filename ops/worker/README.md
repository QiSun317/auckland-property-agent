# 模型代理（可选）

只有部署了这个，公网访客才能不用自带 key 使用助手。**不部署也没关系** ——
模型不可用时助手自动退回本地规则：选区、打分、优缺点全部由页面自己算，只是措辞死板一些。

部署之后分工就变了：**模型从全部 205 个区里挑**，并写出每条推荐的理由；页面负责校验 ——
名字必须在表里、预算复核、每个数字逐条核对、论断闸门，任何一道没过就换回规则生成的文字。
多轮对话的状态也在页面这边，代理收到的是页面整理好的条件，不是对话记录。

## 为什么必须有服务端

页面里藏不住 key。页面是公开的，查看源码 / DevTools / Network 都能拿到；
任何混淆都得由页面自己还原成明文才能发请求，打个断点就出来了。
从公开仓库发布的话，key 还会永久留在 git 历史里，而 Google 和一大堆爬虫都在扫这个。

所以 key 只存在这里，作为 Cloudflare 的 secret。

## 部署

```bash
cd ops/worker
npx wrangler login
npx wrangler secret put GEMINI_API_KEY     # 粘贴你的 key，只有你看得到
npx wrangler deploy
```

免费额度：Cloudflare Workers 每天 10 万次请求。Gemini 那边的实际速率上限
看你自己的项目页 https://aistudio.google.com/rate-limit

部署完拿到 URL（形如 `https://auckland-suburb-agent.<你的子域>.workers.dev`），
然后重新生成页面：

```bash
AKL_AGENT_PROXY=https://auckland-suburb-agent.xxx.workers.dev \
  python3 scripts/build_map.py
./ops/publish.sh
```

`AKL_AGENT_PROXY` 没设的话，页面里就不会出现「本站提供」这个选项，其余功能不受影响。

## 这个代理会做什么

- **key 只在服务端**，页面永远看不到
- **话题限制在服务端强制**：与买房选区无关的请求直接返回 `on_topic:false`，不转发给模型。
  页面里也有同样一套规则，但那只是给正常用户的即时反馈 —— 会滥用开放端点的人正是会改客户端的人
- **接受页面重述的对话上下文**（`context` 字段）：追问天生不带主题词，
  「有没有贵一点的」单看这一句会被闸门拦掉。闸门现在连着 `context` 一起判，
  但**离题形状仍只看请求本身** —— 攒下来的条件不能给「顺便写首诗」买通行证。
  这里收到的是页面整理好的条件（`budget up to ...`、`Last turn you offered: ...`），
  不是对话记录，所以郊区表不会随轮数重复发送
- **按 IP 限流** 12 次/分钟
- **只放行你的站点来源**（`ALLOWED_ORIGIN`）
- 请求截断到 400 字符
- 上游报错不原样透传（错误体可能回显 key）
- 只返回页面用得到的三个字段

## 仍然要知道的

这是个公开端点，额度是你的。限流和话题闸门能挡住顺手薅的人，挡不住铁了心的人。
Gemini 免费额度用完时，助手会自动退回本地规则，页面照常可用。
