# Brassivo Research 项目维护文档（接手须先读）

> 本文件是整个 Brassivo 投研站群的**唯一权威维护说明**。两个连接文件夹的根目录各存一份**完全相同的副本**，改动其一后请同步另一份。
> 最后更新：2026-07-14（合并两份分叉副本：4b「Liquidity 数据管道坑」与 5b「EPS 修正序列」此前各只存在于一份中，现两份齐全；另新增 4c 选股看板周更已知坑 2 条）

---

## 0. 一句话概览

Brassivo Research 是一套「每周自动更新的可证伪投研站群」，由 **4 个纯静态网站**组成，托管在 GitHub Pages + Cloudflare（DNS/CDN），外加一个 Cloudflare Worker + D1 数据库做订阅/会员 CRM。所有页面都是「`index.html`(结构+样式) + `data.js`/`summary.js`(数据)」的模式，数据由每周日的定时任务自动联网刷新后 `git push` 发布。

---

## 1. 两个文件夹 ↔ 仓库 ↔ 域名 映射（最重要）

本项目横跨用户电脑上的**两个文件夹**：

| 站点 | 本地文件夹 | GitHub 仓库 | 线上域名 |
|---|---|---|---|
| **Global Liquidity**（宏观流动性看板） | `~/Documents/Global_Liquidity/` | `hicen87/global-liquidity` | investment.brassivo.com |
| **Global Stocks**（全球AI产业链选股表） | `~/Documents/产业链瓶颈与价值投资/看板/产业链瓶颈看板/` | `hicen87/ai-stock-table` | stocks.brassivo.com |
| **China Stocks**（中国AI产业链选股表） | `~/Documents/产业链瓶颈与价值投资/看板/中国科技股看板/` | `hicen87/china-stocks` | china.brassivo.com |
| **主页 / 导航 / CRM 前端** | `~/Documents/产业链瓶颈与价值投资/brassivo-home/` | `hicen87/brassivo-home` | brassivo.com |

- 每个文件夹**本身就是一个独立 git 仓库**（各有 `.git`），remote URL 里内嵌了 GitHub PAT，可直接 `git push`。
- 沙箱 bash 里路径前缀不同：`~/Documents/Global_Liquidity` → `/sessions/<session>/mnt/Global_Liquidity`；`~/Documents/产业链瓶颈与价值投资` → `/sessions/<session>/mnt/产业链瓶颈与价值投资`。

---

## 2. 技术架构

- **前端**：纯 HTML/CSS/JS，无框架、无构建步骤。图表用 CDN 版 ECharts（仅 Liquidity 页）。改完直接生效，无需编译。
- **数据分层**：`index.html` 只管结构与样式；数据全在 `data.js`（选股表）或 `data.js/data_weekly.js/summary.js`（Liquidity）。**改数据只动 data 文件，不要动 index.html。**
- **托管**：GitHub Pages（每个仓库 Settings→Pages，Deploy from branch `main` / root），自定义域名靠各仓库根目录的 `CNAME` 文件 + Cloudflare DNS 的 CNAME 记录（`<子域>` → `hicen87.github.io`）。
- **CRM 后端**：Cloudflare Worker `brassivo-subscribe`（API 域名 api.brassivo.com）+ D1 数据库 `brassivo-crm`。源码见 `brassivo-home/worker-crm.js`。

---

## 3. 每周自动更新任务（已配好，勿重复创建）

三个 `enabled` 的周更任务，均在**每周日**跑，各自 WebSearch 刷新数据后 `git push`：

| 任务 ID | 时间(UTC) | 作用 | 只改 |
|---|---|---|---|
| `global-liquidity-weekly-update` | 周日 09:00 | 跑定量(build_resume.py/build_weekly.py) + LLM 写定性 summary.js + 事件日历 | data.json/data.js/data_weekly.js/summary.js |
| `refresh-supply-chain-bottleneck-board` | 周日 09:04 | 刷新 Global Stocks 估值双锚+条款 + 美股板块潜力表(sectors.html) + EPS修正序列 | data.js + sectors_data.js + eps_history.json + sector_eps_history.json |
| `refresh-china-stocks-board` | 周日 09:14 | 刷新 China Stocks 估值双锚+条款 + 中国板块潜力表(sectors.html) + EPS修正序列 | data.js + sectors_data.js + eps_history.json + sector_eps_history.json |

- 每个任务的完整 prompt 在 `~/Claude/Scheduled/<任务ID>/SKILL.md`，要改更新逻辑就改那里。
- 另有 `weekly-web-analytics-brief`（周一，拉 Cloudflare 访问数据）和一些 one-time 复查任务。
- **铁律**：周更任务**只换数据、不动 index.html**，所以任何 UI/版式改动都不会被周更覆盖。

---

## 4. 日常改动 & 发布流程

标准流程（以 China Stocks 为例）：

```bash
cd ~/Documents/产业链瓶颈与价值投资/看板/中国科技股看板
# 改 data.js 或 index.html
git commit -am "说明"
git push origin main
```

**已知坑（务必照做）：**

1. **`.git` lock 报 "Operation not permitted"**：先删锁再提交。沙箱里 `find .git -name '*.lock' -delete`；若仍拒绝，调用 `allow_cowork_file_delete` 工具开权限。commit 时若还报 `unable to unlink '.git/objects/**/tmp_obj_*'`，一并清理：`find .git -name 'tmp_obj_*' -delete`（2026-07-12 china-stocks 实发，清完即成功）。
2. **git 身份**：提交请带 `git -c user.name=hicen87 -c user.email=cenhao87@gmail.com commit ...`，否则报 "unable to auto-detect email"。
3. **GitHub Pages 部署间歇性失败**：`pages build and deployment` 的 deploy 步骤经常报 "Some jobs were not successful / Deployment failed, try again later"——这是 GitHub 侧偶发故障，**不是代码问题**。补救：推一个空提交重触发 `git commit --allow-empty -m "chore: retrigger" && git push`。可用 GitHub API 查部署状态：`/repos/hicen87/<repo>/actions/runs?per_page=1`。
4. **浏览器缓存**：`data.js` 等静态文件会被缓存，验证线上是否更新用 `curl -s https://<域名>/data.js -H 'Cache-Control: no-cache'` 或无痕窗口；用户看到"没变"通常是缓存，让其 Cmd+Shift+R。

---

## 4b. Liquidity 数据管道已知坑（2026-07-12 实战记录）

周更沙盒环境不稳定，以下问题都实际发生过，按此处理、不要现场重新摸索：

1. **akshare 45 秒内装不完**：整包 `pip install akshare` 必超时。拆分安装：先 `pip install akshare --no-deps --break-system-packages`，再补依赖 `py_mini_racer tqdm xlrd openpyxl jsonpath beautifulsoup4 html5lib`。pip 超时被杀不影响已装部分，反复"装→`python3 -c "import akshare"` 检查"循环即可。其余依赖（scipy/yfinance/pandas_datareader）也建议逐个装、逐个验。
2. **arm64 沙盒上沪深300（sse）拉取失败**：`build_resume.py` 的 sse 走 akshare `stock_zh_index_daily(sh000300)`，依赖 py_mini_racer 原生库——该库无 aarch64 版本，报 "Native library not available"。同时东财接口（`index_zh_a_hist`，host `push2.eastmoney.com`）被沙盒代理封锁，也不可用。
   **备用方案（已验证）**：用腾讯月K接口直接取数并预写缓存，然后正常跑 build_resume.py（命中缓存即跳过）：
   ```python
   import requests, pickle, pandas as pd
   r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                    params={"param": "sh000300,month,2004-01-01,<今天>,320,qfq"}, timeout=20)
   d = r.json()['data']['sh000300']; rows = d.get('qfqmonth') or d.get('month')
   # 行格式 [日期, 开, 收, 高, 低, 量]，取 x[2] 收盘
   sr = pd.Series([float(x[2]) for x in rows], index=pd.to_datetime([x[0] for x in rows])).resample('ME').last()
   pickle.dump({'sr': sr, 'unit_override': None}, open('/tmp/gl_cache/asset_sse.pkl','wb'))
   ```
   缓存格式必须是 `{'sr': 月末重采样Series, 'unit_override': None}`，文件名 `asset_sse.pkl`。写入后**务必用 yfinance `000300.SS` 交叉验证最近收盘价一致**（2026-07-12 验证过 7/10 收盘 4780.79 两源一致），禁止跳过验证直接发布。
3. **内联 standalone 时的 script 标签**：`index.html` 里本地脚本带 `defer`——`<script defer src="data.js"></script>`，替换匹配串要含 `defer`，否则替换不中、standalone 会残留外链旧数据。
4. **隔日复核先例**（07-04→07-05、07-11→07-12）：若上次更新在 1-2 天内，定量通常无变化，定性只做边际修正；照常走完整流程（prev 转存、history append、updated 改当日），history note 写明"隔日/周末复核"。

---

## 4c. 选股看板周更已知坑（2026-07-12 实战记录）

1. **周末/非交易日刷新时申万估值无新数据属正常**：乐咕乐股 sw-industry-overview 页自带"更新日期"（正文搜"更新日期"），周日跑任务时常仍是上周五口径。此时 12 板块 PE/PB 分位读数与上期完全一致——**保留原读数、照常更新 asOf 与 dataNote 并注明口径日期即可**，不算失败、不要硬造变化。
2. **距上次刷新仅 1-2 天时**（如手动刷新后周更接踵而至）：FPE/估值锚通常无新财报数据，维持原口径并在 dataNote 声明；把精力放在条款证据（近 14 天新闻）与边际信号上，evidence 有实质新数据才改。

---

## 5. 选股表 data.js 字段规范（Global 与 China 必须一致）

每行 `rows[]` 的字段与**紧凑书写规范**（两张表严格对齐，别写长段文字进窄列）：

- `rank/segment/vtype/scarcity/pool/expand/pricing`：排名、环节名、类型、四项打分(1-10)。
- `status`：状态，用 emoji `✅`（健康）/ `⚠️`（警戒）。
- `marginal`：边际变化，用**单个** emoji 圆点 `🟢`(改善)/`🟡`(持平)/`🔴`(恶化)。
- `leaders`：龙头（简短，A股带代码）。
- `fpe`：估值第一锚，短数字/区间（如 `旭创28-30`）。
- `anchor2`：估值第二锚，**一句话**，带前缀（能见度/中枢/GM分位/上架率 等）。
- `priced`：定价充分度，emoji `🟢`(未充分/便宜)/`🟡`(部分)/`🔴`(充分/贵)。
- `verdict`：结论，**短语**（如"优先H股""只做贝塔""⚠周期顶部"），别写长句。
- `tier`：`core`/`debate`/`watch`（决定行底色）。
- `sizeBand`：仓位档，区间字符串（如 `6-10%`/`3-5%`/`0-3%`）。
- `evidence`：**长的财报/数据细节放这里**（渲染在环节名下方那行），窄列保持干净。

顶层还有：`ruleNote`(说明) / `scoreAnchors`(打分锚点4条) / `portfolioRules`(组合规则5条) / `tiers`(分层3条) / `falsifiers`(可证伪条款10条) / `dataNote`(页脚版本说明) / `disclaimer` / `version`。

**版本号规范**：`version` 字段的内容渲染在**页脚小字**，标题永远只显示 `title`。别把版本号写进 `title`。

**⭐ 机械化潜力分与自动排序（2026-07-06 起，逻辑写在 index.html 渲染层，非 data.js）：**
排名不再靠 `rank` 字段人工写死——页面**自动算分并降序排序**，`rank` 字段现被忽略、显示排名=算分后位次。公式：
`潜力分 = √(利润池 × 持续性) × 斜度系数(边际) × 行动系数(定价)`，其中 `持续性 = ∛(紧缺 × 扩产 × 定价权)`。
系数：边际(marginal) 🟢=1.15/🟡=1.0/🔴=0.85；定价(priced) 🟢=1.15/🟡=1.0/🔴=0.82（在 index.html 的 `coefM`/`coefP` 里，要调影响力度改这两个表）。
含义对应「长坡厚雪」：利润池=厚雪、持续性=长坡、边际=坡的斜度、定价=是否行动。**所以周更只要保证 4 项打分 + marginal/priced 两个 emoji 准确，排序会自动正确。**

**列名/图例（2026-07-06）**：表头「边际」列已改名 **EPS±**（表 EPS 边际加速/减速）；表格上方有静态图例行（EPS±/状态/定价圆点含义 + 潜力分公式），写死在 index.html，周更不动它。

---

## 5b. EPS 修正序列管道（2026-07-12 起，两个选股看板各一套）

背景：EPS±（marginal）列此前是每周 WebSearch 的定性判断，无量化序列。Zacks 反爬、Yahoo 返回旧缓存，均不可自动化，故改为**自建修正序列**：每周存一致预期快照，自比得出 30/90 天修正。

**文件（各看板目录下，git 内，随周更 push）：**

- `eps_history.json`：个股 NTM 一致 EPS 序列。口径固定 = StockAnalysis statistics 页 Forward PE（NTM）+ 收盘价，**隐含 NTM EPS = price ÷ forwardPE**。每周 append 一条，**只增不改史**，口径不符宁记 null 不伪造。
- `sector_eps_history.json`：板块修正**方向**序列（弱化版——板块级一致 EPS 数值无公开可抓源）。美股存 FactSet 周报 PDF 文本的方向信息（上修/下修板块名单、被点名板块 CY 增速变化、标普整体值）；中国存沪深300/创业板指/科创50 的 2026E 一致增速 + 方向 + 当周边际信号。

**美股 vs 中国的关键差异：**

- 美股 15 只（TSM/MSFT/GOOGL/AMZN/NVDA/AVGO/ASML/AMAT/SNPS/CDNS/GEV/ETN/VRT/MU/000660.KS），页面实时，每周必出新点。
- 中国 15 只代表票（见文件内 tickers 映射，URL：深市 `/quote/she/<code>/`、沪市含科创板 `/quote/shg/<code>/`、港股 `/quote/hkg/<code>/`），**页面是缓存、滞后 2-5 周**：必须记页面自带 Last updated 为 pageDate，pageDate 未变则不入库，序列点稀疏属正常。
- 周期品（MU/000660.KS/兆易603986）序列仅展示不作判断；FPE 无意义标的（未盈利/业绩异常如华大九天）记 null。

**输出**：某票累计 ≥30 天（≥90 天）跨度的两个观测点后，周更任务自动算修正并写入该行 `marginal` 列，格式 `🟢 NTM30d +2.1%`（阈值 >+0.5% 🟢 / ±0.5% 🟡 / <-0.5% 🔴）；历史不足时保留原定性 emoji 不动。潜力分排序读的还是 emoji 首字符，格式兼容。

**时间线**：基线 2026-07-12。美股约 8/9 出第一批 30 天修正、10 月中旬出 90 天；中国因缓存滞后约 8 月中下旬。

**校验纪律**：周更第 4 步会 node 解析两个 json，确认合法且**历史条数只增不减**；发现被改史视为事故，从 git 历史恢复。

---

## 6. 全站通用约定（4 个 index.html 共享）

- **主题**：cookie `brassivo_theme=light|dark`（域 `.brassivo.com` 全站共享），默认浅灰；每页有「深色/浅色」按钮。CSS 用 `html[data-theme=dark]` 覆盖变量。
- **语言**：cookie `brassivo_lang=zh|en`，**目前仅主页做了中英切换，默认中文**；三个子看板暂未做 i18n（用户 2026-07-06 决定保持现状）。
- **配色变量**：浅色 `--bg:#f6f7f9` 系；深色 `--bg:#171a21` 系。文字对比度已调（浅色 `--txt:#15181e`、深色 `--txt:#edeff4`）。
- **页面宽度**：四站统一 `max-width:1200px`（2026-07-06 起，含主页与 Liquidity）。
- **字号**：全站字号已整体放大约 18%（≈浏览器120%观感，2026-07-06）；改字号时注意 4 站的比例。
- **页眉**：sticky 顶栏，内容限宽居中（`padding:10px max(24px,calc((100% - 1200px)/2 + 24px))`），四站互相跳转 + 主题按钮。
- **favicon**：各仓库根目录 `favicon.svg`（B字标 + 上升折线）。
- **背景**：仅**主页**有极淡静态点阵网格 + Hero 光晕呼吸（纯 CSS，`body::before/::after`）；子看板不加，保持工作区干净。
- **选股表手机端**：≤640px 时表格转**卡片式**（字段竖排「标签:值」，`data-label` 属性驱动），桌面端仍是宽表格；表头 sticky 置顶（`th{position:sticky;top:45px}`）。
- **订阅墙**：三个子看板底部有邮箱订阅墙（`brassivo_sub` cookie，30天试用）；`brassivo_pro` cookie 为付费会员解锁。

---

## 6b. 流动性看板模块结构与自洽（2026-07-06 定稿）

**阅读顺序（信息架构，从上到下）：**
1. 结论层：立场 + 流动性档位 + 紧度仪表 + 本周要点（`完整叙述`折叠）
2. 关键数字卡：G3同比 / 美元净流动性 / **中国锚 M1 同比（月度）**
3. 为什么（机制）：流动性传导链 ①源头→④温度计（`商品轮动时钟`、`五层周期`均默认折叠）
4. 未来催化：未来流动性事件日历（**已移到传导链之后**，作为前瞻）
5. 怎么配：资产配置表 + 加/减风险触发 + **中国资产双因子定位**（默认折叠）
6. 深入自查：自洽校验 + 周频净流动性图 + 月度流动性vs资产叠加图（含 M1）+ 敏感度排序（折叠）

**核心自洽链（单一真值驱动，勿破坏）：** ①源头指标链信号 → 紧度均值 `tight` → 档位 `regime`（中性偏松/边际收紧/收紧）。由它同向派生：立场 stance、紧度仪表指针、双因子卡的"外部松紧"轴。改任一处措辞时确保方向一致。

**中国资产双因子定位（客户端自动算，`#cnbox`）：** M1方向用 `china_liq.m1_yoy` 的**3月均线 vs 前3月均线**判「回升/回落」（抗单月跳动）；外部松紧取 `tight<0.8` 为宽松。两轴交叉定 2×2 象限（戴维斯双击/东边日出西边雨/内需独立行情/戴维斯双杀）。自动随数据刷新，无需人工维护。

**中国锚前瞻子行·政府债发行（2026-07-17 起）：** `build_weekly.py` 末段经 akshare 拉巨潮（`bond_treasure_issue_cninfo` + `bond_local_government_issue_cninfo`），按（债券名称,发行起始日,实际发行总量）去重（同债多市场重复记录），W-FRI 周频聚合并截断未来周桶，算**近4周滚动发行 vs 前13周周均×4** 的倍数：>1.3×=bull（财政脉冲放量，领先M1约1-2个月）、<0.7×=bear、其间warn。写入 `data_weekly.js` 的 `latest.gov4w/gov_ratio/gov_week`、`gov_issue` 序列与 `signals.gov`。前端 `ruleKey` 以 `/政府债/` 匹配自动覆盖信号、AUTO读数自动填充；行名带「中国锚·」前缀故**不参与紧度计算**。口径注意：巨潮无到期量数据，这是**总发行非净发行**。拉取失败时脚本降级跳过（不写gov字段），前端回退 summary.js 人工值——严禁编数。曾评估的"票据转贴现利率"因无可用数据源（akshare无接口、票交所无公开API且sandbox不可达）未实现。

**月度图表（renderChart）：** 所有流动性指标用**虚线**（流动性同比=蓝、固定汇率=紫、中国M1=黄），只有**标的资产价格是实线**。中国M1（黄虚线）仅在 `scope==='g4'` 或选中沪深300/恒生（`CN_ASSETS=['sse','hsi']`）时叠加。tooltip 背景用 `col('--panel')` 跟随主题（浅白/深灰）。

---

## 7. CRM 系统（订阅 + 会员）

- **数据库**：Cloudflare D1，名 `brassivo-crm`，id `aa5f347f-b9e7-4ef3-890b-65c67e1e0974`。三张表：`subscribers`(试用邮箱)、`members`(付费会员 email/key/pass_hash/expires_at)、`keys`(激活码池)。
- **后端**：Worker `brassivo-subscribe`（绑定 D1 变量名 `DB` + KV `SUBS`），源码 `brassivo-home/worker-crm.js`。改代码要在 Cloudflare Dashboard→Workers→Edit code 粘贴后 Deploy（Monaco 编辑器有时加载慢，刷新等待）。
- **端点**：`/subscribe`(试用) `/activate`(激活Key) `/member/info` `/member/passwd` `/admin/overview` `/admin/genkey` `/admin/setmember`。
- **前端页**：`brassivo-home/admin.html`(管理后台，看订阅/会员/Key、生成Key、改到期日) 和 `account.html`(会员激活/查有效期/改密码)。主页页脚有入口。
- **激活码**：明文码存本地私密文件 `~/Documents/产业链瓶颈与价值投资/激活码_私密_勿上传.md`（**不在任何 git 仓库内，勿上传**）；网页/DB 只存 sha256 哈希。发一个划掉一个。
- **⚠️ 待办安全项**：管理员密码目前是 8 位数字（哈希公开在 worker-crm.js，可被暴破）。建议尽快换成 12 位以上强密码：算 `sha256("brassivo:<新密码>")` 替换 worker 里的 `ADMIN_HASH` 常量并重新 Deploy。

---

## 8. 定价与商业模式（改文案时参考）

- 产品：黄金组合专业版，$24.9/月，年付 $189/年（省约37%），全站解锁。
- 流程：留邮箱→首月免费试用→到期邮件联系→微信/支付宝付款→发激活 Key→输入解锁一年。**不接在线支付**。
- 面向海外美股投资者，美元计价。

---

## 9. 凭证与账户（不要外泄，不要写进公开仓库）

- GitHub：用户名 hicen87，各仓库 remote 内嵌 fine-grained PAT（token 名如 `ai-stock-table-push` 已授权 ai-stock-table + china-stocks 两库）。
- Cloudflare：账户 cenhao87@gmail.com。
- 邮箱：cenhao87@gmail.com。
- **注意**：brassivo-home 是**公开**仓库，任何密钥/明文密码都不能提交进去。

---

## 10. 接手第一步 checklist

1. 读完本文件，确认能访问两个文件夹与 4 个仓库。
2. `curl` 四个域名确认在线；查 GitHub Pages 部署状态。
3. 需要改数据→只动对应 `data.js`；改 UI→改 `index.html`（改一处样式记得四站是否要同步）。
4. 提交用第 4 节的标准流程（带身份、先删 lock、Pages 失败就空提交重推）。
5. 周更逻辑改动→改 `~/Claude/Scheduled/<任务ID>/SKILL.md`。
6. 完成后同步更新本 MAINTENANCE.md 并两个文件夹各存一份。
