# 部署手册 · GitHub Pages + Cloudflare 域名

线上访问的是 **`index.html`**（模块版）——真实服务器上能正常读取 `data.js`/`data.json`，
且 `.github/workflows` 里的自动更新工作流每周/每月推送新数据后，网站会自动刷新。
`index_standalone.html` 保留作离线单文件备份。

下面命令在**你的 Mac 上**、项目目录里执行（`cd ~/Documents/Global_Liquidity`）。

---

## 1. 推到 GitHub

如果目录里已有 `.git` 但有问题，先重来一次：`rm -rf .git`

```bash
git init
git add -A
git commit -m "init: 全球流动性看板"
git branch -M main
# 在 GitHub 网页先建一个空仓库(比如叫 global-liquidity)，再执行：
git remote add origin https://github.com/<你的GitHub用户名>/global-liquidity.git
git push -u origin main
```

## 2. 开启 GitHub Pages

GitHub 仓库页 → **Settings → Pages**：

- Source 选 **Deploy from a branch**
- Branch 选 **main** / 目录 **/(root)** → Save

等 1–2 分钟，会给出 `https://<用户名>.github.io/global-liquidity/` 能访问即成功。

## 3. 绑定域名 investment.brassivo.com（Cloudflare DNS）

`CNAME` 文件已生成好，内容就是 `investment.brassivo.com`（第 1 步 push 时会一起上传，无需再动）。

**Cloudflare 后台 → 选择 brassivo.com → DNS → 添加记录：**

| 类型  | 名称          | 目标（Target）        | 代理状态            |
|-------|---------------|-----------------------|---------------------|
| CNAME | `investment`  | `<你的GitHub用户名>.github.io` | 先选 DNS only(灰云) |

> 先用「DNS only(灰云)」让 GitHub 顺利签发 HTTPS 证书；证书生效后可改回「Proxied(橙云)」并把 SSL/TLS 模式设为 **Full**。

**回到 GitHub → Settings → Pages → Custom domain** 填 `investment.brassivo.com` → Save，
证书签发后勾选 **Enforce HTTPS**。

DNS 生效通常几分钟到几十分钟，之后 `https://investment.brassivo.com` 即可访问。

---

## 4. 自动更新（数据自刷新）

`.github/workflows/update.yml`（每月15号）和 `update_weekly.yml`（每周六）已配置好，
推到 GitHub 后自动生效，会自行跑 `build_data.py` / `build_weekly.py` 并回写数据、触发 Pages 重新部署。
无需服务器。首次可在 **Actions** 页手动点 **Run workflow** 验证一次。

> 注意：GitHub Actions 跑 `build_data.py` 需要 `requirements.txt` 里含 akshare（沪深300 全历史依赖它）。
> 若 requirements 缺 akshare，请补上再推。

---

## 若想用 Cloudflare Pages 代替 GitHub Pages（可选）
连接同一个 GitHub 仓库 → 构建命令留空、输出目录填 `/` → 部署，再在 Pages 项目里绑定自定义域名即可（DNS 同在 Cloudflare，一键关联）。数据自动更新仍靠 GitHub Actions。
