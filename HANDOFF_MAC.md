# 交接文档 · 全球流动性看板（迁移到 Mac）

> 目的：把本项目从 Windows 迁到 Mac，由 Mac 全天候待机跑自动化。
> 本机（Windows）相关的本地定时任务**已关闭**；GitHub Actions 是云端、与机器无关。

---

## 0. 当前状态（已完成）

一个纯静态交互看板（`index.html`，ECharts，无后端），含五层：

1. **全球流动性周期主图**：央行资产负债表合计 12 月同比（蓝线）vs 资产价格（右轴）。
2. **口径切换**：美欧日 G3（原版，≈18万亿/-4.3%）｜ +中国 G4（≈25万亿/+0.3%）。
3. **分资产锚定**：中国资产（上证/恒生）自动叠加中国 M1 同比；美股/大宗/金银叠加全球 G3；选中国资产时蓝线自动切换、口径开关灰显。
4. **3.5 年周期弧**：三种相位锚点可切换（手动锚点 2025-12 / 最近谷底 2024-04 / 拟合谷底 2023-11）；进行中的当前周期画成虚线半弧（标“进行中 X%”）。
5. **领先/滞后排行** + **周频美元流动性管道**（净流动性/ON RRP/准备金/SOFR−IORB）+ **资产配置摘要模块**。

数据自洽校验：G3 = 18.07 万亿、同比 −4.28%（与原图一致）。

---

## 1. 文件清单

```
index.html              交互看板（纯静态，双击或静态托管即可）
data.js / data.json     月度框架数据（build_data.py 生成；data.js 供本地双击用）
data_weekly.js          周频美元流动性管道数据（build_weekly.py 生成）
summary.js              资产配置摘要数据（喂给看板摘要模块）
build_data.py           月度数据引擎：FRED+AkShare+Yahoo → 同比/周期/相关性/中国M1
build_weekly.py         周频引擎：FRED → 净流动性/ON RRP/准备金/SOFR-IORB
global_liquidity.py     旧 matplotlib 出图脚本（保留，本地出 PNG 用）
资产配置摘要_2026-06.md  最近一期摘要（markdown）
requirements.txt        Python 依赖
README.md               功能说明 / 上线说明
.github/workflows/      update.yml(月度) + update_weekly.yml(周频) GitHub Actions
```

---

## 2. Mac 环境搭建

```bash
# 1) Python（Mac 自带或用 Homebrew 装）
brew install python        # 如未装
# 2) 进项目目录
cd ~/Projects/global_liquidity2.0     # 放到你 Mac 上的实际路径
# 3) 建虚拟环境 + 装依赖（推荐，避免污染系统 Python）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 4) 跑一次验证
python build_data.py && python build_weekly.py
# 5) 本地预览
python -m http.server 8000   # 浏览器开 http://localhost:8000
```

> 中文字体：Mac 用 `PingFang SC` / `Heiti SC`，看板是网页、用系统字体即可，无需配置。
> 国内网络访问 FRED/Yahoo 超时：运行前 `export PROXY=http://127.0.0.1:7890`（按你的代理端口改）。AkShare（中国央行/M1）国内直连，无需代理。

---

## 3. 在 Mac 上重建自动化（二选一）

### 方案 A（推荐）：GitHub Actions —— 云端跑，最省心、不耗 Mac 电
仓库里已带好两个 workflow：`update.yml`（每月 15 号）、`update_weekly.yml`（每周六）。
1. 把项目推到一个 GitHub 仓库。
2. Actions 自动按 cron 跑、回写 data。GitHub runner 在海外，访问 FRED/Yahoo 通畅、无需代理。
3. 配合 Cloudflare Pages 连仓库即得在线看板（见 README“上线”章）。
> 注意：cron 是 **UTC**。`0 2 15 * *` = UTC 周期；与本机/Mac 无关。

### 方案 B：Mac 本地 launchd —— 适合“全天候待机本地跑”
若你想让 Mac 本地定时跑（不依赖 GitHub），用 launchd（比 cron 更适合 Mac、休眠唤醒后会补跑）：

新建 `~/Library/LaunchAgents/com.qogrisun.liquidity.monthly.plist`：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.qogrisun.liquidity.monthly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd ~/Projects/global_liquidity2.0 &amp;&amp; ./.venv/bin/python build_data.py &amp;&amp; ./.venv/bin/python build_weekly.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Day</key><integer>15</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/liquidity.log</string>
  <key>StandardErrorPath</key><string>/tmp/liquidity.err</string>
</dict></plist>
```
加载：`launchctl load ~/Library/LaunchAgents/com.qogrisun.liquidity.monthly.plist`
（周频可再建一个，把 Day 换成 `Weekday`=6、文件名改 weekly。）

> A 和 B **二选一**，别同时开，否则重复更新。推荐 A（云端、稳定、不占 Mac 资源）。

### Cowork 月度“资产配置摘要”LLM 任务
- 这是需要联网取指标 + 框架判断的 LLM 任务，**Windows 本机已禁用**。
- 在 **Mac 的 Claude 应用**里重建：把本机任务的 prompt 复制过去即可。原 prompt 存档在
  `C:\Users\Administrator\Claude\Scheduled\monthly-liquidity-allocation-summary\SKILL.md`（迁移时一并带走）。
- 注意：Cowork 定时任务**只在 Claude 应用打开时运行**；Mac 待机但应用开着即可，应用关闭则下次打开补跑。

---

## 4. 关键注意事项（避免踩坑）

- **相位是主观的**：3.5 年周期弧的相位（锚点）有三种模式，自动模式与会差一年多——因为这条央行表同比的真实谷底间隔 39~72 个月、并非规整 42 个月。当节奏参考，别当择时铁律。
- **口径区别**：G3（美欧日）对全球资产；中国资产看中国 M1。别混用。
- **数据滞后**：中国央行/M1 是月度、滞后约 1 个月；但流动性领先资产 3-6 个月 > 发布滞后，仍是有效领先指标。想更及时看周频管道面板。
- **编辑文件**：若用编辑器改 `index.html`/`build_*.py`，改完务必刷新浏览器确认各模块都在（历史上出现过保存截断）。
- **不要编造数据**：源不可达就如实报告、跳过，不要填假值。

---

## 5. 数据源速查

| 数据 | 源 | 接口 | 频率 |
|---|---|---|---|
| 美/欧/日央行表、各汇率 | FRED | WALCL/ECBASSETSW/JPNASSETS/DEXUSEU/DEXJPUS/DEXCHUS | 周/日 |
| 中国央行表 | AkShare | macro_china_central_bank_balance | 月 |
| 中国 M1/M2 | AkShare | macro_china_money_supply | 月 |
| 金/银/指数/大宗 | Yahoo（金银兜底上海金交所） | GC=F/SI=F/^GSPC/^IXIC/000001.SS/^HSI/CL=F/HG=F/^BCOM | 日 |
| 净流动性/RRP/SOFR/IORB | FRED | WALCL/WTREGEN/RRPONTSYD/WRESBAL/SOFR/IORB | 周/日 |

---

## 6. 迁移检查清单

- [ ] 整个文件夹拷到 Mac（含 `.github/`、所有 `.py`/`.js`/`.json`/`.md`）
- [ ] Mac 建 venv、`pip install -r requirements.txt`、跑通 `build_data.py` + `build_weekly.py`
- [ ] 浏览器打开 `index.html` 确认五层模块都正常
- [ ] 选方案 A 或 B 配好自动化
- [ ] （可选）在 Mac Claude 应用重建月度摘要 LLM 任务
- [ ] Windows 本机：该项目定时任务已关闭 ✅（其余业务任务未动）
