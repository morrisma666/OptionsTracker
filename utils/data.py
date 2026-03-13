"""
yfinance 数据获取模块
获取期权链、股票价格、IV Rank、财报日期等
支持 Sell Put 和 Sell Call 两种策略
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


@st.cache_data(ttl=300)
def get_option_chain(ticker: str, strategy: str = "Sell Put", expiry: str = None) -> pd.DataFrame:
    """
    获取期权链数据
    strategy: 'Sell Put' 获取认沽期权, 'Sell Call' 获取认购期权
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return pd.DataFrame()
        if expiry and expiry in expirations:
            target_expiries = [expiry]
        else:
            target_expiries = list(expirations[:4])

        all_options = []
        stock_price = get_stock_info(ticker)["price"]
        if stock_price <= 0:
            return pd.DataFrame()

        is_put = (strategy == "Sell Put")

        for exp in target_expiries:
            try:
                chain = stock.option_chain(exp)
                options = chain.puts.copy() if is_put else chain.calls.copy()
                options["expiry"] = exp
                options["stock_price"] = stock_price
                dte = (pd.to_datetime(exp) - pd.Timestamp.now()).days
                options["dte"] = dte

                if is_put:
                    # Put: OTM = 行权价 < 当前价
                    options["otm_pct"] = ((stock_price - options["strike"]) / stock_price * 100).round(2)
                    options = options[options["strike"] < stock_price]
                else:
                    # Call: OTM = 行权价 > 当前价
                    options["otm_pct"] = ((options["strike"] - stock_price) / stock_price * 100).round(2)
                    options = options[options["strike"] > stock_price]

                # 基础过滤：OI >= 100
                options = options[options["openInterest"] >= 100]

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

        # 过滤：权利金 >= $0.10
        df = df[df["last_price"] >= 0.10]

        # 过滤：买卖价差不超过权利金的50%
        if "bid" in df.columns and "ask" in df.columns:
            spread = df["ask"] - df["bid"]
            df = df[(spread <= df["last_price"] * 0.50) | (df["bid"] <= 0)]

        # 用 Black-Scholes 计算 Greeks
        option_type = "put" if is_put else "call"
        greeks_list = []
        for _, row in df.iterrows():
            iv_val = row.get("iv", 0.30)
            if pd.isna(iv_val) or iv_val <= 0:
                iv_val = 0.30
            g = calculate_greeks(
                S=stock_price,
                K=row["strike"],
                T_days=max(row["dte"], 1),
                iv=iv_val,
                option_type=option_type,
            )
            greeks_list.append(g)

        greeks_df = pd.DataFrame(greeks_list)
        df = df.reset_index(drop=True)
        df["delta"] = greeks_df["delta"]
        df["theta"] = greeks_df["theta"]
        df["vega"] = greeks_df["vega"]
        df["gamma"] = greeks_df["gamma"]

        # 过滤：Theta 必须有实际数值
        df = df[df["theta"].abs() > 0.0001]

        # 计算年化收益率，过滤 >= 8%
        df["annual_return"] = (df["last_price"] / df["strike"]) * (365 / df["dte"].clip(lower=1)) * 100
        df = df[df["annual_return"] >= 8]

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
