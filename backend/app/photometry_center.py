"""配光对中校正（逐平面平移版）：每条 C 平面曲线按自身峰值 γ 偏移整体平移，
使峰值对准 γ=0°。曲线形状与各平面光束角严格不变。

适用于「灯具本身非偏光设计、但实测时未完全居中导致配光曲线偏移」的场景。
算法：对每个 C 平面，在 γ≤90° 内找该平面的峰值方向 γ_peak，把该平面曲线
沿 γ 轴平移 −γ_peak（新 γ' = 原 γ − γ_peak），峰值即落在 γ=0。平移后
γ' + γ_peak 超出原垂直角范围的方向填 0（原数据中没有的信息不虚构）。
"""

from __future__ import annotations

import bisect
from copy import deepcopy
from typing import Any

from .photometry import build_photometry_summary


def _bracket_index(angles: list[float], value: float) -> int:
    index = bisect.bisect_right(angles, value) - 1
    if index < 0:
        index = 0
    if index >= len(angles) - 1:
        index = len(angles) - 2
    return index


def _linear_on_vertical(vertical_angles: list[float], row: list[float], gamma: float) -> float:
    """该平面自身 γ 轴上的线性插值（垂直角网格通常 ≤1°，线性足够平滑）。"""
    index = _bracket_index(vertical_angles, gamma)
    a, b = vertical_angles[index], vertical_angles[index + 1]
    if b == a:
        return row[index]
    t = (gamma - a) / (b - a)
    return row[index] + t * (row[index + 1] - row[index])


def _plane_peak_gamma(vertical_angles: list[float], row: list[float]) -> tuple[int, float]:
    best_index, best_value = -1, float("-inf")
    for index, (angle, value) in enumerate(zip(vertical_angles, row)):
        if angle > 90:
            continue
        if value > best_value:
            best_index, best_value = index, value
    return best_index, best_value


def center_photometry(data: dict[str, Any]) -> dict[str, Any]:
    """对中校正：返回 deepcopy 后的新 dict，各 C 平面曲线已平移至峰值对准 γ=0。"""
    vertical_angles = data.get("vertical_angles") or []
    candela_values = data.get("candela_values") or []
    horizontal_angles = data.get("horizontal_angles") or []
    if len(vertical_angles) < 2 or not candela_values or len(candela_values) != len(horizontal_angles):
        raise ValueError("光度数据不完整，无法进行对中校正。")
    if any(len(row) != len(vertical_angles) for row in candela_values):
        raise ValueError("光度矩阵形状不一致，无法进行对中校正。")

    scaled = deepcopy(data)
    max_gamma = vertical_angles[-1]
    min_gamma = vertical_angles[0]
    offsets: list[float] = []
    new_matrix: list[list[float]] = []
    out_of_range = 0
    total = 0
    global_peak = (0.0, 0.0, float("-inf"))

    for c_angle, row in zip(horizontal_angles, candela_values):
        peak_index, peak_value = _plane_peak_gamma(vertical_angles, list(row))
        if peak_value <= 0:
            raise ValueError("无法确定光强峰值方向，无法进行对中校正。")
        offset = vertical_angles[peak_index]
        offsets.append(offset)
        if peak_value > global_peak[2]:
            global_peak = (c_angle, offset, peak_value)
        new_row: list[float] = []
        for gamma_prime in vertical_angles:
            source_gamma = gamma_prime + offset
            total += 1
            if source_gamma > max_gamma:
                new_row.append(0.0)
                out_of_range += 1
            else:
                if source_gamma < min_gamma:
                    source_gamma = min_gamma
                new_row.append(round(_linear_on_vertical(vertical_angles, row, source_gamma), 3))
        new_matrix.append(new_row)

    scaled["candela_values"] = new_matrix
    multiplier = scaled.get("candela_multiplier", 1)
    scaled["max_candela"] = round(max(value for row in new_matrix for value in row) * multiplier, 3)
    # 光通量补偿：平移丢弃了各平面峰值以下的 γ 段（原始数据中该部分信息
    # 在 IES 的 γ≥0 约定下无法表达），按对中前后积分光通量比整体等比缩放，
    # 恢复原始光通量。等比缩放不改变曲线形状与光束角。
    flux_compensation = 1.0
    flux_before = build_photometry_summary(data)["integrated_downward_flux_lm"]
    flux_after = build_photometry_summary(scaled)["integrated_downward_flux_lm"]
    if flux_before > 0 and flux_after > 0 and abs(flux_before - flux_after) > 0.001:
        flux_compensation = flux_before / flux_after
        scaled["candela_values"] = [
            [round(value * flux_compensation, 3) for value in row] for row in new_matrix
        ]
        scaled["max_candela"] = round(
            max(value for row in scaled["candela_values"] for value in row) * multiplier, 3
        )
    max_offset = max(offsets)
    scaled["centering"] = {
        "original_peak_c_angle": round(global_peak[0], 3),
        "original_peak_gamma_angle": round(global_peak[1], 3),
        "original_peak_intensity": round(global_peak[2] * multiplier, 3),
        "centered_peak_intensity": scaled["max_candela"],
        "max_shift_degrees": round(max_offset, 3),
        "out_of_range_ratio": round(out_of_range / total, 3) if total else 0.0,
        "flux_compensation_factor": round(flux_compensation, 4),
    }
    scaled["centering_note"] = (
        f"Photometric centering applied: per-plane peak alignment (max shift {max_offset:g} deg);"
        f" original peak at C={global_peak[0]:g} deg, gamma={global_peak[1]:g} deg;"
        f" flux compensation factor {flux_compensation:.4f}."
    )
    return scaled
