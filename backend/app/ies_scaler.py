from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .risk_rules import evaluate_risk


class IESScaler:
    @staticmethod
    def scale(
        parsed_data: dict[str, Any],
        source_luminous_flux_lm: float,
        target_luminous_flux_lm: float,
        target_model: str,
        target_power_w: float,
        change_type: str,
        target_luminous_length_mm: float | None = None,
        target_luminous_width_mm: float | None = None,
    ) -> dict[str, Any]:
        if not math.isfinite(source_luminous_flux_lm) or source_luminous_flux_lm <= 0:
            raise ValueError("原始实测总光通量必须大于 0。")
        if not math.isfinite(target_luminous_flux_lm) or target_luminous_flux_lm <= 0:
            raise ValueError("目标光通量必须大于 0。")
        if not math.isfinite(target_power_w) or target_power_w <= 0:
            raise ValueError("目标功率必须大于 0。")
        if not target_model.strip():
            raise ValueError("目标型号不能为空。")
        risk = evaluate_risk(change_type)
        if not risk["allow_generate"]:
            raise ValueError(str(risk["risk_message"]))

        exact_factor = target_luminous_flux_lm / source_luminous_flux_lm
        factor = round(exact_factor, 4)
        scaled = deepcopy(parsed_data)
        scaled["candela_values"] = [
            [round(value * exact_factor, 3) for value in row]
            for row in parsed_data["candela_values"]
        ]
        scaled.update(
            {
                "input_watts": float(target_power_w),
                "max_candela": round(parsed_data["max_candela"] * exact_factor, 3),
                "scale_factor": factor,
                "source_luminous_flux_lm": float(source_luminous_flux_lm),
                "target_luminous_flux_lm": float(target_luminous_flux_lm),
                "target_model": target_model.strip(),
                "target_power_w": float(target_power_w),
                "change_type": change_type,
                "estimated": True,
            }
        )
        millimeters_per_unit = 1000.0 if parsed_data["units_type"] == 2 else 304.8
        if target_luminous_length_mm is not None:
            if not math.isfinite(target_luminous_length_mm) or target_luminous_length_mm <= 0:
                raise ValueError("目标发光长度必须大于 0。")
            scaled["length"] = round(target_luminous_length_mm / millimeters_per_unit, 6)
            scaled["target_luminous_length_mm"] = float(target_luminous_length_mm)
        if target_luminous_width_mm is not None:
            if not math.isfinite(target_luminous_width_mm) or target_luminous_width_mm <= 0:
                raise ValueError("目标发光宽度必须大于 0。")
            scaled["width"] = round(target_luminous_width_mm / millimeters_per_unit, 6)
            scaled["target_luminous_width_mm"] = float(target_luminous_width_mm)
        if parsed_data["lumens_per_lamp"] != -1:
            scaled["lumens_per_lamp"] = round(
                target_luminous_flux_lm / parsed_data["number_of_lamps"], 6
            )
        return scaled
