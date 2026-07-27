# ? 宇航员创作工作台（升级版）

为彩妆 / 护肤好物分享赛道博主打造的**一站式创作工作台**，粉色 + 白色 + 金色点缀，左侧 8 大模块：每日计划 · 选题灵感 · 爆款热点/二创 · 内容日历 · 内容复盘 · 数据统计 · 投资理财 · 备忘录。

---

## ? 功能一览

| 模块 | 功能 |
|---|---|
| **? 每日计划** | 任务增删改勾选，默认包含健身课 / 14:30 基金 / 多邻国 |
| **? 选题灵感** | AI 改写后的 10 条爆款选题（带标签 + 钩子角度） |
| **? 爆款热点/二创** | 抖音/小红书/B站/微博/微信专辑多平台抓取，10 条二创角度 |
| **? 内容日历** | 粉色点=已发布，金色点=计划发布，点击日期添加发布计划 |
| **? 内容复盘** | 记录标题 + 数据 + ??问题 / ?做对 / →下次优化 |
| **? 数据统计** | 总发布 / 平均播放 / 平均转化 / 最佳转化 + 趋势柱状图 |
| **? 投资理财** | 大盘指数 + 自选基金净值 + 财经快讯，工作日 14:30 看盘 |
| **? 备忘录** | 随手记，灵感不溜走 |

## ? 新增增强功能

1. **微信专辑 RSSHub 接入**：完整解析微信公众号专辑文章，提取标题 + 摘要 + 发布时间
2. **发布倒计时**：顶部实时倒计时条，一键设置下次发布时间
3. **AI 视频脚本自动生成**：选题卡片上点击「生成脚本」，可生成前 3 秒钩子 / 分镜 / CTA / 标题 / 标签（支持 OpenAI API 或本地模板）
4. **数据统计图表**：基于复盘记录生成发布数趋势 + 转化趋势
5. **数据导出/云同步**：支持 JSON 备份导入导出，可配置 GitHub Gist 跨设备同步
6. **投资理财资讯**：新增独立模块，金色主题，基金可增删

---

## ? 文件结构

```
creator-dashboard/
├── creator_dashboard.html     # 主工作台页面（单页 HTML，手机/电脑）
├── hot_scraper.py             # 每日抓取脚本（热点 + 财经）
├── data/
│   ├── hot_content.json       # 默认热榜/选题数据
│   └── finance.json           # 默认财经数据
├── deploy-gh-pages.sh         # 一键部署到 GitHub Pages（可选）
└── README.md                  # 本文档
```

---

## ? 快速开始

### 方案 A：零代码部署到 GitHub Pages（推荐）

1. 把 `creator-dashboard` 文件夹 push 到 GitHub（或直接网页上传）
2. 打开仓库 **Settings → Pages**
3. Source 选择 **Deploy from a branch → main → / (root)**，Save
4. 等待 1-2 分钟，访问 `https://你的用户名.github.io/creator-dashboard/`
5. 手机 Safari/Chrome 打开 → 添加到主屏幕

也可以直接运行：

```bash
cd creator-dashboard
chmod +x deploy-gh-pages.sh
./deploy-gh-pages.sh 你的GitHub用户名 你的仓库名
```

### 方案 B：本地打开

```bash
cd creator-dashboard
python -m http.server 8765
```

浏览器打开 `http://localhost:8765/creator_dashboard.html`

### 方案 C：Netlify 拖拽部署

1. 打开 [app.netlify.com/drop](https://app.netlify.com/drop)
2. 把 `creator-dashboard` 文件夹拖进去
3. 30 秒后拿到公网链接

---

## ? 配置自动抓取热榜

### 1. 安装依赖

```bash
pip install requests
```

### 2. 设置环境变量

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx   # GitHub Personal Access Token（需要 gist 权限）
export GIST_ID=xxxxxxxxxxxxxxxxxxxxxxxx     # 你的公开 Gist ID
export OPENAI_API_KEY=sk-xxxxxxxxxxxx       # 可选：有 OpenAI Key 改写质量更高
export WX_RSS_URLS="https://rsshub.app/wechat/mp/你的账号1,https://rsshub.app/wechat/mp/你的账号2"  # 可选
export FUNDS="110011,161725,005827"        # 可选：自定义自选基金代码
```

### 3. 手动运行

```bash
cd creator-dashboard
python hot_scraper.py
```

脚本会同时生成 `data/hot_content.json` 和 `data/finance.json`，并推送到 GitHub Gist。

### 4. 配置网页读取 Gist

打开 `creator_dashboard.html`，找到：

```js
const gistUrl = loadData(STORAGE_KEYS.gistUrl, '');
```

直接在工作台里点击右上角 **同步图标** → 输入 Gist Raw URL 保存即可。

或者预先在代码里写死：

```js
const GIST_HOT_URL = 'https://gist.githubusercontent.com/你的用户名/你的gist_id/raw/hot_content.json';
const GIST_FIN_URL = 'https://gist.githubusercontent.com/你的用户名/你的gist_id/raw/finance.json';
```

### 5. 每天自动跑

**GitHub Actions（零成本，推荐）**：

```yaml
# .github/workflows/daily-hot.yml
name: Daily Content & Finance
on:
  schedule: - cron: '0 0 * * *'   # UTC 0点 = 北京时间 8 点
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests
      - run: python hot_scraper.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GIST_ID: ${{ secrets.GIST_ID }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          WX_RSS_URLS: ${{ secrets.WX_RSS_URLS }}
          FUNDS: ${{ secrets.FUNDS }}
```

在仓库 **Settings → Secrets and variables → Actions** 里配置上述 secrets。

---

## ? 添加到手机桌面

### iPhone Safari

1. 打开工作台网址
2. 点击底部 **分享按钮**
3. 选择 **添加到主屏幕**
4. 命名：「? 创作工作台」→ 添加

### Android Chrome

1. 打开工作台网址
2. 点击右上角 **?**
3. 选择 **添加到主屏幕 / 安装应用**

---

## ? 视觉风格

- 主色：`#ff85a2`（粉） / `#d63384`（深粉） / `#ffffff`（白）
- 点缀：`#f5a623`（金）用于投资理财模块
- 背景：`#fff5f7`（奶粉渐变）
- 全部图标使用 **inline SVG**，不依赖系统字体
- 手机端自动切换为顶部横向滚动导航

---

## ?? 自定义配置

### 修改赛道

编辑 `hot_scraper.py`：

```python
TRACK_NAME = "彩妆好物 / 护肤好物"   # 改这里
```

### 配置 AI 脚本生成

编辑 `creator_dashboard.html`：

```js
const AI_CONFIG = {
  apiKey: 'sk-你的key',      // 填入 OpenAI 或兼容 API Key
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini'
};
```

未配置时会自动使用本地模板生成。

### 修改默认基金

编辑 `creator_dashboard.html` 里的 `DEFAULT_FUNDS`，或抓取脚本里的 `DEFAULT_FUND_CODES`。

---

## ? 常见问题

**Q：网页打开是空白的？**
A：确保 `data/hot_content.json` 和 `data/finance.json` 存在。若用 `file://` 协议打开可能因 fetch 限制失败，建议用本地服务器或部署。

**Q：抖音 App 唤起没反应？**
A：浏览器对 scheme 唤起有限制。iOS Safari 通常可以；Android 可能需要用户手势；失败会自动跳网页版。

**Q：Gist 同步后网页没变化？**
A：Gist Raw URL 有缓存，脚本推送后网页会加 `?t=时间戳` 刷新。若仍无变化，检查 Gist 是否公开以及 URL 是否正确。

**Q：怎么备份数据？**
A：点击右上角下载按钮导出 JSON，或在「云同步」弹窗里手动导入导出。

---

## ? 下一步建议

1. ? 先部署到 GitHub Pages / Netlify，手机打开试用
2. ? 配置 GitHub Token + Gist ID，跑 `python hot_scraper.py`
3. ? 接入你的微信公众号专辑 RSSHub 地址
4. ? 配置 OpenAI API Key，让 AI 脚本生成更智能
5. ? 设置 GitHub Actions 每天自动更新

祝爆款不断 ???