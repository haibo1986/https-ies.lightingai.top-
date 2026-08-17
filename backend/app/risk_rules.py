from __future__ import annotations


RISK_RULES = {
    "power_only": {
        "allow_generate": True,
        "risk_level": "low",
        "risk_message": "适合同系列、同光学结构、同角度，仅功率变化的估算换算。",
    },
    "led_count_change": {
        "allow_generate": True,
        "risk_level": "medium",
        "risk_message": "LED 数量变化可能影响近场洗墙均匀性，生成文件仅适合初步模拟。",
    },
    "length_change": {
        "allow_generate": True,
        "risk_level": "medium",
        "risk_message": "灯具长度变化可能影响墙面均匀性，生成文件仅适合初步模拟。",
    },
    "beam_angle_change": {
        "allow_generate": False,
        "risk_level": "high",
        "risk_message": "光束角变化会改变配光形状，不建议通过简单缩放生成 IES，请重新实测。",
    },
    "lens_change": {
        "allow_generate": False,
        "risk_level": "high",
        "risk_message": "透镜变化会改变配光形状，需要重新实测。",
    },
    "optical_structure_change": {
        "allow_generate": False,
        "risk_level": "high",
        "risk_message": "光学结构变化风险高，需要重新实测。",
    },
}


def evaluate_risk(change_type: str) -> dict[str, object]:
    try:
        return dict(RISK_RULES[change_type])
    except KeyError as exc:
        raise ValueError("未知的变更类型。") from exc

