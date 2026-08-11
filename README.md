# 奥克兰选房 AI Agent — 数据底座

第一步：大奥克兰（Auckland Region）按 suburb 的房价热力图 → [`heatmap.html`](heatmap.html)

## 用法

```bash
python3 scripts/fetch_prices.py      # 各 suburb 房价（217 个页面，约 1 分钟）
python3 scripts/fetch_boundaries.py  # LINZ suburb 边界
python3 scripts/fetch_wikipedia.py   # 各 suburb 维基百科简介（限速，约 3 分钟）
python3 scripts/fetch_valuations.py  # 62 万个地块的政府估价 CV（约 2 分钟，10 MB）
python3 scripts/build_detail.py      # 空间关联 + 按 35 米网格聚合
python3 scripts/build_map.py         # 生成 heatmap.html + suburb_prices.csv
python3 scripts/build_db.py          # 装进 DuckDB（约 20 秒）
```

查询：

```bash
python3 scripts/q.py --schema
python3 scripts/q.py "SELECT name, avg_house_value FROM suburb_overview ORDER BY 2 DESC LIMIT 10"
```

四个 `fetch_*` 只需在数据要更新时重跑；改样式只跑最后两个（`build_detail.py`
在边界或估价变了才需要重跑）。

只有 Python 3 标准库，无第三方依赖。生成后直接用浏览器打开 `heatmap.html`
（单文件，无外部请求）。

## 产出

| 文件 | 内容 |
|---|---|
| `heatmap.html` | 独立页面。全区图：发散色阶（蓝＝便宜／红＝贵）、悬停、搜索、数据表。**点任一郊区**进入详情：区内 35 米网格 CV 热力图 + 简介 + 市场指标 + 户型结构 + 房价走势 + CV 分布 |
| `data/suburb_detail.json` | 285 个郊区的网格化 CV（base64 打包）与分位数、直方图 |
| `data/raw/valuations.jsonl.gz` | 623,765 个计税单元的 CV/LV（2021 与 2024 两次估价）+ 地块中心点 |
| `data/raw/wikipedia.json` | 204 个郊区的维基百科简介 |
| `data/suburb_prices.csv` | 286 行扁平表，供 agent 直接查询 |
| `data/join_report.txt` | 边界与价格的匹配结果、无数据郊区清单 |
| `data/raw/opes_suburbs.json` | 原始抓取记录，含 2000 年至今的年度价格序列 |
| `data/raw/auckland_boundaries.geojson` | LINZ 郊区边界（WGS84，已简化） |
| `data/auckland.duckdb` | **主数据库**，59 MB，见下节 |
| `scripts/q.py` | 命令行查询（默认只读）；`--schema` 打印表结构 |
| `queries/examples.sql` | 7 条可直接跑的示例查询 |
| `build/heatmap_body.html` | 同一页面的 body-only 版本（用于发布成 Artifact） |

`suburb_prices.csv` 的列：

```
name, type, major, price, yoy, growth, rent, yield, pop, days, sold, lat, lon, url
```

- `price` — Average House Value（区内全部住宅自动估值的平均），截至 2026-06
- `yoy` — 过去 12 个月变化（小数，-0.078 = 下跌 7.8%）
- `growth` — 长期年化资本增长（%）
- `rent` / `yield` — 周租金中位数（NZD）／估算毛租金回报（%）
- `days` / `sold` — 中位售出天数／近 12 个月成交套数
- 空值 = 数据源未提供（源数据用 0 当缺失标记，已在生成时转为空）

## 数据来源

- **价格**：[Opes Partners](https://www.opespartners.co.nz/property-markets/auckland)
  各 suburb 市场页（数据更新于 2026-04-16，口径为 2026 年 6 月）。
  抓取方式：页面是 Next.js app router，suburb 记录内嵌在 RSC flight payload 的
  `suburbData` 键里，脚本重建 payload 后直接 JSON 解析——不是 HTML 正则。
  `robots.txt` 为 `Allow: /`。
- **边界**：LINZ《NZ Suburbs and Localities》，经 LINZ 官方 ArcGIS Online 要素服务
  取得，CC BY 4.0。查询条件 `territorial_authority LIKE '%Auckland%'`（跨界的
  Pukekohe、Waiuku 在该字段里是 `Auckland, Waikato District`），几何按约 22 米简化。
- **政府估价 CV**：Auckland Council 的 `AGOL_RateAccountInfo1_gdb` 要素服务
  （公开、无需鉴权），逐计税单元给出 `CV/LV`（2021-06-01 估值）与 `LCV/LLV`
  （2024-05-01 重估）。用 `returnCentroid=true` 只取地块中心点，避免拉 62 万个多边形。
- **行政区划**：Auckland Council `Local_Board_boundaries_view`，21 个 local board。
  每个 suburb 按质心归属到一个 board，再归并成「北岸 / 西区 / 中区 / 东区 / 南区 /
  北部乡村 / 海岛」—— 这是奥克兰人真正在用的地理心智模型，用户说「想住东区」才有得匹配。
- **简介**：英文维基百科 API，CC BY-SA 4.0。标题有歧义（Albany 是纽约州的城市），
  所以按 `{名}, Auckland` → `{名}, New Zealand` → `{名}` 依次尝试，并用条目坐标与
  suburb 中心点的距离（≤20 km）核验后才采纳。

## 自动化流水线

`scripts/pipeline.py` 是编排层。核心是一条 **fetch → validate → promote** 的链路：
每个抓取脚本先写进 `data/incoming/`，**只有通过该源的校验才会原子替换 `data/raw/` 里的文件**。
所以源站改版最坏的结果是"沿用上个月的数据 + 日志里一条 failed"，而不是把好数据洗掉。

### 各源按自己的节奏抓

它们根本不同频，全部按月抓是白跑请求：

| 源 | 周期 | 为什么 |
|---|---|---|
| `prices` | 30 天 | Opes 大约季度级刷新 |
| `valuations` | 90 天 | 议会 CV 是三年一轮重估（2021 → 2024 → 约 2027），期间只有零星更正 |
| `boundaries` | 90 天 | LINZ 一年改几次 |
| `localboards` | 365 天 | 议会 21 个 local board，只在行政区划调整时才变 |
| `wikipedia` | 180 天 | 几乎不动 |

`pipeline.py run` 每次只抓到期的；`--force prices` 或 `--force all` 可以强制。

### 校验闸门

| 源 | 通过条件 |
|---|---|
| `prices` | ≥190 个 suburb 有价格；中位数相对库里上一版漂移 ≤30% |
| `valuations` | ≥590,000 个计税单元；≥95% 带 CV；均值漂移 ≤25% |
| `boundaries` | 250–400 个多边形；每个都有 name 和 geometry |
| `wikipedia` | ≥180 条非空简介 |

实测这两条确实会拦下来：源站只返回 20 个 suburb → `only 19 suburbs have a price`；
金额单位变了导致整体除以 3 → `median suburb value moved 66%, tolerance 30%`。

### 改成追加式的数据契约

按月跑之前，原来的 schema 有两个硬伤，都改掉了：

1. **`build_db.py` 原来是 drop 重建**，按月跑只会覆盖不会积累。现在
   `market_snapshot` 和 `valuation` 是**追加表**，按数据源自己的发布日期做主键 ——
   源没更新就一行不插，源发新版就每个 suburb 追加一行。攒下来的时间序列才是月度任务的价值。
2. **`cv_2021` / `cv_2024` 写死成列**，2027 年下一轮重估就得改表。现在估价是长表
   `valuation(ru_id, valuation_date, cv, lv)`，下一轮只是 INSERT。
   `rating_unit_current` 视图取最新一轮（重估是全区同步的，所以这是个等值过滤，不是窗口函数）。

`suburb` 和 `rating_unit` 是缓变参考数据，每次重建，但 `first_seen` 会带过来。

### 每次构建新库再原子替换

`build_db.py` 先写 `auckland.duckdb.building`，通过 `ATTACH` 把历史从旧库搬过来，
最后 `os.replace`。两个原因：

- DuckDB 的 `CREATE OR REPLACE TABLE` 会整表重写且**不回收旧块**。原地构建时，一次
  什么都没变的空跑也会让文件从 192 MB 涨到 215 MB。改成换文件后稳定在 ~96 MB。
- DuckDB 的写锁**排斥读**。构建期间旧文件一直可读，换过去那一刻才切，正在查的进程
  握着旧 inode 不受影响。

`heatmap.html` 同理：先写 `.building` 再 rename，浏览器里开着的页面不会读到半截文件。

### 日志和状态

```bash
python3 scripts/pipeline.py status
```

- `logs/pipeline.jsonl` —— 每次运行一行，即使数据库挂了也写得进去
- `pipeline_run` / `pipeline_step` 表 + `pipeline_status` 视图 —— 每个源最后一次成功
  是什么时候、多少行、是否到期、失败原因

### 调度：launchd

```bash
./ops/install-schedule.sh          # 装到 ~/Library/LaunchAgents（不需要 sudo）
./ops/install-schedule.sh --status
./ops/install-schedule.sh --remove
```

每月 2 号 06:10 跑。**用 launchd 不用 cron**：合盖错过的任务，launchd 会在唤醒后补跑，
cron 直接跳过这个月。代价是关机期间不跑。

立刻手动触发一次：

```bash
launchctl kickstart -p gui/$(id -u)/com.sunqi.auckland-pipeline
```

### 上云的口子

`scripts/` 里没有任何 macOS 专属代码，路径全部走 `AKL_ROOT` / `AKL_RAW_DIR` /
`AKL_OUT_DIR` / `AKL_DB` 环境变量。搬到 CI 只需要换掉 `ops/` 里的调度器，
`ops/github-actions.yml.example` 是现成的模板。

真正要先想清楚的是**状态放哪**：追加的历史在 ~96 MB 的 duckdb 里，每月提交进仓库不现实。
模板里列了三条路，推荐第 (b) 条 —— 把 `data/raw` 快照推到对象存储，每次从快照重建库，
这跟本项目现有的「raw 是唯一真源头」模型一致。

## 中英双语

页面和 suburb 详情页都是双语，右上角切换。

默认语言按 `navigator.languages` 的**优先顺序**判断：从头扫，第一个 `zh*` 就用中文，
第一个 `en*` 就用英文，都没有则英文。之所以强调顺序 —— 一开始我用的是"列表里有 zh 就用中文"，
结果 `["en-GB","en-NZ","zh-Hans-NZ"]`（英文为主、兼懂中文的人）被判成中文，是反的。
手动切换会记进 localStorage，之后一直覆盖自动检测。

实现上不用 key 字典，而是内联双语：

```js
const L = (zh, en) => LANG === 'zh' ? zh : en;
pro.push(L(`长期年化增长 ${g}%，全区前 25%`,
           `Long-term growth ${g}%/yr — top quartile for the region`));
```

两种语言写在同一行，改一个必然看见另一个 —— key 字典最容易出的问题就是改了中文忘了英文。
静态标记同理，用 `data-zh` / `data-en` 属性成对存放。

助手的**输入**两种语言都认，跟界面语言无关：`预算 110 万，三房，北岸` 和
`Budget $1.1m, 3 bedrooms, North Shore` 都能解析。

**维基百科简介只有英文**，中文维基几乎没有奥克兰郊区条目，所以中文界面下这一段仍是英文，
标题写作「简介（英文）」而不是假装有中文。

## 选房助手

页面右下角的悬浮面板。用中文描述需求，它按**预算优先**筛出郊区、说明每个区的优缺点，
并自动打开第一名的区内热力图。

### 预算是硬门槛，不是权重

用户给出预算 B 之后，问题不是"这个区均价是多少"，而是**"B 在这个区能买到多少房子"**。
每个 suburb 的详情数据里带着一条 24 格对数分箱的 CV 直方图，所以这是一次 CDF 查询：

```
affordShare(区, B) = 该区 CV ≤ B 的计税单元占比
```

- `affordShare < 20%` → 直接排除，不进候选
- 打分曲线在 60–75% 处最高：低于此选择面太窄，高于 93% 说明预算明显高出这个区，
  会被提示「可能买得比需要的更便宜」

举个对比：预算 120 万时，Remuera 的 `affordShare` 是 **18%**（排除），
Papakura 是 **91%**。只看均价是看不出这个差别的。

### 优缺点必须挂在数字上

每条优缺点都由规则从数据算出，并和全区四分位基准比较，没有一句是模型写的：

> ＋ 预算内可选约 68% 的房子（区内 2,101 个计税单元）
> ＋ 长期年化增长 6.1%，全区前 25%
> ＋ 71% 的房源是 ≥300 m² 的独立地块（中位 675 m²）
> － 2021→2024 政府重估下调 13%
> － 区内价差大（中间 50% 落在 $210k–$630k），街区选择很关键

其中「独立地块占比」是专门为此加的指标，因为**地块中位数会骗人**：Auckland Central
有地块的房源中位数是 626 m²，看着不小，但只有 **2.6%** 的房源有独立地块，其余全是公寓。
所以「要独立屋带院子」是硬过滤条件（占比 <20% 直接排除），不是加分项。

### 它会明确说自己不知道

问到**学区、治安、族裔构成、洪水风险**，助手会直说这些数据不在数据集里、
推荐没有纳入考虑，而不是拿别的指标搪塞。这几项都在下一步的清单上。

条件无解时也不硬凑，而是诊断是哪一条在卡：

> 按这些条件没有匹配的郊区。
> 放宽其中一条就有结果：**区域限制**（1 个）、**独立地块要求**（3 个）
> 其余条件不变的话，最低门槛在 **Panmure**，那里 25% 分位的 CV 是 $720,000

### 免费模型怎么接

助手底部「接入模型」里可选服务商。**默认不接**，纯本地规则就能用。

浏览器直连能不能通，是这里的硬前提 —— 很多 API 不返回 CORS 头，页面根本调不出去。
实测（用无效 key 探测，能拿到 HTTP 状态码即为通）：

| 服务 | 浏览器直连 | 备注 |
|---|---|---|
| Google Gemini | ✅ | 有免费额度，预置 `gemini-2.5-flash-lite` |
| Groq | ✅ | 有免费额度，速度很快 |
| OpenRouter | ✅ | 有标 `:free` 的模型 |
| Mistral | ✅ | 有免费额度 |
| Anthropic | ✅ | 付费 |
| **Cerebras** | ❌ | **不返回 CORS 头，页面调不通** |
| 本地 Ollama | ✅ | 选「自定义」，端点 `http://localhost:11434/v1`；需要 `OLLAMA_ORIGINS` 放行来源 |

各家免费额度的具体数字变动频繁，以官方文档为准，别信第三方博客（我查的时候几篇博客
互相就对不上）。

这个活儿很轻 —— 就是把一句话解析成 JSON 再写一句开场白，小模型完全够用，
本地 7B 也能跑。

**公网访客用不了你的额度。** key 存在各自浏览器的 localStorage，不会写进页面文件。
任何嵌进公开页面的 key 都会在几小时内被人跑干，所以站点不提供共享额度，
访客要用模型层得自己填。这也是为什么本地规则必须能独立工作。

调用失败会显示真实错误并自动退回本地规则，不会卡住：

> 模型调用失败（HTTP 400: API key not valid. Please pass a valid API key.），已改用本地规则。

### 模型是可选的，而且管不到数字

不填 API key 也完全可用：本地正则解析中英文需求，本地打分排序，本地生成优缺点。

填了 key（Anthropic）之后，模型**只做两件事**：读懂比较口语化的需求描述、写一句开场白。
系统提示里明确禁止它推荐郊区或给出任何数字 —— 候选集、排序、每一个数都由页面从本地数据算，
所以它没有编造的余地。调用失败会自动退回本地规则并提示。

Key 存在浏览器 localStorage，**不写进 `heatmap.html`，也不进 git**。
不过这终究是把密钥放在本机的一个静态页面里，安全性等同于你这台电脑；
要更稳妥就在本地起一个小代理持有密钥，页面只调本地地址。

## 数据库：DuckDB

`data/auckland.duckdb`，59 MB，六张表一个视图：

| 表 | 行数 | 内容 |
|---|---|---|
| `suburb` | 286 | LINZ 多边形 + 质心 + 面积，所有东西挂在它上面 |
| `suburb_market` | 205 | Opes 的估值、租金、回报、成交、户型比例 |
| `suburb_price_history` | 5,070 | 2000 年至今的年度估值序列 |
| `suburb_description` | 204 | 维基百科简介 |
| `rating_unit` | 623,765 | 逐地块：估价号、地址、地块面积、2021/2024 两次 CV 与 LV、坐标 |
| `meta` | 8 | 各数据源的口径与日期 |
| `suburb_overview`（视图） | 286 | 上面几张表拼好的一行一区，大部分问题查它就够 |

`rating_unit.suburb_id` 在建库时就用点在多边形内算好了，所以后续查询都是普通 join，
不用每次跑空间运算。62.4 万条里 3,475 条（0.6%）不落在任何 suburb 内。

### 为什么选它

- **零运维**：`pip install duckdb`，单个文件，没有服务端、没有守护进程、没有配置。
- **空间扩展装得动**：`INSTALL spatial` 是一行 SQL，自带二进制，不需要 homebrew、
  不需要系统装 GDAL。对比 SpatiaLite：要 `brew install libspatialite`，然后
  `mod_spatialite.dylib` 的架构还得和你的 Python 对上 —— anaconda + arm64 这组合是
  经典翻车点（顺带一提，这台机器的 anaconda Python 确实允许 `enable_load_extension`，
  所以 SpatiaLite 路线不是不通，只是麻烦）。
- **查询形态对口**：这个项目实际要跑的是「按区求 CV 中位数/分位数/直方图」这类分析查询，
  正好是列存 + 向量化执行的主场。`median`、`quantile_cont`、`histogram` 都是内置的。
- **直接读原始文件**：`ST_Read('*.geojson')`、`read_json_auto('*.jsonl.gz')`，
  建库脚本基本就是几段 SQL，不用写解析层。
- **对 agent 友好**：给它一个 SQL 工具就够了，schema 小到能整个塞进 prompt。

实测（62.4 万行，M 系列 Mac）：建库 20 秒，示例查询 6–35 ms。

### 代价

1. **写锁是排他的**。实测：两个只读进程可以并存；但只要有一个写连接开着，
   **其他进程连读都进不来**（`IO Error: Could not set lock on file`）。所以
   `build_db.py` 跑的时候不能有查询会话开着。真要做成多人写的服务，这条就是硬伤。
2. **不是 OLTP**。逐行 UPDATE 会重写整表且不回收旧块 —— 我第一版用 `UPDATE` 填
   `suburb_id`，文件 104 MB；改成在 `CREATE TABLE ... AS` 里 join 出来，59 MB，
   同样的数据。以后存用户状态（收藏、笔记）不要塞进这个库。
3. **空间函数的轴序陷阱（我第一次判断错了，这里是更正）**。
   `ST_Distance_Spheroid` / `ST_Area_Spheroid` / `ST_Transform` 都遵循 EPSG:4326 的
   **官方轴序 (lat, lon)**，而项目里所有点都按 (lon, lat) 存。传错顺序的结果不是报错：
   `ST_Area_Spheroid` 全部返回 `nan`，`ST_Distance_Sphere` 则返回一个**看起来很合理的错数**
   （0.01° 经度 @ -36.84 应为 891.9 m，它给 1111.9 m —— 把经度当成了纬度，漏掉了
   cos(纬度) 修正）。我一开始把它当成"扩展有 bug"，其实是我传错了。
   **正解：投影到 NZTM 再算**，彻底绕开轴序：
   `ST_Transform(geom, 'EPSG:4326', 'EPSG:2193', always_xy := true)`，
   之后用普通的 `ST_Area` / `ST_Distance`，单位是米。已验证：Takapuna 距市中心 6.2 km、
   Pukekohe 41.4 km，与实际直线距离相符。
4. **R-tree 在这个量级上不划算**。实测半径 1.5 km 查询：全表扫描 + `ST_Distance_Sphere`
   22 ms，走 R-tree 的 `ST_Within` 反而 50 ms，而索引本身要 40 MB。所以
   `rating_unit` 上没建 R-tree，加回来是一行的事（数据量涨一个数量级再说）。
5. **GIS 生态比 PostGIS 小**：没有拓扑、没有栅格、没有路径规划。以后要算通勤等时圈或
   叠洪水栅格图层，这里做不了。
6. **没有内置向量检索**。想对简介做语义搜索，`vss` 扩展还偏实验性。
7. **文件格式向前不兼容**：新版本写的库老版本打不开。缓解办法是 `data/raw/` 才是
   真源头，这个库随时可以删掉重建（`build_db.py` 就是每次 drop 重来）。

### 什么时候该换

- 变成多人写的 Web 服务，或者要算等时圈 / 路径 / 栅格 → **PostgreSQL + PostGIS**。
  今天不上是因为要多养一个服务端，而在笔记本上跑的工具里换不来任何好处。
  schema 和加载脚本九成可以直接搬。
- 只是要小量高频读写的应用状态（收藏、笔记、会话）→ 单独开一个 **SQLite** 文件，
  别和分析库混在一起。
- 要把数据发给别人 / 进 git → 导出 **Parquet**。但 Parquet 没有索引、没有几何类型，
  当交换格式可以，当工作库不行。
- 这台机器上装了 **MongoDB**，它也有地理索引；但 62 万行求分位数用聚合管道写起来又
  笨又慢，而且 agent 没法用 SQL。这个场景不合适。

## 区内热力图怎么算的

1. 62.4 万个计税单元按**点在多边形内**判定归属（不是用地址里的 suburb 字段）——
   地图画的是 LINZ 多边形，点必须和多边形一致。61.7 万个成功落入某个 suburb。
2. 每个 suburb 内按 **35 米方格**聚合，取格内 CV 中位数。这一步也顺便把 cross-lease
   公寓（同一个地块中心点的多个单元）合并掉了。
3. 道路、绿地等格内没有地块，细网格会呈现为散点而不是面。因此做 2 轮补洞：空格若周围
   有 ≥3 个相邻格有值，就取邻格中位数。其余留空（显示为底色）。补出来的格约占四成，
   这是**插值不是实测**。
4. 渲染成连续热力图，不是方块。关键是**平滑数值场、绝不平滑颜色** —— 这是发散色阶，
   蓝和红在 RGB 上混合会得到中性灰，而灰在这套色阶里恰好代表"等于中位数"，
   直接模糊像素会凭空造出错误的读数。做法是归一化卷积：对 (数值 × 掩码) 和 (掩码)
   分别做盒式模糊再相除，没有地块的格子权重为 0 而不是"值为 0"，小空洞顺带按邻域正确填上。
   模糊量 σ≈1.4 格（约 50 米），刚好盖住格子边缘、不超过 35 米的数据分辨率 ——
   试过 86 米，整个区糊成墨团，街区结构全没了。
   色阶还做了插值：原来按 101 档 LUT 取整，平滑之后反而暴露出明显色带。
   详情页右上角可切回「网格」看原始分辨率，悬停读数始终是**实测格值**而非平滑值。
   区内图支持滚轮缩放、拖拽平移、双击复位、双指捏合。放大不会糊 —— 画面是从连续场
   **逐像素重采样**，不是放大位图。缩放上限按数据分辨率自适应（一个 35 米格最多占
   40 屏幕像素），所以 Herne Bay 这种小区只给 3.3×、Papakura 给到 14×，
   再往里放大只是把空气放大。
5. 色阶中点是**该 suburb 自身的** CV 中位数，两端是区内 10/90 分位。所以每个区都用满
   整条色带，**不同区之间的颜色不能横向比较**——跨区比较请看全区图。

## 已知口径问题

1. **`price` 是估值均值，不是成交中位价。** 同期全奥克兰成交中位价为 $980,000
   （REINZ 口径），而本数据集 205 个郊区估值的中位数是 $1,165,950。两者不可直接比较：
   前者按成交量加权、只看实际卖出的房子，后者对每个郊区等权、覆盖全部存量住宅。
   地图上的中点用的是后者。
2. **覆盖不全。** 286 个郊区/地区中 205 个有价格。缺失的多为农村、林地、机场、医院，
   但也包括 Western Springs、Westgate、Hillpark、Wairau Valley、Lucas Heights、
   Tōtara Park 等真实住宅区——价格源本身没收录。
3. **大堡岛（Aotea / Great Barrier）未绘制**：LINZ 郊区图层没有把该岛细分为
   suburb/locality，且无价格数据。Waiheke 已按 Oneroa / Ostend / Surfdale 等分区绘制。
4. **单一数据源。** suburb 层面的价格来自一家（其底层为自动估值模型）。好消息是
   议会 CV 是完全独立的第二来源，两者的中位数比值中位数为 **1.01**，互相印证。
5. **CV 含全部计税单元**，不只住宅。公寓密集处成片低值（那是"一套公寓多少钱"），
   Penrose 这类工业区、Western Springs 这类以公园/球场为主的多边形，CV 中位数会
   明显偏离住宅口径。看区内热力图时要留意这一点。
6. **授权。** 议会的逐地块估价可在其网站免费查询，这个要素服务也是公开无鉴权的；
   但议会另有收费的 RID 批量数据产品。本项目按个人研究用途使用，
   **若要商用或对外分发这份数据，需先向 Auckland Council 确认授权。**

## 配色说明

发散色阶，蓝 ↔ 红，中性灰为中点——不是彩虹色阶。蓝臂取自一条标准蓝色 sequential
ramp，红臂在 OKLCH 空间镜像每一档的明度与彩度，因此两侧感知强度对称。明暗主题各有
一套色阶：亮色主题中点最亮、两端加深；暗色主题中点为中灰（对 `#1a1a19` 底色仍有
2:1 对比），两端提亮。无数据用 45° 斜纹而非纯灰，避免与"接近中位价"的中性灰混淆。

## 下一步

- [x] ~~点开 suburb 看简介 + 区内房价热力图~~
- [x] ~~本地数据库 + 每月自动刷新~~
- [ ] 攒够几期 `market_snapshot` 后，在详情页加一条「我们自己观测到的」价格曲线
      （现在图上那条是数据源给的历史，不是我们采集的）
- [x] ~~页面内嵌选房助手，预算优先 + 优缺点 + 自动打开对应热力图~~
- [ ] 补上助手现在会明确拒答的维度：学区（Ministry of Education 校网边界）、
      洪水与滑坡风险（议会图层）、治安（NZ Police 统计）
- [ ] 区内热力图加住宅口径过滤（用 Unitary Plan 分区图层剔除商业/工业地块）
- [ ] 交叉验证价格（REINZ / QV / homes.co.nz），给每个 suburb 一个置信度
- [ ] 接入在售房源（Trade Me Property / realestate.co.nz）
- [ ] 加入通勤时间、学区（decile / in-zone 学校）、洪水与滑坡风险图层
- [ ] Agent 层：把 `suburb_prices.csv` 加上上述图层做成检索工具，按预算 + 通勤 +
      学区 + 户型给候选 suburb 排序
