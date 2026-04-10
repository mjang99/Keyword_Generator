from __future__ import annotations

import json
from pathlib import Path

from scripts import evaluate_ocr_benchmark as benchmark

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "ocr_benchmark_public"


def test_extract_reference_text_from_google_vision_json_prefers_full_text() -> None:
    payload = {
        "responses": [
            {
                "fullTextAnnotation": {"text": "Retinol Cream 30ml"},
                "textAnnotations": [{"description": "fallback"}],
            }
        ]
    }

    assert benchmark._extract_reference_text_from_google_vision_json(payload) == "Retinol Cream 30ml"


def test_extract_reference_text_from_google_vision_json_reads_top_level_list_description() -> None:
    payload = [{"locale": "fr", "description": "ORIGINALE\nLAIT\n"}]

    assert benchmark._extract_reference_text_from_google_vision_json(payload) == "ORIGINALE\nLAIT"


def test_discover_finegrainocr_samples_reads_same_stem_google_vision_json() -> None:
    samples = benchmark._discover_finegrainocr_samples(FIXTURE_ROOT / "finegrain", 5)

    assert len(samples) == 1
    assert samples[0].dataset == "FineGrainOCR"
    assert samples[0].reference_source == "google_vision_json"
    assert samples[0].reference_text == "APRILSKIN calming serum"


def test_discover_finegrainocr_samples_reads_mirrored_images_text_layout() -> None:
    samples = benchmark._discover_finegrainocr_samples(FIXTURE_ROOT / "finegrain_mirrored", 5)

    assert len(samples) == 1
    assert samples[0].reference_text == "Mirrored OCR text"


def test_discover_unitail_ocr_samples_reads_txt_and_json_labels() -> None:
    samples = benchmark._discover_unitail_ocr_samples(FIXTURE_ROOT / "unitail", 5)

    assert len(samples) == 2
    assert [sample.reference_text for sample in samples] == ["Hydro Mask", "Cicapair Cream"]


def test_discover_unitail_ocr_samples_reads_mirrored_images_texts_layout() -> None:
    samples = benchmark._discover_unitail_ocr_samples(FIXTURE_ROOT / "unitail_mirrored", 5)

    assert len(samples) == 1
    assert samples[0].reference_text == "Retail Sample"


def test_discover_unitail_ocr_samples_reads_manifest_annotations() -> None:
    samples = benchmark._discover_unitail_ocr_samples(FIXTURE_ROOT / "unitail_manifest", 5)

    assert len(samples) == 1
    assert samples[0].reference_source == "ocr_gt.json#annotations"
    assert samples[0].reference_text == "Cicapair Cream 50ml"


def test_discover_korean_product_label_samples_uses_parent_folder_as_product_name() -> None:
    samples = benchmark._discover_korean_product_label_samples(FIXTURE_ROOT / "korean", 5)

    assert len(samples) == 1
    assert samples[0].product_name == "skin food"
    assert "skin" in samples[0].product_tokens
    assert "food" in samples[0].product_tokens


def test_discover_korean_product_label_samples_skips_local_benchmark_derivatives() -> None:
    samples = benchmark._discover_korean_product_label_samples(FIXTURE_ROOT / "korean_generated", 5)

    assert [sample.label for sample in samples] == ["Kgen_Korean Product Labels_1005_1"]
