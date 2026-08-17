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


def _plane_summary(angles: list[float], values: list[float]) -> dict[str, float | None]:
    peak_index = max(range(len(values)), key=values.__getitem__)
    peak = values[peak_index]
    return {
        "peak_angle": angles[peak_index],
        "peak_intensity": peak,
        "threshold": peak * 0.5,
        "crossing_angle": _intensity_crossing(angles, values, 0.5),
        "threshold_10": peak * 0.1,
        "crossing_angle_10": _intensity_crossing(angles, values, 0.1),
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

    beam_angles = []
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
        if plane["crossing_angle"] is not None and opposite["crossing_angle"] is not None:
            width_50 = round(plane["crossing_angle"] + opposite["crossing_angle"], 2)
        if plane["crossing_angle_10"] is not None and opposite["crossing_angle_10"] is not None:
            width_10 = round(plane["crossing_angle_10"] + opposite["crossing_angle_10"], 2)
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

    peak_plane = max(planes, key=lambda plane: plane["peak_intensity"])
    global_peak = max(plane["peak_intensity"] for plane in planes) or 1
    normalized_shapes = [[value / global_peak for value in plane["candela"]] for plane in planes]
    maximum_shape_delta = 0.0
    if len(normalized_shapes) > 1:
        reference = normalized_shapes[0]
        maximum_shape_delta = max(abs(value - reference[index]) for shape in normalized_shapes[1:] for index, value in enumerate(shape))
    distribution_type = "rotational_symmetric" if len(planes) == 1 or maximum_shape_delta <= 0.05 else "approximately_symmetric" if maximum_shape_delta <= 0.15 else "asymmetric"
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

    return {
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
