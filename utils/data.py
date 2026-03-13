"""
yfinance 数据获取模块
获取期权链、股票价格、IV Rank、财报日期等
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st


@st.cache_data(ttl=300)
def get_stock_info(ticker: str) -> dict:
    """获取股票基本信息"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "name": info.get("shortName", ticker),
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "market_cap": info.get("marketCap", 0),
            "sector": info.get("sector", ""),
            "earnings_date": _get_next_earnings(stock),
        }
    except Exception as e:
        st.error(f"获取 {ticker} 信息失败: {e}")
        return {"name": ticker, "price": 0, "market_cap": 0, "sector": "", "earnings_date": None}


def _get_next_earnings(stock) -> str:
    """获取下一个财报日期"""
    try:
        cal = stock.calendar
        if cal is not None:
            if isinstance(cal, dict):
                earnings = cal.get("Earnings Date")
                if earnings:
                    if isinstance(earnings, list) and len(earnings) > 0:
                        return str(earnings[0])
                    return str(earnings)
            elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"].iloc[0]
                return str(val)
    except Exception:
        pass
    return None


@st.cache_data(ttl=300)
def get_option_chain(ticker: str, expiry: str = None) -> pd.DataFrame:
    """获取期权链数据"""
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return pd.DataFrame()
        if expiry and expiry in expirations:
            target_expiries = [expiry]
        else:
            # 取前4个到期日
            target_expiries = list(expirations[:4])
        all_puts = []
        stock_price = get_stock_info(ticker)["price"]
        if stock_price <= 0:
            return pd.DataFrame()
        for exp in target_expiries:
            try:
                chain = stock.option_chain(exp)
                puts = chain.puts.copy()
                puts["expiry"] = exp
                puts["stock_price"] = stock_price
                puts["dte"] = (pd.to_datetime(exp) - pd.Timestamp.now()).days
                # 计算 OTM%
                puts["otm_pct"] = ((stock_price - puts["strike"]) / stock_price * 100).round(2)
                # 过滤 OTM 的 put（行权价低于当前价）
                puts = puts[puts["strike"] < stock_price]
                # 过滤流动性太差的
                puts = puts[puts["openInterest"] >= 10]
                all_puts.append(puts)
            except Exception:
                continue
        if not all_puts:
            return pd.DataFrame()
        df = pd.concat(all_puts, ignore_index=True)
        # 标准化列名
        df = df.rename(columns={
            "contractSymbol": "contract",
            "lastPrice": "last_price",
            "openInterest": "oi",
            "impliedVolatility": "iv",
        })
        return df
    except Exception as e:
        st.error(f"获取期权链失败: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_iv_rank(ticker: str) -> float:
    """计算 IV Rank（基于过去一年 IV 的百分位）"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 20:
            return 50.0
        # 用历史波动率近似计算 IV Rank
        returns = hist["Close"].pct_change().dropna()
        rolling_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
        rolling_vol = rolling_vol.dropna()
        if len(rolling_vol) < 10:
            return 50.0
        current_vol = rolling_vol.iloc[-1]
        rank = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100
        return round(rank, 1)
    except Exception:
        return 50.0


@st.cache_data(ttl=3600)
def get_moving_averages(ticker: str) -> dict:
    """获取均线数据，用于技术支撑分析"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty:
            return {}
        close = hist["Close"]
        return {
            "ma20": round(close.rolling(20).mean().iloc[-1], 2),
            "ma50": round(close.rolling(50).mean().iloc[-1], 2),
            "ma200": round(close.rolling(200).mean().iloc[-1], 2) if len(close) >= 200 else None,
            "current": round(close.iloc[-1], 2),
        }
    except Exception:
        return {}


@st.cache_data(ttl=300)
def get_expiration_dates(ticker: str) -> list:
    """获取可用到期日列表"""
    try:
        stock = yf.Ticker(ticker)
        return list(stock.options) if stock.options else []
    except Exception:
        return []


def get_current_option_price(contract_symbol: str) -> float:
    """获取期权合约当前价格（用于持仓实时更新）"""
    try:
        ticker = yf.Ticker(contract_symbol)
        info = ticker.info
        return info.get("lastPrice") or info.get("regularMarketPrice", 0)
    except Exception:
        return 0
