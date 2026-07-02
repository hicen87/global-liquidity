# 全球流动性周期看板（全球流动性框架）

复现「全球流动性条件 vs 黄金/白银」叠加图，做成可在线访问、每月自动更新的交互看板。

- **蓝色面积**：美/欧/日（+可选中国）央行资产负债表合计的 12 月同比（%），代表流动性边际松紧
- **彩色线**：所选资产价格（右轴），可在三组标的间切换
  - 贵金属：黄金、白银（右移领先 4 月）
  - 指数：标普500、纳斯达克、上证综指、恒生指数
  - 大宗：WTI原油、铜、彭博商品指数
- **领先/滞后排行**：各资产 12 月同比与流动性同比的最佳正相关，横向比较"谁对流动性更敏感"（大宗领先约 10-12 月最清晰）
- **底部红弧**：850天 ≈ 3.5年 周期尺子（上凸穹顶）；红三角 = 实际波谷。**周期锚点 3 种可切换**：
  - 手动锚点：相位锚到 2025-12（与原图一致，默认）
  - 最近谷底：锚到程序检测的最近流动性谷底（2024-04）
  - 拟合谷底：对所有历史谷底做循环均值拟合相位（2023-11）
  - 进行中的当前周期不画完整穹顶，按已过月数画成虚线半弧（标“进行中 X%”），避免把未走完的周期误画成完整曲线
  - 说明：实际流动性谷底间隔 39~72 个月、并非规整 42 个月，故三模式相位各异；自动模式与会有出入，属正常。可在 build_data.py 改 ANCHOR_DATE 调手动相位
- **美元流动性管道（周频）**：净流动性=美联储总资产−财政部TGA−隔夜逆回购，外加 ON RRP/准备金/SOFR−IORB 利差，补月度央行数据的及时性（周频自动更新）
- **分资产锚定流动性**：中国资产(上证/恒生)自动锚定中国 M1 同比(AkShare 货币供应量)；美股/大宗/金银锚定全球 G3；选中国资产时主图蓝线自动切换、口径开关灰显
- **口径切换**：美欧日（原版，回归基线 ≈18万亿 / -4.3%）｜ ＋中国（≈25万亿 / +0.3%）

## 文件结构

```
build_data.py        数据引擎：拉数 → 算同比/周期 → 写 data.json
data.json            月度框架数据（由 build_data.py 生成）
build_weekly.py      周频美元流动性管道引擎 → data_weekly.js
data_weekly.js       周频数据（净流动性/ON RRP/准备金/SOFR-IORB）
index.html           交互看板（ECharts，纯静态，无需后端）
global_liquidity.py  原 matplotlib 出图脚本（保留，本地出 PNG 用）
requirements.txt     Python 依赖
.github/workflows/update.yml   每月自动重算 data.json 并回写
```

## 本地预览

```bash
python build_data.py          # 重新拉数据（可选，data.json 已生成）
python -m http.server 8000    # 然后浏览器打开 http://localhost:8000
```

> 国内访问 FRED/Yahoo 超时：运行前设代理 `set PROXY=http://127.0.0.1:7890`（Windows）/ `export PROXY=...`（mac/Linux）。中国央行(AkShare)国内直连无需代理。

## 上线（Cloudflare Pages，推荐 — 全自动）

需要你自己的 GitHub + Cloudflare 账号（登录态只有你有，这一步我无法代劳）：

1. 把本文件夹推到一个 GitHub 仓库。
2. Cloudflare Dashboard → Workers & Pages → Create → Pages → 连接该仓库。
3. 构建设置：**Framework preset = None**，**Build command 留空**，**Output directory = `/`（根目录）**。
4. 部署完成即得公网地址（`xxx.pages.dev`）。
5. 自动更新：仓库已带 GitHub Actions（每月2号跑 `build_data.py` 回写 `data.json`），push 后 Cloudflare Pages 自动重新部署 → 看板每月自更新。

> GitHub Actions runner 在海外，访问 FRED/Yahoo 通畅，无需代理；AkShare 海外 runner 偶发受限，若失败可在 Actions 日志查看后再议兜底。

## 上线（备选：一条命令，无需 GitHub）

本机装 Node 后：

```bash
npx wrangler pages deploy . --project-name global-liquidity
```

首次会让你登录 Cloudflare。缺点：data.json 不会自动更新，需本地重跑 `build_data.py` 后再 deploy。

## 数据源

| 数据 | 源 | 接口 |
|---|---|---|
| 美/欧/日央行表、各汇率 | FRED | WALCL / ECBASSETSW / JPNASSETS / DEXUSEU / DEXJPUS / DEXCHUS |
| 中国央行表 | AkShare | macro_china_central_bank_balance |
| 金 / 银 | Yahoo（兜底上海金交所） | GC=F / SI=F |
