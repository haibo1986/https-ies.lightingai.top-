from pathlib import Path
import math

import pytest

from app.ies_parser import IESParseError, IESParser
from app.ies_scaler import IESScaler
from app.ies_writer import IESWriter, sanitize_file_stem
from app.photometry import build_photometry_summary
from app.report_generator import ReportGenerator
from app.report_model import build_report_data
from app.classic_report import generate_classic_pdf
from app.standard_report import validate_standard_report
from app.risk_rules import evaluate_risk
from app.photometry_center import center_photometry


def tilted_ies_text(c_peak=90.0, gamma_peak=30.0, sigma=20.0) -> str:
    """合成一个峰值方向在 (C_peak, γ_peak) 的高斯型配光 IES 文件文本。"""
    vertical = list(range(0, 91, 10))
    horizontal = list(range(0, 360, 30))
    peak_dir = (
        math.sin(math.radians(gamma_peak)) * math.cos(math.radians(c_peak)),
        math.sin(math.radians(gamma_peak)) * math.sin(math.radians(c_peak)),
        -math.cos(math.radians(gamma_peak)),
    )
    lines = [
        "IESNA:LM-63-2002",
        "[TEST] Synthetic tilted fixture",
        "TILT=NONE",
        f"1 1000 1 {len(vertical)} {len(horizontal)} 1 2 0.1 0.2 0.3",
        "1 1 100",
        " ".join(str(value) for value in vertical),
        " ".join(str(value) for value in horizontal),
    ]
    for c in horizontal:
        row = []
        for g in vertical:
            direction = (
                math.sin(math.radians(g)) * math.cos(math.radians(c)),
                math.sin(math.radians(g)) * math.sin(math.radians(c)),
                -math.cos(math.radians(g)),
            )
            dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(direction, peak_dir))))
            row.append(f"{1000 * math.exp(-(math.degrees(math.acos(dot)) ** 2) / (2 * sigma ** 2)):.3f}")
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


def _parse_tilted(tmp_path: Path, **kwargs) -> dict:
    path = tmp_path / "tilted.ies"
    path.write_text(tilted_ies_text(**kwargs), encoding="utf-8")
    return IESParser.parse(path)


def test_parser_reads_complete_matrix(sample_path: Path):
    data = IESParser.parse(sample_path)
    assert data["ies_version"] == "IESNA:LM-63-2002"
    assert data["num_vertical_angles"] == 3
    assert data["num_horizontal_angles"] == 2
    assert sum(map(len, data["candela_values"])) == 6
    assert data["candela_values"][1] == [80, 160, 40]
    assert data["suggested_source_luminous_flux_lm"] == 1000
    assert data["keywords"]["TEST"] == "Minimal valid fixture"


def test_photometry_summary_interpolates_half_power_beam_angle(sample_path: Path):
    summary = build_photometry_summary(IESParser.parse(sample_path))
    assert summary["planes"][0]["peak_intensity"] == 200
    assert summary["planes"][0]["threshold"] == 100
    assert summary["planes"][0]["crossing_angle"] == 75
    assert summary["beam_angles_50"][0]["beam_angle_50"] == 150
    assert summary["peak_direction"] == {"c_angle": 0, "gamma_angle": 45, "intensity": 200}
    assert summary["vertical_range"] == [0, 90]
    assert summary["horizontal_range"] == [0, 90]
    assert summary["minimum_vertical_step"] == 45
    assert summary["distribution_type"] == "asymmetric"
    assert summary["zonal_flux"]
    assert len(summary["illuminance_cone"]) == 8
    assert summary["integrated_downward_flux_lm"] > 0


def test_photometry_summary_uses_lm63_horizontal_symmetry(sample_path: Path, tmp_path: Path):
    content = sample_path.read_text(encoding="utf-8").replace(
        "1 1000 1 3 2", "1 1000 1 3 3"
    ).replace("0 90\n100 200 50\n80 160 40", "0 90 180\n100 200 0\n80 160 0\n60 120 0")
    path = tmp_path / "symmetric.ies"
    path.write_text(content, encoding="utf-8")
    summary = build_photometry_summary(IESParser.parse(path))
    assert summary["beam_angles_50"][0]["negative_c_angle"] == 180
    assert summary["beam_angles_50"][1]["negative_c_angle"] == 270
    assert summary["beam_angles_50"][1]["negative_data_c_angle"] == 90
    assert summary["beam_angles_50"][0]["field_angle_10"] is not None


def test_parser_supports_1995_and_cross_line_numbers(sample_path: Path, tmp_path: Path):
    content = sample_path.read_text(encoding="utf-8").replace("IESNA:LM-63-2002", "IESNA:LM-63-1995")
    content = content.replace("1 1000 1 3 2", "1\n1000 1\n3 2")
    path = tmp_path / "1995.ies"
    path.write_text(content, encoding="utf-8")
    assert IESParser.parse(path)["ies_version"] == "IESNA:LM-63-1995"


def test_parser_handles_absolute_photometry(sample_path: Path, tmp_path: Path):
    content = sample_path.read_text(encoding="utf-8").replace("1 1000 1 3 2", "1 -1 1 3 2")
    path = tmp_path / "absolute.ies"
    path.write_text(content, encoding="utf-8")
    parsed = IESParser.parse(path)
    assert parsed["is_absolute_photometry"] is True
    assert parsed["suggested_source_luminous_flux_lm"] is None
    scaled = IESScaler.scale(parsed, 1000, 1200, "Absolute", 30, "power_only")
    assert scaled["lumens_per_lamp"] == -1


@pytest.mark.parametrize("fixture", ["invalid_tilt.ies", "incomplete.ies"])
def test_parser_rejects_unsupported_or_incomplete(fixture: str):
    path = Path(__file__).parent / "sample_files" / fixture
    with pytest.raises(IESParseError):
        IESParser.parse(path)


@pytest.mark.parametrize(
    "content,error_text",
    [
        ("", "文件为空"),
        ("IESNA:LM-63-2002\nTILT=FILE\n", "TILT=FILE"),
    ],
)
def test_parser_rejects_empty_and_tilt_file(tmp_path: Path, content: str, error_text: str):
    path = tmp_path / "invalid.ies"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(IESParseError, match=error_text):
        IESParser.parse(path)


@pytest.mark.parametrize(
    "old,new,error_text",
    [
        ("1 1000 1 3 2", "1 1000 0 3 2", "candela_multiplier"),
        ("1 1000 1 3 2 1 2", "1 1000 1 3 2 9 2", "photometric_type"),
        ("1 1000 1 3 2 1 2", "1 1000 1 3 2 1 9", "units_type"),
        ("100 200 50", "100 -200 50", "candela"),
    ],
)
def test_parser_rejects_invalid_standard_values(sample_path: Path, tmp_path: Path, old, new, error_text):
    path = tmp_path / "invalid-values.ies"
    path.write_text(sample_path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    with pytest.raises(IESParseError, match=error_text):
        IESParser.parse(path)


def test_scaler_uses_luminous_flux_ratio(sample_path: Path):
    parsed = IESParser.parse(sample_path)
    scaled = IESScaler.scale(parsed, 1000, 1375, "WWL/36W", 36, "power_only")
    assert scaled["scale_factor"] == 1.375
    assert scaled["candela_values"][0] == [137.5, 275.0, 68.75]
    assert scaled["input_watts"] == 36
    assert scaled["max_candela"] == 275
    assert scaled["lumens_per_lamp"] == 1375


def test_scaler_updates_luminous_opening_dimensions(sample_path: Path):
    parsed = IESParser.parse(sample_path)
    scaled = IESScaler.scale(
        parsed, 1000, 1500, "Long model", 36, "length_change",
        target_luminous_length_mm=1200, target_luminous_width_mm=80,
    )
    assert scaled["length"] == 1.2
    assert scaled["width"] == 0.08


def test_report_model_converts_feet_dimensions_to_mm(sample_path: Path, tmp_path: Path):
    content = sample_path.read_text(encoding="utf-8").replace("1 1000 1 3 2 1 2", "1 1000 1 3 2 1 1")
    path = tmp_path / "feet.ies"
    path.write_text(content, encoding="utf-8")
    parsed = IESParser.parse(path)
    assert parsed["units_type"] == 1
    scaled = IESScaler.scale(
        parsed, 1000, 1500, "Feet model", 36, "power_only",
        target_luminous_length_mm=1200, target_luminous_width_mm=80,
    )
    data = build_report_data(parsed, scaled, evaluate_risk("power_only"))
    assert data["product"]["luminous_length_mm"] == 1200.0
    assert data["product"]["luminous_width_mm"] == 80.0
    assert data["product"]["luminous_height_mm"] == round(0.3 * 304.8, 2)


def test_parser_reads_gbk_encoded_header(tmp_path: Path):
    path = tmp_path / "gbk.ies"
    path.write_bytes(b"IESNA:LM-63-2002\n[TEST] \xd6\xd0\xce\xc4\xb1\xea\xc7\xa9\nTILT=NONE\n1 1000 1 3 2 1 2 0.1 0.2 0.3\n1 1 24\n0 45 90\n0 90\n100 200 50\n80 160 40\n")
    parsed = IESParser.parse(path)
    assert parsed["keywords"]["TEST"] == "中文标签"


@pytest.mark.parametrize(
    "source,target,power,model",
    [(0, 1000, 20, "A"), (1000, 0, 20, "A"), (1000, 1200, 0, "A"), (1000, 1200, 20, " ")],
)
def test_scaler_validates_inputs(sample_path: Path, source, target, power, model):
    with pytest.raises(ValueError):
        IESScaler.scale(IESParser.parse(sample_path), source, target, model, power, "power_only")


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_scaler_rejects_non_finite_values(sample_path: Path, invalid: float):
    parsed = IESParser.parse(sample_path)
    with pytest.raises(ValueError):
        IESScaler.scale(parsed, invalid, 1200, "A", 20, "power_only")
    with pytest.raises(ValueError):
        IESScaler.scale(parsed, 1000, invalid, "A", 20, "power_only")
    with pytest.raises(ValueError):
        IESScaler.scale(parsed, 1000, 1200, "A", invalid, "power_only")


@pytest.mark.parametrize(
    "change_type,allowed,level",
    [
        ("power_only", True, "low"), ("led_count_change", True, "medium"),
        ("length_change", True, "medium"), ("beam_angle_change", False, "high"),
        ("lens_change", False, "high"), ("optical_structure_change", False, "high"),
    ],
)
def test_risk_rules(change_type, allowed, level):
    result = evaluate_risk(change_type)
    assert result["allow_generate"] is allowed
    assert result["risk_level"] == level


def test_writer_and_report_include_disclaimer(sample_path: Path, tmp_path: Path):
    parsed = IESParser.parse(sample_path)
    scaled = IESScaler.scale(parsed, 1000, 1200, "Model A", 30, "power_only")
    risk = evaluate_risk("power_only")
    ies_path = tmp_path / "out.ies"
    report_path = tmp_path / "report.md"
    IESWriter.write(scaled, ies_path)
    ReportGenerator.generate(parsed, scaled, risk, report_path)
    output = ies_path.read_text(encoding="utf-8")
    assert "ESTIMATED" in output
    assert "Not a certified photometric test report" in output
    reparsed = IESParser.parse(ies_path)
    assert reparsed["input_watts"] == 30
    assert "使用声明" in report_path.read_text(encoding="utf-8")
    assert sanitize_file_stem(' A/B:*? ') == "A_B___"


def test_center_photometry_aligns_peak_to_nadir(tmp_path: Path):
    parsed = _parse_tilted(tmp_path)
    scaled = IESScaler.scale(parsed, 1000, 1500, "Tilted", 36, "power_only")
    centered = center_photometry(scaled)
    summary = build_photometry_summary(centered)
    assert summary["peak_direction"]["gamma_angle"] == 0
    assert summary["peak_direction"]["c_angle"] == 0
    assert summary["peak_direction"]["intensity"] == 1500
    assert centered["max_candela"] == 1500
    assert centered["centering"]["original_peak_c_angle"] == 90
    assert centered["centering"]["original_peak_gamma_angle"] == 30
    assert len(centered["candela_values"]) == centered["num_horizontal_angles"] == 12


def test_center_photometry_expands_symmetric_c_planes():
    row_c0 = [100.0, 50.0, 10.0]
    row_c90 = [80.0, 40.0, 8.0]
    parsed = {
        "vertical_angles": [0.0, 45.0, 90.0],
        "horizontal_angles": [0.0, 90.0],
        "candela_values": [row_c0, row_c90],
        "candela_multiplier": 1,
    }
    centered = center_photometry(parsed)
    assert centered["horizontal_angles"] == [0.0, 90.0, 180.0, 270.0, 360.0]
    assert centered["num_horizontal_angles"] == 5
    # 峰值在 (C0, γ0) → 旋转为单位变换；γ=0 行为正下方光强（与方位角无关，全部取峰值），
    # 其余各行按 LM-63 镜像规则映射回源平面
    assert centered["candela_values"] == [
        [100.0, 50.0, 10.0],
        [100.0, 40.0, 8.0],
        [100.0, 50.0, 10.0],
        [100.0, 40.0, 8.0],
        [100.0, 50.0, 10.0],
    ]


def test_center_photometry_preserves_flux_within_tolerance(tmp_path: Path):
    parsed = _parse_tilted(tmp_path, c_peak=90.0, gamma_peak=25.0)
    before = build_photometry_summary(parsed)["integrated_downward_flux_lm"]
    centered = center_photometry(parsed)
    after = build_photometry_summary(centered)["integrated_downward_flux_lm"]
    assert after == pytest.approx(before, rel=0.03)


def test_center_photometry_roundtrip_writes_note_and_reparses(tmp_path: Path):
    parsed = _parse_tilted(tmp_path)
    scaled = IESScaler.scale(parsed, 1000, 1500, "Tilted", 36, "power_only")
    centered = center_photometry(scaled)
    ies_path = tmp_path / "centered.ies"
    IESWriter.write(centered, ies_path)
    output = ies_path.read_text(encoding="utf-8")
    assert "[MORE] Photometric centering applied" in output
    reparsed = IESParser.parse(ies_path)
    assert reparsed["num_horizontal_angles"] == len(reparsed["horizontal_angles"]) == 12
    assert build_photometry_summary(reparsed)["peak_direction"]["gamma_angle"] == 0


def test_center_photometry_large_tilt_fills_out_of_range_with_zeros(tmp_path: Path):
    parsed = _parse_tilted(tmp_path, c_peak=0.0, gamma_peak=40.0)
    centered = center_photometry(parsed)
    assert centered["centering"]["out_of_range_ratio"] > 0
    # 垂直角只到 90°，40° 大倾斜旋转后远侧方向无数据 → 填 0
    assert any(value == 0 for row in centered["candela_values"] for value in row)


def test_center_photometry_uses_candela_multiplier(tmp_path: Path):
    parsed = _parse_tilted(tmp_path)
    parsed["candela_multiplier"] = 2
    parsed["candela_values"] = [[value / 2 for value in row] for row in parsed["candela_values"]]
    centered = center_photometry(parsed)
    assert centered["max_candela"] == 1000  # 原始峰值 500 raw × 2 倍率


def test_center_photometry_rejects_empty_peak(tmp_path: Path):
    parsed = _parse_tilted(tmp_path)
    parsed["candela_values"] = [[0.0] * len(row) for row in parsed["candela_values"]]
    with pytest.raises(ValueError, match="峰值"):
        center_photometry(parsed)


def test_standard_report_model_pdf_and_validation(sample_path: Path, tmp_path: Path):
    parsed = IESParser.parse(sample_path)
    parsed["original_file_name"] = "source.ies"
    scaled = IESScaler.scale(parsed, 1000, 1200, "Model A", 30, "power_only")
    risk = evaluate_risk("power_only")
    data = build_report_data(parsed, scaled, risk, {
        "company_name": "Example Lighting", "voltage_v": 24,
        "current_a": 1.25, "power_factor": .95, "cct_k": 4000,
    })
    ies_path, pdf_path = tmp_path / "out.ies", tmp_path / "report.pdf"
    IESWriter.write(scaled, ies_path)
    generate_classic_pdf(data, pdf_path)
    assert len(__import__("pypdf").PdfReader(pdf_path).pages) == 13
    assert data["electrical"]["voltage_v"] == 24
    checks = validate_standard_report(data, ies_path, pdf_path)
    assert len(checks) == 22
    assert any(not item["ok"] and "积分" in item["label"] for item in checks)
    assert all(item["ok"] for item in checks if "积分" not in item["label"])
