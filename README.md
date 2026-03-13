# 期权卖方助手

卖方期权策略分析软件，支持三种交易意图：纯收租、愿意接股、主动接股。

## 功能

- **期权扫描**：根据交易意图自动筛选、评分 Sell Put 机会
- **持仓管理**：实时跟踪持仓、风险预警、平仓/展期/赋权操作
- **仪表盘**：核心指标、风险预警、到期日历
- **历史记录**：统计分析、图表、CSV导出

## 部署步骤

### 1. 创建 Supabase 数据库

在 [Supabase](https://supabase.com) 创建免费项目，然后在 SQL Editor 中执行以下建表语句：

```sql
-- 持仓表
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    strategy VARCHAR(20) DEFAULT 'Sell Put',
    intent VARCHAR(20) NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    expiry DATE NOT NULL,
    open_date DATE NOT NULL DEFAULT CURRENT_DATE,
    premium DECIMAL(10,4) NOT NULL,
    margin DECIMAL(12,2) DEFAULT 0,
    current_price DECIMAL(10,4) DEFAULT 0,
    pnl_pct DECIMAL(8,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT '持仓中',
    target_cost DECIMAL(10,2),
    take_profit_price DECIMAL(10,4),
    score DECIMAL(5,1),
    contract_symbol VARCHAR(50),
    close_price DECIMAL(10,4),
    close_date DATE,
    pnl DECIMAL(10,2),
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 历史记录表
CREATE TABLE history (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    strategy VARCHAR(20) DEFAULT 'Sell Put',
    intent VARCHAR(20) NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    expiry DATE NOT NULL,
    open_date DATE NOT NULL,
    close_date DATE NOT NULL,
    premium DECIMAL(10,4) NOT NULL,
    close_price DECIMAL(10,4) DEFAULT 0,
    pnl DECIMAL(10,2) DEFAULT 0,
    pnl_pct DECIMAL(8,2) DEFAULT 0,
    result VARCHAR(20) DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 启用 RLS（行级安全）
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE history ENABLE ROW LEVEL SECURITY;

-- 允许匿名访问（因为使用 anon key）
CREATE POLICY "Allow all on positions" ON positions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on history" ON history FOR ALL USING (true) WITH CHECK (true);
```

### 2. 配置 Secrets

#### 本地开发

创建 `.streamlit/secrets.toml`：

```toml
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your-anon-public-key"
```

#### Streamlit Cloud

在 App Settings → Secrets 中添加：

```toml
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your-anon-public-key"
```

### 3. 部署到 Streamlit Cloud

```bash
# 推送到 GitHub
git init
git add .
git commit -m "初始化期权卖方助手"
git remote add origin https://github.com/你的用户名/OptionsTracker.git
git push -u origin main
```

然后在 [Streamlit Cloud](https://share.streamlit.io)：
1. 点击 "New app"
2. 选择你的 GitHub 仓库
3. Main file path 填 `app.py`
4. 在 Advanced settings → Secrets 中配置 Supabase 连接信息
5. 点击 Deploy

### 4. PWA 添加到手机

部署后在手机浏览器打开应用 URL，点击"添加到主屏幕"即可。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```
