"""
期权评分模块
根据不同交易意图计算综合评分
"""

import numpy as np
from datetime import datetime


def score_pure_income(option: dict, iv_rank: float) -> dict:
    """
    纯收租模式评分
    权重：IV Rank 30%、OTM安全边际 25%、Theta日收益 20%、流动性OI 15%、Delta绝对值 10%
    """
    scores = {}
    reasons = []

    # IV Rank 评分 (30%) - IV Rank 越高越好（权利金越肥）
    iv_score = min(iv_rank / 100 * 100, 100)
    scores["iv_rank"] = iv_score * 0.30
    if iv_rank > 60:
        reasons.append(f"IV Rank {iv_rank:.0f}%处于高位，权利金丰厚")
    elif iv_rank < 25:
        reasons.append(f"IV Rank {iv_rank:.0f}%偏低，权利金不够肥")

    # OTM 安全边际 (25%) - OTM% 越高越安全
    otm_pct = option.get("otm_pct", 0)
    otm_score = min(otm_pct / 20 * 100, 100)  # 20% OTM = 满分
    scores["otm"] = otm_score * 0.25
    if otm_pct > 15:
        reasons.append(f"OTM {otm_pct:.1f}%，安全边际充足")
    elif otm_pct < 5:
        reasons.append(f"OTM仅{otm_pct:.1f}%，安全边际偏低")

    # Theta 日收益 (20%)
    theta = abs(option.get("theta", 0))
    premium = option.get("last_price", 0)
    strike = option.get("strike", 1)
    theta_yield = theta / strike * 365 * 100  # 年化
    theta_score = min(theta_yield / 15 * 100, 100)  # 15%年化 = 满分
    scores["theta"] = theta_score * 0.20
    if theta_yield > 10:
        reasons.append(f"Theta衰减快，年化{theta_yield:.1f}%")

    # 流动性 OI (15%)
    oi = option.get("oi", 0)
    oi_score = min(oi / 5000 * 100, 100)  # 5000 OI = 满分
    scores["oi"] = oi_score * 0.15
    if oi < 100:
        reasons.append("流动性较差，注意滑点")
    elif oi > 2000:
        reasons.append("流动性良好")

    # Delta 绝对值 (10%) - 越小越好
    delta = abs(option.get("delta", 0.15))
    delta_score = max((0.30 - delta) / 0.30 * 100, 0)
    scores["delta"] = delta_score * 0.10
    if delta < 0.10:
        reasons.append(f"Delta {delta:.2f}极低，被行权概率很小")
    elif delta > 0.20:
        reasons.append(f"Delta {delta:.2f}偏高，纯收租偏激进")

    total = sum(scores.values())

    # 止盈触发价（收取50%权利金时的期权价格）
    take_profit_price = premium * 0.5 if premium > 0 else 0

    # 年化收益率
    dte = max(option.get("dte", 30), 1)
    annual_return = (premium / strike) * (365 / dte) * 100

    return {
        "total_score": round(total, 1),
        "scores": scores,
        "reasons": reasons,
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
    ar_score = min(annual_return / 30 * 100, 100)  # 30%年化 = 满分
    scores["annual_return"] = ar_score * 0.30
    if annual_return > 20:
        reasons.append(f"年化收益率{annual_return:.1f}%，非常可观")
    elif annual_return > 10:
        reasons.append(f"年化收益率{annual_return:.1f}%，尚可")

    # 目标成本价合理性 (25%) - 目标成本价相对当前价的折扣
    target_cost = strike - premium
    discount = (stock_price - target_cost) / stock_price * 100
    cost_score = min(discount / 15 * 100, 100)  # 15%折扣 = 满分
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

    # 技术支撑 (10%) - 行权价接近均线支撑
    ma_support = option.get("ma_support_score", 50)
    scores["support"] = (ma_support / 100) * 100 * 0.10
    if ma_support > 70:
        reasons.append("行权价在均线支撑附近")

    total = sum(scores.values())

    return {
        "total_score": round(total, 1),
        "scores": scores,
        "reasons": reasons,
        "target_cost": round(target_cost, 2),
        "annual_return": round(annual_return, 1),
        "mode": "愿意接股",
    }


def score_active_assign(option: dict, iv_rank: float, stock_price: float, target_buy_price: float = 0) -> dict:
    """
    主动接股模式评分
    权重：行权价贴近建仓价 35%、均线支撑强度 25%、接股后CC年化 20%、保证金占比 10%、IV Rank 10%
    """
    scores = {}
    reasons = []
    premium = option.get("last_price", 0)
    strike = option.get("strike", 1)
    dte = max(option.get("dte", 30), 1)

    # 行权价贴近建仓价 (35%)
    if target_buy_price > 0:
        price_diff_pct = abs(strike - target_buy_price) / target_buy_price * 100
        price_score = max(100 - price_diff_pct * 10, 0)  # 每偏离1%扣10分
        scores["price_match"] = price_score * 0.35
        if price_diff_pct < 3:
            reasons.append(f"行权价${strike}贴近目标建仓价${target_buy_price}")
        else:
            reasons.append(f"行权价偏离目标建仓价{price_diff_pct:.1f}%")
    else:
        # 没设目标价，按OTM合理性评
        otm_pct = option.get("otm_pct", 0)
        price_score = min(otm_pct / 10 * 100, 100)
        scores["price_match"] = price_score * 0.35

    # 均线支撑强度 (25%)
    ma_support = option.get("ma_support_score", 50)
    scores["ma_support"] = (ma_support / 100) * 100 * 0.25
    if ma_support > 70:
        reasons.append("均线支撑强劲")
    elif ma_support < 30:
        reasons.append("均线支撑偏弱")

    # 接股后CC年化 (20%) - 估算接股后卖Covered Call的收益
    target_cost = strike - premium
    # 假设卖OTM 5%的CC，权利金约为股价的1%/月
    estimated_cc_premium = target_cost * 0.01
    cc_annual = estimated_cc_premium * 12 / target_cost * 100
    cc_score = min(cc_annual / 15 * 100, 100)
    scores["cc_annual"] = cc_score * 0.20
    reasons.append(f"接股后CC预估年化{cc_annual:.1f}%")

    # 保证金占比 (10%) - 保证金占用越低越好
    margin = strike * 100 * 0.20  # 大约20%保证金
    margin_score = max(100 - margin / 10000 * 100, 0)
    scores["margin"] = min(margin_score, 100) * 0.10

    # IV Rank (10%)
    iv_score = min(iv_rank / 100 * 100, 100)
    scores["iv_rank"] = iv_score * 0.10

    total = sum(scores.values())
    annual_return = (premium / strike) * (365 / dte) * 100

    return {
        "total_score": round(total, 1),
        "scores": scores,
        "reasons": reasons,
        "target_cost": round(target_cost, 2),
        "cc_annual": round(cc_annual, 1),
        "margin_used": round(margin, 0),
        "annual_return": round(annual_return, 1),
        "mode": "主动接股",
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

    # 行权价在均线附近加分
    for ma_val, weight in [(ma20, 15), (ma50, 20), (ma200, 25)]:
        if ma_val and ma_val > 0:
            diff_pct = abs(strike - ma_val) / ma_val * 100
            if diff_pct < 2:
                score += weight
            elif diff_pct < 5:
                score += weight * 0.5
    # 行权价在均线之下加分（有支撑）
    if ma50 > 0 and strike < ma50:
        score += 10
    if ma200 and ma200 > 0 and strike < ma200:
        score += 10

    return min(score, 100)


def cross_mode_hint(option: dict, iv_rank: float, stock_price: float, current_mode: str) -> str:
    """检查其他模式是否分数更高，返回提示"""
    results = {}
    opt_copy = option.copy()

    if current_mode != "纯收租":
        r = score_pure_income(opt_copy, iv_rank)
        results["纯收租"] = r["total_score"]
    if current_mode != "愿意接股":
        r = score_willing_assign(opt_copy, iv_rank, stock_price)
        results["愿意接股"] = r["total_score"]
    if current_mode != "主动接股":
        r = score_active_assign(opt_copy, iv_rank, stock_price)
        results["主动接股"] = r["total_score"]

    # 找最高分的其他模式
    if results:
        best_mode = max(results, key=results.get)
        best_score = results[best_mode]
        return best_mode, best_score
    return None, 0
