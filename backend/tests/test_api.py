from pathlib import Path
from io import BytesIO
import os
import time
import uuid

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app import main
from app.main import OUTPUT_DIR, SOURCE_REPORTS, UPLOADS, app
from app.ies_parser import IESParser
from app.photometry import build_photometry_summary
from test_core import tilted_ies_text


client = TestClient(app)


def upload_sample(sample_path: Path):
    with sample_path.open("rb") as file:
        return client.post("/api/upload", files={"file": ("sample.ies", file, "application/octet-stream")})


def cleanup_result(result: dict):
    for key in ("ies_file", "report_file", "html_report_file", "pdf_report_file", "template_pdf_file"):
        if result.get(key):
            (OUTPUT_DIR / result[key]).unlink(missing_ok=True)


def source_pdf_bytes() -> bytes:
    stream = BytesIO()
    document = canvas.Canvas(stream)
    document.drawString(72, 760, "Model: LAB-24W")
    document.drawString(72, 740, "Input Power: 24 W")
    document.drawString(72, 720, "Luminous Flux: 1000 lm")
    document.drawString(72, 700, "Luminous Efficacy: 41.67 lm/W")
    document.drawString(72, 680, "Maximum Intensity: 200 cd")
    document.save()
    return stream.getvalue()


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_generate_and_download(sample_path: Path):
    upload = upload_sample(sample_path)
    assert upload.status_code == 200
    body = upload.json()
    assert body["parsed_info"]["num_vertical_angles"] == 3
    assert body["photometry"]["vertical_angles"] == [0, 45, 90]
    assert body["photometry"]["beam_angles_50"][0]["beam_angle_50"] == 150
    assert body["parsed_info"]["photometric_type"] == 1
    assert body["parsed_info"]["number_of_lamps"] == 1
    response = client.post("/api/generate", json={
        "uploaded_file_id": body["uploaded_file_id"], "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1500, "target_model": "Model/Test",
        "target_power_w": 36, "target_luminous_length_mm": 300, "target_luminous_width_mm": 50, "change_type": "power_only",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["scale_factor"] == 1.5
    assert client.get(result["ies_download_url"]).status_code == 200
    assert client.get(result["report_download_url"]).status_code == 200
    assert client.get(result["html_report_url"]).status_code == 200
    assert client.get(result["pdf_report_url"]).content.startswith(b"%PDF-")
    assert result["ies_preview"]["validation"]
    cleanup_result(result)


def test_source_pdf_is_preserved_and_linked_to_estimated_report(sample_path: Path):
    for stale in OUTPUT_DIR.glob("Linked_report*"):
        stale.unlink(missing_ok=True)
    source_bytes = source_pdf_bytes()
    source = client.post("/api/source-report", files={"file": ("lab-source.pdf", source_bytes, "application/pdf")})
    assert source.status_code == 200
    source_info = source.json()
    assert client.get(source_info["preview_url"]).content == source_bytes
    assert source_info["analysis"]["searchable"] is True
    assert source_info["analysis"]["fields"]["power_w"]["value"] == 24
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    result = client.post("/api/generate", json={
        "uploaded_file_id": uploaded_id, "source_report_id": source_info["source_report_id"],
        "source_luminous_flux_lm": 1000, "target_luminous_flux_lm": 1200,
        "target_model": "Linked report", "target_power_w": 30, "target_luminous_length_mm": 300, "target_luminous_width_mm": 50, "change_type": "power_only",
        "source_field_mapping": {
            "model":{"page":1,"x":.1,"y":.1,"w":.2,"h":.03},
            "power_w":{"page":1,"x":.1,"y":.2,"w":.2,"h":.03},
            "luminous_flux_lm":{"page":1,"x":.1,"y":.3,"w":.2,"h":.03},
            "efficacy_lm_w":{"page":1,"x":.1,"y":.4,"w":.2,"h":.03},
            "max_candela_cd":{"page":1,"x":.1,"y":.5,"w":.2,"h":.03},
        },
    }).json()
    assert result["source_report"]["file_name"] == "lab-source.pdf"
    assert result["source_report"]["analysis"]["recognized_count"] >= 4
    assert result["pdf_template_applied"] is True
    assert result["template_pdf_file"] == "Linked_report_原版式报告.pdf"
    assert client.get(result["template_pdf_url"]).content.startswith(b"%PDF-")
    assert result["report_schema_version"] == "1.0"
    assert len(__import__("pypdf").PdfReader(OUTPUT_DIR / result["pdf_report_file"]).pages) == 13
    assert result["ies_file"] == "Linked_report.ies"
    assert result["pdf_report_file"] == "Linked_report_方案光度报告.pdf"
    assert "光度数据报告" in (OUTPUT_DIR / result["html_report_file"]).read_text(encoding="utf-8")
    cleanup_result(result)
    record = SOURCE_REPORTS.pop(source_info["source_report_id"])
    record["path"].unlink(missing_ok=True)


def test_upload_rejections(tmp_path: Path):
    wrong = client.post("/api/upload", files={"file": ("bad.txt", b"x", "text/plain")})
    assert wrong.status_code == 400
    broken = client.post("/api/upload", files={"file": ("bad.ies", b"broken", "text/plain")})
    assert broken.status_code == 400
    empty = client.post("/api/upload", files={"file": ("empty.ies", b"", "text/plain")})
    assert empty.status_code == 400
    large = client.post("/api/upload", files={"file": ("large.ies", b"x" * (10 * 1024 * 1024 + 1), "text/plain")})
    assert large.status_code == 413


def test_generate_missing_id_and_high_risk(sample_path: Path):
    base = {"source_luminous_flux_lm": 1000, "target_luminous_flux_lm": 1200,
            "target_model": "A", "target_power_w": 30, "target_luminous_length_mm": 300, "target_luminous_width_mm": 50, "change_type": "power_only"}
    assert client.post("/api/generate", json={"uploaded_file_id": "missing", **base}).status_code == 404
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    response = client.post("/api/generate", json={"uploaded_file_id": uploaded_id, **base, "change_type": "lens_change"})
    assert response.status_code == 200
    assert response.json() == {
        "allow_generate": False, "risk_level": "high", "risk_message": "透镜变化会改变配光形状，需要重新实测。"
    }


def test_all_high_risk_changes_are_blocked(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    for change_type in ("beam_angle_change", "lens_change", "optical_structure_change"):
        response = client.post("/api/generate", json={
            "uploaded_file_id": uploaded_id,
            "source_luminous_flux_lm": 1000,
            "target_luminous_flux_lm": 1200,
            "target_model": "A",
            "target_power_w": 30,
            "target_luminous_length_mm": 300, "target_luminous_width_mm": 50,
            "change_type": change_type,
        })
        assert response.status_code == 200
        assert response.json()["allow_generate"] is False


def test_generate_rejects_invalid_and_non_finite_fields(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    base = {
        "uploaded_file_id": uploaded_id,
        "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1200,
        "target_model": "A",
        "target_power_w": 30,
        "target_luminous_length_mm": 300, "target_luminous_width_mm": 50,
        "change_type": "power_only",
    }
    for field, value in (
        ("source_luminous_flux_lm", 0),
        ("target_luminous_flux_lm", -1),
        ("target_power_w", 0),
        ("target_model", "   "),
    ):
        response = client.post("/api/generate", json={**base, field: value})
        assert response.status_code == 422
    response = client.post(
        "/api/generate",
        content=(
            '{"uploaded_file_id":"%s","source_luminous_flux_lm":NaN,'
            '"target_luminous_flux_lm":1200,"target_model":"A",'
            '"target_power_w":30,"target_luminous_length_mm":300,"target_luminous_width_mm":50,"change_type":"power_only"}' % uploaded_id
        ),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_output_names_are_safe_and_do_not_overwrite(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    payload = {
        "uploaded_file_id": uploaded_id,
        "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1200,
        "target_model": "Model/Test:*?",
        "target_power_w": 30,
        "target_luminous_length_mm": 300, "target_luminous_width_mm": 50,
        "change_type": "power_only",
    }
    first = client.post("/api/generate", json=payload).json()
    second = client.post("/api/generate", json=payload).json()
    assert first["ies_file"] != second["ies_file"]
    assert not any(char in first["ies_file"] for char in '/:*?<>|"')
    for result in (first, second):
        cleanup_result(result)


def test_generate_accepts_target_luminous_dimensions(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    response = client.post("/api/generate", json={
        "uploaded_file_id": uploaded_id,
        "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1500,
        "target_model": "Long model",
        "target_power_w": 36,
        "change_type": "length_change",
        "target_luminous_length_mm": 1200,
        "target_luminous_width_mm": 80,
    })
    assert response.status_code == 200
    result = response.json()
    generated = IESParser.parse(OUTPUT_DIR / result["ies_file"])
    assert generated["length"] == 1.2
    assert generated["width"] == 0.08
    cleanup_result(result)


def test_generate_accepts_report_supplement_and_runs_full_validation(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    response = client.post("/api/generate", json={
        "uploaded_file_id": uploaded_id, "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1200, "target_model": "Report Model",
        "target_power_w": 30, "target_luminous_length_mm": 300, "target_luminous_width_mm": 50, "change_type": "power_only",
        "report_supplement": {"company_name":"Example Lighting","voltage_v":24,"current_a":1.25,"power_factor":.95,"cct_k":4000,"cri_ra":80},
    })
    assert response.status_code == 200
    result = response.json()
    # The intentionally minimal fixture declares a flux that is not consistent
    # with its candela matrix; the new numerical audit must expose that mismatch.
    assert result["ies_preview"]["validation_passed"] is False
    assert len(result["ies_preview"]["validation"]) == 22
    assert any(not item["ok"] and "积分" in item["label"] for item in result["ies_preview"]["validation"])
    cleanup_result(result)


def test_generate_requires_luminous_opening_dimensions(sample_path: Path):
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]
    response = client.post("/api/generate", json={
        "uploaded_file_id": uploaded_id, "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1200, "target_model": "Missing dimensions",
        "target_power_w": 30, "change_type": "power_only",
    })
    assert response.status_code == 422


def test_download_safety():
    assert client.get("/api/download/not-found.ies").status_code == 404
    assert client.get("/api/download/..%2Fsecret.txt").status_code in {400, 404}


def test_expired_runtime_files_are_cleaned_up():
    path = OUTPUT_DIR / f"expired-{uuid.uuid4().hex}.tmp"
    path.write_text("old", encoding="utf-8")
    old_time = time.time() - main.FILE_RETENTION_SECONDS - 10
    os.utime(path, (old_time, old_time))
    main.cleanup_expired_files()
    assert not path.exists()


def test_led_library_seed_save_and_dedupe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main, "LED_LIBRARY_PATH", tmp_path / "led_library.json")
    seed = client.get("/api/led-library").json()
    assert len(seed["models"]) >= 3  # 内置种子型号
    response = client.post("/api/led-library", json={"name": "测试2835", "note": "测试", "points": [[100, 36], [60, 23]]})
    assert response.status_code == 200
    models = response.json()["models"]
    assert models[-1]["name"] == "测试2835"
    assert models[-1]["points"][0] == [60.0, 23.0]  # 按电流排序
    client.post("/api/led-library", json={"name": "测试2835", "points": [[60, 20], [100, 35]]})
    names = [m["name"] for m in client.get("/api/led-library").json()["models"]]
    assert names.count("测试2835") == 1  # 同名覆盖
    assert client.post("/api/led-library", json={"name": "坏数据", "points": [[60, 23]]}).status_code == 400
    assert client.post("/api/led-library", json={"name": "坏数据", "points": [[-1, 23], [100, 36]]}).status_code == 400


def test_generate_with_photometric_centering(tmp_path: Path):
    tilted = tmp_path / "tilted.ies"
    tilted.write_text(tilted_ies_text(), encoding="utf-8")
    with tilted.open("rb") as file:
        upload = client.post("/api/upload", files={"file": ("tilted.ies", file, "application/octet-stream")})
    assert upload.status_code == 200
    body = upload.json()
    assert body["photometry"]["peak_direction"]["gamma_angle"] == 30
    response = client.post("/api/generate", json={
        "uploaded_file_id": body["uploaded_file_id"], "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1500, "target_model": "Centered/Model",
        "target_power_w": 36, "target_luminous_length_mm": 300, "target_luminous_width_mm": 50,
        "change_type": "power_only", "center_photometry": True,
    })
    # 带 center_photometry 字段不发 500（防 model_dump 透传回归）
    assert response.status_code == 200
    result = response.json()
    assert result["centering_applied"] is True
    assert result["centering"]["original_peak_c_angle"] == 90
    assert result["centering"]["original_peak_gamma_angle"] == 30
    assert result["ies_preview"]["photometry"]["peak_direction"]["gamma_angle"] == 0
    generated = IESParser.parse(OUTPUT_DIR / result["ies_file"])
    assert build_photometry_summary(generated)["peak_direction"]["gamma_angle"] == 0
    assert client.get(result["ies_download_url"]).status_code == 200
    cleanup_result(result)


def test_generation_failure_rolls_back_all_outputs(sample_path: Path, monkeypatch):
    for stale in OUTPUT_DIR.glob("AtomicFailure*"):
        stale.unlink(missing_ok=True)
    uploaded_id = upload_sample(sample_path).json()["uploaded_file_id"]

    def fail_report(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(main.ReportGenerator, "generate_all", fail_report)
    response = client.post("/api/generate", json={
        "uploaded_file_id": uploaded_id,
        "source_luminous_flux_lm": 1000,
        "target_luminous_flux_lm": 1200,
        "target_model": "AtomicFailure",
        "target_power_w": 30,
        "target_luminous_length_mm": 300, "target_luminous_width_mm": 50,
        "change_type": "power_only",
    })
    assert response.status_code == 500
    assert "IES" in response.json()["error"]
    assert not list(OUTPUT_DIR.glob("AtomicFailure*"))
