"""配光对中校正：把光强分布整体旋转，使最大光强对准正下方（γ=0°）。

适用于「灯具本身非偏光设计、但实测时未完全居中导致配光曲线偏移」的场景。
算法：按 LM-63 对称规则把 C 平面展开为完整 0-360 网格 → 在下半球（γ≤90°）
找到全局峰值方向 (C_p, γ_p) → 旋转 R = Ry(γ_p)·Rz(−C_p) 把峰值映射到
(0,0,−1) → 新网格逐点反旋转回原坐标后双线性插值。
方向向量约定：x = sinγ·cosC, y = sinγ·sinC, z = −cosγ（γ=0 即正下方）。
"""

from __future__ import annotations

import bisect
import math
from copy import deepcopy
from typing import Any


def expand_c_planes(horizontal_angles: list[float]) -> list[float]:
    """按 LM-63 对称规则把 C 平面展开为完整 0-360 网格（round(6) 去重排序）。"""
    last_angle = max(horizontal_angles)
    if last_angle <= 90:
        candidates = [angle for c in horizontal_angles for angle in (c, 180 - c, 180 + c, 360 - c)]
    elif last_angle <= 180:
        candidates = [angle for c in horizontal_angles for angle in (c, 360 - c)]
    else:
        candidates = list(horizontal_angles)
    grid: list[float] = []
    for angle in candidates:
        rounded = round(angle, 6)
        if rounded not in grid:
            grid.append(rounded)
    grid.sort()
    return grid


def _expand_matrix(horizontal_angles: list[float], candela_values: list[list[float]], c_grid: list[float]) -> list[list[float]]:
    """把矩阵按展开后的 C 网格重组：镜像平面映射回源平面取数；首平面非 C0 时环绕合成 C=0 行。"""
    last_angle = max(horizontal_angles)
    by_angle = {round(c, 6): list(row) for c, row in zip(horizontal_angles, candela_values)}

    def source_plane(angle: float) -> float:
        if last_angle <= 90:
            return angle if angle <= 90 else (180 - angle if angle < 180 else (angle - 180 if angle < 270 else 360 - angle))
        if last_angle <= 180:
            return angle if angle <= 180 else 360 - angle
        return angle

    matrix = [by_angle[round(source_plane(angle), 6)] for angle in c_grid]
    if 0 not in c_grid:
        a, b = c_grid[-1], c_grid[0] + 360.0
        t = (360.0 - a) / (b - a)
        zero_row = [round(va + t * (vb - va), 3) for va, vb in zip(matrix[-1], matrix[0])]
        c_grid.insert(0, 0.0)
        matrix.insert(0, zero_row)
    return matrix


def _inverse_rotation(c_prime: float, gamma_prime: float, cp_deg: float, gp_deg: float) -> tuple[float, float]:
    """新网格方向 (C′,γ′) 反旋转回原坐标 (C,γ)。R = Ry(γp)·Rz(−Cp)，此处用转置。"""
    gamma_rad = math.radians(gamma_prime)
    vx = math.sin(gamma_rad) * math.cos(math.radians(c_prime))
    vy = math.sin(gamma_rad) * math.sin(math.radians(c_prime))
    vz = -math.cos(gamma_rad)
    gp, cp = math.radians(gp_deg), math.radians(cp_deg)
    sg, cg = math.sin(gp), math.cos(gp)
    x1 = cg * vx - sg * vz
    z1 = sg * vx + cg * vz
    sc, ss = math.cos(cp), math.sin(cp)
    x = sc * x1 - ss * vy
    y = ss * x1 + sc * vy
    z = z1
    gamma = math.degrees(math.acos(max(-1.0, min(1.0, -z))))
    c = math.degrees(math.atan2(y, x)) % 360.0
    return c, gamma


def _bracket(angles: list[float], value: float) -> tuple[int, int, float]:
    index = bisect.bisect_right(angles, value) - 1
    if index < 0:
        index = 0
    if index >= len(angles) - 1:
        index = len(angles) - 2
    a, b = angles[index], angles[index + 1]
    t = 0.0 if b == a else (value - a) / (b - a)
    return index, index + 1, t


def _bilinear(c_grid: list[float], vertical_angles: list[float], matrix: list[list[float]], c: float, gamma: float) -> float:
    """在展开网格上做双线性插值：C 维环绕 0↔360；γ 超出最大垂直角取 0（不虚构数据）。"""
    if gamma > vertical_angles[-1]:
        return 0.0
    if gamma < vertical_angles[0]:
        gamma = vertical_angles[0]
    gi0, gi1, gt = _bracket(vertical_angles, gamma)
    c_ext = c_grid + [c_grid[0] + 360.0]
    ci0, ci1, ct = _bracket(c_ext, c)
    rows = [matrix[ci0 % len(c_grid)], matrix[ci1 % len(c_grid)]]
    v0 = rows[0][gi0] + gt * (rows[0][gi1] - rows[0][gi0])
    v1 = rows[1][gi0] + gt * (rows[1][gi1] - rows[1][gi0])
    return v0 + ct * (v1 - v0)


def _find_peak(c_grid: list[float], vertical_angles: list[float], matrix: list[list[float]]) -> tuple[float, float, float]:
    best = (0.0, 0.0, float("-inf"))
    for ci, row in enumerate(matrix):
        for vi, value in enumerate(row):
            if vertical_angles[vi] > 90:
                continue
            if value > best[2]:
                best = (c_grid[ci], vertical_angles[vi], value)
    return best


def center_photometry(data: dict[str, Any]) -> dict[str, Any]:
    """对中校正：返回 deepcopy 后的新 dict，candela 矩阵已旋转至峰值对准 γ=0。"""
    vertical_angles = data.get("vertical_angles") or []
    horizontal_angles = data.get("horizontal_angles") or []
    candela_values = data.get("candela_values") or []
    if len(vertical_angles) < 2 or not horizontal_angles or len(candela_values) != len(horizontal_angles):
        raise ValueError("光度数据不完整，无法进行对中校正。")
    if any(len(row) != len(vertical_angles) for row in candela_values):
        raise ValueError("光度矩阵形状不一致，无法进行对中校正。")

    scaled = deepcopy(data)
    c_grid = expand_c_planes(list(horizontal_angles))
    matrix = _expand_matrix(list(horizontal_angles), [list(row) for row in candela_values], c_grid)
    cp, gp, peak = _find_peak(c_grid, vertical_angles, matrix)
    if peak <= 0:
        raise ValueError("无法确定光强峰值方向，无法进行对中校正。")

    new_matrix: list[list[float]] = []
    out_of_range = 0
    total = 0
    for c_prime in c_grid:
        row: list[float] = []
        for gamma_prime in vertical_angles:
            c, gamma = _inverse_rotation(c_prime, gamma_prime, cp, gp)
            total += 1
            if gamma > vertical_angles[-1]:
                row.append(0.0)
                out_of_range += 1
            else:
                row.append(round(_bilinear(c_grid, vertical_angles, matrix, c, gamma), 3))
        new_matrix.append(row)

    scaled["horizontal_angles"] = c_grid
    scaled["num_horizontal_angles"] = len(c_grid)
    scaled["candela_values"] = new_matrix
    multiplier = scaled.get("candela_multiplier", 1)
    scaled["max_candela"] = round(max(value for row in new_matrix for value in row) * multiplier, 3)
    scaled["centering"] = {
        "original_peak_c_angle": round(cp, 3),
        "original_peak_gamma_angle": round(gp, 3),
        "original_peak_intensity": round(peak * multiplier, 3),
        "centered_peak_intensity": scaled["max_candela"],
        "out_of_range_ratio": round(out_of_range / total, 3) if total else 0.0,
    }
    scaled["centering_note"] = (
        f"Photometric centering applied: original peak at C={cp:g} deg, gamma={gp:g} deg;"
        f" rotated to center at gamma=0 deg (bilinear resample)."
    )
    return scaled
