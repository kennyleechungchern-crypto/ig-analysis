# IG 每日分析系统 · 设置指南

## 第一步：申请 Instagram Graph API 凭证

### 1.1 创建 Facebook Developer App
1. 前往 [developers.facebook.com](https://developers.facebook.com)
2. 点击 **My Apps → Create App**
3. 选择 **Business** 类型
4. 填写 App 名称 → 创建

### 1.2 添加 Instagram 产品
1. 进入 App Dashboard
2. 左侧菜单 → **Add Product** → 找到 **Instagram** → 点击 Set Up
3. 选择 **Instagram Graph API**

### 1.3 获取 Access Token
1. 进入 **Instagram Graph API → Getting Started**
2. 点击 **Generate Access Token**，用你的 Instagram Business 账号授权
3. 复制 **Short-lived Token**（1小时有效）

### 1.4 换成长期 Token（60 天有效）
```bash
curl "https://graph.facebook.com/v21.0/oauth/access_token\
?grant_type=fb_exchange_token\
&client_id=YOUR_APP_ID\
&client_secret=YOUR_APP_SECRET\
&fb_exchange_token=SHORT_LIVED_TOKEN"
```
复制返回的 `access_token`，这就是 `IG_ACCESS_TOKEN`。

> ⚠️ Long-lived token 60天后过期，需要每次过期前重新换取并更新 GitHub Secret。

---

## 第二步：获取 Notion Token

1. 前往 [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 点击 **New integration**
3. 填写名称，选择对应的 Workspace → Submit
4. 复制 **Internal Integration Token**（以 `secret_` 开头）
5. **重要**：在你想存放报告的 Notion 页面，右上角 **...** → **Connections** → 添加你的 Integration

---

## 第三步：获取 Notion Page ID

1. 打开你想存放报告的 Notion 页面
2. URL 格式为：`https://www.notion.so/Your-Page-Title-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
3. 最后 32 位字符就是 Page ID（格式化为：`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）

---

## 第四步：配置 GitHub Secrets

进入 GitHub Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 值 |
|-------------|-----|
| `IG_ACCESS_TOKEN` | Instagram 长期 Token |
| `ANTHROPIC_API_KEY` | Claude API Key |
| `NOTION_TOKEN` | Notion Integration Token |
| `NOTION_PAGE_ID` | Notion 父页面 ID |

---

## 第五步：手动触发测试

1. 进入 GitHub Repo → **Actions → IG Daily Analysis**
2. 点击 **Run workflow** 测试一次
3. 检查 Notion 是否出现了今日报告页面

---

## 自动化调度

已配置为每天 **台北时间 09:00**（UTC 01:00）自动执行。

如需修改时间，编辑 `.github/workflows/daily_analysis.yml` 中的 cron 表达式：
```yaml
- cron: "0 1 * * *"  # UTC 时间，台北 = UTC+8
```

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入真实 Token
cd src
export $(cat ../.env | xargs)
python main.py
```
