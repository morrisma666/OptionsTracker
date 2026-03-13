"""
历史记录页 - 已平仓/赋权记录、统计分析、图表
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="历史记录", page_icon="📋", layout="wide")

from utils.db import get_history

st.title("📋 历史记录")

# ========== 筛选条件 ==========
col1, col2, col3 = st.columns(3)
with col1:
    ticker_filter = st.text_input("股票代码筛选", placeholder="如 NVDA，留空显示全部").upper().strip()
with col2:
    month_filter = st.text_input("月份筛选", placeholder="如 2026-03，留空显示全部").strip()
with col3:
    intent_filter = st.selectbox("模式筛选", ["全部", "纯收租", "愿意接股", "主动接股"])

filters = {}
if ticker_filter:
    filters["ticker"] = ticker_filter
if month_filter:
    filters["month"] = month_filter
if intent_filter != "全部":
    filters["intent"] = intent_filter

# 获取数据
history = get_history(filters if filters else None)

if not history:
    st.info("暂无历史记录。平仓或赋权后的持仓会显示在这里。")
    st.stop()

df = pd.DataFrame(history)

# ========== 统计概览 ==========
st.subheader("📊 统计概览")
col1, col2, col3, col4 = st.columns(4)

total_trades = len(df)
wins = len(df[df["pnl"].apply(lambda x: float(x) > 0)])
win_rate = wins / total_trades * 100 if total_trades > 0 else 0
avg_win = df[df["pnl"].apply(lambda x: float(x) > 0)]["pnl"].apply(float).mean() if wins > 0 else 0
losses = df[df["pnl"].apply(lambda x: float(x) <= 0)]
avg_loss = losses["pnl"].apply(float).mean() if len(losses) > 0 else 0
total_income = df["pnl"].apply(float).sum()

col1.metric("胜率", f"{win_rate:.1f}%", f"{wins}/{total_trades}")
col2.metric("平均盈利", f"${avg_win:.2f}")
col3.metric("平均亏损", f"${avg_loss:.2f}")
col4.metric("总收入", f"${total_income:,.2f}")

st.markdown("---")

# ========== 图表 ==========
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📈 每月权利金收入")
    df_chart = df.copy()
    df_chart["pnl_float"] = df_chart["pnl"].apply(float)
    df_chart["month"] = pd.to_datetime(df_chart["close_date"]).dt.to_period("M").astype(str)
    monthly = df_chart.groupby("month")["pnl_float"].sum().reset_index()
    monthly.columns = ["月份", "收入"]

    if not monthly.empty:
        colors = ["#10b981" if x >= 0 else "#ef4444" for x in monthly["收入"]]
        fig = go.Figure(data=[
            go.Bar(x=monthly["月份"], y=monthly["收入"], marker_color=colors)
        ])
        fig.update_layout(
            xaxis_title="月份", yaxis_title="收入 ($)",
            height=350, margin=dict(l=20, r=20, t=20, b=20),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6f1ff"),
        )
        st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    st.subheader("📊 各模式收益率对比")
    if "intent" in df.columns:
        df_chart2 = df.copy()
        df_chart2["pnl_float"] = df_chart2["pnl"].apply(float)
        mode_stats = df_chart2.groupby("intent").agg(
            总收入=("pnl_float", "sum"),
            笔数=("pnl_float", "count"),
            平均收益=("pnl_float", "mean"),
        ).reset_index()

        if not mode_stats.empty:
            fig2 = px.bar(mode_stats, x="intent", y=["总收入", "平均收益"],
                          barmode="group", color_discrete_sequence=["#059669", "#2563eb"])
            fig2.update_layout(
                xaxis_title="模式", yaxis_title="金额 ($)",
                height=350, margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6f1ff"),
            )
            st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ========== 详细记录 ==========
st.subheader("📝 详细记录")

# 格式化显示
display_df = df[["ticker", "strategy", "intent", "strike", "expiry", "open_date",
                  "close_date", "premium", "close_price", "pnl", "pnl_pct", "result", "notes"]].copy()
display_df.columns = ["代码", "策略", "模式", "行权价", "到期日", "开仓日",
                       "平仓日", "权利金", "平仓价", "盈亏", "盈亏%", "结果", "备注"]

# 样式化表格
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "行权价": st.column_config.NumberColumn(format="$%.2f"),
        "权利金": st.column_config.NumberColumn(format="$%.2f"),
        "平仓价": st.column_config.NumberColumn(format="$%.2f"),
        "盈亏": st.column_config.NumberColumn(format="$%.2f"),
        "盈亏%": st.column_config.NumberColumn(format="%.1f%%"),
    },
)

# ========== 导出CSV ==========
st.markdown("---")
csv = display_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "📥 导出CSV",
    data=csv,
    file_name=f"期权历史记录_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
    use_container_width=True,
)
