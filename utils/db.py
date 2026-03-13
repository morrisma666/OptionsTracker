"""
Supabase 数据库操作模块

配置说明：
1. 在 Supabase 创建项目后，获取 URL 和 anon key
2. 本地开发：在 .streamlit/secrets.toml 中配置：
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-anon-key"
3. Streamlit Cloud 部署：在 Settings -> Secrets 中配置同样的内容
"""

import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date
import json


def get_supabase_client() -> Client:
    """获取 Supabase 客户端"""
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


def _serialize_dates(data: dict) -> dict:
    """将 date/datetime 对象转换为字符串"""
    result = {}
    for k, v in data.items():
        if isinstance(v, (date, datetime)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ========== 持仓操作 ==========

def add_position(position: dict) -> bool:
    """添加新持仓"""
    client = get_supabase_client()
    if not client:
        st.error("数据库未配置，请先配置 Supabase")
        return False
    try:
        data = _serialize_dates(position)
        client.table("positions").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"添加持仓失败: {e}")
        return False


def get_positions(status: str = None) -> list:
    """获取持仓列表"""
    client = get_supabase_client()
    if not client:
        return []
    try:
        query = client.table("positions").select("*").order("created_at", desc=True)
        if status:
            query = query.eq("status", status)
        result = query.execute()
        return result.data or []
    except Exception as e:
        st.error(f"获取持仓失败: {e}")
        return []


def update_position(position_id: int, updates: dict) -> bool:
    """更新持仓"""
    client = get_supabase_client()
    if not client:
        return False
    try:
        data = _serialize_dates(updates)
        client.table("positions").update(data).eq("id", position_id).execute()
        return True
    except Exception as e:
        st.error(f"更新持仓失败: {e}")
        return False


def close_position(position_id: int, close_price: float, close_date: str = None) -> bool:
    """平仓"""
    if not close_date:
        close_date = date.today().isoformat()
    # 先获取持仓信息
    client = get_supabase_client()
    if not client:
        return False
    try:
        pos = client.table("positions").select("*").eq("id", position_id).execute()
        if not pos.data:
            return False
        pos_data = pos.data[0]
        # 计算盈亏
        premium = float(pos_data.get("premium", 0))
        pnl = premium - close_price
        pnl_pct = (pnl / premium * 100) if premium > 0 else 0
        # 更新持仓状态
        client.table("positions").update({
            "status": "已平仓",
            "close_price": close_price,
            "close_date": close_date,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        }).eq("id", position_id).execute()
        # 添加到历史记录
        history_data = {
            "ticker": pos_data["ticker"],
            "strategy": pos_data["strategy"],
            "intent": pos_data["intent"],
            "strike": pos_data["strike"],
            "expiry": pos_data["expiry"],
            "open_date": pos_data["open_date"],
            "close_date": close_date,
            "premium": premium,
            "close_price": close_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "result": "盈利" if pnl > 0 else "亏损",
            "notes": pos_data.get("notes", ""),
        }
        client.table("history").insert(history_data).execute()
        return True
    except Exception as e:
        st.error(f"平仓失败: {e}")
        return False


def assign_position(position_id: int) -> bool:
    """标记赋权"""
    client = get_supabase_client()
    if not client:
        return False
    try:
        pos = client.table("positions").select("*").eq("id", position_id).execute()
        if not pos.data:
            return False
        pos_data = pos.data[0]
        premium = float(pos_data.get("premium", 0))
        # 更新状态
        client.table("positions").update({
            "status": "已赋权",
            "close_date": date.today().isoformat(),
        }).eq("id", position_id).execute()
        # 添加到历史
        history_data = {
            "ticker": pos_data["ticker"],
            "strategy": pos_data["strategy"],
            "intent": pos_data["intent"],
            "strike": pos_data["strike"],
            "expiry": pos_data["expiry"],
            "open_date": pos_data["open_date"],
            "close_date": date.today().isoformat(),
            "premium": premium,
            "close_price": 0,
            "pnl": premium,
            "pnl_pct": 0,
            "result": "赋权",
            "notes": pos_data.get("notes", ""),
        }
        client.table("history").insert(history_data).execute()
        return True
    except Exception as e:
        st.error(f"标记赋权失败: {e}")
        return False


def get_history(filters: dict = None) -> list:
    """获取历史记录"""
    client = get_supabase_client()
    if not client:
        return []
    try:
        query = client.table("history").select("*").order("close_date", desc=True)
        if filters:
            if filters.get("ticker"):
                query = query.eq("ticker", filters["ticker"])
            if filters.get("intent"):
                query = query.eq("intent", filters["intent"])
            if filters.get("month"):
                month_str = filters["month"]
                query = query.gte("close_date", f"{month_str}-01").lt("close_date", f"{month_str}-32")
        result = query.execute()
        return result.data or []
    except Exception as e:
        st.error(f"获取历史记录失败: {e}")
        return []


def get_dashboard_stats() -> dict:
    """获取仪表盘统计数据"""
    client = get_supabase_client()
    if not client:
        return {}
    try:
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        current_year = now.strftime("%Y")
        # 本月历史
        month_history = client.table("history").select("*")\
            .gte("close_date", f"{current_month}-01")\
            .execute().data or []
        # 本年历史
        year_history = client.table("history").select("*")\
            .gte("close_date", f"{current_year}-01-01")\
            .execute().data or []
        # 当前持仓
        positions = client.table("positions").select("*")\
            .eq("status", "持仓中").execute().data or []
        # 计算统计
        month_premium = sum(float(h.get("pnl", 0)) for h in month_history)
        year_income = sum(float(h.get("pnl", 0)) for h in year_history)
        total_trades = len(year_history)
        wins = len([h for h in year_history if float(h.get("pnl", 0)) > 0])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        return {
            "month_premium": round(month_premium, 2),
            "year_income": round(year_income, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "active_positions": len(positions),
            "positions": positions,
            "month_history": month_history,
            "year_history": year_history,
        }
    except Exception as e:
        st.error(f"获取统计数据失败: {e}")
        return {}
