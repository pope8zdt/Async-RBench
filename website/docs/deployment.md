# 无常驻服务器部署

本方案：官网静态托管，参与者电脑运行评测，维护者审核结果。官网无需数据库或在线评测任务队列。当前代码已包含 Track A 真实配置生成、教程、真实实验快照和 Track B 模拟。

## GitHub Pages

1. 使用主仓库 `pope8zdt/Async-RBench`，网站源码位于 `website/`，发布工作流位于根目录 `.github/workflows/pages.yml`。仅发布 `website/out/`。
2. 将网站改动合并到 `main`。
3. 在 Settings → Pages → Build and deployment 中选择 GitHub Actions。
4. 在 Actions 中手动运行 `Publish benchmark website`，或推送下一次更新。
5. 工作流安装依赖、验证配置/数据、生成静态页面并部署。打开部署任务显示的 HTTPS 地址即可访问。

工作流使用 Pages 返回的 `base_path`：项目站点通常为 `/仓库名`，账号主页或自定义域名通常为空。图标、下载、导航与实验详情均随路径构建。请按部署任务显示的实际地址访问；本文不虚构已上线域名。

官方依据：[自定义 Pages 工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。

## Vercel

1. 在 Vercel 导入 `pope8zdt/Async-RBench`，Root Directory 设置为 `website`。
2. Framework Preset 使用 **Other**。项目内 `vercel.json` 已指定安装 `npm ci`、构建 `npm run build:static && npm run test:static`、发布目录 `out`。
3. 使用 Node.js 22（至少 22.13）或 24；默认域名部署时不要设置 `NEXT_PUBLIC_BASE_PATH`。
4. 部署后使用项目显示的 Production URL。如需匿名访问，确认该部署的访问保护设置允许公众访问。

官方依据：[构建与输出目录](https://vercel.com/docs/builds/configure-a-build)。

## 本地验证静态产物

在主仓库的 `website/` 目录执行：

```powershell
npm ci
npm run build:static
npm run test:static
python -m http.server 3000 --directory out
```

通过 `http://localhost:3000` 浏览，不要直接双击 HTML 文件。按 Ctrl+C 停止本地预览。

项目子路径构建检查：

```powershell
$env:NEXT_PUBLIC_BASE_PATH = '/Async-RBench'
npm run build:static
npm run test:static
Remove-Item Env:NEXT_PUBLIC_BASE_PATH
```

这个子路径产物部署后必须挂载在 `/Async-RBench/` 下；根目录预览请重新执行默认构建。

## 结果如何进入网站

- 参与者在授权的本地环境完成评测，保留完整证据。模型调用在本地发起，费用由使用的服务决定。
- 参与者使用根目录 `.github/ISSUE_TEMPLATE/benchmark-result.yml` 对应的公开 GitHub 表单提交摘要与复现信息。维护者审核后通过 PR 更新 `website/public/data/experiments.json`；表单不会自动修改数据或认证成绩。
- 维护者检查材料与发布合约。自动格式检查、人工材料审核、独立复现是不同级别，不以本地文件哈希代替独立验证。
- 当前维护者可执行 `python scripts/export_results.py AUTHORIZED_CHECKOUT_PATH` 更新允许公开的内部实验快照。该导出器不是参与者一键提交工具，且不会把快照自动升级为正式排名。
- 将审核后的公开数据更新合并到 `main`，托管平台自动重建。Track B 模拟不会产生提交或榜单记录。

当前 benchmark 含私有验证材料与测试数据；授权本地 checkout 仍是运行前提。公开官网不等于已发布可自由分发的评测包。若要让任意访客直接下载运行，还需单独整理参与者发行包与任务资源授权。
