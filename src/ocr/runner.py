from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.collection.models import NormalizedPageSnapshot
from src.ocr.models import OcrRunResult


class OcrRunner(Protocol):
    def run(
        self,
        snapshot: NormalizedPageSnapshot,
        candidates: list[dict[str, Any]],
    ) -> OcrRunResult | list[dict[str, Any]]:
        ...


@dataclass(slots=True)
class SubprocessOcrRunner:
    ocr_python: str
    site_packages_path: str | None = None
    max_images: int = 24
    timeout_seconds: int = 120
    structured_enabled: bool = False
    rectify_enabled: bool = False

    def run(self, snapshot: NormalizedPageSnapshot, candidates: list[dict[str, Any]]) -> OcrRunResult:
        blocks: list[dict[str, Any]] = []
        image_results: list[dict[str, Any]] = []
        for candidate in candidates[: self.max_images]:
            src = str(candidate.get("src", "")).strip()
            if not src:
                continue
            requested_pipeline = str(candidate.get("ocr_pipeline_type", "plain_text") or "plain_text")
            pipeline_type = requested_pipeline if self.structured_enabled else "plain_text"
            candidate_type = str(candidate.get("candidate_type", "general_detail_image") or "general_detail_image")
            payload = _run_paddleocr_subprocess(
                ocr_python=self.ocr_python,
                site_packages_path=self.site_packages_path,
                image_source=src,
                timeout_seconds=self.timeout_seconds,
                pipeline_type=pipeline_type,
                rectify_enabled=self.rectify_enabled,
            )
            raw_blocks = list(payload.get("blocks", []))
            image_results.append(
                {
                    "image_src": src,
                    "image_attribute": candidate.get("attribute"),
                    "image_score": candidate.get("score"),
                    "candidate_type": candidate_type,
                    "pipeline_type": pipeline_type,
                    "engine_used": payload.get("engine_used"),
                    "raw_block_count": int(payload.get("block_count", len(raw_blocks))),
                    "raw_char_count": int(payload.get("char_count", 0)),
                    "status": (
                        "error"
                        if not payload.get("engine_ok")
                        else ("completed" if raw_blocks else "completed_no_text")
                    ),
                    "error": payload.get("error"),
                }
            )
            if not payload.get("engine_ok"):
                continue
            for raw_block in raw_blocks:
                text = str(raw_block.get("text", "")).strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "text": text,
                        "source": "image",
                        "image_src": src,
                        "image_attribute": candidate.get("attribute"),
                        "image_score": candidate.get("score"),
                        "candidate_type": candidate_type,
                        "pipeline_type": pipeline_type,
                        "engine_used": payload.get("engine_used"),
                    }
                )
        return OcrRunResult(blocks=blocks, image_results=image_results)


def create_subprocess_ocr_runner_from_env() -> OcrRunner | None:
    enabled = os.environ.get("KEYWORD_GENERATOR_OCR_ENABLED", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None

    ocr_python = os.environ.get("KEYWORD_GENERATOR_OCR_PYTHON")
    if ocr_python:
        python_path = Path(ocr_python)
    else:
        python_path = _default_ocr_python()
    if not python_path.exists():
        return None

    site_packages_path = os.environ.get("KEYWORD_GENERATOR_OCR_SITE_PACKAGES")
    if not site_packages_path:
        inferred = _default_site_packages_path()
        site_packages_path = str(inferred) if inferred.exists() else None

    try:
        max_images = max(1, int(os.environ.get("KEYWORD_GENERATOR_OCR_MAX_IMAGES", "24")))
    except ValueError:
        max_images = 24
    try:
        timeout_seconds = max(1, int(os.environ.get("KEYWORD_GENERATOR_OCR_TIMEOUT_SECONDS", "120")))
    except ValueError:
        timeout_seconds = 120
    structured_enabled = os.environ.get("KEYWORD_GENERATOR_OCR_STRUCTURED_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    rectify_enabled = os.environ.get("KEYWORD_GENERATOR_OCR_RECTIFY_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return SubprocessOcrRunner(
        ocr_python=str(python_path),
        site_packages_path=site_packages_path,
        max_images=max_images,
        timeout_seconds=timeout_seconds,
        structured_enabled=structured_enabled,
        rectify_enabled=rectify_enabled,
    )


def _default_ocr_python() -> Path:
    root = Path(__file__).resolve().parents[2]
    pyvenv_cfg = root / ".venv-paddleocr" / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if not line.lower().startswith("executable = "):
                continue
            candidate = Path(line.split("=", 1)[1].strip())
            if candidate.exists():
                return candidate
    return root / ".venv-paddleocr" / "Scripts" / "python.exe"


def _default_site_packages_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / ".venv-paddleocr" / "Lib" / "site-packages"


def _run_paddleocr_subprocess(
    *,
    ocr_python: str,
    site_packages_path: str | None,
    image_source: str,
    timeout_seconds: int,
    pipeline_type: str,
    rectify_enabled: bool,
) -> dict[str, Any]:
    inline = textwrap.dedent(
        """
        import html
        import json
        import re
        import sys
        import tempfile
        import urllib.parse
        import urllib.request
        from pathlib import Path

        def _texts_from_page(page):
            if page is None:
                return []
            if hasattr(page, "res"):
                return _texts_from_page(page.res)
            if isinstance(page, dict):
                texts = []
                for key in ("rec_texts", "texts", "markdown", "text", "content", "table_html", "html"):
                    values = page.get(key)
                    if values:
                        texts.extend(_texts_from_page(values))
                for key, values in page.items():
                    if key in {"rec_texts", "texts", "markdown", "text", "content", "table_html", "html"}:
                        continue
                    if isinstance(values, (dict, list, tuple)):
                        texts.extend(_texts_from_page(values))
                return texts
            if isinstance(page, (list, tuple)):
                if page and isinstance(page[0], (list, tuple)) and len(page[0]) >= 2:
                    texts = []
                    for item in page:
                        if len(item) < 2:
                            continue
                        value = item[1]
                        if isinstance(value, (list, tuple)) and value:
                            text = str(value[0]).strip()
                            if text:
                                texts.append(text)
                    return texts
                texts = []
                for item in page:
                    texts.extend(_texts_from_page(item))
                return texts
            if isinstance(page, str):
                cleaned = re.sub(r"<[^>]+>", " ", html.unescape(page))
                normalized = " ".join(cleaned.split()).strip()
                return [normalized] if normalized else []
            return []

        def _materialize_image(source):
            parsed = urllib.parse.urlsplit(source)
            if parsed.scheme in {"http", "https"}:
                suffix = Path(parsed.path).suffix or ".img"
                temp_dir = tempfile.TemporaryDirectory()
                original_path = Path(temp_dir.name) / f"ocr_input{suffix}"
                urllib.request.urlretrieve(source, original_path)
                prepared_path = original_path
            else:
                temp_dir = None
                original_path = Path(source)
                prepared_path = original_path

            if prepared_path.suffix.lower() == ".webp":
                try:
                    from PIL import Image

                    converted_path = prepared_path.with_suffix(".png")
                    with Image.open(prepared_path) as image:
                        image.convert("RGB").save(converted_path, format="PNG")
                    prepared_path = converted_path
                except Exception:
                    pass
            return temp_dir, prepared_path

        payload = {
            "engine_ok": False,
            "blocks": [],
            "block_count": 0,
            "char_count": 0,
            "engine_used": None,
            "pipeline_type": sys.argv[2],
            "error": None,
        }
        temp_dir = None
        try:
            pipeline_type = sys.argv[2]
            rectify_enabled = sys.argv[3].lower() in {"1", "true", "yes", "on"}
            if pipeline_type == "structured_table":
                from paddleocr import PPStructureV3
            else:
                from paddleocr import PaddleOCR

            temp_dir, image_path = _materialize_image(sys.argv[1])
            if pipeline_type == "structured_table":
                ocr = PPStructureV3(
                    lang="korean",
                    ocr_version="PP-OCRv5",
                    use_textline_orientation=True,
                    use_doc_unwarping=rectify_enabled,
                    use_table_recognition=True,
                    device="cpu",
                    enable_mkldnn=False,
                    enable_cinn=False,
                    enable_hpi=False,
                )
                result = ocr.predict(
                    str(image_path),
                    use_textline_orientation=True,
                    use_doc_unwarping=rectify_enabled,
                    use_table_recognition=True,
                )
                payload["engine_used"] = "PPStructureV3"
            else:
                ocr = PaddleOCR(
                    lang="korean",
                    use_textline_orientation=True,
                    use_doc_unwarping=rectify_enabled,
                    device="cpu",
                    enable_mkldnn=False,
                    enable_cinn=False,
                    enable_hpi=False,
                )
                if hasattr(ocr, "predict"):
                    result = ocr.predict(str(image_path))
                else:
                    result = ocr.ocr(str(image_path))
                payload["engine_used"] = "PaddleOCR"
            blocks = []
            for page in result or []:
                for text in _texts_from_page(page):
                    if text:
                        blocks.append({"text": text})
            payload["engine_ok"] = True
            payload["blocks"] = blocks
            payload["block_count"] = len(blocks)
            payload["char_count"] = len(" ".join(block["text"] for block in blocks).strip())
        except Exception as exc:
            payload["error"] = str(exc)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
        print(json.dumps(payload, ensure_ascii=False))
        """
    ).strip()

    pythonpath = os.environ.get("PYTHONPATH", "")
    if site_packages_path:
        pythonpath = os.pathsep.join(part for part in (site_packages_path, pythonpath) if part)

    process = subprocess.run(
        [ocr_python, "-c", inline, image_source, pipeline_type, "1" if rectify_enabled else "0"],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env={
            **os.environ,
            "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "1",
            "PYTHONPATH": pythonpath,
        },
    )
    stdout = process.stdout.strip()
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {"engine_ok": False, "blocks": [], "error": stdout}
    else:
        payload = {"engine_ok": False, "blocks": [], "error": process.stderr.strip()}
    if process.returncode != 0 and not payload.get("error"):
        payload["error"] = process.stderr.strip() or f"paddleocr subprocess failed with exit code {process.returncode}"
    return payload
