from __future__ import annotations

from datetime import date
from typing import Any

from .photometry import build_photometry_summary
from .photometric_engine import PhotometricEngine


def build_report_data(
    source: dict[str, Any],
    target: dict[str, Any],
    risk: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single canonical data source used by every report renderer."""
    supplement = {key: value for key, value in (supplement or {}).items() if value not in (None, "")}
    photometry = build_photometry_summary(target)
    engine = PhotometricEngine.from_parsed(target)
    photometry["integrated_downward_flux_lm"] = engine.integrated_flux()
    photometry["zonal_flux"] = engine.zonal_flux()
    source_flux = float(target["source_luminous_flux_lm"])
    target_flux = float(target["target_luminous_flux_lm"])
    # IES 尺寸字段的单位由 units_type 决定：1=英尺，2=米。
    millimeters_per_unit = 1000.0 if target.get("units_type", 2) == 2 else 304.8
    dimensions = {
        "luminous_length_mm": round(float(target.get("length", 0)) * millimeters_per_unit, 2),
        "luminous_width_mm": round(float(target.get("width", 0)) * millimeters_per_unit, 2),
        "luminous_height_mm": round(float(target.get("height", 0)) * millimeters_per_unit, 2),
    }
    dimensions.update({key: supplement[key] for key in ("fixture_length_mm", "fixture_width_mm", "fixture_height_mm") if key in supplement})
    return {
        "schema_version": "1.0",
        "report_type": "estimated_photometric_data",
        "report_title": "估算光度数据报告",
        "generated_on": supplement.get("report_date") or date.today().isoformat(),
        "report_number": supplement.get("report_number") or f"EST-{target['target_model']}",
        "company": supplement.get("company_name") or "内部光度工程中心",
        "company_website": supplement.get("company_website") or "",
        "company_phone": supplement.get("company_phone") or "",
        "company_logo_data_url": supplement.get("company_logo_data_url") or "",
        "product": {
            "model": target["target_model"],
            "manufacturer": supplement.get("manufacturer") or supplement.get("company_name") or "-",
            "description": supplement.get("product_description") or "LED 灯具",
            "cct_k": supplement.get("cct_k"), "cri_ra": supplement.get("cri_ra"),
            **dimensions,
        },
        "electrical": {
            "power_w": float(target["target_power_w"]),
            "voltage_v": supplement.get("voltage_v"), "current_a": supplement.get("current_a"),
            "power_factor": supplement.get("power_factor"),
        },
        "photometric": {
            "source_flux_lm": source_flux, "target_flux_lm": target_flux,
            "efficacy_lm_w": target_flux / float(target["target_power_w"]),
            "max_candela_cd": float(target["max_candela"]),
            **photometry,
        },
        "conversion": {
            "source_file": source.get("original_file_name", "-"),
            "scale_factor": float(target["scale_factor"]), "change_type": target["change_type"],
            "risk_level": risk["risk_level"], "risk_message": risk["risk_message"],
        },
        "supplement": supplement,
        "calculation": {"height_m": supplement.get("calculation_height_m", 10), "plane_extent_m": supplement.get("plane_extent_m", 20)},
        "notes": supplement.get("notes") or "",
        "disclaimer": "本报告由原始实测 IES 按工程假设换算生成，并非实验室实测报告，不可用于认证、验收或第三方检测结论。",
    }
