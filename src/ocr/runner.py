from __future__ import annotations

import json
import os
import subprocess
import textwrap
import urllib.parse
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
    multipass_enabled: bool = True
    tiling_enabled: bool = True
    language_routing_enabled: bool = False

    def run(self, snapshot: NormalizedPageSnapshot, candidates: list[dict[str, Any]]) -> OcrRunResult:
        blocks: list[dict[str, Any]] = []
        image_results: list[dict[str, Any]] = []
        for candidate in candidates[: self.max_images]:
            src = str(candidate.get("src", "")).strip()
            if not src:
                continue
            requested_pipeline = str(candidate.get("ocr_pipeline_type", "plain_text") or "plain_text")
            candidate_type = str(candidate.get("candidate_type", "general_detail_image") or "general_detail_image")
            pass_plans = _plan_candidate_passes(
                candidate=candidate,
                requested_pipeline=requested_pipeline,
                candidate_type=candidate_type,
                structured_enabled=self.structured_enabled,
                multipass_enabled=self.multipass_enabled,
                tiling_enabled=self.tiling_enabled,
                language_routing_enabled=self.language_routing_enabled,
            )
            best_payload: dict[str, Any] | None = None
            pass_summaries: list[dict[str, Any]] = []
            total_runtime_ms = 0

            for plan in pass_plans:
                payload = _run_paddleocr_subprocess(
                    ocr_python=self.ocr_python,
                    site_packages_path=self.site_packages_path,
                    image_source=src,
                    timeout_seconds=self.timeout_seconds,
                    pipeline_type=str(plan["pipeline_type"]),
                    rectify_enabled=self.rectify_enabled,
                    preprocessing_variant=str(plan["preprocessing_variant"]),
                    ocr_lang=str(plan["ocr_lang"]),
                    tile_mode=str(plan["tile_mode"]),
                )
                total_runtime_ms += int(payload.get("runtime_ms", 0) or 0)
                pass_summary = {
                    "pipeline_type": str(plan["pipeline_type"]),
                    "preprocessing_variant": str(plan["preprocessing_variant"]),
                    "recognizer_lang": str(plan["ocr_lang"]),
                    "tile_mode": str(plan["tile_mode"]),
                    "engine_used": payload.get("engine_used"),
                    "block_count": int(payload.get("block_count", 0) or 0),
                    "char_count": int(payload.get("char_count", 0) or 0),
                    "tile_count": int(payload.get("tile_count", 1) or 1),
                    "runtime_ms": int(payload.get("runtime_ms", 0) or 0),
                    "engine_ok": bool(payload.get("engine_ok")),
                    "error": payload.get("error"),
                }
                pass_summaries.append(pass_summary)
                if _is_better_payload(payload, best_payload):
                    best_payload = payload
                if _good_enough_payload(payload, candidate_type=candidate_type):
                    break

            if best_payload is None:
                best_payload = {
                    "engine_ok": False,
                    "blocks": [],
                    "block_count": 0,
                    "char_count": 0,
                    "engine_used": None,
                    "pipeline_type": requested_pipeline,
                    "preprocessing_variant": "original",
                    "recognizer_lang": "korean",
                    "tile_mode": "none",
                    "tile_count": 1,
                    "runtime_ms": total_runtime_ms,
                    "error": "no_ocr_pass_executed",
                }

            raw_blocks = list(best_payload.get("blocks", []))
            image_results.append(
                {
                    "image_src": src,
                    "image_attribute": candidate.get("attribute"),
                    "image_score": candidate.get("score"),
                    "candidate_type": candidate_type,
                    "selection_reason_codes": list(candidate.get("selection_reason_codes", [])),
                    "estimated_text_density": candidate.get("estimated_text_density"),
                    "needs_tiling": bool(candidate.get("needs_tiling", False)),
                    "pipeline_type": best_payload.get("pipeline_type"),
                    "engine_used": best_payload.get("engine_used"),
                    "recognizer_lang": best_payload.get("recognizer_lang"),
                    "preprocessing_variant": best_payload.get("preprocessing_variant"),
                    "tile_mode": best_payload.get("tile_mode"),
                    "tile_count": int(best_payload.get("tile_count", 1) or 1),
                    "ocr_passes": pass_summaries,
                    "raw_block_count": int(best_payload.get("block_count", len(raw_blocks))),
                    "raw_char_count": int(best_payload.get("char_count", 0)),
                    "runtime_ms": total_runtime_ms,
                    "status": (
                        "error"
                        if not best_payload.get("engine_ok")
                        else ("completed" if raw_blocks else "completed_no_text")
                    ),
                    "error": best_payload.get("error"),
                }
            )
            if not best_payload.get("engine_ok"):
                continue

            for block_index, raw_block in enumerate(raw_blocks):
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
                        "pipeline_type": best_payload.get("pipeline_type"),
                        "engine_used": best_payload.get("engine_used"),
                        "recognizer_lang": best_payload.get("recognizer_lang"),
                        "preprocessing_variant": best_payload.get("preprocessing_variant"),
                        "tile_mode": best_payload.get("tile_mode"),
                        "tile_index": int(raw_block.get("tile_index", 0) or 0),
                        "block_order": block_index,
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

    structured_enabled = _env_flag("KEYWORD_GENERATOR_OCR_STRUCTURED_ENABLED", default=False)
    rectify_enabled = _env_flag("KEYWORD_GENERATOR_OCR_RECTIFY_ENABLED", default=False)
    multipass_enabled = _env_flag("KEYWORD_GENERATOR_OCR_MULTIPASS_ENABLED", default=True)
    tiling_enabled = _env_flag("KEYWORD_GENERATOR_OCR_TILING_ENABLED", default=True)
    language_routing_enabled = _env_flag("KEYWORD_GENERATOR_OCR_LANGUAGE_ROUTING_ENABLED", default=False)

    return SubprocessOcrRunner(
        ocr_python=str(python_path),
        site_packages_path=site_packages_path,
        max_images=max_images,
        timeout_seconds=timeout_seconds,
        structured_enabled=structured_enabled,
        rectify_enabled=rectify_enabled,
        multipass_enabled=multipass_enabled,
        tiling_enabled=tiling_enabled,
        language_routing_enabled=language_routing_enabled,
    )


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def _plan_candidate_passes(
    *,
    candidate: dict[str, Any],
    requested_pipeline: str,
    candidate_type: str,
    structured_enabled: bool,
    multipass_enabled: bool,
    tiling_enabled: bool,
    language_routing_enabled: bool,
) -> list[dict[str, str]]:
    passes: list[dict[str, str]] = []
    if requested_pipeline == "structured_table":
        passes.append(
            {
                "pipeline_type": "structured_table" if structured_enabled else "plain_text",
                "preprocessing_variant": "original",
                "ocr_lang": "korean",
                "tile_mode": "none",
            }
        )
        if structured_enabled:
            passes.append(
                {
                    "pipeline_type": "plain_text",
                    "preprocessing_variant": "enhance_contrast" if multipass_enabled else "original",
                    "ocr_lang": "korean",
                    "tile_mode": "none",
                }
            )
        return _dedupe_passes(passes)

    tile_mode = "vertical" if tiling_enabled and candidate_type == "long_detail_banner" else "none"
    passes.append(
        {
            "pipeline_type": "plain_text",
            "preprocessing_variant": "original",
            "ocr_lang": "korean",
            "tile_mode": tile_mode,
        }
    )
    if multipass_enabled:
        passes.append(
            {
                "pipeline_type": "plain_text",
                "preprocessing_variant": "enhance_contrast",
                "ocr_lang": "korean",
                "tile_mode": tile_mode,
            }
        )
        if candidate_type == "front_label_closeup":
            passes.append(
                {
                    "pipeline_type": "plain_text",
                    "preprocessing_variant": "upscale_x2",
                    "ocr_lang": "korean",
                    "tile_mode": tile_mode,
                }
            )
    if language_routing_enabled and _looks_english_heavy(candidate):
        passes.append(
            {
                "pipeline_type": "plain_text",
                "preprocessing_variant": "original",
                "ocr_lang": "en",
                "tile_mode": tile_mode,
            }
        )
    return _dedupe_passes(passes)


def _looks_english_heavy(candidate: dict[str, Any]) -> bool:
    combined = f"{candidate.get('src', '')} {candidate.get('alt', '')}"
    latin_count = sum(char.isascii() and char.isalpha() for char in combined)
    hangul_count = sum("\uac00" <= char <= "\ud7a3" for char in combined)
    return latin_count >= 6 and hangul_count == 0


def _dedupe_passes(values: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in values:
        key = (
            str(item["pipeline_type"]),
            str(item["preprocessing_variant"]),
            str(item["ocr_lang"]),
            str(item["tile_mode"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _is_better_payload(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True
    current_score = _payload_quality_score(current)
    candidate_score = _payload_quality_score(candidate)
    if candidate_score != current_score:
        return candidate_score > current_score
    return int(candidate.get("runtime_ms", 0) or 0) < int(current.get("runtime_ms", 0) or 0)


def _good_enough_payload(payload: dict[str, Any], *, candidate_type: str) -> bool:
    if not payload.get("engine_ok"):
        return False
    char_count = int(payload.get("char_count", 0) or 0)
    block_count = int(payload.get("block_count", 0) or 0)
    if payload.get("pipeline_type") == "structured_table" and block_count >= 6:
        return True
    if candidate_type == "front_label_closeup":
        return char_count >= 80 or block_count >= 6
    if candidate_type == "long_detail_banner":
        return char_count >= 180 or block_count >= 12
    return char_count >= 120 or block_count >= 8


def _payload_quality_score(payload: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        1 if payload.get("engine_ok") else 0,
        int(payload.get("char_count", 0) or 0),
        int(payload.get("block_count", 0) or 0),
        1 if payload.get("pipeline_type") == "structured_table" else 0,
    )


def _run_paddleocr_subprocess(
    *,
    ocr_python: str,
    site_packages_path: str | None,
    image_source: str,
    timeout_seconds: int,
    pipeline_type: str,
    rectify_enabled: bool,
    preprocessing_variant: str,
    ocr_lang: str,
    tile_mode: str,
) -> dict[str, Any]:
    inline = textwrap.dedent(
        """
        import html
        import json
        import re
        import sys
        import tempfile
        import time
        import urllib.parse
        import urllib.request
        from pathlib import Path

        def _texts_from_page(page, tile_index):
            if page is None:
                return []
            if hasattr(page, "res"):
                return _texts_from_page(page.res, tile_index)
            if isinstance(page, dict):
                texts = []
                for key in ("rec_texts", "texts", "markdown", "text", "content", "table_html", "html"):
                    values = page.get(key)
                    if values:
                        texts.extend(_texts_from_page(values, tile_index))
                for key, values in page.items():
                    if key in {"rec_texts", "texts", "markdown", "text", "content", "table_html", "html"}:
                        continue
                    if isinstance(values, (dict, list, tuple)):
                        texts.extend(_texts_from_page(values, tile_index))
                return texts
            if isinstance(page, (list, tuple)):
                if page and isinstance(page[0], (list, tuple)) and len(page[0]) >= 2:
                    texts = []
                    for block_index, item in enumerate(page):
                        if len(item) < 2:
                            continue
                        value = item[1]
                        if isinstance(value, (list, tuple)) and value:
                            text = str(value[0]).strip()
                            if text:
                                texts.append({"text": text, "tile_index": tile_index, "block_order": block_index})
                    return texts
                texts = []
                for item in page:
                    texts.extend(_texts_from_page(item, tile_index))
                return texts
            if isinstance(page, str):
                cleaned = re.sub(r"<[^>]+>", " ", html.unescape(page))
                normalized = " ".join(cleaned.split()).strip()
                return [{"text": normalized, "tile_index": tile_index, "block_order": 0}] if normalized else []
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
            return temp_dir, prepared_path

        def _convert_webp(image_path):
            if image_path.suffix.lower() != ".webp":
                return image_path
            from PIL import Image
            converted_path = image_path.with_suffix(".png")
            with Image.open(image_path) as image:
                image.convert("RGB").save(converted_path, format="PNG")
            return converted_path

        def _preprocess_image(image_path, variant):
            from PIL import Image, ImageEnhance, ImageOps

            with Image.open(image_path) as image:
                processed = image.convert("RGB")
                if variant == "enhance_contrast":
                    processed = ImageOps.autocontrast(processed)
                    processed = ImageEnhance.Contrast(processed).enhance(1.8)
                    processed = ImageEnhance.Sharpness(processed).enhance(1.2)
                elif variant == "upscale_x2":
                    processed = processed.resize((processed.width * 2, processed.height * 2))
                    processed = ImageEnhance.Sharpness(processed).enhance(1.15)
                if variant == "original":
                    return image_path
                target_path = image_path.with_name(f"{image_path.stem}_{variant}.png")
                processed.save(target_path, format="PNG")
                return target_path

        def _tile_image(image_path, tile_mode):
            from PIL import Image

            with Image.open(image_path) as image:
                width = int(image.width)
                height = int(image.height)
                if tile_mode != "vertical" or height <= max(width * 2, 1600):
                    return [image_path]
                tile_height = max(min(max(width * 2, 900), 1600), 700)
                overlap = max(int(tile_height * 0.18), 120)
                paths = []
                top = 0
                tile_index = 0
                while top < height:
                    lower = min(height, top + tile_height)
                    crop = image.crop((0, top, width, lower))
                    tile_path = image_path.with_name(f"{image_path.stem}_tile{tile_index:02d}.png")
                    crop.save(tile_path, format="PNG")
                    paths.append(tile_path)
                    tile_index += 1
                    if lower >= height:
                        break
                    top = max(0, lower - overlap)
                return paths

        payload = {
            "engine_ok": False,
            "blocks": [],
            "block_count": 0,
            "char_count": 0,
            "engine_used": None,
            "pipeline_type": sys.argv[2],
            "preprocessing_variant": sys.argv[4],
            "recognizer_lang": sys.argv[5],
            "tile_mode": sys.argv[6],
            "tile_count": 1,
            "runtime_ms": 0,
            "error": None,
        }
        temp_dir = None
        started = time.perf_counter()
        try:
            pipeline_type = sys.argv[2]
            rectify_enabled = sys.argv[3].lower() in {"1", "true", "yes", "on"}
            preprocessing_variant = sys.argv[4]
            recognizer_lang = sys.argv[5]
            tile_mode = sys.argv[6]
            if pipeline_type == "structured_table":
                from paddleocr import PPStructureV3
            else:
                from paddleocr import PaddleOCR

            temp_dir, image_path = _materialize_image(sys.argv[1])
            image_path = _convert_webp(image_path)
            image_path = _preprocess_image(image_path, preprocessing_variant)
            image_paths = _tile_image(image_path, tile_mode)
            payload["tile_count"] = len(image_paths)

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
                payload["engine_used"] = "PPStructureV3"
            else:
                ocr = PaddleOCR(
                    lang=recognizer_lang,
                    use_textline_orientation=True,
                    use_doc_unwarping=rectify_enabled,
                    device="cpu",
                    enable_mkldnn=False,
                    enable_cinn=False,
                    enable_hpi=False,
                )
                payload["engine_used"] = "PaddleOCR"

            blocks = []
            for tile_index, current_path in enumerate(image_paths):
                if pipeline_type == "structured_table":
                    result = ocr.predict(
                        str(current_path),
                        use_textline_orientation=True,
                        use_doc_unwarping=rectify_enabled,
                        use_table_recognition=True,
                    )
                elif hasattr(ocr, "predict"):
                    result = ocr.predict(str(current_path))
                else:
                    result = ocr.ocr(str(current_path))
                for page in result or []:
                    blocks.extend(_texts_from_page(page, tile_index))

            payload["engine_ok"] = True
            payload["blocks"] = blocks
            payload["block_count"] = len(blocks)
            payload["char_count"] = len(" ".join(block["text"] for block in blocks).strip())
        except Exception as exc:
            payload["error"] = str(exc)
        finally:
            payload["runtime_ms"] = int((time.perf_counter() - started) * 1000)
            if temp_dir is not None:
                temp_dir.cleanup()
        print(json.dumps(payload, ensure_ascii=False))
        """
    ).strip()

    pythonpath = os.environ.get("PYTHONPATH", "")
    if site_packages_path:
        pythonpath = os.pathsep.join(part for part in (site_packages_path, pythonpath) if part)

    try:
        process = subprocess.run(
            [
                ocr_python,
                "-c",
                inline,
                image_source,
                pipeline_type,
                "1" if rectify_enabled else "0",
                preprocessing_variant,
                ocr_lang,
                tile_mode,
            ],
            capture_output=True,
            text=False,
            check=False,
            timeout=timeout_seconds,
            env={
                **os.environ,
                "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "1",
                "PYTHONPATH": pythonpath,
                "PYTHONIOENCODING": "utf-8",
            },
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "engine_ok": False,
            "blocks": [],
            "block_count": 0,
            "char_count": 0,
            "engine_used": None,
            "pipeline_type": pipeline_type,
            "preprocessing_variant": preprocessing_variant,
            "recognizer_lang": ocr_lang,
            "tile_mode": tile_mode,
            "tile_count": 1,
            "runtime_ms": int(timeout_seconds * 1000),
            "error": f"paddleocr subprocess timed out after {timeout_seconds}s",
            "stdout": _decode_subprocess_stream(exc.stdout),
            "stderr": _decode_subprocess_stream(exc.stderr),
        }
    stdout = _decode_subprocess_stream(process.stdout)
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {"engine_ok": False, "blocks": [], "error": stdout}
    else:
        payload = {"engine_ok": False, "blocks": [], "error": _decode_subprocess_stream(process.stderr)}
    if process.returncode != 0 and not payload.get("error"):
        payload["error"] = _decode_subprocess_stream(process.stderr) or (
            f"paddleocr subprocess failed with exit code {process.returncode}"
        )
    payload.setdefault("pipeline_type", pipeline_type)
    payload.setdefault("preprocessing_variant", preprocessing_variant)
    payload.setdefault("recognizer_lang", ocr_lang)
    payload.setdefault("tile_mode", tile_mode)
    payload.setdefault("tile_count", 1)
    payload.setdefault("runtime_ms", 0)
    return payload


def _decode_subprocess_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    for encoding in ("utf-8", "cp949"):
        try:
            return value.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace").strip()
