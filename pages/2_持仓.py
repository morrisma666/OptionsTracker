"""
持仓管理页 - 查看、管理当前持仓，风险预警
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="持仓管理", page_icon="💼", layout="wide")

from utils.db import get_positions, update_position, close_position, assign_position


# ========== 样式 ==========
st.markdown("""<style>
.metric-card { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 12px; padding: 1rem 1.2rem; border-left: 4px solid #0f3460; margin-bottom: 0.5rem; }
.metric-card h3 { font-size: 0.85rem; color: #8892b0; margin: 0; }
.metric-card .value { font-size: 1.6rem; font-weight: 700; color: #e6f1ff; }
.warning-card { background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; color: #92400e; }
.danger-card { background: #fee2e2; border-left: 4px solid #ef4444; border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; color: #991b1b; }
.intent-tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.tag-income { background: #059669; color: white; }
.tag-willing { background: #2563eb; color: white; }
.tag-active { background: #7c3aed; color: white; }
</style>""", unsafe_allow_html=True)


st.title("💼 持仓管理")

# 获取持仓
positions = get_positions(status="持仓中")

if not positions:
    st.info("暂无持仓记录。前往 🔍 扫描页面添加持仓。")
    st.page_link("pages/1_扫描.py", label="前往扫描", icon="🔍")
    st.stop()

# ========== 风险预警汇总 ==========
st.subheader("⚠️ 风险预警")
today = date.today()
warnings = []
ticker_counts = {}
week_expiry = 0

for p in positions:
    ticker = p.get("ticker", "")
    ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
    expiry = p.get("expiry", "")
    if expiry:
        try:
            exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte <= 3:
                warnings.append(("danger", f"🔴 {ticker} ${p.get('strike')} {expiry} — 仅剩{dte}天！需立即处理"))
            elif dte <= 7:
                warnings.append(("warning", f"🟠 {ticker} ${p.get('strike')} {expiry} — 还剩{dte}天到期"))
                week_expiry += 1
        except ValueError:
            pass
    # 安全边际检查
    otm_pct = float(p.get("otm_pct", 10))
    if otm_pct < 5:
        warnings.append(("warning", f"⚠️ {ticker} ${p.get('strike')} 安全边际仅{otm_pct:.1f}%"))

# 同标的超配
for ticker, count in ticker_counts.items():
    if count >= 3:
        warnings.append(("warning", f"⚠️ {ticker} 持仓{count}笔，注意超配风险"))

if week_expiry > 3:
    warnings.append(("warning", f"⚠️ 同一周到期超过{week_expiry}笔，注意集中到期风险"))

if warnings:
    for level, msg in warnings:
        css_class = "danger-card" if level == "danger" else "warning-card"
        st.markdown(f'<div class="{css_class}">{msg}</div>', unsafe_allow_html=True)
else:
    st.success("✅ 当前无风险预警")

st.markdown("---")

# ========== 持仓列表 ==========
st.subheader(f"📋 当前持仓 ({len(positions)}笔)")

for i, p in enumerate(positions):
    intent = p.get("intent", "纯收租")
    tag_class = {"纯收租": "tag-income", "愿意接股": "tag-willing", "主动接股": "tag-active"}.get(intent, "tag-income")

    with st.expander(
        f"{p.get('ticker', '')} | ${p.get('strike', 0)} | {p.get('expiry', '')} | {intent}",
        expanded=False,
    ):
        # 基本信息
        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f"**股票代码**: {p.get('ticker', '')}")
        col2.markdown(f"**策略**: {p.get('strategy', 'Sell Put')}")
        col3.markdown(f'<span class="intent-tag {tag_class}">{intent}</span>', unsafe_allow_html=True)
        col4.markdown(f"**状态**: {p.get('status', '持仓中')}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("行权价", f"${p.get('strike', 0)}")
        col2.metric("到期日", p.get("expiry", ""))

        # 计算DTE
        expiry = p.get("expiry", "")
        dte = "N/A"
        if expiry:
            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                dte = (exp_date - today).days
            except ValueError:
                pass
        col3.metric("DTE", f"{dte}天" if isinstance(dte, int) else dte)
        col4.metric("开仓日期", p.get("open_date", ""))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("收取权利金", f"${p.get('premium', 0):.2f}")
        col2.metric("保证金占用", f"${p.get('margin', 0):,.0f}")
        current = float(p.get("current_price", 0))
        premium = float(p.get("premium", 0))
        pnl = premium - current
        pnl_pct = (pnl / premium * 100) if premium > 0 else 0
        col3.metric("当前价格", f"${current:.2f}")
        col4.metric("盈亏", f"${pnl:.2f} ({pnl_pct:+.1f}%)")

        # 模式特有字段
        if intent == "纯收租":
            tp = p.get("take_profit_price")
            if tp:
                st.info(f"💰 止盈触发价: ${float(tp):.2f}（当期权跌到此价格考虑平仓止盈）")
        elif intent in ("愿意接股", "主动接股"):
            tc = p.get("target_cost")
            if tc:
                st.info(f"🎯 目标成本价: ${float(tc):.2f}（行权价 - 权利金）")

        # 备注
        notes = st.text_input("备注", value=p.get("notes", ""), key=f"notes_{i}")
        if notes != p.get("notes", ""):
            update_position(p["id"], {"notes": notes})

        st.markdown("---")

        # ===== 操作按钮 =====
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if st.button("✅ 平仓", key=f"close_{i}", use_container_width=True):
                st.session_state[f"closing_{i}"] = True

            if st.session_state.get(f"closing_{i}", False):
                close_price = st.number_input(
                    "平仓价格 ($)", value=current, step=0.01,
                    key=f"close_price_{i}"
                )
                if st.button("确认平仓", key=f"confirm_close_{i}"):
                    if close_position(p["id"], close_price):
                        st.success("✅ 已平仓")
                        st.rerun()

        with btn_col2:
            if st.button("🔄 展期", key=f"roll_{i}", use_container_width=True):
                st.session_state[f"rolling_{i}"] = True

            if st.session_state.get(f"rolling_{i}", False):
                new_expiry = st.text_input("新到期日 (YYYY-MM-DD)", key=f"new_expiry_{i}")
                new_premium = st.number_input("新权利金 ($)", value=0.0, step=0.01, key=f"new_prem_{i}")
                if st.button("确认展期", key=f"confirm_roll_{i}"):
                    if new_expiry and new_premium > 0:
                        # 先平仓旧的
                        close_position(p["id"], current)
                        # 创建新持仓
                        from utils.db import add_position
                        new_pos = {
                            "ticker": p["ticker"],
                            "strategy": p["strategy"],
                            "intent": p["intent"],
                            "strike": p["strike"],
                            "expiry": new_expiry,
                            "open_date": date.today().isoformat(),
                            "premium": new_premium,
                            "margin": p.get("margin", 0),
                            "current_price": new_premium,
                            "pnl_pct": 0,
                            "status": "持仓中",
                            "target_cost": p.get("target_cost"),
                            "take_profit_price": new_premium * 0.5 if intent == "纯收租" else None,
                            "notes": f"展期自 {p.get('expiry', '')}",
                        }
                        add_position(new_pos)
                        st.success("✅ 展期成功")
                        st.rerun()

        with btn_col3:
            if st.button("📌 标记赋权", key=f"assign_{i}", use_container_width=True):
                st.session_state[f"assigning_{i}"] = True

            if st.session_state.get(f"assigning_{i}", False):
                st.warning("确认被赋权(Assignment)？这将记录转为股票持仓。")
                if st.button("确认赋权", key=f"confirm_assign_{i}"):
                    if assign_position(p["id"]):
                        st.success("✅ 已标记赋权")
                        if intent in ("愿意接股", "主动接股"):
                            st.info(f"🎯 恭喜以目标价接股！建议开始卖 Covered Call 继续收租。"
                                    f"前往扫描页搜索 {p.get('ticker', '')} 的 Sell Call 机会。")
                        st.rerun()
