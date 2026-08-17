from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .ies_parser import IESParseError, IESParser
from .ies_scaler import IESScaler
from .ies_writer import IESWriter, sanitize_file_stem
from .photometry import build_photometry_summary
from .report_model import build_report_data
from .report_generator import ReportGenerator
from .risk_rules import evaluate_risk
from .source_report import analyze_source_pdf
from .classic_report import generate_classic_pdf
from .pdf_template import generate_from_source_template
from .standard_report import validate_standard_report

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_SOURCE_REPORT_SIZE = 20 * 1024 * 1024
FILE_RETENTION_SECONDS = 24 * 60 * 60
UPLOADS: dict[str, dict[str, Any]] = {}
SOURCE_REPORTS: dict[str, dict[str, Any]] = {}
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ies-tool")

app = FastAPI(title="内部IES快速换算工具", version="1.1.0")
# 部署时如需跨源访问，通过环境变量指定来源，例如 IES_ALLOWED_ORIGINS="https://ies.example.com"。
_allowed_origins = [origin.strip() for origin in os.getenv("IES_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])


class ReportSupplement(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    company_name: str | None = Field(default=None, max_length=120)
    company_website: str | None = Field(default=None, max_length=160)
    company_phone: str | None = Field(default=None, max_length=80)
    company_logo_data_url: str | None = Field(default=None, max_length=2_800_000)
    manufacturer: str | None = Field(default=None, max_length=120)
    report_number: str | None = Field(default=None, max_length=80)
    report_date: str | None = Field(default=None, max_length=20)
    product_description: str | None = Field(default=None, max_length=200)
    voltage_v: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    current_a: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    power_factor: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    cct_k: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    cri_ra: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    fixture_length_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    fixture_width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    fixture_height_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    calculation_height_m: float = Field(default=10, gt=0, le=100, allow_inf_nan=False)
    plane_extent_m: float = Field(default=20, gt=0, le=500, allow_inf_nan=False)
    notes: str | None = Field(default=None, max_length=500)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    uploaded_file_id: str = Field(min_length=1)
    source_luminous_flux_lm: float = Field(gt=0, allow_inf_nan=False)
    target_luminous_flux_lm: float = Field(gt=0, allow_inf_nan=False)
    target_model: str = Field(min_length=1, max_length=200)
    target_power_w: float = Field(gt=0, allow_inf_nan=False)
    target_luminous_length_mm: float = Field(gt=0, allow_inf_nan=False)
    target_luminous_width_mm: float = Field(gt=0, allow_inf_nan=False)
    source_report_id: str | None = Field(default=None, min_length=1)
    source_field_mapping: dict[str, "FieldBox"] | None = None
    report_supplement: ReportSupplement = Field(default_factory=ReportSupplement)
    change_type: Literal["power_only", "led_count_change", "length_change", "beam_angle_change", "lens_change", "optical_structure_change"]


class FieldBox(BaseModel):
    page: int = Field(default=1, ge=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


def cleanup_expired_files() -> None:
    cutoff = time.time() - FILE_RETENTION_SECONDS
    for directory in (UPLOAD_DIR, OUTPUT_DIR):
        for path in directory.iterdir():
            try:
                if path.is_file() and path.name != ".gitkeep" and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
    for records in (UPLOADS, SOURCE_REPORTS):
        for item_id, record in list(records.items()):
            if not record["path"].exists():
                records.pop(item_id, None)
    for key in list(_PAGE_RENDER_CACHE):
        if not Path(key[0]).is_file():
            _PAGE_RENDER_CACHE.pop(key, None)


def reserve_output_paths(stem: str) -> tuple[Path, Path, Path, Path]:
    candidate, counter = stem, 2
    while True:
        paths = (
            OUTPUT_DIR / f"{candidate}.ies",
            OUTPUT_DIR / f"{candidate}_内部说明.md",
            OUTPUT_DIR / f"{candidate}_报告预览.html",
            OUTPUT_DIR / f"{candidate}_方案光度报告.pdf",
        )
        reserved: list[Path] = []
        try:
            for path in paths:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd);reserved.append(path)
            return paths
        except FileExistsError:
            for path in reserved:path.unlink(missing_ok=True)
            candidate=f"{stem}_{counter}";counter+=1
        except OSError:
            for path in reserved:path.unlink(missing_ok=True)
            raise


def _reserve_extra_path(stem: str) -> Path:
    candidate, counter = f"{stem}_原版式报告.pdf", 2
    while True:
        path = OUTPUT_DIR / candidate
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return path
        except FileExistsError:
            candidate = f"{stem}_原版式报告_{counter}.pdf"
            counter += 1


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first.get("loc", [])[1:])
    return JSONResponse(status_code=422, content={"error": f"参数 {location}：{first.get('msg', '请求参数无效')}"})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/source-report")
async def upload_source_report(file: UploadFile = File(...)) -> dict[str, Any]:
    cleanup_expired_files();original_name = Path(file.filename or "").name
    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="原始光度测试文件必须是PDF。")
    report_id=uuid.uuid4().hex;destination=UPLOAD_DIR/f"source-report-{report_id}.pdf";size=0;header=b""
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024*1024):
                if not header:header=chunk[:5]
                size+=len(chunk)
                if size>MAX_SOURCE_REPORT_SIZE:raise HTTPException(status_code=413,detail="原始PDF不能超过20MB。")
                output.write(chunk)
        if header!=b"%PDF-":raise HTTPException(status_code=400,detail="文件内容不是有效的PDF。")
    except HTTPException:
        destination.unlink(missing_ok=True);raise
    finally:
        await file.close()
    try:
        analysis = analyze_source_pdf(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.warning("源PDF解析失败: %s", original_name, exc_info=True)
        raise HTTPException(status_code=400, detail="无法解析该 PDF，请确认文件未加密且可以正常打开。") from exc
    SOURCE_REPORTS[report_id]={"path":destination,"original_name":original_name,"analysis":analysis}
    return {"source_report_id":report_id,"file_name":original_name,"preview_url":f"/api/source-report/{report_id}","analysis":analysis}


@app.get("/api/source-report/{report_id}")
def view_source_report(report_id: str) -> FileResponse:
    record=SOURCE_REPORTS.get(report_id)
    if record is None or not record["path"].is_file():raise HTTPException(status_code=404,detail="原始光度测试PDF不存在或已过期。")
    return FileResponse(record["path"],media_type="application/pdf",headers={"Content-Disposition":"inline"})


_PAGE_RENDER_CACHE: dict[tuple[str, int], bytes] = {}
_PAGE_RENDER_CACHE_LIMIT = 32


def _render_source_page_png(path: Path, page_number: int) -> bytes:
    key = (str(path), page_number)
    cached = _PAGE_RENDER_CACHE.get(key)
    if cached is not None:
        return cached
    import pdfplumber
    from io import BytesIO
    with pdfplumber.open(path) as document:
        image=document.pages[page_number-1].to_image(resolution=110).original
        stream=BytesIO();image.save(stream,format="PNG")
    payload=stream.getvalue()
    if len(_PAGE_RENDER_CACHE) >= _PAGE_RENDER_CACHE_LIMIT:
        _PAGE_RENDER_CACHE.clear()
    _PAGE_RENDER_CACHE[key]=payload
    return payload


@app.get("/api/source-report/{report_id}/page/{page_number}.png")
def render_source_report_page(report_id: str, page_number: int) -> Response:
    record=SOURCE_REPORTS.get(report_id)
    if record is None or not record["path"].is_file():raise HTTPException(status_code=404,detail="原始光度测试PDF不存在或已过期。")
    if page_number < 1 or page_number > record["analysis"]["page_count"]:raise HTTPException(status_code=404,detail="PDF页面不存在。")
    return Response(content=_render_source_page_png(record["path"], page_number),media_type="image/png",headers={"Cache-Control":"private, max-age=300"})


@app.post("/api/upload")
async def upload_ies(file: UploadFile = File(...)) -> dict[str, Any]:
    cleanup_expired_files();original_name=Path(file.filename or "").name
    if not original_name.lower().endswith(".ies"):raise HTTPException(status_code=400,detail="文件格式必须是.ies。")
    file_id=uuid.uuid4().hex;destination=UPLOAD_DIR/f"{file_id}.ies";size=0
    try:
        with destination.open("wb") as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_UPLOAD_SIZE:raise HTTPException(status_code=413,detail="IES文件不能超过10MB。")
                output.write(chunk)
        parsed=IESParser.parse(destination);parsed["original_file_name"]=original_name
    except (IESParseError,ValueError) as exc:
        destination.unlink(missing_ok=True);logger.info("IES解析被拒绝: %s - %s", original_name, exc)
        raise HTTPException(status_code=400,detail=str(exc)) from exc
    except HTTPException:
        destination.unlink(missing_ok=True);raise
    except OSError as exc:
        destination.unlink(missing_ok=True);raise HTTPException(status_code=500,detail="上传文件保存失败，请检查磁盘空间和目录权限。") from exc
    finally:
        await file.close()
    UPLOADS[file_id]={"path":destination,"parsed":parsed}
    fields=["ies_version","tilt_type","input_watts","number_of_lamps","lumens_per_lamp","candela_multiplier","num_vertical_angles","num_horizontal_angles","max_candela","is_absolute_photometry","supports_auto_conversion","suggested_source_luminous_flux_lm","photometric_type","units_type","width","length","height","ballast_factor","ballast_lamp_photometric_factor","keywords"]
    return {"uploaded_file_id":file_id,"file_name":original_name,"parsed_info":{key:parsed[key] for key in fields},"photometry":build_photometry_summary(parsed)}


@app.post("/api/generate")
def generate_ies(payload: GenerateRequest) -> dict[str, Any]:
    cleanup_expired_files();record=UPLOADS.get(payload.uploaded_file_id)
    if record is None:raise HTTPException(status_code=404,detail="上传记录不存在或服务已重启，请重新上传IES文件。")
    source_report=SOURCE_REPORTS.get(payload.source_report_id) if payload.source_report_id else None
    if payload.source_report_id and source_report is None:raise HTTPException(status_code=404,detail="原始光度测试PDF不存在或已过期，请重新上传。")
    try:risk=evaluate_risk(payload.change_type)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    if not risk["allow_generate"]:return {**risk}
    try:scaled=IESScaler.scale(record["parsed"],**payload.model_dump(exclude={"uploaded_file_id","source_report_id","source_field_mapping","report_supplement"}))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    stem=sanitize_file_stem(payload.target_model)
    try:ies_path,md_path,html_path,pdf_path=reserve_output_paths(stem)
    except OSError as exc:raise HTTPException(status_code=500,detail="无法创建输出文件，请检查磁盘空间和目录权限。") from exc
    temp_paths=(OUTPUT_DIR/f".{uuid.uuid4().hex}.ies.tmp",OUTPUT_DIR/f".{uuid.uuid4().hex}.md.tmp",OUTPUT_DIR/f".{uuid.uuid4().hex}.html.tmp",OUTPUT_DIR/f".{uuid.uuid4().hex}.pdf.tmp")
    try:
        IESWriter.write(scaled,temp_paths[0]);ReportGenerator.generate_all(record["parsed"],scaled,risk,temp_paths[1],temp_paths[2],temp_paths[3],source_report)
        report_data=build_report_data(record["parsed"],scaled,risk,payload.report_supplement.model_dump())
        generate_classic_pdf(report_data,temp_paths[3])
        for source,target in zip(temp_paths,(ies_path,md_path,html_path,pdf_path)):os.replace(source,target)
    except Exception as exc:
        for path in (*temp_paths,ies_path,md_path,html_path,pdf_path):path.unlink(missing_ok=True)
        logger.exception("生成失败: upload=%s model=%s", payload.uploaded_file_id, payload.target_model)
        raise HTTPException(status_code=500,detail="生成报告或IES文件失败，请检查依赖与目录权限。") from exc
    # 可选：原版式报告叠加。仅当源 PDF 被识别为已知版式或用户完成人工标定才生成；
    # 叠加失败不影响已生成的标准报告。
    template_path: Path | None = None
    template_applied = False
    if source_report is not None:
        analysis=source_report.get("analysis", {})
        automatic=analysis.get("template", {}).get("id") == "huipu_cpm1800b_16p"
        if automatic or payload.source_field_mapping:
            template_path=_reserve_extra_path(stem)
            template_temp=OUTPUT_DIR/f".{uuid.uuid4().hex}.template.tmp"
            field_mapping={key: box.model_dump() for key, box in payload.source_field_mapping.items()} if payload.source_field_mapping else None
            try:
                template_applied=generate_from_source_template(source_report,scaled,template_temp,field_mapping)
                if template_applied:
                    os.replace(template_temp,template_path)
                else:
                    template_path.unlink(missing_ok=True);template_path=None
            except Exception:
                template_temp.unlink(missing_ok=True)
                if template_path is not None:
                    template_path.unlink(missing_ok=True);template_path=None
                logger.warning("原版式报告叠加失败，仅输出标准报告", exc_info=True)
    validation=validate_standard_report(report_data,ies_path,pdf_path)
    return {**risk,"scale_factor":scaled["scale_factor"],"pdf_template_applied":template_applied,"report_schema_version":report_data["schema_version"],"ies_file":ies_path.name,"report_file":md_path.name,"ies_download_url":f"/api/download/{ies_path.name}","report_download_url":f"/api/download/{md_path.name}","html_report_file":html_path.name,"pdf_report_file":pdf_path.name,"html_report_url":f"/api/view/{html_path.name}","pdf_report_url":f"/api/view/{pdf_path.name}","html_report_download_url":f"/api/download/{html_path.name}","pdf_report_download_url":f"/api/download/{pdf_path.name}","markdown_report_url":f"/api/download/{md_path.name}","template_pdf_file":template_path.name if template_path else None,"template_pdf_url":f"/api/view/{template_path.name}" if template_path else None,"template_pdf_download_url":f"/api/download/{template_path.name}" if template_path else None,"source_report":{"file_name":source_report["original_name"],"preview_url":f"/api/source-report/{payload.source_report_id}","analysis":source_report["analysis"]} if source_report else None,"ies_preview":{"target_model":scaled["target_model"],"target_power_w":scaled["target_power_w"],"target_luminous_flux_lm":scaled["target_luminous_flux_lm"],"max_candela":scaled["max_candela"],"length":scaled["length"],"width":scaled["width"],"photometry":build_photometry_summary(scaled),"validation":validation,"validation_passed":all(item["ok"] for item in validation),"text":"\n".join(ies_path.read_text(encoding="utf-8").splitlines()[:120])}}


def _safe_output(file_name: str) -> Path:
    if file_name!=Path(file_name).name or file_name in {".",".."}:raise HTTPException(status_code=400,detail="非法文件名。")
    path=(OUTPUT_DIR/file_name).resolve()
    if path.parent!=OUTPUT_DIR.resolve():raise HTTPException(status_code=400,detail="非法文件路径。")
    if not path.is_file():raise HTTPException(status_code=404,detail="文件不存在。")
    return path


@app.get("/api/view/{file_name}")
def view_output(file_name: str) -> FileResponse:
    path=_safe_output(file_name)
    if path.suffix.lower() not in {".html",".pdf"}:raise HTTPException(status_code=400,detail="不支持预览该文件。")
    media="text/html; charset=utf-8" if path.suffix.lower()==".html" else "application/pdf"
    return FileResponse(path,media_type=media,headers={"Content-Disposition":"inline"})


@app.get("/api/download/{file_name}")
def download(file_name: str) -> FileResponse:
    path=_safe_output(file_name)
    return FileResponse(path,filename=path.name,media_type="application/octet-stream")


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,content={"error":str(exc.detail)})
