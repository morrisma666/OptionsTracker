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


def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


# ========== 筛选条件 ==========
col1, col2, col3 = st.columns(3)
with col1:
    ticker_filter = st.text_input("股票代码筛选", placeholder="如 NVDA，留空显示全部").upper().strip()
with col2:
    month_filter = st.text_input("月份筛选", placeholder="如 2026-03，留空显示全部").strip()
with col3:
    intent_filter = st.selectbox("模式筛选", ["全部", "纯收租", "愿意接股"])

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

# 安全转换 pnl 列
df["pnl_float"] = df["pnl"].apply(lambda x: safe_float(x))
df["pnl_pct_float"] = df.get("pnl_pct", pd.Series([0]*len(df))).apply(lambda x: safe_float(x))

# ========== 统计概览 ==========
st.subheader("📊 统计概览")
col1, col2, col3, col4 = st.columns(4)

total_trades = len(df)
wins = len(df[df["pnl_float"] > 0])
win_rate = wins / total_trades * 100 if total_trades > 0 else 0
avg_win = df[df["pnl_float"] > 0]["pnl_float"].mean() if wins > 0 else 0
loss_df = df[df["pnl_float"] <= 0]
avg_loss = loss_df["pnl_float"].mean() if len(loss_df) > 0 else 0
total_income = df["pnl_float"].sum()

col1.metric("胜率", f"{win_rate:.1f}%", f"{wins}/{total_trades}")
col2.metric("平均盈利", f"${avg_win:.2f}")
col3.metric("平均亏损", f"${avg_loss:.2f}")
col4.metric("总收入", f"${total_income:,.2f}")

st.markdown("---")

# ========== 图表 ==========
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📈 每月权利金收入")
    try:
        df_chart = df.copy()
        df_chart["close_date_parsed"] = pd.to_datetime(df_chart["close_date"], errors="coerce")
        df_chart = df_chart.dropna(subset=["close_date_parsed"])
        if not df_chart.empty:
            df_chart["month"] = df_chart["close_date_parsed"].dt.to_period("M").astype(str)
            monthly = df_chart.groupby("month")["pnl_float"].sum().reset_index()
            monthly.columns = ["月份", "收入"]

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
    except Exception as e:
        st.warning(f"图表渲染失败: {e}")

with chart_col2:
    st.subheader("📊 各模式收益率对比")
    try:
        if "intent" in df.columns:
            mode_stats = df.groupby("intent").agg(
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
    except Exception as e:
        st.warning(f"图表渲染失败: {e}")

st.markdown("---")

# ========== 详细记录 ==========
st.subheader("📝 详细记录")

# 构建显示列（安全处理缺失列）
display_cols = []
col_map = {}
for col, label in [
    ("ticker", "代码"), ("strategy", "策略"), ("intent", "模式"),
    ("strike", "行权价"), ("expiry", "到期日"), ("open_date", "开仓日"),
    ("close_date", "平仓日"), ("premium", "权利金"), ("close_price", "平仓价"),
    ("pnl", "盈亏"), ("pnl_pct", "盈亏%"), ("result", "结果"), ("notes", "备注"),
]:
    if col in df.columns:
        display_cols.append(col)
        col_map[col] = label

if display_cols:
    display_df = df[display_cols].copy()
    display_df.columns = [col_map[c] for c in display_cols]

    col_config = {}
    if "行权价" in display_df.columns:
        col_config["行权价"] = st.column_config.NumberColumn(format="$%.2f")
    if "权利金" in display_df.columns:
        col_config["权利金"] = st.column_config.NumberColumn(format="$%.2f")
    if "平仓价" in display_df.columns:
        col_config["平仓价"] = st.column_config.NumberColumn(format="$%.2f")
    if "盈亏" in display_df.columns:
        col_config["盈亏"] = st.column_config.NumberColumn(format="$%.2f")
    if "盈亏%" in display_df.columns:
        col_config["盈亏%"] = st.column_config.NumberColumn(format="%.1f%%")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
    )

    # 导出CSV
    st.markdown("---")
    csv = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 导出CSV",
        data=csv,
        file_name=f"期权历史记录_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
