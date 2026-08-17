from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Any

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


HUIPU_PAGE1_FIELDS = {
    # These boxes start at the original value, not at the preceding label or colon.
    # Their vertical coordinates match the Verdana text baseline in the source PDF.
    "model": (101.72, 222.70, 285, 234.38),
    "power_w": (367.04, 237.85, 397.2, 247.82),
    "source_flux": (382.06, 264.73, 425.0, 274.70),
    "max_candela": (370.66, 326.29, 414.0, 336.26),
    "luminous_flux": (113.14, 339.61, 163.0, 349.58),
    "efficacy": (129.63, 366.49, 160.0, 376.46),
    "center_candela": (370.66, 379.93, 414.0, 389.90),
    # Target values can grow from three to four integer digits.  Include the unit
    # here so it can be moved as one text run instead of being overwritten.
    "effective_flux": (382.06, 393.25, 435.0, 403.22),
    "erp_flux": (445.78, 406.69, 489.0, 416.66),
}


def _draw_replacement(
    overlay: canvas.Canvas,
    page_height: float,
    box: tuple[float, float, float, float],
    text: str,
    size: float = 9.96,
    *,
    exact_baseline: bool = False,
) -> None:
    x0, top, x1, bottom = box
    y0 = page_height - bottom
    overlay.setFillColorRGB(1, 1, 1)
    overlay.rect(x0 - 0.35, y0 - 0.45, x1 - x0 + 0.7, bottom - top + 0.9, stroke=0, fill=1)
    overlay.setFillColorRGB(0, 0, 0)
    font = "Verdana" if text.isascii() and "Verdana" in pdfmetrics.getRegisteredFontNames() else "STSong-Light"
    overlay.setFont(font, size)
    # pdfplumber's `bottom` is the source glyph baseline for this report.  The old
    # implementation added 2.2 pt here, which made every replacement visibly float.
    baseline = page_height - bottom if exact_baseline else page_height - bottom + 0.4
    overlay.drawString(x0, baseline, text)


def _scaled_text(raw: str, factor: float) -> str:
    decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
    value = float(raw) * factor
    return f"{value:.{decimals}f}" if decimals else str(round(value))


def generate_from_source_template(source_report: dict[str, Any], scaled: dict[str, Any], output_path: str | Path, manual_mapping: dict[str, Any] | None = None) -> bool:
    analysis = source_report.get("analysis", {})
    automatic = analysis.get("template", {}).get("id") == "huipu_cpm1800b_16p"
    if not automatic and not manual_mapping:
        return False
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    verdana_path = Path(r"C:\Windows\Fonts\verdana.ttf")
    if verdana_path.exists() and "Verdana" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Verdana", str(verdana_path)))
    reader = PdfReader(str(source_report["path"]))
    writer = PdfWriter()
    scale = float(scaled["scale_factor"])
    with pdfplumber.open(str(source_report["path"])) as document:
        first_page = document.pages[0]
        page_words = [page.extract_words() for page in document.pages]
        def original_number(key: str, fallback: float) -> float:
            text = first_page.within_bbox(HUIPU_PAGE1_FIELDS[key]).extract_text() or ""
            match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
            return float(match.group()) if match else fallback
        originals = {
            "report_flux": original_number("luminous_flux", scaled["target_luminous_flux_lm"]/scale),
            "report_max": original_number("max_candela", scaled["max_candela"]/scale),
            "center_candela": original_number("center_candela", scaled["max_candela"]/scale),
            "effective_flux": original_number("effective_flux", scaled["target_luminous_flux_lm"]/scale),
            "erp_flux": original_number("erp_flux", scaled["target_luminous_flux_lm"]/scale),
        }
    flux_scale = float(scaled["target_luminous_flux_lm"]) / originals["report_flux"]
    candela_scale = float(scaled["max_candela"]) / originals["report_max"]
    values = {
        "model": str(scaled["target_model"]),
        "power_w": f"{scaled['target_power_w']:.2f}",
        "source_flux": f"{scaled['target_luminous_flux_lm']:.2f}",
        "max_candela": f"{scaled['max_candela']:.2f}",
        "luminous_flux": f"{scaled['target_luminous_flux_lm']:.3f}",
        "efficacy": f"{scaled['target_luminous_flux_lm']/scaled['target_power_w']:.2f}",
        "center_candela": f"{originals['center_candela']*candela_scale:.2f}",
        "effective_flux": f"{originals['effective_flux']*flux_scale:.2f} lm",
        "erp_flux": f"{originals['erp_flux']*flux_scale:.2f}",
    }
    note = "本报告数据基于原始光度测试结果换算生成，目标型号未重新进行光度实测。"
    for page_index, page in enumerate(reader.pages):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        stream = BytesIO(); overlay = canvas.Canvas(stream, pagesize=(width, height))
        if automatic and page_index == 0:
            for key, box in HUIPU_PAGE1_FIELDS.items():
                _draw_replacement(overlay, height, box, values[key], exact_baseline=True)
        elif manual_mapping:
            manual_values = {
                "model": values["model"],
                "power_w": f'{values["power_w"]} W',
                "luminous_flux_lm": f'{values["luminous_flux"]} lm',
                "efficacy_lm_w": f'{values["efficacy"]} lm/W',
                "max_candela_cd": f'{values["max_candela"]} cd',
            }
            for key, mapping in manual_mapping.items():
                if int(mapping.get("page", 1)) != page_index + 1 or key not in manual_values:
                    continue
                box = (float(mapping["x"])*width,float(mapping["y"])*height,(float(mapping["x"])+float(mapping["w"]))*width,(float(mapping["y"])+float(mapping["h"]))*height)
                _draw_replacement(overlay, height, box, manual_values[key])
        if automatic:
            for word in page_words[page_index]:
                raw = word["text"].strip().replace(",", "")
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
                    continue
                numeric = float(raw)
                factor = None
                if page_index in (0, 1) and 430 < word["top"] < 735 and numeric > 180:
                    factor = candela_scale
                elif page_index == 3 and abs(numeric - originals["report_flux"]) < max(1, originals["report_flux"]*.002):
                    factor = flux_scale
                elif 10 <= page_index <= 15 and 145 < word["top"] < 730 and word["x0"] > 100:
                    factor = candela_scale
                if factor is not None:
                    _draw_replacement(overlay,height,(word["x0"]-1,word["top"]-1,word["x1"]+2,word["bottom"]+1),_scaled_text(raw,factor),max(6,min(9.5,word["height"]*.82)))
        overlay.setFillColorRGB(.42, .46, .44); overlay.setFont("STSong-Light", 6.2)
        overlay.drawString(48, 13, note)
        overlay.save(); stream.seek(0)
        page.merge_page(PdfReader(stream).pages[0]); writer.add_page(page)
    target = Path(output_path)
    temporary = target.with_name(f".{target.name}.template")
    with temporary.open("wb") as file:
        writer.write(file)
    temporary.replace(target)
    return True
