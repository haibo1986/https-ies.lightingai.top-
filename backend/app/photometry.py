from __future__ import annotations

import math
from typing import Any


def _interpolate_crossing(angle_a: float, intensity_a: float, angle_b: float, intensity_b: float, threshold: float) -> float:
    if intensity_a == intensity_b:
        return angle_b
    ratio = (threshold - intensity_a) / (intensity_b - intensity_a)
    return angle_a + ratio * (angle_b - angle_a)


def _intensity_crossing(angles: list[float], values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    peak_index = max(range(len(values)), key=values.__getitem__)
    peak = values[peak_index]
    if peak <= 0:
        return None
    threshold = peak * fraction
    for index in range(peak_index, len(values) - 1):
        current, following = values[index], values[index + 1]
        if current >= threshold >= following:
            return _interpolate_crossing(angles[index], current, angles[index + 1], following, threshold)
    return None


def _intensity_crossing_ascending(angles: list[float], values: list[float], fraction: float) -> float | None:
    """从峰值向 γ 减小方向搜索交点（上升边）；峰值在 γ=0 附近时返回 0。"""
    if not values:
        return None
    peak_index = max(range(len(values)), key=values.__getitem__)
    threshold = values[peak_index] * fraction
    if values[0] >= threshold:
        return angles[0]
    for index in range(peak_index, 0, -1):
        previous, current = values[index - 1], values[index]
        if previous <= threshold <= current:
            return _interpolate_crossing(angles[index - 1], previous, angles[index], current, threshold)
    return None


def _trapz(values: list[float], steps: list[float]) -> float:
    total = 0.0
    for (left, right), step in zip(zip(values, values[1:]), steps):
        total += (left + right) / 2 * step
    return total


def _integrate_absolute_flux_lm(parsed: dict[str, Any]) -> float | None:
    """绝对光度文件（lumens_per_lamp=-1）的光通量估算：对 candela 矩阵做数值球面积分。

    Type C：方位平均 × 2π × ∫ sin(γ) dγ（方位平均自动兼容 C 平面数量编码的对称性，
    末位 360° 平面与 0° 重复不重复计；γ 范围取文件实际范围，通常为下半球）。
    Type B/A：∫∫ cos(V) dV dH（Type B 覆盖前半球，Type A 覆盖全空间）。
    """
    multiplier = parsed["candela_multiplier"]
    vertical = parsed["vertical_angles"]
    horizontal = parsed["horizontal_angles"]
    matrix = [[value * multiplier for value in row] for row in parsed["candela_values"]]
    if len(vertical) < 2 or len(horizontal) < 2:
        return None
    if int(parsed.get("photometric_type", 1)) == 1:
        rows = matrix
        if abs(horizontal[-1] - horizontal[0] - 360) < 1e-6:
            rows = rows[:-1]

        def azimuth_average(index: int) -> float:
            return sum(row[index] for row in rows) / len(rows) if rows else 0.0

        gamma_steps = [math.radians(vertical[index + 1] - vertical[index]) for index in range(len(vertical) - 1)]
        integrand = [azimuth_average(index) * math.sin(math.radians(gamma)) for index, gamma in enumerate(vertical)]
        return 2 * math.pi * _trapz(integrand, gamma_steps)
    h_steps = [math.radians(horizontal[index + 1] - horizontal[index]) for index in range(len(horizontal) - 1)]
    v_steps = [math.radians(vertical[index + 1] - vertical[index]) for index in range(len(vertical) - 1)]
    row_integrals = [
        _trapz([value * math.cos(math.radians(gamma)) for gamma, value in zip(vertical, row)], v_steps)
        for row in matrix
    ]
    return _trapz(row_integrals, h_steps)


def _plane_summary(angles: list[float], values: list[float]) -> dict[str, float | None]:
    peak_index = max(range(len(values)), key=values.__getitem__)
    peak = values[peak_index]
    return {
        "peak_angle": angles[peak_index],
        "peak_intensity": peak,
        "threshold": peak * 0.5,
        "crossing_angle": _intensity_crossing(angles, values, 0.5),
        "crossing_angle_asc": _intensity_crossing_ascending(angles, values, 0.5),
        "threshold_10": peak * 0.1,
        "crossing_angle_10": _intensity_crossing(angles, values, 0.1),
        "crossing_angle_10_asc": _intensity_crossing_ascending(angles, values, 0.1),
    }


def build_photometry_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    multiplier = parsed["candela_multiplier"]
    vertical_angles = parsed["vertical_angles"]
    planes = []
    for horizontal_angle, raw_values in zip(parsed["horizontal_angles"], parsed["candela_values"]):
        values = [round(value * multiplier, 6) for value in raw_values]
        planes.append({"c_angle": horizontal_angle, "candela": values, **_plane_summary(vertical_angles, values)})

    by_angle = {round(plane["c_angle"] % 360, 6): plane for plane in planes}

    def represented_plane(target: float) -> dict[str, Any] | None:
        target = round(target % 360, 6)
        if target in by_angle:
            return by_angle[target]
        last_angle = max(by_angle)
        if len(planes) == 1:
            mapped = next(iter(by_angle))
        elif last_angle <= 90:
            mapped = target % 180
            mapped = 180 - mapped if mapped > 90 else mapped
        elif last_angle <= 180:
            mapped = 360 - target if target > 180 else target
        else:
            return None
        return by_angle.get(round(mapped, 6))

    def _half_width(plane: dict[str, Any], crossing_key: str, asc_key: str) -> float | None:
        """峰值下降边交点 − 上升边交点（即该平面内真实半宽）；上升边无交点时以峰值角为界。"""
        if plane[crossing_key] is None:
            return None
        ascending = plane[asc_key] if plane[asc_key] is not None else plane["peak_angle"]
        return plane[crossing_key] - ascending

    beam_angles = []
    if int(parsed.get("photometric_type", 1)) == 1:
        handled_axes: set[tuple[float, float]] = set()
        for plane in planes:
            c_angle = round(plane["c_angle"] % 360, 6)
            opposite_angle = round((c_angle + 180) % 360, 6)
            axis = tuple(sorted((c_angle, opposite_angle)))
            if axis in handled_axes:
                continue
            opposite = represented_plane(opposite_angle)
            if opposite is None:
                continue
            width_50 = None
            width_10 = None
            # 峰值不在 γ=0 时，仅测下降边会把偏移量算进光束角（虚高 2×γ_peak），
            # 改为「下降边 − 上升边」的真实半宽之和；峰值在 γ0 时结果与旧公式一致。
            half_50 = _half_width(plane, "crossing_angle", "crossing_angle_asc")
            half_50_opp = _half_width(opposite, "crossing_angle", "crossing_angle_asc")
            if half_50 is not None and half_50_opp is not None:
                width_50 = round(half_50 + half_50_opp, 2)
            half_10 = _half_width(plane, "crossing_angle_10", "crossing_angle_10_asc")
            half_10_opp = _half_width(opposite, "crossing_angle_10", "crossing_angle_10_asc")
            if half_10 is not None and half_10_opp is not None:
                width_10 = round(half_10 + half_10_opp, 2)
            if width_50 is None and width_10 is None:
                continue
            handled_axes.add(axis)
            beam_angles.append({
                "label": f"C{plane['c_angle']:g}–C{opposite_angle:g}平面",
                "positive_c_angle": plane["c_angle"],
                "negative_c_angle": opposite_angle,
                "negative_data_c_angle": opposite["c_angle"],
                "beam_angle_50": width_50,
                "field_angle_10": width_10,
            })
    else:
        # Type B/A：水平平面中只有 H≈0 经过光轴，Type C 的 180° 配对映射不适用
        # （负角度取模后落在 270~360 区间，represented_plane 会返回 None）。
        # 光束角改为「H≈0 垂直主剖面」的单平面 FWHM（下降边 − 上升边）。
        main_plane = min(planes, key=lambda plane: abs(plane["c_angle"]))
        width_50 = _half_width(main_plane, "crossing_angle", "crossing_angle_asc")
        width_10 = _half_width(main_plane, "crossing_angle_10", "crossing_angle_10_asc")
        beam_angles.append({
            "label": f"H{main_plane['c_angle']:g}°垂直剖面",
            "positive_c_angle": 0.0,
            "negative_c_angle": 180.0,
            "negative_data_c_angle": main_plane["c_angle"],
            "beam_angle_50": round(width_50, 2) if width_50 is not None else None,
            "field_angle_10": round(width_10, 2) if width_10 is not None else None,
        })

    peak_plane = max(planes, key=lambda plane: plane["peak_intensity"])
    global_peak = max(plane["peak_intensity"] for plane in planes) or 1
    if int(parsed.get("photometric_type", 1)) == 1:
        # Type C：所有 C 平面都经过光轴，旋转对称配光的各平面垂直轮廓应完全一致。
        normalized_shapes = [[value / global_peak for value in plane["candela"]] for plane in planes]
        maximum_shape_delta = 0.0
        if len(normalized_shapes) > 1:
            reference = normalized_shapes[0]
            maximum_shape_delta = max(abs(value - reference[index]) for shape in normalized_shapes[1:] for index, value in enumerate(shape))
        distribution_type = "rotational_symmetric" if len(planes) == 1 or maximum_shape_delta <= 0.05 else "approximately_symmetric" if maximum_shape_delta <= 0.15 else "asymmetric"
    else:
        # Type B/A：水平平面不都经过光轴，跨平面比形状必然误判；
        # 对称性改按 +h/−h 成对镜像平面判断（绕光轴对称的配光，±h 平面应一致）。
        pair_delta = 0.0
        pair_count = 0
        for plane in planes:
            h = plane["c_angle"]
            if h > 0:
                opposite = next((item for item in planes if abs(item["c_angle"] + h) < 1e-6), None)
                if opposite is not None:
                    pair_delta = max(pair_delta, max(abs(a - b) for a, b in zip(plane["candela"], opposite["candela"])) / global_peak)
                    pair_count += 1
        distribution_type = "asymmetric" if pair_count == 0 else ("rotational_symmetric" if pair_delta <= 0.05 else "approximately_symmetric" if pair_delta <= 0.15 else "asymmetric")
    angle_steps = [round(vertical_angles[index + 1] - vertical_angles[index], 6) for index in range(len(vertical_angles) - 1)]
    # Zonal flux is integrated from the azimuth-averaged intensity.  This works
    # for full LM-63 C-plane sets and for the standard symmetry encodings.
    zone_edges = list(range(0, 91, 10))
    if zone_edges[-1] != 90:
        zone_edges.append(90)

    def mean_intensity(gamma: float) -> float:
        samples = []
        for plane in planes:
            values = plane["candela"]
            if gamma <= vertical_angles[0]:
                samples.append(values[0]); continue
            if gamma >= vertical_angles[-1]:
                samples.append(values[-1]); continue
            for i in range(len(vertical_angles) - 1):
                a, b = vertical_angles[i], vertical_angles[i + 1]
                if a <= gamma <= b:
                    ratio = (gamma - a) / (b - a) if b != a else 0
                    samples.append(values[i] + ratio * (values[i + 1] - values[i]))
                    break
        # A duplicated 360-degree plane must not receive extra weight.
        if len(samples) > 1 and round(parsed["horizontal_angles"][-1] - parsed["horizontal_angles"][0], 6) == 360:
            samples = samples[:-1]
        return sum(samples) / len(samples) if samples else 0.0

    zones = []
    cumulative = 0.0
    for start, end in zip(zone_edges, zone_edges[1:]):
        step = 1.0
        samples = []
        angle = float(start)
        while angle < end:
            next_angle = min(angle + step, float(end))
            a, b = math.radians(angle), math.radians(next_angle)
            flux = 2 * math.pi * ((mean_intensity(angle) + mean_intensity(next_angle)) / 2) * (math.cos(a) - math.cos(b))
            samples.append(flux); angle = next_angle
        zone_flux = sum(samples); cumulative += zone_flux
        zones.append({"start_angle": start, "end_angle": end, "flux_lm": round(zone_flux, 3), "cumulative_lm": round(cumulative, 3)})

    principal = []
    for target in (0, 90):
        candidate = min(beam_angles, key=lambda item: abs(item["positive_c_angle"] - target), default=None)
        if candidate and candidate not in principal:
            principal.append(candidate)
    center_intensity = sum(plane["candela"][0] for plane in planes) / len(planes)
    cone = []
    for height in (1, 2, 3, 4, 5, 6, 8, 10):
        row = {"height_m": height, "center_lux": round(center_intensity / height**2, 2), "max_lux": round(global_peak / height**2, 2)}
        for index, beam in enumerate(principal):
            width = beam.get("beam_angle_50")
            row[f"diameter_{index + 1}_m"] = round(2 * height * math.tan(math.radians(width / 2)), 2) if width else None
        cone.append(row)

    total_integrated = cumulative
    for zone in zones:
        zone["percent"] = round(zone["flux_lm"] / total_integrated * 100, 2) if total_integrated else 0

    summary = {
        # Type C 专用配光分析（光束角/球面积分/等照度）仅对 Type C 有效；Type B/A 标记为不支持。
        "photometric_analysis_supported": int(parsed.get("photometric_type", 1)) == 1,
        "vertical_angles": vertical_angles,
        "planes": planes,
        "beam_angles_50": beam_angles,
        "peak_direction": {"c_angle": peak_plane["c_angle"], "gamma_angle": peak_plane["peak_angle"], "intensity": peak_plane["peak_intensity"]},
        "distribution_type": distribution_type,
        "vertical_range": [vertical_angles[0], vertical_angles[-1]],
        "horizontal_range": [parsed["horizontal_angles"][0], parsed["horizontal_angles"][-1]],
        "minimum_vertical_step": min(angle_steps) if angle_steps else None,
        "center_intensity": round(center_intensity, 3),
        "integrated_downward_flux_lm": round(total_integrated, 3),
        "zonal_flux": zones,
        "illuminance_cone": cone,
        "definition": "Beam and field angles are measured at 50% and 10% of peak intensity.",
    }
    # 绝对光度文件不声明光通量：用光强矩阵数值积分给出估算值供界面预填与展示
    if parsed.get("lumens_per_lamp") == -1:
        estimate = _integrate_absolute_flux_lm(parsed)
        summary["estimated_source_flux_lm"] = round(estimate, 1) if estimate else None
        summary["estimated_source_flux_note"] = "由绝对光强矩阵数值积分估算，非文件声明值；请与实测总光通量核对。"
    return summary
