"""
期权扫描页 - 支持 Sell Put / Sell Call，两种交易意图
Greeks 全部用 Black-Scholes 计算（r=5%, q=0%）
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
    score_pure_income, score_willing_assign,
    calculate_ma_support_score, cross_mode_hint,
)
from utils.db import add_position

# ========== 样式 ==========
st.markdown("""<style>
.score-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-weight:600; font-size:0.9rem; }
.score-high { background:#10b981; color:white; }
.score-mid { background:#f59e0b; color:white; }
.score-low { background:#ef4444; color:white; }
.warning-card { background:#fef3c7; border-left:4px solid #f59e0b; border-radius:8px; padding:0.8rem; margin:0.3rem 0; color:#92400e; }
.danger-card { background:#fee2e2; border-left:4px solid #ef4444; border-radius:8px; padding:0.8rem; margin:0.3rem 0; color:#991b1b; }
.strategy-tag { display:inline-block; padding:3px 10px; border-radius:6px; font-weight:700; font-size:0.8rem; margin-bottom:4px; }
.tag-put { background:#7c3aed; color:white; }
.tag-call { background:#0891b2; color:white; }
</style>""", unsafe_allow_html=True)


def get_score_badge(score):
    if score >= 70:
        return f'<span class="score-badge score-high">{score:.0f}分</span>'
    elif score >= 45:
        return f'<span class="score-badge score-mid">{score:.0f}分</span>'
    else:
        return f'<span class="score-badge score-low">{score:.0f}分</span>'


def render_option_card(opt, result, stock_info, iv_rank, mode, strategy, idx):
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
        # 策略标签
        tag_cls = "tag-put" if strategy == "Sell Put" else "tag-call"
        st.markdown(f'<span class="strategy-tag {tag_cls}">{strategy}</span>', unsafe_allow_html=True)

        if earnings_warning:
            st.markdown('<div class="danger-card">🚨 财报前禁入警告：到期日跨越财报日！</div>',
                        unsafe_allow_html=True)

        for w in result.get("warnings", []):
            st.markdown(f'<div class="danger-card">{w}</div>', unsafe_allow_html=True)

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
        c3.metric("Delta", f"{opt.get('delta', 0):.4f}")
        c4.metric("权利金", f"${opt.get('last_price', 0):.2f}")
        c5.metric("IV", f"{opt.get('iv', 0)*100:.1f}%")
        c6.metric("OI", f"{opt.get('oi', 0):,.0f}")

        # Greeks 行
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Theta", f"{opt.get('theta', 0):.4f}")
        c2.metric("Vega", f"{opt.get('vega', 0):.4f}")
        c3.metric("Gamma", f"{opt.get('gamma', 0):.6f}")
        c4.metric("IV Rank", f"{iv_rank:.0f}%")
        c5.metric("年化收益", f"{result.get('annual_return', 0):.1f}%")

        if mode == "纯收租":
            c6.metric("止盈触发价", f"${result.get('take_profit_price', 0):.2f}")
        elif mode == "愿意接股":
            c6.metric("目标成本价", f"${result.get('target_cost', 0):.2f}")

        # 推荐理由
        reasons = result.get("reasons", [])
        if reasons:
            st.markdown(f"💡 **推荐理由**：{' · '.join(reasons)}")

        # 跨模式提示
        stock_price = stock_info.get("price", 0)
        hint_mode, hint_score = cross_mode_hint(opt, iv_rank, stock_price, mode)
        if hint_score > result["total_score"] + 5:
            st.markdown(f"<div class='warning-card'>💡 切换到「{hint_mode}」模式评分更高: "
                        f"{hint_score:.0f}分</div>", unsafe_allow_html=True)

        # 加入持仓按钮 -> 弹出表单
        contract_key = opt.get('contract', f'{idx}')
        if st.button(f"➕ 加入持仓", key=f"add_{idx}_{contract_key}"):
            st.session_state[f"show_form_{contract_key}"] = True

        if st.session_state.get(f"show_form_{contract_key}", False):
            with st.form(key=f"form_{contract_key}"):
                st.subheader("确认加入持仓")
                fc1, fc2 = st.columns(2)
                fc1.text_input("股票代码", value=opt.get("ticker", ""), disabled=True)
                fc2.text_input("策略", value=strategy, disabled=True)
                fc1.text_input("行权价", value=f"${opt.get('strike', 0):.2f}", disabled=True)
                fc2.text_input("到期日", value=opt.get("expiry", ""), disabled=True)
                fc1.text_input("权利金", value=f"${opt.get('last_price', 0):.2f}", disabled=True)
                fc2.text_input("交易意图", value=mode, disabled=True)
                margin_input = fc1.number_input(
                    "保证金占用 ($)",
                    value=round(opt.get("strike", 0) * 100 * 0.20, 0),
                    step=100.0,
                    min_value=0.0,
                )
                notes_input = fc2.text_input("备注", value="")

                submitted = st.form_submit_button("✅ 确认保存", use_container_width=True)
                if submitted:
                    position = {
                        "ticker": opt.get("ticker", ""),
                        "strategy": strategy,
                        "intent": mode,
                        "strike": opt.get("strike", 0),
                        "expiry": opt.get("expiry", ""),
                        "open_date": date.today().isoformat(),
                        "premium": opt.get("last_price", 0),
                        "margin": margin_input,
                        "current_price": opt.get("last_price", 0),
                        "pnl_pct": 0,
                        "status": "持仓中",
                        "target_cost": result.get("target_cost", None),
                        "take_profit_price": result.get("take_profit_price", None),
                        "score": result["total_score"],
                        "contract_symbol": opt.get("contract", ""),
                        "notes": notes_input,
                    }
                    if add_position(position):
                        st.success(f"✅ 已保存: {opt.get('ticker', '')} ${opt.get('strike', 0)} {opt.get('expiry', '')}")
                        st.session_state[f"show_form_{contract_key}"] = False
                    else:
                        st.warning("保存失败。请检查数据库配置。")

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

# 第一行：代码 + 策略切换 + 交易意图
col_ticker, col_strategy, col_intent = st.columns([2, 1, 1])

with col_ticker:
    default_ticker = selected_quick or st.session_state.get("scan_ticker", "NVDA")
    ticker_input = st.text_input("股票代码", value=default_ticker, placeholder="输入美股代码，如 NVDA").upper().strip()
    if selected_quick:
        ticker_input = selected_quick
        st.session_state["scan_ticker"] = selected_quick

with col_strategy:
    strategy = st.radio(
        "📌 策略类型",
        ["Sell Put", "Sell Call"],
        horizontal=True,
        help="Sell Put = 卖出认沽期权 | Sell Call = 卖出认购期权",
    )

with col_intent:
    mode = st.radio(
        "🎯 交易意图",
        ["纯收租", "愿意接股"],
        horizontal=True,
        help="纯收租：低Delta安全收租 | 愿意接股：较高Delta换取更高权利金",
    )

# Delta范围说明
delta_info = {
    "纯收租": "Delta 0.05-0.20 | 目标：收取时间价值，远离行权价",
    "愿意接股": "Delta 0.20-0.40 | 目标：收租+愿意以折扣价接股",
}
strategy_label = "认沽期权(Put)" if strategy == "Sell Put" else "认购期权(Call)"
st.caption(f"📋 {strategy_label} · {delta_info[mode]}")

# 到期日筛选（只显示DTE>=21天）
expiry_filter = None
if ticker_input:
    expirations = get_expiration_dates(ticker_input)
    if expirations:
        # 找默认：第一个DTE在21-45天的
        default_idx = 0
        for i, exp in enumerate(expirations):
            dte = (pd.to_datetime(exp) - pd.Timestamp.now()).days
            if 21 <= dte <= 45:
                default_idx = i + 1
                break

        expiry_options = ["全部（DTE≥21天）"] + expirations
        selected_expiry = st.selectbox(
            "到期日 ⏱️ 建议选21-45天（卖方甜蜜区间）",
            expiry_options,
            index=default_idx,
        )
        if selected_expiry != "全部（DTE≥21天）":
            expiry_filter = selected_expiry

# ========== 扫描执行 ==========
if ticker_input and st.button("🔍 开始扫描", type="primary", use_container_width=True):
    with st.spinner(f"正在扫描 {ticker_input} 的 {strategy} 机会..."):
        stock_info = get_stock_info(ticker_input)
        if stock_info["price"] <= 0:
            st.error(f"无法获取 {ticker_input} 的股价，请检查代码是否正确")
            st.stop()

        st.markdown(f"### {stock_info['name']} (${stock_info['price']:.2f})")

        iv_rank = get_iv_rank(ticker_input)
        ma_data = get_moving_averages(ticker_input)
        chain = get_option_chain(ticker_input, strategy, expiry_filter)

        if chain.empty:
            st.warning("未找到符合条件的期权（权利金≥$0.05, OI≥50）。请尝试换一个到期日或股票代码。")
            st.stop()

        chain["ticker"] = ticker_input

        # 计算评分
        results = []
        for _, row in chain.iterrows():
            opt = row.to_dict()
            opt["ma_support_score"] = calculate_ma_support_score(opt["strike"], ma_data)

            if mode == "纯收租":
                result = score_pure_income(opt, iv_rank)
            else:
                result = score_willing_assign(opt, iv_rank, stock_info["price"])

            results.append((opt, result))

        # 排序：纯收租按评分（IV Rank权重最高），愿意接股按年化收益率
        if mode == "纯收租":
            results.sort(key=lambda x: x[1]["total_score"], reverse=True)
        else:
            results.sort(key=lambda x: x[0].get("annual_return", 0), reverse=True)

        sort_label = "综合评分（IV Rank权重最高）" if mode == "纯收租" else "年化收益率"
        st.markdown(f"**找到 {len(results)} 个结果** · 排序：{sort_label}")
        st.markdown("---")

        for idx, (opt, result) in enumerate(results[:20]):
            render_option_card(opt, result, stock_info, iv_rank, mode, strategy, idx)
