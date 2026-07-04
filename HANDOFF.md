# 交接文档：全球流动性指标复现与自动化（全球流动性框架）

> 给 Codex 执行。目标是把现有 MVP 脚本 `global_liquidity.py` 迭代到「含中国央行 + 850天周期弧线 + 定时自动更新」的可交付状态。
> 执行风格：MVP 分阶段，每个 Phase 跑通验收后再进下一个；优先复用成熟开源库；不要为绕过问题编造假数据或假workaround，跑不通就如实报告。

---

## 0. 背景与最终目标

复现「全球流动性条件 vs 黄金/白银」叠加图：
- **蓝线**：主要央行资产负债表合计（折美元），取 12 个月同比(%) 表示边际松紧。
- **白线**：黄金 / 白银价格，白银右移 3–6 个月（领先关系）。
- **底部弧线**：850天 ≈ 42个月 ≈ 3.5年 周期标记。
- 最终：每月自动更新出图。

核心信条（保证逻辑不跑偏）：流动性同比飙升 → 随后贵金属上涨；流动性同比转负 = 边际转弱预警。当前（2026.05）总量约 18 万亿美元、同比约 -4.3%，处于边际转弱区，与原图一致——**任何改动后这个定性结论不应被破坏，可用作回归检验**。

---

## 1. 当前状态（v1，已验证）

文件：`global_liquidity.py`（随本文档一起交付）。

已跑通的数据源（**在海外网络验证通过**）：

| 数据 | 源 | 代码/接口 | 单位 | 库 |
|---|---|---|---|---|
| 美联储资产 | FRED | `WALCL` | 百万美元 | pandas_datareader |
| 欧央行资产 | FRED | `ECBASSETSW` | 百万欧元 | pandas_datareader |
| 日央行资产 | FRED | `JPNASSETS` | 亿日元(100M) | pandas_datareader |
| 美元/欧元 | FRED | `DEXUSEU` | 美元每欧元 | pandas_datareader |
| 日元/美元 | FRED | `DEXJPUS` | 日元每美元 | pandas_datareader |
| 黄金 | Yahoo | `GC=F` | 美元 | yfinance |
| 白银 | Yahoo | `SI=F` | 美元 | yfinance |

v1 折算逻辑（统一到「万亿美元」，已验证正确）：
```
fed_t = WALCL / 1e6
ecb_t = ECBASSETSW * DEXUSEU / 1e6
boj_t = JPNASSETS / (DEXJPUS * 1e4)
gl    = (fed_t + ecb_t + boj_t)          # 月末重采样后相加
gl_yoy = gl.pct_change(12) * 100         # 蓝线
```

---

## 2. 环境约束（重要）

- 运行机：**Windows，Python 3.14**，用户为 Python 初学者。
- 解释器路径：`C:/Users/Administrator/AppData/Local/Python/pythoncore-3.14-64/python.exe`
- 装包必须用该解释器：`<python.exe> -m pip install ...`
- **用户在中国大陆**：FRED（fred.stlouisfed.org）、Yahoo Finance 国内**经常超时/连不上**。这是首要风险。
- 中文字体：Windows 用 `Microsoft YaHei` / `SimHei`，脚本已设置。

---

## Phase 0：数据源可达性加固（金银部分✅已做, 央行表代理待办）

**问题**：FRED / Yahoo 在国内可能 `Unable to read URL` / `ConnectionError` / 长时间卡死。

**任务**：
1. 给所有网络请求加 **超时 + 重试**（建议 `tenacity` 或简单 for 循环，3 次、指数退避）。
2. 把数据获取抽象成「主源 + 备用源」：主源失败自动切备用源，并在控制台**明确打印用了哪个源**。
3. 备用源（国内可直连，已验证可用）：

| 数据 | 国内备用源（AkShare） | 接口 | 单位 |
|---|---|---|---|
| 黄金 | 上海金交所 | `ak.spot_hist_sge(symbol='Au99.99')` → `close` | 人民币/克 |
| 白银 | 上海金交所 | `ak.spot_hist_sge(symbol='Ag(T+D)')` → `close` | 人民币/克 |
| 人民币汇率 | AkShare/新浪 | `ak.currency_boc_sina` 或 `ak.fx_spot_quote`（需Codex验证字段） | — |

> 注：美/欧/日央行表 AkShare 没有，只能走 FRED。若 FRED 国内不可达，方案是让**用户在脚本顶部填一个 HTTP 代理变量**（`PROXY = "http://127.0.0.1:7890"`，留空则不用），requests/pandas_datareader 通过该代理访问。不要硬编码代理，留成可配置项。
> 若用 SGE 金价（人民币/克）替代 Yahoo（美元/盎司），需用汇率换算或在图上注明单位差异——优先保持「主源 Yahoo 用美元」，备用源仅在主源失败时启用并注明。

**验收**：在「无代理 / 有代理 / FRED不通」三种情况下脚本都能给出明确反馈（成功出图，或清楚报告哪个源不可达），不会静默卡死。

---

## Phase 1：加入中国央行

**接口（已验证，国内直连，AkShare）**：
```python
import akshare as ak
df = ak.macro_china_central_bank_balance()
# 关键列: '统计时间'(如 '2026.5')、'总资产'(单位: 亿元人民币)
# 353+ 行月度数据，更新至最新月
```

**折算**（加入 gl）：
```
pboc_t = 总资产(亿元) / (CNY_per_USD * 1e4)   # → 万亿美元
# CNY_per_USD: FRED 'DEXCHUS'(人民币每美元)；国内不通时用 AkShare 汇率
gl = fed_t + ecb_t + boj_t + pboc_t
```

**注意**：
- `统计时间` 格式是 `'2026.5'`，需解析成月末日期对齐其他序列。
- 中国央行表是月度、披露有滞后（通常滞后 1 个月），对齐时用 `dropna()` 自然截断即可。
- 加中国后总量会显著抬升（中国央行约 48 万亿人民币 ≈ 6.7 万亿美元），蓝线形态会变化——**这是预期内的**，不是 bug。

**验收**：出图正常，控制台打印「最新全球流动性总量（含中国）」，且 2008/2020 流动性同比仍出现显著正峰、当前仍处边际转弱区（定性回归检验通过）。

---

## Phase 2：850天 / 3.5年 周期弧线  ✅【已完成, 见 global_liquidity.py】

> 已实现: `draw_cycle_arcs()`。默认 `ARC_MODE='fixed'`(以首个显著波谷为相位锚点, 每 `CYCLE_MONTHS=42` 个月画等距半椭圆弧, 还原"3.5年尺子"); 可切 `ARC_MODE='trough'`(连实际波谷)。两种模式都用红三角标 `scipy.find_peaks` 找到的实际波谷供对照。Codex 无需重做此阶段, 后续 Phase 1/3 直接在此版本上叠加。


在图底部叠加周期弧线（复现原图底部的半圆弧 + `3.5yrs` 标注）。

**算法（MVP）**：
1. 对流动性序列找**波谷**：`scipy.signal.find_peaks(-series, distance=30)`（distance 约束最小间距≈30个月，避免噪声谷）。对 `gl_yoy` 或 `gl` 找谷皆可，建议对 `gl_yoy`（与蓝线一致）。
2. 在每对相邻波谷之间，于子图底部画一段**向下凸的半椭圆弧**（`matplotlib.patches.Arc`，或用参数方程画半椭圆），弧的两端落在两个波谷的 x 位置。
3. 在每段弧上方标注两谷间隔月数（如 `41m` / `3.4yrs`），对照 42个月理论值。

**可选第二模式**（更贴近原图）：从一个锚定波谷起，每隔**固定 42 个月**画等距弧（`mode='fixed'`），与「实际波谷弧」（`mode='trough'`）二选一，参数化。MVP 先交付 `mode='trough'`。

**验收**：弧线渲染在子图底部，不遮挡主曲线；标注的周期间隔大多落在 ~36–48 个月区间（符合 3.5年周期），明显偏离的谷允许存在但需肉眼合理。

---

## Phase 3：定时自动更新

**复用用户已有范式**（World Cup 项目：Python + GitHub Actions + cron，已跑通）。

**MVP 方案**：
1. 仓库化：`global_liquidity.py` + `requirements.txt` + `.github/workflows/update.yml`。
2. Actions：`schedule: cron` 每月 1 号跑一次（央行数据月度，日频无意义）；`workflow_dispatch` 支持手动触发。
3. 产物：生成 `output/global_liquidity.png`，用 `git commit` 回写仓库 `output/` 目录（或用 actions-artifact 上传）。
4. **网络注意**：GitHub Actions runner 在海外，**访问 FRED/Yahoo 通畅，反而不需要代理**；但 AkShare（中国央行）从海外 runner 访问东财/新浪可能受限——Phase 0 的主备源切换在此同样适用，需验证 runner 上 AkShare 中国央行接口是否可达，不可达则需 Phase 0 的代理/备源逻辑兜底，或考虑中国央行数据改用其他海外可达源（如 FRED 中国 M2 代理 `MABMM301CNM189S`，作为退路，注意口径是 M3 不是央行表，需在图上注明）。
5. 可选：跑完用邮件/Server酱推送图到微信。非 MVP，最后做。

**验收**：手动触发 workflow 能成功生成并提交 png；cron 配置正确。

---

## 4. 全局约束（不要做的事）

- 不要编造数据或在源不可达时填充假值；跑不通就报告。
- 不要把代理地址、API key、邮箱密码硬编码进脚本；用环境变量或顶部可配置项。
- 不要把 v1 已验证的单位换算逻辑改错——改动后用第 0 节的定性回归检验自查。
- 不要过度工程化：每个 Phase 出一个能跑的版本即可，不要一次性堆全部功能。

## 5. 交付物清单

- [部分] Phase 0：金银已实现 yfinance重试+上海金交所兜底✅; 央行表(FRED)国内代理兜底仍待办
- [ ] Phase 1：含中国央行的版本，定性回归检验通过
- [x] Phase 2：叠加 850天周期弧线 ✅
- [ ] Phase 3：`requirements.txt` + GitHub Actions workflow，手动触发跑通
- [ ] 每个 Phase 在 commit message 注明阶段与验收结果
