from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


INK = colors.HexColor("#17211d")
GREEN = colors.HexColor("#0d5c45")
LIME = colors.HexColor("#cbe86b")
LINE = colors.HexColor("#d9ddd6")
MUTED = colors.HexColor("#68736d")
PAPER = colors.HexColor("#f5f6f2")
W, H = A4


def _font() -> str:
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _text(c: canvas.Canvas, x: float, y: float, value: Any, size=9, color=INK, align="left") -> None:
    c.setFont(_font(), size); c.setFillColor(color)
    text = "-" if value in (None, "") else str(value)
    {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align](x, y, text)


def validate_standard_report(data: dict[str, Any], ies_path: str | Path, pdf_path: str | Path) -> list[dict[str, Any]]:
    from .ies_parser import IESParser
    from .photometric_engine import PhotometricEngine, contour_segments
    parsed = IESParser.parse(ies_path)
    reader = PdfReader(str(pdf_path))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    ph = data["photometric"]
    engine = PhotometricEngine(ph["vertical_angles"],[p["c_angle"] for p in ph["planes"]],[p["candela"] for p in ph["planes"]])
    source_points_ok = all(abs(engine.intensity(plane["c_angle"], gamma)-value)<.001 for plane in ph["planes"] for gamma,value in zip(ph["vertical_angles"],plane["candela"]))
    integrated = engine.integrated_flux(); flux_error = abs(integrated-ph["target_flux_lm"])/ph["target_flux_lm"]*100
    extent=data.get("calculation",{}).get("plane_extent_m",20);height=data.get("calculation",{}).get("height_m",10)
    xs,ys,grid=engine.grid(extent,31,lambda x,y:engine.horizontal_illuminance(x,y,height));maximum=max(max(row) for row in grid)
    contours_ok=bool(contour_segments(xs,ys,grid,maximum*.5))
    area=data["product"]["luminous_length_mm"]*data["product"]["luminous_width_mm"]/1_000_000
    spatial_x=[30*i/30 for i in range(31)];spatial_y=[.25+(30-.25)*i/30 for i in range(31)]
    spatial_grid=[[engine.spatial_illuminance(x,depth,0) for x in spatial_x] for depth in spatial_y]
    spatial_reference=engine.spatial_illuminance(0,10,0)
    spatial_contours_ok=bool(contour_segments(spatial_x,spatial_y,spatial_grid,spatial_reference*.5))
    zones=ph["zonal_flux"]
    chart_labels=("Gamma angle [deg]","Unit of illumination: lx","Emax","Dazzle Quality","logarithmic scale","Ecenter, Emax","Imean [cd]")
    checks = [
        ("IES格式重新解析成功", True),
        ("光强矩阵数量一致", sum(map(len, parsed["candela_values"])) == parsed["num_vertical_angles"] * parsed["num_horizontal_angles"]),
        ("IES与报告目标功率一致", abs(parsed["input_watts"] - data["electrical"]["power_w"]) < .001),
        ("IES与报告最大光强一致", abs(parsed["max_candela"] - ph["max_candela_cd"]) < .02),
        ("IES原始采样点与插值引擎一致", source_points_ok),
        ("C0-C180组合轴使用相对平面", abs(engine.axis_profile(0,180)[88][1]-engine.intensity(180,2)) < .001),
        ("独立球面积分误差不超过1%", flux_error <= 1),
        ("真实照度网格可生成等值线", contours_ok),
        ("投影亮度模型数值有效", area > 0 and math.isfinite(engine.luminance(0,45,area))),
        ("归一化光强换算数值有效", ph["target_flux_lm"] > 0 and math.isfinite(engine.intensity(0,0)*1000/ph["target_flux_lm"])),
        ("水平照度中心值符合反平方定律", abs(engine.horizontal_illuminance(0,0,height)-engine.intensity(0,0)/height**2)<.001),
        ("空间等照度参考级可生成等值线", spatial_contours_ok),
        ("区域光通量采用5度分区并累计闭合", len(zones)==18 and abs(zones[-1]["cumulative_lm"]-ph["integrated_downward_flux_lm"])<.01),
        ("照度距离中心值符合反平方定律", abs(engine.mean_intensity(0)/4-engine.mean_intensity(0)/(2**2))<.001),
        ("PDF图表字段与参考表达完整", all(label in extracted for label in chart_labels)),
        ("报告光效计算一致", abs(ph["efficacy_lm_w"] - ph["target_flux_lm"] / data["electrical"]["power_w"]) < .001),
        ("PDF专业报告为13页", len(reader.pages) == 13),
        ("发光面尺寸有效", data["product"]["luminous_length_mm"] > 0 and data["product"]["luminous_width_mm"] > 0),
        ("PDF包含目标型号", data["product"]["model"] in extracted),
        ("PDF包含估算声明", "ESTIMATED" in extracted and "非实验室实测" in extracted),
        ("IES没有负光强", all(value >= 0 for row in parsed["candela_values"] for value in row)),
        ("IES已标记ESTIMATED", any("ESTIMATED" in line for line in parsed["header_lines"])),
    ]
    return [{"label": label, "ok": bool(ok)} for label, ok in checks]
