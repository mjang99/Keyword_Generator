from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collection.models import NormalizedPageSnapshot
from src.ocr import run_ocr_policy


DEFAULT_FUNSD_ZIP = ROOT / ".tmp" / "funsd_dataset.zip"
DEFAULT_PRODUCT_SAMPLES: tuple[dict[str, Any], ...] = (
    {
        "label": "APRILSKIN",
        "path": ROOT / ".tmp" / "ocr_real" / "aprilskin_detail" / "png" / "centella1_03.png",
        "product_name": "APRILSKIN Mugwort Centella Calming Serum",
        "product_tokens": ["aprilskin", "mugwort", "centella", "calming", "serum"],
    },
    {
        "label": "DRJART",
        "path": ROOT / ".tmp" / "ocr_real" / "drjart" / "ingredient.jpg",
        "product_name": "Dr.Jart Hydro Mask",
        "product_tokens": ["dr.jart", "drjart", "hydro", "mask"],
    },
    {
        "label": "LANEIGE",
        "path": ROOT / ".tmp" / "ocr_real" / "laneige_batch" / "pdp_prn_3x_retinol_img10_kr_260317.jpg",
        "product_name": "LANEIGE Retinol",
        "product_tokens": ["laneige", "retinol"],
    },
)


@dataclass(frozen=True, slots=True)
class ProductSample:
    label: str
    path: Path
    product_name: str
    product_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceImageSample:
    dataset: str
    image_path: Path
    reference_text: str
    reference_source: str
    label: str | None = None


PRODUCT_SAMPLES: tuple[ProductSample, ...] = tuple(
    ProductSample(
        label=str(item["label"]),
        path=Path(item["path"]),
        product_name=str(item["product_name"]),
        product_tokens=tuple(str(token) for token in item["product_tokens"]),
    )
    for item in DEFAULT_PRODUCT_SAMPLES
)
PRODUCT_SAMPLE_BY_LABEL = {sample.label: sample for sample in PRODUCT_SAMPLES}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TEXT_LABEL_SUFFIXES = (".txt", ".label.txt", ".gt.txt", ".transcription.txt")
JSON_LABEL_SUFFIXES = (".json", ".label.json", ".gt.json", ".transcription.json")
BENCHMARK_DERIVATIVE_STEM_SUFFIXES = (
    "_enhance_contrast",
    "_upscale_x2",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a lightweight OCR benchmark on local benchmark assets and product-detail images."
    )
    parser.add_argument(
        "--funsd-zip",
        default=str(DEFAULT_FUNSD_ZIP),
        help="Path to the local FUNSD dataset zip.",
    )
    parser.add_argument(
        "--funsd-sample-count",
        type=int,
        default=3,
        help="How many FUNSD pages to evaluate from the training split.",
    )
    parser.add_argument(
        "--skip-funsd",
        action="store_true",
        help="Skip the FUNSD benchmark.",
    )
    parser.add_argument(
        "--skip-product-smoke",
        action="store_true",
        help="Skip the local product-image smoke benchmark.",
    )
    parser.add_argument(
        "--product-sample-count",
        type=int,
        default=len(DEFAULT_PRODUCT_SAMPLES),
        help="How many local product smoke images to evaluate.",
    )
    parser.add_argument(
        "--product-label",
        action="append",
        default=[],
        help=(
            "Benchmark only the named local product sample. "
            f"Repeatable. Known labels: {', '.join(sample.label for sample in PRODUCT_SAMPLES)}"
        ),
    )
    parser.add_argument(
        "--product-max-side",
        type=int,
        default=0,
        help=(
            "If > 0, benchmark product images through a temporary resized copy whose longest side "
            "is capped to this value. Default keeps the original image."
        ),
    )
    parser.add_argument(
        "--output",
        choices=("json", "text"),
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--finegrainocr-root",
        default="",
        help="Local extracted FineGrainOCR root. When provided, run the dataset reference benchmark.",
    )
    parser.add_argument(
        "--finegrainocr-sample-count",
        type=int,
        default=5,
        help="How many FineGrainOCR images to benchmark once the root is available.",
    )
    parser.add_argument(
        "--unitail-ocr-root",
        default="",
        help="Local extracted Unitail-OCR root. When provided, run the dataset reference benchmark.",
    )
    parser.add_argument(
        "--unitail-ocr-sample-count",
        type=int,
        default=5,
        help="How many Unitail-OCR images to benchmark once the root is available.",
    )
    parser.add_argument(
        "--korean-product-labels-root",
        default="",
        help="Local extracted Korean_Product_Labels_Image_Dataset root. When provided, run the packaging smoke benchmark.",
    )
    parser.add_argument(
        "--korean-product-labels-sample-count",
        type=int,
        default=10,
        help="How many Korean product label images to benchmark once the root is available.",
    )
    parser.add_argument(
        "--dataset-max-side",
        type=int,
        default=0,
        help=(
            "If > 0, benchmark public-dataset images through a temporary resized copy whose longest side "
            "is capped to this value."
        ),
    )
    return parser.parse_args()


def _normalize_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^0-9a-z\uac00-\ud7a3]+", " ", lowered)
    return " ".join(lowered.split()).strip()


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return normalized.split() if normalized else []


def _levenshtein_distance(seq_a: list[str], seq_b: list[str]) -> int:
    if not seq_a:
        return len(seq_b)
    if not seq_b:
        return len(seq_a)
    previous = list(range(len(seq_b) + 1))
    for index_a, item_a in enumerate(seq_a, start=1):
        current = [index_a]
        for index_b, item_b in enumerate(seq_b, start=1):
            substitution_cost = 0 if item_a == item_b else 1
            current.append(
                min(
                    previous[index_b] + 1,
                    current[index_b - 1] + 1,
                    previous[index_b - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]


def _error_rate(reference: list[str], prediction: list[str]) -> float:
    if not reference:
        return 0.0 if not prediction else 1.0
    return _levenshtein_distance(reference, prediction) / len(reference)


def _multiset_precision_recall_f1(reference_tokens: list[str], predicted_tokens: list[str]) -> tuple[float, float, float]:
    remaining: dict[str, int] = {}
    for token in reference_tokens:
        remaining[token] = remaining.get(token, 0) + 1

    true_positive = 0
    for token in predicted_tokens:
        count = remaining.get(token, 0)
        if count > 0:
            remaining[token] = count - 1
            true_positive += 1

    precision = true_positive / len(predicted_tokens) if predicted_tokens else 0.0
    recall = true_positive / len(reference_tokens) if reference_tokens else 0.0
    if precision + recall == 0:
        return precision, recall, 0.0
    return precision, recall, 2 * precision * recall / (precision + recall)


def _extract_texts_from_paddle_result(result: Any) -> list[str]:
    texts: list[str] = []

    def walk(node: Any) -> None:
        if node is None:
            return
        if hasattr(node, "res"):
            walk(node.res)
            return
        if isinstance(node, dict):
            for key in ("rec_texts", "texts", "markdown", "text", "content", "table_html", "html"):
                value = node.get(key)
                if value:
                    walk(value)
            for key, value in node.items():
                if key in {"rec_texts", "texts", "markdown", "text", "content", "table_html", "html"}:
                    continue
                if isinstance(value, (dict, list, tuple)):
                    walk(value)
            return
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (list, tuple)) and len(node[0]) >= 2:
                for item in node:
                    if len(item) < 2:
                        continue
                    value = item[1]
                    if isinstance(value, (list, tuple)) and value:
                        text = str(value[0]).strip()
                        if text:
                            texts.append(text)
                return
            for item in node:
                walk(item)
            return
        if isinstance(node, str):
            text = " ".join(node.split()).strip()
            if text:
                texts.append(text)

    for page in result or []:
        walk(page)
    return texts


def _create_ocr_engine() -> Any:
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "1")

    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang="korean",
        use_textline_orientation=True,
        use_doc_unwarping=False,
        device="cpu",
        enable_mkldnn=False,
        enable_cinn=False,
        enable_hpi=False,
    )


def _resolve_product_samples(args: argparse.Namespace) -> list[ProductSample]:
    if args.product_label:
        selected: list[ProductSample] = []
        for label in args.product_label:
            sample = PRODUCT_SAMPLE_BY_LABEL.get(label.upper())
            if sample is None:
                raise SystemExit(f"unknown --product-label: {label!r}")
            selected.append(sample)
        return selected
    return list(PRODUCT_SAMPLES[: max(0, args.product_sample_count)])


def _iter_image_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and not _is_benchmark_derivative_image(path)
    )


def _is_benchmark_derivative_image(path: Path) -> bool:
    stem = path.stem.lower()
    return any(stem.endswith(suffix) for suffix in BENCHMARK_DERIVATIVE_STEM_SUFFIXES)


def _safe_read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "latin1"):
        try:
            return path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _extract_reference_text_from_google_vision_json(payload: Any) -> str:
    if isinstance(payload, dict):
        full = payload.get("fullTextAnnotation")
        if isinstance(full, dict):
            text = str(full.get("text", "")).strip()
            if text:
                return text
        annotations = payload.get("textAnnotations")
        if isinstance(annotations, list) and annotations:
            description = annotations[0]
            if isinstance(description, dict):
                text = str(description.get("description", "")).strip()
                if text:
                    return text
        responses = payload.get("responses")
        if isinstance(responses, list):
            for item in responses:
                text = _extract_reference_text_from_google_vision_json(item)
                if text:
                    return text
        description = payload.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    if isinstance(payload, list):
        for item in payload:
            text = _extract_reference_text_from_google_vision_json(item)
            if text:
                return text
    return ""


def _extract_reference_text_from_json(payload: Any) -> str:
    text = _extract_reference_text_from_google_vision_json(payload)
    if text:
        return text
    if isinstance(payload, dict):
        for key in ("text", "transcription", "label", "word", "words", "content", "description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                joined = " ".join(str(item).strip() for item in value if str(item).strip()).strip()
                if joined:
                    return joined
        for value in payload.values():
            text = _extract_reference_text_from_json(value)
            if text:
                return text
    if isinstance(payload, list):
        joined = []
        for item in payload:
            text = _extract_reference_text_from_json(item)
            if text:
                joined.append(text)
        return " ".join(joined).strip()
    return ""


def _find_same_stem_text(path: Path, suffixes: tuple[str, ...]) -> Path | None:
    for suffix in suffixes:
        candidate = path.with_name(f"{path.stem}{suffix}")
        if candidate.exists():
            return candidate
    return None


def _find_mirrored_text_file(image_path: Path, image_root_name: str, text_root_name: str) -> Path | None:
    parts = list(image_path.parts)
    try:
        root_index = parts.index(image_root_name)
    except ValueError:
        return None
    relative_parts = parts[root_index + 1 :]
    if not relative_parts:
        return None
    base_root = Path(*parts[:root_index])
    mirrored_parent = base_root / text_root_name
    if len(relative_parts) > 1:
        mirrored_parent = mirrored_parent.joinpath(*relative_parts[:-1])
    stem = Path(relative_parts[-1]).stem
    for suffix in (*JSON_LABEL_SUFFIXES, *TEXT_LABEL_SUFFIXES):
        candidate = mirrored_parent / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _discover_finegrainocr_samples(root: Path, sample_count: int) -> list[ReferenceImageSample]:
    samples: list[ReferenceImageSample] = []
    for image_path in _iter_image_files(root):
        label_path = _find_same_stem_text(image_path, JSON_LABEL_SUFFIXES)
        if label_path is None:
            label_path = _find_mirrored_text_file(image_path, "Images", "Text")
        if label_path is None:
            continue
        try:
            payload = json.loads(_safe_read_text(label_path))
        except json.JSONDecodeError:
            continue
        reference_text = _extract_reference_text_from_google_vision_json(payload)
        if not reference_text:
            continue
        samples.append(
            ReferenceImageSample(
                dataset="FineGrainOCR",
                image_path=image_path,
                reference_text=reference_text,
                reference_source="google_vision_json",
                label=image_path.stem,
            )
        )
        if len(samples) >= max(0, sample_count):
            break
    return samples


def _discover_unitail_ocr_samples(root: Path, sample_count: int) -> list[ReferenceImageSample]:
    manifest_samples = _discover_unitail_manifest_samples(root, sample_count)
    if manifest_samples:
        return manifest_samples

    samples: list[ReferenceImageSample] = []
    for image_path in _iter_image_files(root):
        label_path = _find_same_stem_text(image_path, TEXT_LABEL_SUFFIXES)
        if label_path is None:
            label_path = _find_mirrored_text_file(image_path, "images", "texts")
        reference_text = ""
        reference_source = ""
        if label_path is not None:
            reference_text = _safe_read_text(label_path)
            reference_source = label_path.suffix.lower()
        else:
            json_path = _find_same_stem_text(image_path, JSON_LABEL_SUFFIXES)
            if json_path is None:
                json_path = _find_mirrored_text_file(image_path, "images", "texts")
            if json_path is not None:
                try:
                    payload = json.loads(_safe_read_text(json_path))
                except json.JSONDecodeError:
                    payload = None
                if payload is not None:
                    reference_text = _extract_reference_text_from_json(payload)
                    reference_source = json_path.suffix.lower()
        if not reference_text:
            continue
        samples.append(
            ReferenceImageSample(
                dataset="Unitail-OCR",
                image_path=image_path,
                reference_text=reference_text,
                reference_source=reference_source or "same_stem_label",
                label=image_path.stem,
            )
        )
        if len(samples) >= max(0, sample_count):
            break
    return samples


def _find_unitail_manifest(root: Path) -> Path | None:
    for candidate in (
        root / "ocr_gt.json",
        root / "gallery" / "ocr_gt.json",
        root / "unitail-ocr" / "gallery" / "ocr_gt.json",
    ):
        if candidate.exists():
            return candidate
    return None


def _extract_unitail_annotation_text(annotation: dict[str, Any]) -> str:
    for key in ("text-words", "text", "utf8_string", "label"):
        value = annotation.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _annotation_sort_key(annotation: dict[str, Any]) -> tuple[int, float, float, int]:
    bbox = annotation.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        x = float(bbox[0])
        y = float(bbox[1])
        height = float(bbox[3]) or 1.0
        line_bucket = int(round(y / max(height, 1.0)))
        return (line_bucket, y, x, int(annotation.get("id", 0)))
    return (0, 0.0, 0.0, int(annotation.get("id", 0)))


def _resolve_manifest_image_path(manifest_path: Path, image_file_name: str) -> Path:
    relative_path = Path(str(image_file_name).replace("\\", "/"))
    if relative_path.parts and relative_path.parts[0] == ".":
        relative_path = Path(*relative_path.parts[1:])
    return (manifest_path.parent / relative_path).resolve()


def _discover_unitail_manifest_samples(root: Path, sample_count: int) -> list[ReferenceImageSample]:
    manifest_path = _find_unitail_manifest(root)
    if manifest_path is None:
        return []
    try:
        payload = json.loads(_safe_read_text(manifest_path))
    except json.JSONDecodeError:
        return []
    images = payload.get("images")
    annotations = payload.get("annotations")
    if not isinstance(images, list) or not isinstance(annotations, list):
        return []

    annotations_by_image_id: dict[int, list[dict[str, Any]]] = {}
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        image_id = annotation.get("image_id")
        if not isinstance(image_id, int):
            continue
        text = _extract_unitail_annotation_text(annotation)
        if not text:
            continue
        annotations_by_image_id.setdefault(image_id, []).append(annotation)

    samples: list[ReferenceImageSample] = []
    for image_meta in images:
        if not isinstance(image_meta, dict):
            continue
        image_id = image_meta.get("id")
        image_file_name = image_meta.get("file_name")
        if not isinstance(image_id, int) or not isinstance(image_file_name, str):
            continue
        image_annotations = annotations_by_image_id.get(image_id, [])
        if not image_annotations:
            continue
        image_path = _resolve_manifest_image_path(manifest_path, image_file_name)
        if not image_path.exists() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        ordered_tokens = [
            _extract_unitail_annotation_text(annotation)
            for annotation in sorted(image_annotations, key=_annotation_sort_key)
        ]
        reference_text = " ".join(token for token in ordered_tokens if token).strip()
        if not reference_text:
            continue
        samples.append(
            ReferenceImageSample(
                dataset="Unitail-OCR",
                image_path=image_path,
                reference_text=reference_text,
                reference_source=f"{manifest_path.name}#annotations",
                label=image_path.stem,
            )
        )
        if len(samples) >= max(0, sample_count):
            break
    return samples


def _tokenize_label_text(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.split(r"[^0-9A-Za-z\uac00-\ud7a3]+", value)
        if len(token.strip()) >= 2
    )


def _infer_product_name_from_image_path(image_path: Path, root: Path) -> str:
    relative_parent = image_path.parent.relative_to(root) if image_path.parent != root else Path()
    parent_label = " ".join(part for part in relative_parent.parts if part.lower() not in {"train", "test", "valid", "images"})
    stem_label = image_path.stem.replace("_", " ").replace("-", " ").strip()
    if parent_label:
        return parent_label.replace("_", " ").replace("-", " ").strip()
    return stem_label or image_path.stem


def _discover_korean_product_label_samples(root: Path, sample_count: int) -> list[ProductSample]:
    samples: list[ProductSample] = []
    for image_path in _iter_image_files(root)[: max(0, sample_count)]:
        product_name = _infer_product_name_from_image_path(image_path, root)
        product_tokens = _tokenize_label_text(f"{product_name} {image_path.stem}")
        samples.append(
            ProductSample(
                label=image_path.stem,
                path=image_path,
                product_name=product_name,
                product_tokens=product_tokens,
            )
        )
    return samples


def _create_snapshot(
    *,
    image_path: Path,
    product_name: str,
    product_tokens: list[str],
    blocks: list[dict[str, Any]],
) -> NormalizedPageSnapshot:
    unique_tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in [*product_tokens, *product_name.replace("/", " ").split()]:
        token = raw_token.strip()
        if len(token) < 2:
            continue
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_tokens.append(token)

    image_dimensions = _image_dimensions(image_path) or (1200, 1200)
    image_width, image_height = image_dimensions

    return NormalizedPageSnapshot(
        raw_url=str(image_path),
        canonical_url=str(image_path),
        page_class_hint="image_heavy_commerce_pdp",
        final_url=str(image_path),
        http_status=200,
        content_type=f"image/{image_path.suffix.lstrip('.')}",
        fetch_profile_used="ocr_benchmark",
        fetched_at=None,
        charset_selected="utf-8",
        charset_confidence=1.0,
        mojibake_flags=[],
        meta_locale="ko_KR",
        language_scores={"ko": 1.0, "en": 0.0},
        title=product_name,
        meta_description=None,
        canonical_tag=None,
        decoded_text="",
        visible_text_blocks=[],
        breadcrumbs=[],
        structured_data=[],
        primary_product_tokens=unique_tokens,
        price_signals=[],
        buy_signals=[],
        stock_signals=[],
        promo_signals=[],
        support_signals=[],
        download_signals=[],
        blocker_signals=[],
        waiting_signals=[],
        image_candidates=[
            {
                "src": str(image_path),
                "alt": product_name,
                "width": image_width,
                "height": image_height,
                "detail_hint": True,
            }
        ],
        ocr_trigger_reasons=["benchmark_product_smoke"],
        single_product_confidence=0.95,
        sellability_confidence=0.7,
        support_density=0.0,
        download_density=0.0,
        promo_density=0.0,
        usable_text_chars=0,
        product_name=product_name,
        locale_detected="ko",
        market_locale="ko_KR",
        sellability_state="sellable",
        stock_state="Unknown",
        sufficiency_state="borderline",
        quality_warning=True,
        fallback_used=False,
        weak_backfill_used=False,
        facts=[],
        ocr_text_blocks=blocks,
    )


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def _prepare_product_image(image_path: Path, *, max_side: int) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "original_image_path": str(image_path),
        "benchmark_image_path": str(image_path),
        "resized_for_benchmark": False,
    }
    original_dimensions = _image_dimensions(image_path)
    if original_dimensions is not None:
        metadata["original_dimensions"] = list(original_dimensions)
        metadata["benchmark_dimensions"] = list(original_dimensions)

    if max_side <= 0:
        return image_path, None, metadata

    try:
        from PIL import Image
    except Exception:
        metadata["resize_skipped_reason"] = "pillow_unavailable"
        return image_path, None, metadata

    with Image.open(image_path) as image:
        longest_side = max(int(image.width), int(image.height))
        if longest_side <= max_side:
            return image_path, None, metadata

        scale = max_side / float(longest_side)
        resized_size = (
            max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))),
        )
        temp_dir = tempfile.TemporaryDirectory()
        prepared_path = Path(temp_dir.name) / f"{image_path.stem}_max{max_side}{image_path.suffix}"
        image.resize(resized_size).save(prepared_path)

    metadata["benchmark_image_path"] = str(prepared_path)
    metadata["resized_for_benchmark"] = True
    metadata["benchmark_dimensions"] = [resized_size[0], resized_size[1]]
    metadata["product_max_side"] = max_side
    return prepared_path, temp_dir, metadata


def _load_funsd_manifest(funsd_zip: Path, sample_count: int) -> list[tuple[str, str]]:
    with zipfile.ZipFile(funsd_zip) as archive:
        annotation_entries = sorted(
            entry
            for entry in archive.namelist()
            if entry.startswith("dataset/training_data/annotations/") and entry.endswith(".json")
        )
        selected = annotation_entries[:sample_count]
        manifest: list[tuple[str, str]] = []
        for annotation_entry in selected:
            stem = Path(annotation_entry).stem
            image_entry = f"dataset/training_data/images/{stem}.png"
            if image_entry in archive.namelist():
                manifest.append((annotation_entry, image_entry))
    return manifest


def _extract_funsd_ground_truth(archive: zipfile.ZipFile, annotation_entry: str) -> str:
    with archive.open(annotation_entry) as handle:
        payload = json.load(handle)
    texts: list[str] = []
    for item in payload.get("form", []):
        words = item.get("words") or []
        if words:
            for word in words:
                text = str(word.get("text", "")).strip()
                if text:
                    texts.append(text)
            continue
        text = str(item.get("text", "")).strip()
        if text:
            texts.append(text)
    return " ".join(texts).strip()


def _run_funsd_benchmark(*, ocr: Any, funsd_zip: Path, sample_count: int) -> dict[str, Any]:
    if not funsd_zip.exists():
        return {"status": "skipped", "reason": f"missing zip: {funsd_zip}"}

    manifest = _load_funsd_manifest(funsd_zip, sample_count)
    rows: list[dict[str, Any]] = []
    benchmark_started_at = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir, zipfile.ZipFile(funsd_zip) as archive:
        temp_root = Path(temp_dir)
        for annotation_entry, image_entry in manifest:
            target_path = temp_root / Path(image_entry).name
            with archive.open(image_entry) as source, target_path.open("wb") as destination:
                destination.write(source.read())

            reference_text = _extract_funsd_ground_truth(archive, annotation_entry)
            sample_started_at = time.perf_counter()
            result = ocr.predict(str(target_path)) if hasattr(ocr, "predict") else ocr.ocr(str(target_path))
            predicted_text = " ".join(_extract_texts_from_paddle_result(result)).strip()

            normalized_reference = _normalize_text(reference_text)
            normalized_prediction = _normalize_text(predicted_text)
            reference_chars = list(normalized_reference)
            prediction_chars = list(normalized_prediction)
            reference_words = _tokenize(reference_text)
            prediction_words = _tokenize(predicted_text)
            precision, recall, f1 = _multiset_precision_recall_f1(reference_words, prediction_words)

            rows.append(
                {
                    "image": target_path.name,
                    "reference_chars": len(reference_chars),
                    "prediction_chars": len(prediction_chars),
                    "reference_words": len(reference_words),
                    "prediction_words": len(prediction_words),
                    "cer": round(_error_rate(reference_chars, prediction_chars), 4),
                    "wer": round(_error_rate(reference_words, prediction_words), 4),
                    "word_precision": round(precision, 4),
                    "word_recall": round(recall, 4),
                    "word_f1": round(f1, 4),
                    "elapsed_seconds": round(time.perf_counter() - sample_started_at, 2),
                }
            )

    if not rows:
        return {"status": "skipped", "reason": "no FUNSD samples available"}

    return {
        "status": "ok",
        "dataset": "FUNSD",
        "sample_count": len(rows),
        "mean_cer": round(sum(row["cer"] for row in rows) / len(rows), 4),
        "mean_wer": round(sum(row["wer"] for row in rows) / len(rows), 4),
        "mean_word_precision": round(sum(row["word_precision"] for row in rows) / len(rows), 4),
        "mean_word_recall": round(sum(row["word_recall"] for row in rows) / len(rows), 4),
        "mean_word_f1": round(sum(row["word_f1"] for row in rows) / len(rows), 4),
        "elapsed_seconds": round(time.perf_counter() - benchmark_started_at, 2),
        "rows": rows,
    }


def _run_reference_image_benchmark(
    *,
    dataset_name: str,
    ocr: Any,
    samples: list[ReferenceImageSample],
    dataset_max_side: int,
) -> dict[str, Any]:
    if not samples:
        return {"status": "skipped", "reason": f"no {dataset_name} samples discovered"}

    rows: list[dict[str, Any]] = []
    benchmark_started_at = time.perf_counter()
    for sample in samples:
        prepared_path, temp_dir, image_metadata = _prepare_product_image(sample.image_path, max_side=dataset_max_side)
        sample_started_at = time.perf_counter()
        try:
            result = ocr.predict(str(prepared_path)) if hasattr(ocr, "predict") else ocr.ocr(str(prepared_path))
        finally:
            elapsed_seconds = round(time.perf_counter() - sample_started_at, 2)
            if temp_dir is not None:
                temp_dir.cleanup()

        predicted_text = " ".join(_extract_texts_from_paddle_result(result)).strip()
        normalized_reference = _normalize_text(sample.reference_text)
        normalized_prediction = _normalize_text(predicted_text)
        reference_chars = list(normalized_reference)
        prediction_chars = list(normalized_prediction)
        reference_words = _tokenize(sample.reference_text)
        prediction_words = _tokenize(predicted_text)
        precision, recall, f1 = _multiset_precision_recall_f1(reference_words, prediction_words)
        rows.append(
            {
                "label": sample.label or sample.image_path.stem,
                "image": sample.image_path.name,
                "reference_source": sample.reference_source,
                "reference_chars": len(reference_chars),
                "prediction_chars": len(prediction_chars),
                "reference_words": len(reference_words),
                "prediction_words": len(prediction_words),
                "cer": round(_error_rate(reference_chars, prediction_chars), 4),
                "wer": round(_error_rate(reference_words, prediction_words), 4),
                "word_precision": round(precision, 4),
                "word_recall": round(recall, 4),
                "word_f1": round(f1, 4),
                "failure_tags": _reference_failure_tags(
                    prediction_chars=len(prediction_chars),
                    cer=round(_error_rate(reference_chars, prediction_chars), 4),
                    wer=round(_error_rate(reference_words, prediction_words), 4),
                    word_f1=round(f1, 4),
                ),
                "elapsed_seconds": elapsed_seconds,
                **image_metadata,
            }
        )

    return {
        "status": "ok",
        "dataset": dataset_name,
        "sample_count": len(rows),
        "mean_cer": round(sum(row["cer"] for row in rows) / len(rows), 4),
        "mean_wer": round(sum(row["wer"] for row in rows) / len(rows), 4),
        "mean_word_precision": round(sum(row["word_precision"] for row in rows) / len(rows), 4),
        "mean_word_recall": round(sum(row["word_recall"] for row in rows) / len(rows), 4),
        "mean_word_f1": round(sum(row["word_f1"] for row in rows) / len(rows), 4),
        "elapsed_seconds": round(time.perf_counter() - benchmark_started_at, 2),
        "rows": rows,
    }


def _run_product_smoke(*, ocr: Any, samples: list[ProductSample], product_max_side: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    benchmark_started_at = time.perf_counter()
    for sample in samples:
        image_path = sample.path
        if not image_path.exists():
            rows.append(
                {
                    "label": sample.label,
                    "image": image_path.name,
                    "status": "missing",
                }
            )
            continue

        prepared_path, temp_dir, image_metadata = _prepare_product_image(image_path, max_side=product_max_side)
        sample_started_at = time.perf_counter()
        try:
            result = ocr.predict(str(prepared_path)) if hasattr(ocr, "predict") else ocr.ocr(str(prepared_path))
        finally:
            elapsed_seconds = round(time.perf_counter() - sample_started_at, 2)
            if temp_dir is not None:
                temp_dir.cleanup()
        texts = _extract_texts_from_paddle_result(result)
        blocks = [{"text": text, "source": "image", "image_src": str(image_path)} for text in texts]
        snapshot = _create_snapshot(
            image_path=image_path,
            product_name=sample.product_name,
            product_tokens=list(sample.product_tokens),
            blocks=blocks,
        )
        decision = run_ocr_policy(snapshot)
        rows.append(
            {
                "label": sample.label,
                "image": image_path.name,
                "raw_block_count": len(blocks),
                "raw_char_count": len(" ".join(texts).strip()),
                "admitted_block_count": len(decision.admitted_blocks),
                "rejected_block_count": len(decision.rejected_blocks),
                "line_group_count": len(decision.line_groups),
                "direct_fact_candidate_count": len(decision.direct_fact_candidates),
                "mean_same_product_score": round(
                    float(decision.same_product_metrics.get("mean_same_product_score", 0.0) or 0.0), 4
                ),
                "failure_tags": _product_failure_tags(
                    raw_block_count=len(blocks),
                    admitted_block_count=len(decision.admitted_blocks),
                    direct_fact_candidate_count=len(decision.direct_fact_candidates),
                ),
                "status": decision.status,
                "elapsed_seconds": elapsed_seconds,
                **image_metadata,
                "preview": texts[:5],
            }
        )

    present_rows = [row for row in rows if row.get("status") != "missing"]
    if not present_rows:
        return {"status": "skipped", "reason": "no local product samples found", "rows": rows}

    return {
        "status": "ok",
        "dataset": "local_product_images",
        "sample_count": len(present_rows),
        "images_with_raw_text": sum(row["raw_block_count"] > 0 for row in present_rows),
        "images_with_admitted_text": sum(row["admitted_block_count"] > 0 for row in present_rows),
        "images_with_direct_fact_candidates": sum(row["direct_fact_candidate_count"] > 0 for row in present_rows),
        "mean_raw_blocks": round(sum(row["raw_block_count"] for row in present_rows) / len(present_rows), 2),
        "mean_raw_chars": round(sum(row["raw_char_count"] for row in present_rows) / len(present_rows), 2),
        "mean_admitted_blocks": round(
            sum(row["admitted_block_count"] for row in present_rows) / len(present_rows), 2
        ),
        "mean_direct_fact_candidates": round(
            sum(row["direct_fact_candidate_count"] for row in present_rows) / len(present_rows), 2
        ),
        "mean_same_product_score": round(
            sum(float(row["mean_same_product_score"]) for row in present_rows) / len(present_rows), 4
        ),
        "mean_rejected_blocks": round(
            sum(row["rejected_block_count"] for row in present_rows) / len(present_rows), 2
        ),
        "failure_tag_counts": _failure_tag_counts(present_rows),
        "elapsed_seconds": round(time.perf_counter() - benchmark_started_at, 2),
        "rows": rows,
    }


def _reference_failure_tags(*, prediction_chars: int, cer: float, wer: float, word_f1: float) -> list[str]:
    tags: list[str] = []
    if prediction_chars == 0:
        tags.append("no_text_detected")
    if word_f1 < 0.25:
        tags.append("small_text_miss")
    elif word_f1 < 0.5:
        tags.append("partial_text_loss")
    if cer > 0.8:
        tags.append("char_drift")
    if wer > 1.0:
        tags.append("line_order_break")
    return tags


def _product_failure_tags(*, raw_block_count: int, admitted_block_count: int, direct_fact_candidate_count: int) -> list[str]:
    tags: list[str] = []
    if raw_block_count == 0:
        tags.append("no_text_detected")
    if raw_block_count > 0 and admitted_block_count == 0:
        tags.append("admission_drop")
    if admitted_block_count > 0 and direct_fact_candidate_count == 0:
        tags.append("no_trusted_direct_candidate")
    return tags


def _failure_tag_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for tag in row.get("failure_tags", []):
            counts[str(tag)] = counts.get(str(tag), 0) + 1
    return counts


def _run_public_dataset_benchmarks(args: argparse.Namespace, ocr: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "finegrainocr": None,
        "unitail_ocr": None,
        "korean_product_labels": None,
    }

    if args.finegrainocr_root:
        finegrain_root = Path(args.finegrainocr_root)
        finegrain_samples = _discover_finegrainocr_samples(
            finegrain_root,
            max(0, args.finegrainocr_sample_count),
        )
        payload["finegrainocr"] = _run_reference_image_benchmark(
            dataset_name="FineGrainOCR",
            ocr=ocr,
            samples=finegrain_samples,
            dataset_max_side=max(0, args.dataset_max_side),
        )

    if args.unitail_ocr_root:
        unitail_root = Path(args.unitail_ocr_root)
        unitail_samples = _discover_unitail_ocr_samples(
            unitail_root,
            max(0, args.unitail_ocr_sample_count),
        )
        payload["unitail_ocr"] = _run_reference_image_benchmark(
            dataset_name="Unitail-OCR",
            ocr=ocr,
            samples=unitail_samples,
            dataset_max_side=max(0, args.dataset_max_side),
        )

    if args.korean_product_labels_root:
        korean_root = Path(args.korean_product_labels_root)
        korean_samples = _discover_korean_product_label_samples(
            korean_root,
            max(0, args.korean_product_labels_sample_count),
        )
        payload["korean_product_labels"] = _run_product_smoke(
            ocr=ocr,
            samples=korean_samples,
            product_max_side=max(0, args.dataset_max_side),
        )
        if payload["korean_product_labels"] is not None:
            payload["korean_product_labels"]["dataset"] = "Korean_Product_Labels_Image_Dataset"

    return payload


def _print_text(payload: dict[str, Any]) -> None:
    print("OCR benchmark summary")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = _parse_args()
    selected_product_samples = _resolve_product_samples(args)
    ocr = _create_ocr_engine()

    payload: dict[str, Any] = {
        "benchmark": {
            "funsd": None,
            "product_smoke": None,
            "public_datasets": {
                "finegrainocr": None,
                "unitail_ocr": None,
                "korean_product_labels": None,
            },
        }
    }

    if not args.skip_funsd:
        payload["benchmark"]["funsd"] = _run_funsd_benchmark(
            ocr=ocr,
            funsd_zip=Path(args.funsd_zip),
            sample_count=max(1, args.funsd_sample_count),
        )
    if not args.skip_product_smoke:
        payload["benchmark"]["product_smoke"] = _run_product_smoke(
            ocr=ocr,
            samples=selected_product_samples,
            product_max_side=max(0, args.product_max_side),
        )
    payload["benchmark"]["public_datasets"] = _run_public_dataset_benchmarks(args, ocr)

    if args.output == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)


if __name__ == "__main__":
    main()
