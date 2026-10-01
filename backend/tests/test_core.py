from pathlib import Path
import math

import pytest

from app.ies_parser import IESParseError, IESParser
from app.ies_scaler import IESScaler
from app.ies_writer import IESWriter, sanitize_file_stem
from app.photometry import build_photometry_summary
from app.report_generator import ReportGenerator
from app.report_model import build_report_data
from app.classic_report import REDUCED_PAGE_COUNT, generate_classic_pdf
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


def type_b_ies_text() -> str:
    """合成 Type B 光度文件：垂直/水平角均 -90~90，0° 峰值的高斯型配光（仿 SW3015 类投光灯）。"""
    vertical = list(range(-90, 91, 15))
    horizontal = [-90, -45, 0, 45, 90]
    lines = [
        "IESNA:LM-63-2002",
        "[TEST] Synthetic Type B fixture",
        "TILT=NONE",
        f"1 1900 1 {len(vertical)} {len(horizontal)} 2 2 0.1 0.2 0.3",
        "1 1 21",
        " ".join(str(value) for value in vertical),
        " ".join(str(value) for value in horizontal),
    ]
    for h in horizontal:
        factor = 0.7 + 0.3 * (1 - abs(h) / 90)
        lines.append(" ".join(f"{200 * factor * math.exp(-((v / 25) ** 2)):.3f}" for v in vertical))
    return "\n".join(lines) + "\n"


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


def test_parser_accepts_type_b_negative_angles(tmp_path: Path):
    path = tmp_path / "type-b.ies"
    path.write_text(type_b_ies_text(), encoding="utf-8")
    parsed = IESParser.parse(path)
    assert parsed["photometric_type"] == 2
    assert parsed["vertical_angles"][0] == -90
    assert parsed["vertical_angles"][-1] == 90
    assert parsed["horizontal_angles"] == [-90, -45, 0, 45, 90]
    summary = build_photometry_summary(parsed)
    assert summary["photometric_analysis_supported"] is False
    assert summary["vertical_range"] == [-90, 90]
    assert summary["horizontal_range"] == [-90, 90]


def test_absolute_photometry_estimates_flux_from_matrix(sample_path: Path, tmp_path: Path):
    content = sample_path.read_text(encoding="utf-8").replace("1 1000 1 3 2", "1 -1 1 3 2")
    path = tmp_path / "absolute.ies"
    path.write_text(content, encoding="utf-8")
    summary = build_photometry_summary(IESParser.parse(path))
    # 方位平均 [90, 180, 45] cd，γ=0/45/90°：2π × trapz(avg·sinγ) ≈ 739.1 lm
    assert summary["estimated_source_flux_lm"] == pytest.approx(739.1, abs=0.5)
    assert "积分估算" in summary["estimated_source_flux_note"]
    # 相对光度文件不产生该估算字段
    relative = build_photometry_summary(IESParser.parse(sample_path))
    assert "estimated_source_flux_lm" not in relative


def test_type_b_absolute_flux_integrates_cos_v(tmp_path: Path):
    lines = ["IESNA:LM-63-2002", "[TEST] const type b", "TILT=NONE",
             "1 -1 1 3 3 2 2 0.1 0.2 0.3", "1 1 10",
             "-90 0 90", "-90 0 90",
             "100 100 100", "100 100 100", "100 100 100"]
    path = tmp_path / "const-b.ies"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = build_photometry_summary(IESParser.parse(path))
    # trapz(cosV, ΔV=π/2 三点) = π/2；trapz(1, ΔH=π/2 三点) = π → 100 × π/2 × π ≈ 493.5 lm
    assert summary["estimated_source_flux_lm"] == pytest.approx(493.5, abs=0.5)


def test_parser_still_rejects_negative_angles_for_type_c(tmp_path: Path):
    content = type_b_ies_text().replace("5 2 2 0.1", "5 1 2 0.1")
    path = tmp_path / "type-c-negative.ies"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(IESParseError, match="垂直角必须位于 0 到 180 度之间"):
        IESParser.parse(path)


def test_type_b_beam_angle_and_symmetry_from_principal_plane(tmp_path: Path):
    path = tmp_path / "type-b.ies"
    path.write_text(type_b_ies_text(), encoding="utf-8")
    summary = build_photometry_summary(IESParser.parse(path))
    beams = summary["beam_angles_50"]
    assert len(beams) == 1
    assert beams[0]["label"] == "H0°垂直剖面"
    # 高斯合成文件（σ=25°，15° 网格）：FWHM 理论值 2√(2ln2)·σ ≈ 41.59°，线性插值后 42.87°
    assert beams[0]["beam_angle_50"] == pytest.approx(42.87, abs=0.05)
    assert beams[0]["field_angle_10"] == pytest.approx(80.77, abs=0.1)
    # ±h 平面完全一致 → 旋转对称
    assert summary["distribution_type"] == "rotational_symmetric"


def test_type_b_full_chain_generates_simplified_report(tmp_path: Path):
    path = tmp_path / "type-b.ies"
    path.write_text(type_b_ies_text(), encoding="utf-8")
    parsed = IESParser.parse(path)
    parsed["original_file_name"] = "type-b.ies"
    scaled = IESScaler.scale(parsed, 1900, 2100, "TypeB-21W", 21, "power_only")
    risk = evaluate_risk("power_only")
    data = build_report_data(parsed, scaled, risk, {})
    assert data["photometric"]["photometric_type"] == 2
    assert data["photometric"]["photometric_analysis_supported"] is False
    ies_path, pdf_path = tmp_path / "out.ies", tmp_path / "report.pdf"
    IESWriter.write(scaled, ies_path)
    generate_classic_pdf(data, pdf_path)
    assert len(__import__("pypdf").PdfReader(pdf_path).pages) == REDUCED_PAGE_COUNT
    checks = validate_standard_report(data, ies_path, pdf_path)
    assert all(item["ok"] for item in checks)
    assert any("非TypeC" in item["label"] for item in checks)
    # 缩放矩阵按光通量比生效（1900 → 2100，比例 1.105263…，保留 3 位小数）
    assert scaled["candela_values"][0][6] == round(parsed["candela_values"][0][6] * 2100 / 1900, 3)
    markdown_path = tmp_path / "report.md"
    ReportGenerator.generate(parsed, scaled, risk, markdown_path)
    assert "Type 2 光度坐标" in markdown_path.read_text(encoding="utf-8")


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
    factor = centered["centering"]["flux_compensation_factor"]
    assert summary["peak_direction"]["gamma_angle"] == 0
    assert summary["peak_direction"]["c_angle"] == 90  # 峰值所在平面保持原 C 角，仅曲线平移
    assert summary["peak_direction"]["intensity"] == pytest.approx(1500 * factor, rel=1e-3)
    assert centered["max_candela"] == pytest.approx(1500 * factor, rel=1e-3)
    assert factor > 1  # 平移丢弃峰值以下 γ 段后按光通量补偿放大
    assert centered["centering"]["original_peak_c_angle"] == 90
    assert centered["centering"]["original_peak_gamma_angle"] == 30
    assert len(centered["candela_values"]) == centered["num_horizontal_angles"] == 12


def test_center_photometry_shifts_each_plane_and_preserves_shape():
    # 两平面峰值分别在 γ45：平移后各自峰值落到 γ0、曲线形状保持（等比补偿后相邻值比例不变），
    # 超出 90° 填 0
    parsed = {
        "vertical_angles": [0.0, 45.0, 90.0],
        "horizontal_angles": [0.0, 90.0],
        "candela_values": [[50.0, 100.0, 10.0], [40.0, 80.0, 8.0]],
        "candela_multiplier": 1,
    }
    centered = center_photometry(parsed)
    factor = centered["centering"]["flux_compensation_factor"]
    assert centered["horizontal_angles"] == [0.0, 90.0]
    assert centered["candela_values"][0][0] == pytest.approx(100.0 * factor, rel=1e-3)
    assert centered["candela_values"][0][1] == pytest.approx(10.0 * factor, rel=1e-3)
    assert centered["candela_values"][0][2] == 0.0
    assert centered["candela_values"][1][0] == pytest.approx(80.0 * factor, rel=1e-3)
    assert centered["candela_values"][1][1] == pytest.approx(8.0 * factor, rel=1e-3)
    assert centered["centering"]["max_shift_degrees"] == 45
    assert centered["max_candela"] == pytest.approx(100.0 * factor, rel=1e-3)


def test_center_photometry_preserves_plane_beam_shape(tmp_path: Path):
    # 平移对中的核心承诺：各平面峰值落到 γ0、曲线形状（半宽 = 交叉角 − 峰值角）严格不变。
    parsed = _parse_tilted(tmp_path, c_peak=90.0, gamma_peak=25.0)
    before = build_photometry_summary(parsed)["planes"]
    after = build_photometry_summary(center_photometry(parsed))["planes"]
    for a, b in zip(before, after):
        assert b["peak_angle"] == 0
        h_a = a["crossing_angle"] - a["peak_angle"] if a["crossing_angle"] is not None else None
        h_b = b["crossing_angle"] - b["peak_angle"] if b["crossing_angle"] is not None else None
        assert (h_a is None) == (h_b is None)
        if h_a is not None:
            assert h_b == pytest.approx(h_a, abs=0.02)


def test_beam_angle_is_true_fwhm_for_tilted_distribution(tmp_path: Path):
    # 倾斜高斯（峰值 C90/γ25，σ=20°）：过峰 C90 平面的真实 FWHM =
    # 下降边(25+24.1) − 上升边(25−24.1) = 48.2°。旧公式只测下降边会把
    # 峰值偏移量算进宽度（虚高），此处断言修正后的两侧测量值。
    parsed = _parse_tilted(tmp_path, c_peak=90.0, gamma_peak=25.0)
    plane_c90 = next(p for p in build_photometry_summary(parsed)["planes"] if p["c_angle"] == 90)
    fwhm = plane_c90["crossing_angle"] - plane_c90["crossing_angle_asc"]
    assert fwhm == pytest.approx(48.2, abs=1.0)
    # 旧公式（只测下降边）会得到 ≈49.1 且不含上升边信息；交叉角上升边必须小于峰值角
    assert plane_c90["crossing_angle_asc"] < plane_c90["peak_angle"]


def test_center_photometry_preserves_flux_within_tolerance(tmp_path: Path):
    parsed = _parse_tilted(tmp_path, c_peak=90.0, gamma_peak=25.0)
    before = build_photometry_summary(parsed)["integrated_downward_flux_lm"]
    centered = center_photometry(parsed)
    after = build_photometry_summary(centered)["integrated_downward_flux_lm"]
    assert after == pytest.approx(before, rel=0.01)


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
    factor = centered["centering"]["flux_compensation_factor"]
    # 原始峰值 500 raw × 2 倍率 × 光通量补偿
    assert centered["max_candela"] == pytest.approx(1000 * factor, rel=1e-3)


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
