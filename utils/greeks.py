"""
Black-Scholes Greeks 计算模块
自行计算 Delta、Theta、Vega，不依赖 yfinance 返回值
"""

import numpy as np
from scipy.stats import norm


def bs_d1(S, K, T, r, sigma):
    """计算 Black-Scholes d1"""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    return (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))


def bs_d2(S, K, T, r, sigma):
    """计算 Black-Scholes d2"""
    if T <= 0 or sigma <= 0:
        return 0.0
    return bs_d1(S, K, T, r, sigma) - sigma * np.sqrt(T)


def calc_delta(S, K, T, r, sigma, option_type="put"):
    """
    计算 Delta
    S: 标的价格, K: 行权价, T: 剩余年限, r: 无风险利率, sigma: 隐含波动率
    option_type: 'put' 或 'call'
    """
    if T <= 0 or sigma <= 0:
        if option_type == "put":
            return -1.0 if S < K else 0.0
        else:
            return 1.0 if S > K else 0.0
    d1 = bs_d1(S, K, T, r, sigma)
    if option_type == "put":
        return norm.cdf(d1) - 1  # 负值
    else:
        return norm.cdf(d1)


def calc_theta(S, K, T, r, sigma, option_type="put"):
    """
    计算 Theta（每日）
    返回值为负数（期权价值随时间衰减）
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = bs_d1(S, K, T, r, sigma)
    d2 = bs_d2(S, K, T, r, sigma)
    sqrt_T = np.sqrt(T)
    # 第一项：时间价值衰减
    term1 = -(S * norm.pdf(d1) * sigma) / (2 * sqrt_T)
    if option_type == "put":
        term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
        theta_annual = term1 + term2
    else:
        term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
        theta_annual = term1 + term2
    # 转换为每日
    return theta_annual / 365


def calc_vega(S, K, T, r, sigma):
    """
    计算 Vega（IV变动1%对应的期权价格变化）
    Put 和 Call 的 Vega 相同
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = bs_d1(S, K, T, r, sigma)
    # vega per 1% IV change
    return S * norm.pdf(d1) * np.sqrt(T) / 100


def calc_gamma(S, K, T, r, sigma):
    """计算 Gamma"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = bs_d1(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


def calculate_greeks(S, K, T_days, iv, option_type="put", r=0.05):
    """
    一次性计算所有 Greeks
    S: 标的价格
    K: 行权价
    T_days: 剩余天数 (DTE)
    iv: 隐含波动率（小数形式，如 0.35 表示 35%）
    option_type: 'put' 或 'call'
    r: 无风险利率（默认 5%）
    返回 dict: {delta, theta, vega, gamma}
    """
    T = max(T_days, 0.5) / 365  # 转换为年，最少保留半天
    sigma = max(iv, 0.01)  # 最低 1% IV

    return {
        "delta": round(calc_delta(S, K, T, r, sigma, option_type), 4),
        "theta": round(calc_theta(S, K, T, r, sigma, option_type), 4),
        "vega": round(calc_vega(S, K, T, r, sigma), 4),
        "gamma": round(calc_gamma(S, K, T, r, sigma), 4),
    }
