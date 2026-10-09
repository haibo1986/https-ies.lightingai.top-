"""Type B/A → Type C 光度坐标转换（球面旋转 + 双线性重采样）。

Type B/A 的方位坐标 (H, V) 与 Type C 的 (C, γ) 是同一球面上的两套参数化：
    方向向量 u(H, V) = (cosV·sinH, sinV, −cosV·cosH)      （光轴指向 −z，即正下方）
    方向向量 u(C, γ) = (sinγ·cosC, sinγ·sinC, −cosγ)      （γ 从天底起算）

正变换（用于报告坐标系约定，H=0 剖面映射到 C0 平面）：
    γ = arccos(cosV·cosH)
    C = atan2(sinV, cosV·sinH) − 90°  （mod 360）

重采样（对每个目标 (C, γ) 网格点反算 (H, V) 并在原矩阵上双线性插值）：
    V = asin(sinγ·sinC)，H = atan2(sinγ·cosC, cosγ)，其中 C = C目标 + 90°

输出为标准的 Type C 数据 dict，可直接喂给经典 13 页报告引擎。
"""

from __future__ import annotations

import math
from typing import Any


def _bilinear(h_grid: list[float], v_grid: list[float], matrix: list[list[float]], h: float, v: float) -> float:
    """在 (H, V) 均匀网格上做双线性插值；越界返回 0。"""
    h0, h1 = h_grid[0], h_grid[-1]
    v0, v1 = v_grid[0], v_grid[-1]
    if h < h0 or h > h1 or v < v0 or v > v1:
        return 0.0
    dh = (h1 - h0) / max(1, len(h_grid) - 1)
    dv = (v1 - v0) / max(1, len(v_grid) - 1)
    fi = (h - h0) / dh
    fj = (v - v0) / dv
    i = min(int(fi), len(h_grid) - 2)
    j = min(int(fj), len(v_grid) - 2)
    ti, tj = fi - i, fj - j
    a = matrix[i][j]
    b = matrix[i + 1][j]
    c = matrix[i][j + 1]
    d = matrix[i + 1][j + 1]
    return a + (b - a) * ti + (c - a) * tj + (a - b - c + d) * ti * tj


def convert_to_type_c(data: dict[str, Any]) -> dict[str, Any]:
    """把 Type B/A 的 data dict 转换为 Type C 数据 dict（重采样到规则网格）。

    不满足转换前提（水平角未覆盖 ±90、垂直角未覆盖 −90~90）时抛 ValueError，
    调用方应回退到简化版报告。
    """
    ptype = int(data.get("photometric_type", 1))
    if ptype == 1:
        return data
    vertical = list(map(float, data["vertical_angles"]))
    horizontal = list(map(float, data["horizontal_angles"]))
    multiplier = float(data.get("candela_multiplier", 1))
    matrix = [[float(v) * multiplier for v in row] for row in data["candela_values"]]
    if min(horizontal) > -89.9 or max(horizontal) < 89.9:
        raise ValueError("Type B/A 水平角必须覆盖 -90°~90°，无法转换为 Type C 报告。")
    if min(vertical) > -89.9 or max(vertical) < 89.9:
        raise ValueError("Type B/A 垂直角必须覆盖 -90°~90°，无法转换为 Type C 报告。")
    if len(horizontal) < 2 or len(vertical) < 2:
        raise ValueError("角度数据不足，无法转换为 Type C 报告。")

    h_grid = horizontal
    v_grid = vertical
    # 重采样网格：γ 取 0~90（源垂直步长），C 取 0~357.5（源水平步长）
    dg = (v_grid[-1] - v_grid[0]) / (len(v_grid) - 1)
    dc = (h_grid[-1] - h_grid[0]) / (len(h_grid) - 1)
    gamma_grid = [round(i * dg, 6) for i in range(int(round(90.0 / dg)) + 1)]
    c_grid = [round(i * dc, 6) for i in range(int(round(360.0 / dc)))]

    converted: list[list[float]] = []
    for c_target in c_grid:
        row = []
        for gamma in gamma_grid:
            c = math.radians(c_target + 90.0)
            g = math.radians(gamma)
            v = math.degrees(math.asin(max(-1.0, min(1.0, math.sin(g) * math.sin(c)))))
            h = math.degrees(math.atan2(math.sin(g) * math.cos(c), math.cos(g)))
            row.append(round(_bilinear(h_grid, v_grid, matrix, h, v), 3))
        converted.append(row)

    result = {**data}
    result.update({
        "photometric_type": 1,
        "vertical_angles": gamma_grid,
        "horizontal_angles": c_grid,
        "candela_values": converted,
        "num_vertical_angles": len(gamma_grid),
        "num_horizontal_angles": len(c_grid),
        "candela_multiplier": 1.0,
        "max_candela": round(max(max(row) for row in converted), 3),
        "converted_from_type": ptype,
        "conversion_note": f"配光分析基于 Type {ptype} → Type C 球面坐标转换与双线性重采样（γ {dg:g}°×C {dc:g}° 网格）。",
    })
    return result
