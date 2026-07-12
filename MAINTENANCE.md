# Brassivo Research 项目维护文档（接手须先读）

> 本文件是整个 Brassivo 投研站群的**唯一权威维护说明**。两个连接文件夹的根目录各存一份**完全相同的副本**，改动其一后请同步另一份。
> 最后更新：2026-07-06（含当日 UI/逻辑大改：机械化潜力分、中国资产双因子定位、图表 M1 叠加、全站宽度/字号统一等）

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
| `refresh-supply-chain-bottleneck-board` | 周日 09:04 | 刷新 Global Stocks 估值双锚+条款 + 美股板块潜力表(sectors.html) | data.js + sectors_data.js |
| `refresh-china-stocks-board` | 周日 09:14 | 刷新 China Stocks 估值双锚+条款 + 中国板块潜力表(sectors.html) | data.js + sectors_data.js |

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

1. **`.git` lock 报 "Operation not permitted"**：先删锁再提交。沙箱里 `find .git -name '*.lock' -delete`；若仍拒绝，调用 `allow_cowork_file_delete` 工具开权限。
2. **git 身份**：提交请带 `git -c user.name=hicen87 -c user.email=cenhao87@gmail.com commit ...`，否则报 "unable to auto-detect email"。
3. **GitHub Pages 部署间歇性失败**：`pages build and deployment` 的 deploy 步骤经常报 "Some jobs were not successful / Deployment failed, try again later"——这是 GitHub 侧偶发故障，**不是代码问题**。补救：推一个空提交重触发 `git commit --allow-empty -m "chore: retrigger" && git push`。可用 GitHub API 查部署状态：`/repos/hicen87/<repo>/actions/runs?per_page=1`。
4. **浏览器缓存**：`data.js` 等静态文件会被缓存，验证线上是否更新用 `curl -s https://<域名>/data.js -H 'Cache-Control: no-cache'` 或无痕窗口；用户看到"没变"通常是缓存，让其 Cmd+Shift+R。

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

**资产配置比例（2026-07-12 新增）：** `summary.js` 的 `allocPlan` 存进攻/中性/防御三档目标比例模板（各档合计=100，资产名须与 `allocation` 第一列一致）。前端自动判档：防御=`tight≥1.5` 或 (`tight≥0.8` 且④温度计有bear)；进攻=`tight<0.8` 且④无bear；其余中性。配置表第三列显示当前档比例+色条，档位按钮可预览其他档（标"⚠预览"）。**模板是慢变量，每周不用动**——只在框架观点变化时改模板；周报只维护 `allocation` 的立场与理由照旧。

**中国资产双因子定位（客户端自动算，`#cnbox`）：** M1方向用 `china_liq.m1_yoy` 的**3月均线 vs 前3月均线**判「回升/回落」（抗单月跳动）；外部松紧取 `tight<0.8` 为宽松。两轴交叉定 2×2 象限（戴维斯双击/东边日出西边雨/内需独立行情/戴维斯双杀）。自动随数据刷新，无需人工维护。

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
