from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


FIELD_RULES: dict[str, tuple[str, list[str]]] = {
    "model": ("灯具型号", [r"(?:型号|Model|Luminaire)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_./ -]{2,50})"]),
    "power_w": ("输入功率", [r"(?:输入功率|功率|Power|Input Power)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*W\b"]),
    "luminous_flux_lm": ("总光通量", [r"(?:总光通量|光通量|Luminous Flux|Total Flux)\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)\s*lm\b"]),
    "efficacy_lm_w": ("光效", [r"(?:光效|Luminous Efficacy|Efficacy)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*lm\s*/\s*W"]),
    "max_candela_cd": ("最大光强", [r"(?:最大光强|Max(?:imum)?\s*(?:Intensity|Candela))\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)\s*cd\b"]),
    "cct_k": ("相关色温", [r"(?:相关色温|色温|CCT)\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)\s*K\b"]),
    "cri_ra": ("显色指数", [r"(?:显色指数|CRI|Ra)\s*[:：]?\s*(?:Ra\s*)?([0-9]+(?:\.[0-9]+)?)"]),
    "power_factor": ("功率因数", [r"(?:功率因数|Power Factor|PF)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)"]),
    "voltage_v": ("输入电压", [r"(?:输入电压|电压|Voltage)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*V\b"]),
    "current_a": ("输入电流", [r"(?:输入电流|电流|Current)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*A\b"]),
}


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def analyze_source_pdf(path: str | Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n".join(page_texts)
    fields: dict[str, dict[str, Any]] = {}
    for key, (label, patterns) in FIELD_RULES.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                fields[key] = {"label": label, "value": _number(raw) if key != "model" else raw, "matched_text": match.group(0).strip()[:120]}
                break
    sizes = [{"width_pt": round(float(page.mediabox.width), 2), "height_pt": round(float(page.mediabox.height), 2)} for page in reader.pages]
    text_char_count = sum(len(item) for item in page_texts)
    is_huipu = len(reader.pages) == 16 and ("Huipu CPM-1800B" in text or "www.hpyiqi.com" in text)
    template = {"id":"huipu_cpm1800b_16p","name":"惠谱 CPM-1800B 16页报告","mode":"automatic"} if is_huipu else {"id":None,"name":"未知报告版式","mode":"manual"}
    replacement_plan = [
        {"key":"model","label":"灯具型号","status":"automatic" if is_huipu else "manual"},
        {"key":"power_w","label":"输入功率","status":"automatic" if is_huipu else "manual"},
        {"key":"luminous_flux_lm","label":"总光通量","status":"automatic" if is_huipu else "manual"},
        {"key":"efficacy_lm_w","label":"光效","status":"automatic" if is_huipu else "manual"},
        {"key":"max_candela_cd","label":"最大光强","status":"automatic" if is_huipu else "manual"},
    ]
    return {
        "page_count": len(reader.pages),
        "page_sizes": sizes,
        "searchable": text_char_count >= 20,
        "text_char_count": text_char_count,
        "fields": fields,
        "recognized_count": len(fields),
        "template": template,
        "replacement_plan": replacement_plan,
        "warnings": [] if text_char_count >= 20 else ["该 PDF 可能是扫描件，第一版暂不支持自动 OCR，请人工核对或上传可搜索文字版 PDF。"],
    }
