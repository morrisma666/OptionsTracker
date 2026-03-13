"""
yfinance 数据获取模块
- Greeks 全部用 Black-Scholes 自行计算（r=5%, q=0%）
- IV 用 yfinance 的 impliedVolatility，为空则用30日历史波动率
- IV Rank 用252个交易日历史IV百分位
- 过滤条件仅：权利金 >= $0.05, OI >= 50
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
from utils.greeks import calculate_greeks


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


@st.cache_data(ttl=600)
def _get_hist_vol(ticker: str) -> float:
    """获取30日历史波动率，作为IV的后备值"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        if hist.empty or len(hist) < 20:
            return 0.30
        returns = hist["Close"].pct_change().dropna()
        vol = returns.tail(30).std() * np.sqrt(252)
        return max(float(vol), 0.05)
    except Exception:
        return 0.30


@st.cache_data(ttl=300)
def get_option_chain(ticker: str, strategy: str = "Sell Put", expiry: str = None) -> pd.DataFrame:
    """
    获取期权链数据
    过滤条件仅两条：权利金 >= $0.05, OI >= 50
    Greeks 全部用 Black-Scholes 计算（r=5%, q=0%）
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return pd.DataFrame()

        if expiry and expiry in expirations:
            target_expiries = [expiry]
        else:
            # 默认取 DTE >= 21 天的到期日
            cutoff_min = (pd.Timestamp.now() + pd.Timedelta(days=21)).strftime("%Y-%m-%d")
            target_expiries = [e for e in expirations if e >= cutoff_min]
            if not target_expiries:
                target_expiries = list(expirations[:3])

        stock_price = get_stock_info(ticker)["price"]
        if stock_price <= 0:
            return pd.DataFrame()

        fallback_iv = _get_hist_vol(ticker)
        is_put = (strategy == "Sell Put")
        all_options = []

        for exp in target_expiries:
            try:
                chain = stock.option_chain(exp)
                options = chain.puts.copy() if is_put else chain.calls.copy()
                options["expiry"] = exp
                options["stock_price"] = stock_price
                options["dte"] = (pd.to_datetime(exp) - pd.Timestamp.now()).days
                all_options.append(options)
            except Exception:
                continue

        if not all_options:
            return pd.DataFrame()

        df = pd.concat(all_options, ignore_index=True)

        # 标准化列名
        df = df.rename(columns={
            "contractSymbol": "contract",
            "lastPrice": "last_price",
            "openInterest": "oi",
            "impliedVolatility": "iv",
        })

        # OTM 过滤
        if is_put:
            df["otm_pct"] = ((stock_price - df["strike"]) / stock_price * 100).round(2)
            df = df[df["strike"] < stock_price]
        else:
            df["otm_pct"] = ((df["strike"] - stock_price) / stock_price * 100).round(2)
            df = df[df["strike"] > stock_price]

        # === 仅两条过滤 ===
        df["oi"] = df["oi"].fillna(0)
        df = df[df["oi"] >= 50]
        df = df[df["last_price"] >= 0.05]

        if df.empty:
            return pd.DataFrame()

        # IV：用 yfinance 的 impliedVolatility，缺失则用30日历史波动率
        df["iv"] = df["iv"].apply(lambda x: x if (pd.notna(x) and x > 0) else fallback_iv)

        # Black-Scholes 计算全部 Greeks（r=5%, q=0%）
        option_type = "put" if is_put else "call"
        greeks_list = []
        for _, row in df.iterrows():
            g = calculate_greeks(
                S=stock_price,
                K=row["strike"],
                T_days=max(row["dte"], 1),
                iv=row["iv"],
                option_type=option_type,
                r=0.05,
            )
            greeks_list.append(g)

        greeks_df = pd.DataFrame(greeks_list)
        df = df.reset_index(drop=True)
        df["delta"] = greeks_df["delta"]
        df["theta"] = greeks_df["theta"]
        df["vega"] = greeks_df["vega"]
        df["gamma"] = greeks_df["gamma"]

        # 计算年化收益率（仅显示/排序用，不过滤）
        df["annual_return"] = (df["last_price"] / df["strike"]) * (365 / df["dte"].clip(lower=1)) * 100

        return df

    except Exception as e:
        st.error(f"获取期权链失败: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_iv_rank(ticker: str) -> float:
    """
    IV Rank：过去252个交易日的历史IV百分位
    用每个交易日的20日滚动波动率作为该日的IV代理值，
    然后计算当前IV在过去252天中的百分位排名
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2y")
        if hist.empty or len(hist) < 60:
            return 50.0
        returns = hist["Close"].pct_change().dropna()
        # 20日滚动波动率年化 = 每日的"IV代理值"
        rolling_iv = returns.rolling(window=20).std() * np.sqrt(252)
        rolling_iv = rolling_iv.dropna()
        if len(rolling_iv) < 60:
            return 50.0
        # 取最近252个交易日
        iv_window = rolling_iv.tail(252)
        current_iv = iv_window.iloc[-1]
        iv_min = iv_window.min()
        iv_max = iv_window.max()
        # IV Rank = (当前IV - 252日最低IV) / (252日最高IV - 252日最低IV)
        if iv_max == iv_min:
            return 50.0
        rank = (current_iv - iv_min) / (iv_max - iv_min) * 100
        return round(float(rank), 1)
    except Exception:
        return 50.0


@st.cache_data(ttl=3600)
def get_moving_averages(ticker: str) -> dict:
    """获取均线数据"""
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
    """获取可用到期日列表，只返回DTE>=21天的"""
    try:
        stock = yf.Ticker(ticker)
        all_dates = list(stock.options) if stock.options else []
        cutoff = (pd.Timestamp.now() + pd.Timedelta(days=21)).strftime("%Y-%m-%d")
        filtered = [d for d in all_dates if d >= cutoff]
        return filtered if filtered else all_dates[:5]
    except Exception:
        return []


def get_current_option_price(contract_symbol: str) -> float:
    """获取期权合约当前价格"""
    try:
        ticker = yf.Ticker(contract_symbol)
        info = ticker.info
        return info.get("lastPrice") or info.get("regularMarketPrice", 0)
    except Exception:
        return 0
