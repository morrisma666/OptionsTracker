"""
期权评分模块
两种交易意图：纯收租、愿意接股
"""

import numpy as np
from datetime import datetime


def score_pure_income(option: dict, iv_rank: float) -> dict:
    """
    纯收租模式评分
    权重：IV Rank 35%、OTM安全边际 30%、Theta日收益 20%、流动性OI 15%
    """
    scores = {}
    reasons = []

    # IV Rank 评分 (35%) - IV Rank 越高越好
    iv_score = min(iv_rank / 100 * 100, 100)
    scores["iv_rank"] = iv_score * 0.35
    if iv_rank > 60:
        reasons.append(f"IV Rank {iv_rank:.0f}%处于高位，权利金丰厚")
    elif iv_rank < 25:
        reasons.append(f"IV Rank {iv_rank:.0f}%偏低，权利金不够肥")

    # OTM 安全边际 (30%) - OTM% 越高越安全
    otm_pct = option.get("otm_pct", 0)
    otm_score = min(otm_pct / 20 * 100, 100)
    scores["otm"] = otm_score * 0.30
    if otm_pct > 15:
        reasons.append(f"OTM {otm_pct:.1f}%，安全边际充足")
    elif otm_pct < 5:
        reasons.append(f"⚠️ OTM仅{otm_pct:.1f}%，安全边际偏低，建议关注")

    # Theta 日收益 (20%)
    theta = abs(option.get("theta", 0))
    strike = option.get("strike", 1)
    theta_yield = theta / strike * 365 * 100
    theta_score = min(theta_yield / 15 * 100, 100)
    scores["theta"] = theta_score * 0.20
    if theta_yield > 10:
        reasons.append(f"Theta衰减快，年化{theta_yield:.1f}%")

    # 流动性 OI (15%)
    oi = option.get("oi", 0)
    oi_score = min(oi / 5000 * 100, 100)
    scores["oi"] = oi_score * 0.15
    if oi < 200:
        reasons.append("流动性一般，注意滑点")
    elif oi > 2000:
        reasons.append("流动性良好")

    total = sum(scores.values())

    # 止盈触发价（收取50%权利金时的期权价格）
    premium = option.get("last_price", 0)
    take_profit_price = premium * 0.5 if premium > 0 else 0

    # 年化收益率
    dte = max(option.get("dte", 30), 1)
    annual_return = (premium / strike) * (365 / dte) * 100

    # DTE/安全边际预警
    warnings = []
    if dte <= 3:
        warnings.append("🔴 DTE≤3天，建议立即平仓或展期")
    if otm_pct < 5:
        warnings.append("🔴 安全边际<5%，建议平仓或展期")

    return {
        "total_score": round(total, 1),
        "scores": scores,
        "reasons": reasons,
        "warnings": warnings,
        "take_profit_price": round(take_profit_price, 2),
        "annual_return": round(annual_return, 1),
        "mode": "纯收租",
    }


def score_willing_assign(option: dict, iv_rank: float, stock_price: float) -> dict:
    """
    愿意接股模式评分
    权重：年化收益率 30%、目标成本价合理性 25%、IV Rank 20%、Theta 15%、技术支撑 10%
    """
    scores = {}
    reasons = []
    premium = option.get("last_price", 0)
    strike = option.get("strike", 1)
    dte = max(option.get("dte", 30), 1)

    # 年化收益率 (30%)
    annual_return = (premium / strike) * (365 / dte) * 100
    ar_score = min(annual_return / 30 * 100, 100)
    scores["annual_return"] = ar_score * 0.30
    if annual_return > 20:
        reasons.append(f"年化收益率{annual_return:.1f}%，非常可观")
    elif annual_return > 10:
        reasons.append(f"年化收益率{annual_return:.1f}%，尚可")

    # 目标成本价合理性 (25%)
    target_cost = strike - premium
    discount = (stock_price - target_cost) / stock_price * 100
    cost_score = min(discount / 15 * 100, 100)
    scores["cost"] = cost_score * 0.25
    if discount > 10:
        reasons.append(f"目标成本价${target_cost:.2f}，较现价折扣{discount:.1f}%")
    else:
        reasons.append(f"目标成本价${target_cost:.2f}，折扣{discount:.1f}%偏低")

    # IV Rank (20%)
    iv_score = min(iv_rank / 100 * 100, 100)
    scores["iv_rank"] = iv_score * 0.20
    if iv_rank > 50:
        reasons.append(f"IV Rank {iv_rank:.0f}%，权利金溢价高")

    # Theta (15%)
    theta = abs(option.get("theta", 0))
    theta_yield = theta / strike * 365 * 100
    theta_score = min(theta_yield / 15 * 100, 100)
    scores["theta"] = theta_score * 0.15

    # 技术支撑 (10%)
    ma_support = option.get("ma_support_score", 50)
    scores["support"] = (ma_support / 100) * 100 * 0.10
    if ma_support > 70:
        reasons.append("行权价在均线支撑附近")

    total = sum(scores.values())

    return {
        "total_score": round(total, 1),
        "scores": scores,
        "reasons": reasons,
        "warnings": [],
        "target_cost": round(target_cost, 2),
        "annual_return": round(annual_return, 1),
        "mode": "愿意接股",
    }


def calculate_ma_support_score(strike: float, ma_data: dict) -> float:
    """计算均线支撑评分"""
    if not ma_data:
        return 50
    score = 50
    current = ma_data.get("current", 0)
    if current <= 0:
        return 50
    ma20 = ma_data.get("ma20", 0)
    ma50 = ma_data.get("ma50", 0)
    ma200 = ma_data.get("ma200")

    for ma_val, weight in [(ma20, 15), (ma50, 20), (ma200, 25)]:
        if ma_val and ma_val > 0:
            diff_pct = abs(strike - ma_val) / ma_val * 100
            if diff_pct < 2:
                score += weight
            elif diff_pct < 5:
                score += weight * 0.5
    if ma50 > 0 and strike < ma50:
        score += 10
    if ma200 and ma200 > 0 and strike < ma200:
        score += 10

    return min(score, 100)


def cross_mode_hint(option: dict, iv_rank: float, stock_price: float, current_mode: str) -> tuple:
    """检查另一种模式是否分数更高，返回提示"""
    opt_copy = option.copy()

    if current_mode == "纯收租":
        r = score_willing_assign(opt_copy, iv_rank, stock_price)
        return "愿意接股", r["total_score"]
    else:
        r = score_pure_income(opt_copy, iv_rank)
        return "纯收租", r["total_score"]
