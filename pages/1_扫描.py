"""
期权扫描页 - 根据交易意图筛选和评分期权
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="期权扫描", page_icon="🔍", layout="wide")

from utils.data import (
    get_stock_info, get_option_chain, get_iv_rank,
    get_moving_averages, get_expiration_dates,
)
from utils.scoring import (
    score_pure_income, score_willing_assign, score_active_assign,
    calculate_ma_support_score, cross_mode_hint,
)
from utils.db import add_position


def get_score_badge(score):
    """根据分数返回徽章HTML"""
    if score >= 70:
        return f'<span class="score-badge score-high">{score:.0f}分</span>'
    elif score >= 45:
        return f'<span class="score-badge score-mid">{score:.0f}分</span>'
    else:
        return f'<span class="score-badge score-low">{score:.0f}分</span>'


def render_option_card(opt, result, stock_info, iv_rank, mode, idx):
    """渲染单个期权结果卡片"""
    earnings = stock_info.get("earnings_date")
    earnings_warning = False
    if earnings:
        try:
            earn_date = pd.to_datetime(earnings).date()
            exp_date = pd.to_datetime(opt["expiry"]).date()
            if exp_date >= earn_date:
                earnings_warning = True
        except Exception:
            pass

    with st.container():
        if earnings_warning:
            st.markdown('<div class="danger-card">🚨 财报前禁入警告：到期日跨越财报日！</div>',
                        unsafe_allow_html=True)

        # 标题行
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.markdown(f"**{stock_info['name']}** `{opt.get('contract', '')}`")
        with col2:
            st.markdown(f"到期: **{opt['expiry']}** | DTE: **{opt.get('dte', 0)}天**")
        with col3:
            st.markdown(get_score_badge(result["total_score"]), unsafe_allow_html=True)

        # 核心数据
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("行权价", f"${opt.get('strike', 0):.2f}")
        c2.metric("OTM%", f"{opt.get('otm_pct', 0):.1f}%")
        delta_val = opt.get("delta", 0)
        c3.metric("Delta", f"{delta_val:.3f}" if delta_val else "N/A")
        c4.metric("权利金", f"${opt.get('last_price', 0):.2f}")
        c5.metric("IV", f"{opt.get('iv', 0)*100:.1f}%")
        c6.metric("OI", f"{opt.get('oi', 0):,}")

        # Greeks 行
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        theta_val = opt.get("theta", 0)
        c1.metric("Theta", f"{theta_val:.4f}" if theta_val else "N/A")
        vega_val = opt.get("vega", 0)
        c2.metric("Vega", f"{vega_val:.4f}" if vega_val else "N/A")
        c3.metric("IV Rank", f"{iv_rank:.0f}%")
        c4.metric("年化收益", f"{result.get('annual_return', 0):.1f}%")

        # 模式特有字段
        if mode == "纯收租":
            c5.metric("止盈触发价", f"${result.get('take_profit_price', 0):.2f}")
        elif mode == "愿意接股":
            c5.metric("目标成本价", f"${result.get('target_cost', 0):.2f}")
        elif mode == "主动接股":
            c5.metric("目标成本价", f"${result.get('target_cost', 0):.2f}")
            c6.metric("CC预估年化", f"{result.get('cc_annual', 0):.1f}%")

        # 推荐理由
        reasons = result.get("reasons", [])
        if reasons:
            reason_text = " · ".join(reasons)
            st.markdown(f"💡 **推荐理由**：{reason_text}")

        # 跨模式提示
        stock_price = stock_info.get("price", 0)
        hint_mode, hint_score = cross_mode_hint(opt, iv_rank, stock_price, mode)
        if hint_mode and hint_score > result["total_score"] + 5:
            st.markdown(f"<div class='warning-card'>💡 切换到「{hint_mode}」模式评分更高: "
                        f"{hint_score:.0f}分</div>", unsafe_allow_html=True)

        # 加入持仓按钮
        if st.button(f"➕ 加入持仓", key=f"add_{idx}_{opt.get('contract', '')}"):
            position = {
                "ticker": opt.get("ticker", ""),
                "strategy": "Sell Put",
                "intent": mode,
                "strike": opt.get("strike", 0),
                "expiry": opt.get("expiry", ""),
                "open_date": date.today().isoformat(),
                "premium": opt.get("last_price", 0),
                "margin": opt.get("strike", 0) * 100 * 0.20,
                "current_price": opt.get("last_price", 0),
                "pnl_pct": 0,
                "status": "持仓中",
                "target_cost": result.get("target_cost", None),
                "take_profit_price": result.get("take_profit_price", None),
                "score": result["total_score"],
                "contract_symbol": opt.get("contract", ""),
                "notes": "",
            }
            if add_position(position):
                st.success(f"✅ 已加入持仓: {opt.get('ticker', '')} ${opt.get('strike', 0)} {opt.get('expiry', '')}")
            else:
                st.warning("添加到数据库失败。如未配置数据库，持仓不会持久保存。")

        st.markdown("---")


# ========== 主界面 ==========
st.title("🔍 期权扫描")

# 侧边栏 - 快捷标签
with st.sidebar:
    st.subheader("⚡ 快捷标签")
    quick_tickers = ["NVDA", "MSFT", "AMZN", "NOW", "META", "CRWD", "RDDT", "GOOG"]
    selected_quick = None
    cols = st.columns(2)
    for i, ticker in enumerate(quick_tickers):
        if cols[i % 2].button(ticker, key=f"quick_{ticker}", use_container_width=True):
            selected_quick = ticker

# 搜索框
col_search, col_intent = st.columns([2, 1])
with col_search:
    default_ticker = selected_quick or st.session_state.get("scan_ticker", "NVDA")
    ticker_input = st.text_input("股票代码", value=default_ticker, placeholder="输入美股代码，如 NVDA").upper().strip()
    if selected_quick:
        ticker_input = selected_quick
        st.session_state["scan_ticker"] = selected_quick

with col_intent:
    mode = st.radio(
        "交易意图（必选）",
        ["纯收租", "愿意接股", "主动接股"],
        horizontal=True,
        help="不同意图对应不同的Delta范围和评分权重"
    )

# Delta范围说明
delta_ranges = {
    "纯收租": "Delta < 0.20 | 目标：收取时间价值，不被行权",
    "愿意接股": "Delta 0.20-0.35 | 目标：收租+有意愿以折扣价接股",
    "主动接股": "Delta 0.35-0.50 | 目标：主动以目标价位建仓",
}
st.caption(delta_ranges[mode])

# 主动接股模式额外参数
target_buy_price = 0
if mode == "主动接股":
    target_buy_price = st.number_input("目标建仓价 ($)", value=0.0, step=1.0,
                                        help="输入你期望的建仓价格，系统会优先推荐贴近该价格的行权价")

# 到期日筛选
expiry_filter = None
if ticker_input:
    expirations = get_expiration_dates(ticker_input)
    if expirations:
        expiry_options = ["全部（前4个到期日）"] + expirations[:8]
        selected_expiry = st.selectbox("到期日", expiry_options)
        if selected_expiry != "全部（前4个到期日）":
            expiry_filter = selected_expiry

# ========== 扫描执行 ==========
if ticker_input and st.button("🔍 开始扫描", type="primary", use_container_width=True):
    with st.spinner(f"正在扫描 {ticker_input} 的 Sell Put 机会..."):
        stock_info = get_stock_info(ticker_input)
        if stock_info["price"] <= 0:
            st.error(f"无法获取 {ticker_input} 的股价，请检查代码是否正确")
            st.stop()

        st.markdown(f"### {stock_info['name']} (${stock_info['price']:.2f})")

        iv_rank = get_iv_rank(ticker_input)
        ma_data = get_moving_averages(ticker_input)
        chain = get_option_chain(ticker_input, expiry_filter)

        if chain.empty:
            st.warning("未找到符合条件的期权数据")
            st.stop()

        # 添加ticker列
        chain["ticker"] = ticker_input

        # 根据模式过滤 Delta
        # yfinance的put delta是负数，取绝对值
        if "delta" not in chain.columns:
            # 如果没有delta数据，用OTM%估算
            chain["delta"] = -(0.50 - chain["otm_pct"] / 100 * 0.50).clip(0.01, 0.50)

        chain["abs_delta"] = chain["delta"].abs()

        if mode == "纯收租":
            filtered = chain[chain["abs_delta"] < 0.20]
        elif mode == "愿意接股":
            filtered = chain[(chain["abs_delta"] >= 0.20) & (chain["abs_delta"] <= 0.35)]
        else:  # 主动接股
            filtered = chain[(chain["abs_delta"] >= 0.35) & (chain["abs_delta"] <= 0.50)]

        # 如果过滤后太少，放宽条件
        if len(filtered) < 3:
            st.info(f"严格Delta范围内仅{len(filtered)}个结果，已适当放宽范围")
            if mode == "纯收租":
                filtered = chain[chain["abs_delta"] < 0.30]
            elif mode == "愿意接股":
                filtered = chain[(chain["abs_delta"] >= 0.15) & (chain["abs_delta"] <= 0.40)]
            else:
                filtered = chain[(chain["abs_delta"] >= 0.25) & (chain["abs_delta"] <= 0.55)]

        if filtered.empty:
            st.warning("没有找到符合Delta范围的期权")
            st.stop()

        # 计算评分
        results = []
        for _, row in filtered.iterrows():
            opt = row.to_dict()
            # 计算均线支撑评分
            opt["ma_support_score"] = calculate_ma_support_score(opt["strike"], ma_data)

            if mode == "纯收租":
                result = score_pure_income(opt, iv_rank)
            elif mode == "愿意接股":
                result = score_willing_assign(opt, iv_rank, stock_info["price"])
            else:
                result = score_active_assign(opt, iv_rank, stock_info["price"], target_buy_price)

            results.append((opt, result))

        # 按分数排序
        results.sort(key=lambda x: x[1]["total_score"], reverse=True)

        st.markdown(f"**找到 {len(results)} 个结果，按评分排序：**")
        st.markdown("---")

        # 渲染结果卡片
        for idx, (opt, result) in enumerate(results[:15]):
            render_option_card(opt, result, stock_info, iv_rank, mode, idx)
