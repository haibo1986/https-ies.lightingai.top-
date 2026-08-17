from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .photometry import build_photometry_summary


CHANGE_LABELS = {
    "power_only": "仅功率或LED电流变化",
    "led_count_change": "LED数量或密度变化",
    "length_change": "灯具长度或模组变化",
    "beam_angle_change": "光束角变化",
    "lens_change": "透镜变化",
    "optical_structure_change": "光学结构变化",
}
DISCLAIMER = "本报告由原始实测IES按工程假设估算生成，并非实验室实测报告，不可用于认证、验收或第三方检测结论。"


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def _context(parsed: dict[str, Any], scaled: dict[str, Any], risk: dict[str, Any], source_report: dict[str, Any] | None) -> dict[str, Any]:
    photometry = build_photometry_summary(scaled)
    beams = photometry["beam_angles_50"]
    return {
        "parsed": parsed,
        "scaled": scaled,
        "risk": risk,
        "photometry": photometry,
        "beams": beams,
        "source_report": source_report,
        "source_analysis": source_report.get("analysis", {}) if source_report else {},
        "source_efficacy": scaled["source_luminous_flux_lm"] / parsed["input_watts"] if parsed["input_watts"] else None,
        "target_efficacy": scaled["target_luminous_flux_lm"] / scaled["target_power_w"] if scaled["target_power_w"] else None,
    }


def _source_value(ctx: dict[str, Any], key: str, fallback: Any) -> Any:
    field = ctx["source_analysis"].get("fields", {}).get(key)
    return field["value"] if field else fallback


def _principal_planes(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    planes = ctx["photometry"]["planes"]
    if not planes:
        return []
    picks = [min(planes, key=lambda plane: abs(plane["c_angle"] - target)) for target in (0, 90)]
    return [plane for index, plane in enumerate(picks) if plane["c_angle"] not in {item["c_angle"] for item in picks[:index]}]


def _svg_chart(ctx: dict[str, Any]) -> str:
    planes = _principal_planes(ctx)
    if not planes:
        return ""
    angles = ctx["photometry"]["vertical_angles"]
    maximum = max(max(plane["candela"]) for plane in planes) or 1
    cx, cy, radius = 230, 215, 170
    colors_ = ["#0d5c45", "#c07823"]
    paths = []
    for index, plane in enumerate(planes):
        points = []
        for mirror in (-1, 1):
            iterable = list(zip(angles, plane["candela"]))
            if mirror == -1:
                iterable.reverse()
            for angle, intensity in iterable:
                import math
                rad = math.radians(angle * mirror)
                r = intensity / maximum * radius
                points.append((cx + r * math.sin(rad), cy - r * math.cos(rad)))
        d = " ".join(("M" if point_index == 0 else "L") + f"{x:.1f},{y:.1f}" for point_index, (x, y) in enumerate(points))
        paths.append(f'<path d="{d}" fill="none" stroke="{colors_[index]}" stroke-width="4" stroke-linecap="round"/>')
    rings = "".join(f'<circle cx="{cx}" cy="{cy}" r="{radius*ratio}" fill="none" stroke="#d4dad5"/>' for ratio in (.25, .5, .75, 1))
    return f'<svg viewBox="0 0 460 430" role="img" aria-label="主要C平面光强分布曲线">{rings}<line x1="{cx}" y1="35" x2="{cx}" y2="395" stroke="#bcc6bf" stroke-dasharray="4 5"/><line x1="50" y1="{cy}" x2="410" y2="{cy}" stroke="#bcc6bf" stroke-dasharray="4 5"/>{"".join(paths)}</svg>'


def _markdown(ctx: dict[str, Any]) -> str:
    p, s, r = ctx["parsed"], ctx["scaled"], ctx["risk"]
    source_pdf = ctx["source_report"]["original_name"] if ctx["source_report"] else "未提供"
    beam_lines = "\n".join(f"- {beam['label']}：50%光束角 {_fmt(beam['beam_angle_50'])}°；10%光强角 {_fmt(beam['field_angle_10'])}°" for beam in ctx["beams"]) or "- 无法计算"
    return f"""# 估算光度模拟报告

> **ESTIMATED · 非实验室实测**  
> {DISCLAIMER}

## 1. 来源与溯源

- 原始IES：{p['original_file_name']}
- 原始光度测试PDF：{source_pdf}
- 目标型号：{s['target_model']}
- 变更类型：{CHANGE_LABELS[s['change_type']]}

## 2. 原始与目标参数

| 参数 | 原始实测/来源值 | 目标估算值 |
|---|---:|---:|
| 输入功率 | {_fmt(_source_value(ctx, 'power_w', p['input_watts']))} W | {_fmt(s['target_power_w'])} W |
| 光通量 | {_fmt(_source_value(ctx, 'luminous_flux_lm', s['source_luminous_flux_lm']))} lm | {_fmt(s['target_luminous_flux_lm'])} lm |
| 光效 | {_fmt(_source_value(ctx, 'efficacy_lm_w', ctx['source_efficacy']))} lm/W | {_fmt(ctx['target_efficacy'])} lm/W |
| 最大光强 | {_fmt(_source_value(ctx, 'max_candela_cd', p['max_candela']))} cd | {_fmt(s['max_candela'])} cd |
| 发光口长度 | {_fmt(p['length'])} | {_fmt(s['length'])} |
| 发光口宽度 | {_fmt(p['width'])} | {_fmt(s['width'])} |

## 3. 配光分析

{beam_lines}

归一化配光形状沿用原始实测IES，仅按光通量比例缩放绝对光强。

## 4. 换算依据

- 光强缩放比例：{s['scale_factor']:.4f}
- 风险等级：{r['risk_level']}
- 风险说明：{r['risk_message']}

## 5. 使用声明

{DISCLAIMER}
"""


def _html(ctx: dict[str, Any]) -> str:
    p, s = ctx["parsed"], ctx["scaled"]
    rows = [("输入功率",f"{_fmt(s['target_power_w'])} W"),("总光通量",f"{_fmt(s['target_luminous_flux_lm'])} lm"),("光效",f"{_fmt(ctx['target_efficacy'])} lm/W"),("最大光强",f"{_fmt(s['max_candela'])} cd"),("发光口尺寸",f"{_fmt(s['length'])} × {_fmt(s['width'])}")]
    for key, unit in (("cct_k","K"),("cri_ra","Ra"),("power_factor",""),("voltage_v","V"),("current_a","A")):
        field=ctx["source_analysis"].get("fields",{}).get(key)
        if field: rows.append((field["label"],f"{_fmt(field['value'])} {unit}".strip()))
    table_rows = "".join(f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>" for label, value in rows)
    beams = "".join(f"<article><b>{escape(beam['label'])}</b><span>50% {_fmt(beam['beam_angle_50'])}°</span><span>10% {_fmt(beam['field_angle_10'])}°</span></article>" for beam in ctx["beams"])
    note="本报告数据基于原始光度测试结果换算生成，目标型号未重新进行光度实测。"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{escape(s['target_model'])} 光度报告</title><style>body{{margin:0;background:#eef0eb;color:#17211d;font-family:'Microsoft YaHei',sans-serif}}main{{max-width:900px;margin:30px auto;background:white;padding:42px;box-shadow:0 8px 30px #17211d14}}header{{border-bottom:4px solid #0d5c45;padding-bottom:22px}}.mark{{font:700 11px monospace;letter-spacing:2px;color:#0d5c45}}h1{{margin:8px 0;font-size:32px}}h2{{font-size:20px;margin-top:34px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;border:1px solid #d9ddd6;text-align:left}}th{{width:40%;background:#f4f6f2}}.beams{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.beams article{{border-top:3px solid #0d5c45;background:#f5f7f3;padding:14px;display:flex;justify-content:space-between;gap:10px}}.chart{{max-width:560px;margin:auto}}footer{{margin-top:36px;border-top:1px solid #d9ddd6;padding-top:12px;color:#66716b;font-size:10px;line-height:1.7}}@media(max-width:700px){{main{{margin:0;padding:22px}}.beams{{grid-template-columns:1fr}}}}</style></head><body><main><header><div class="mark">PHOTOMETRIC DATA REPORT</div><h1>光度数据报告</h1><p>产品型号：<b>{escape(s['target_model'])}</b></p></header><h2>产品光度参数</h2><table><tbody>{table_rows}</tbody></table><h2>光强分布曲线</h2><div class="chart">{_svg_chart(ctx)}</div><div class="beams">{beams}</div><footer>{escape(note)}</footer></main></body></html>"""


class ReportGenerator:
    @staticmethod
    def generate_all(parsed_data: dict[str, Any], scaled_data: dict[str, Any], risk_result: dict[str, Any], markdown_path: str | Path, html_path: str | Path, pdf_path: str | Path, source_report: dict[str, Any] | None = None) -> dict[str, str]:
        # pdf_path 仅保留以兼容调用签名；专业 PDF 由 classic_report.generate_classic_pdf 单独生成。
        paths = {"markdown": Path(markdown_path), "html": Path(html_path)}
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        ctx = _context(parsed_data, scaled_data, risk_result, source_report)
        paths["markdown"].write_text(_markdown(ctx), encoding="utf-8")
        paths["html"].write_text(_html(ctx), encoding="utf-8")
        return {key: str(path) for key, path in paths.items()}

    @staticmethod
    def generate(parsed_data: dict[str, Any], scaled_data: dict[str, Any], risk_result: dict[str, Any], output_path: str | Path) -> str:
        path = Path(output_path);ctx = _context(parsed_data, scaled_data, risk_result, None);path.write_text(_markdown(ctx), encoding="utf-8");return str(path)
