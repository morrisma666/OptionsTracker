"""
卖方期权分析软件 - 主入口
支持三种交易意图：纯收租、愿意接股、主动接股
"""

import streamlit as st

# ========== 页面配置 ==========
st.set_page_config(
    page_title="期权卖方助手",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="auto",
)

# ========== PWA + 响应式布局 CSS ==========
st.markdown("""
<head>
    <link rel="manifest" href="app/static/manifest.json">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#1a1a2e">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
</head>
<style>
/* 全局样式 */
.main .block-container { padding-top: 1rem; }
.metric-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 12px; padding: 1rem 1.2rem;
    border-left: 4px solid #0f3460; margin-bottom: 0.5rem;
}
.metric-card h3 { font-size: 0.85rem; color: #8892b0; margin: 0; }
.metric-card .value { font-size: 1.6rem; font-weight: 700; color: #e6f1ff; }
.score-badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-weight: 600; font-size: 0.9rem;
}
.score-high { background: #10b981; color: white; }
.score-mid { background: #f59e0b; color: white; }
.score-low { background: #ef4444; color: white; }
.warning-card {
    background: #fef3c7; border-left: 4px solid #f59e0b;
    border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; color: #92400e;
}
.danger-card {
    background: #fee2e2; border-left: 4px solid #ef4444;
    border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; color: #991b1b;
}
.option-card {
    background: #1e293b; border-radius: 12px; padding: 1.2rem;
    margin-bottom: 1rem; border: 1px solid #334155;
}
.intent-tag {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.75rem; font-weight: 600;
}
.tag-income { background: #059669; color: white; }
.tag-willing { background: #2563eb; color: white; }
.tag-active { background: #7c3aed; color: white; }

/* 手机底部导航栏 */
@media (max-width: 768px) {
    section[data-testid="stSidebar"] { display: none !important; }
    .bottom-nav {
        display: flex !important; position: fixed; bottom: 0; left: 0; right: 0;
        background: #0f172a; border-top: 1px solid #334155;
        z-index: 999; padding: 8px 0;
    }
    .bottom-nav a {
        flex: 1; text-align: center; text-decoration: none;
        color: #94a3b8; font-size: 0.75rem; padding: 4px 0;
    }
    .bottom-nav a.active { color: #60a5fa; }
    .bottom-nav .nav-icon { font-size: 1.3rem; display: block; }
    .main .block-container { padding-bottom: 70px; }
}
@media (min-width: 769px) {
    .bottom-nav { display: none !important; }
}
</style>

<!-- 手机底部导航栏 -->
<div class="bottom-nav">
    <a href="/" class="active"><span class="nav-icon">📊</span>仪表盘</a>
    <a href="/扫描"><span class="nav-icon">🔍</span>扫描</a>
    <a href="/持仓"><span class="nav-icon">💼</span>持仓</a>
    <a href="/历史"><span class="nav-icon">📋</span>历史</a>
</div>
""", unsafe_allow_html=True)


# ========== 仪表盘主页 ==========
def main():
    st.title("📊 期权卖方助手")
    st.caption("卖方期权策略分析 · 持仓管理 · 风险监控")

    from utils.db import get_dashboard_stats, get_positions
    from datetime import datetime, date

    stats = get_dashboard_stats()

    if not stats:
        st.info("👋 欢迎使用期权卖方助手！请先配置 Supabase 数据库连接。")
        st.markdown("""
        ### 快速开始
        1. 在 [Supabase](https://supabase.com) 创建免费项目
        2. 执行建表 SQL（见 README）
        3. 在 `.streamlit/secrets.toml` 配置：
        ```toml
        SUPABASE_URL = "https://your-project.supabase.co"
        SUPABASE_KEY = "your-anon-key"
        ```
        4. 重启应用即可使用
        """)

        st.markdown("---")
        st.subheader("🔍 先试试期权扫描")
        st.page_link("pages/1_扫描.py", label="前往扫描页面", icon="🔍")
        return

    # ===== 顶部4个核心指标 =====
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""<div class="metric-card">
            <h3>本月已收权利金</h3>
            <div class="value">${stats.get('month_premium', 0):,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        # 浮动盈亏
        positions = stats.get("positions", [])
        floating_pnl = 0
        for p in positions:
            prem = float(p.get("premium", 0))
            cur = float(p.get("current_price", 0))
            floating_pnl += (prem - cur) * 100
        st.markdown(f"""<div class="metric-card">
            <h3>持仓浮动盈亏</h3>
            <div class="value" style="color: {'#10b981' if floating_pnl >= 0 else '#ef4444'}">
                ${floating_pnl:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card">
            <h3>本年累计收入</h3>
            <div class="value">${stats.get('year_income', 0):,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="metric-card">
            <h3>账户胜率</h3>
            <div class="value">{stats.get('win_rate', 0):.1f}%</div>
        </div>""", unsafe_allow_html=True)

    # ===== 第二行指标 =====
    col1, col2, col3, col4 = st.columns(4)
    today = date.today()

    # 计算风险数据
    positions = stats.get("positions", [])
    expiring_7d = 0
    risk_count = 0
    total_margin = 0
    for p in positions:
        expiry = p.get("expiry", "")
        if expiry:
            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                dte = (exp_date - today).days
                if dte <= 7:
                    expiring_7d += 1
                if dte <= 3:
                    risk_count += 1
            except ValueError:
                pass
        total_margin += float(p.get("margin", 0))

    with col1:
        st.metric("当前持仓数", f"{len(positions)} 笔")
    with col2:
        st.metric("7日内到期", f"{expiring_7d} 笔")
    with col3:
        st.metric("风险预警数", f"{risk_count}")
    with col4:
        st.metric("保证金占用", f"${total_margin:,.0f}")

    st.markdown("---")

    # ===== 两列布局 =====
    left, right = st.columns(2)

    with left:
        st.subheader("⚠️ 风险预警")
        if not positions:
            st.info("暂无持仓")
        else:
            has_warning = False
            # 按标的分组检查超配
            ticker_counts = {}
            week_expiry_count = 0
            for p in positions:
                ticker = p.get("ticker", "")
                ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
                expiry = p.get("expiry", "")
                if expiry:
                    try:
                        exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                        dte = (exp_date - today).days
                        if dte <= 7:
                            week_expiry_count += 1
                        if dte <= 3:
                            has_warning = True
                            st.markdown(f'<div class="danger-card">🔴 {ticker} ${p.get("strike")} '
                                        f'{expiry} 仅剩{dte}天到期！</div>', unsafe_allow_html=True)
                        elif dte <= 7:
                            has_warning = True
                            st.markdown(f'<div class="warning-card">🟠 {ticker} ${p.get("strike")} '
                                        f'{expiry} 还剩{dte}天到期</div>', unsafe_allow_html=True)
                    except ValueError:
                        pass

            for ticker, count in ticker_counts.items():
                if count >= 3:
                    has_warning = True
                    st.markdown(f'<div class="warning-card">⚠️ {ticker} 持仓{count}笔，注意超配风险</div>',
                                unsafe_allow_html=True)

            if week_expiry_count > 3:
                st.markdown(f'<div class="warning-card">⚠️ 本周有{week_expiry_count}笔到期，注意集中到期风险</div>',
                            unsafe_allow_html=True)

            if not has_warning:
                st.success("✅ 当前无风险预警")

        # 保证金进度条
        st.subheader("💰 保证金使用")
        account_size = st.session_state.get("account_size", 100000)
        margin_pct = (total_margin / account_size * 100) if account_size > 0 else 0
        color = "#10b981" if margin_pct < 50 else "#f59e0b" if margin_pct < 75 else "#ef4444"
        st.markdown(f"""
        <div style="background:#1e293b;border-radius:8px;padding:12px;margin-top:8px">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span>已用 ${total_margin:,.0f}</span>
                <span>{margin_pct:.1f}%</span>
            </div>
            <div style="background:#334155;border-radius:4px;height:12px">
                <div style="background:{color};width:{min(margin_pct,100):.1f}%;height:100%;border-radius:4px"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.subheader("📅 近期到期日历")
        if positions:
            sorted_pos = sorted(positions, key=lambda x: x.get("expiry", ""))
            for p in sorted_pos[:8]:
                expiry = p.get("expiry", "")
                ticker = p.get("ticker", "")
                intent = p.get("intent", "")
                tag_class = {"纯收租": "tag-income", "愿意接股": "tag-willing", "主动接股": "tag-active"}.get(intent, "tag-income")
                st.markdown(f"""<div style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #334155">
                    <span style="width:90px;color:#94a3b8">{expiry}</span>
                    <strong style="width:60px">{ticker}</strong>
                    <span>${p.get('strike', 0)}</span>
                    <span class="intent-tag {tag_class}" style="margin-left:auto">{intent}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("暂无持仓")

        st.subheader("📢 财报预警")
        st.caption("持仓标的近期财报日期将在此显示")

    # ===== 底部持仓概览 =====
    st.markdown("---")
    st.subheader("📋 当前持仓概览")
    if positions:
        for p in positions:
            intent = p.get("intent", "")
            tag_class = {"纯收租": "tag-income", "愿意接股": "tag-willing", "主动接股": "tag-active"}.get(intent, "tag-income")
            pnl = float(p.get("pnl_pct", 0))
            pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
            st.markdown(f"""<div class="option-card" style="display:flex;align-items:center;flex-wrap:wrap;gap:12px">
                <strong style="font-size:1.1rem">{p.get('ticker','')}</strong>
                <span>${p.get('strike',0)} | {p.get('expiry','')}</span>
                <span class="intent-tag {tag_class}">{intent}</span>
                <span style="color:{pnl_color};margin-left:auto;font-weight:600">{pnl:+.1f}%</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("暂无持仓记录。前往 🔍 扫描页面开始分析！")

    # 账户大小设置（侧边栏）
    with st.sidebar:
        st.markdown("---")
        account = st.number_input("账户总资金 ($)", value=100000, step=10000, key="account_size_input")
        if account != st.session_state.get("account_size", 100000):
            st.session_state["account_size"] = account


if __name__ == "__main__":
    main()
