from __future__ import annotations

from scripts.run_crawl4ai_preprocessing_benchmark import _selected_cases, _selected_profiles, _summarize_payload


def test_selected_cases_returns_fixture_or_live_subset() -> None:
    fixture_cases = _selected_cases(fixtures_only=True, live_only=False)
    live_cases = _selected_cases(fixtures_only=False, live_only=True)
    all_cases = _selected_cases(fixtures_only=False, live_only=False)

    assert fixture_cases
    assert live_cases
    assert len(all_cases) == len(fixture_cases) + len(live_cases)
    assert all(case["case_type"] == "fixture" for case in fixture_cases)
    assert all(case["case_type"] == "live" for case in live_cases)


def test_selected_profiles_defaults_to_full_quality_tuning_matrix() -> None:
    profiles = _selected_profiles(None)

    assert profiles == [
        "baseline_render",
        "wait_images_render",
        "interaction_render",
        "magic_render",
        "stealth_render",
        "text_rich_render",
    ]


def test_summarize_payload_groups_candidate_flags_and_regressions() -> None:
    payload_summary = _summarize_payload(
        [
            {
                "profile_name": "baseline_render",
                "ocr_mode": "eligible_all",
                "rows": [
                    {"candidate_source": "raw_html", "recommendation_flag": "candidate"},
                    {"candidate_source": "cleaned_html", "recommendation_flag": "reject"},
                ],
                "parity_reports": [
                    {"regression_stages": []},
                    {"regression_stages": ["classification", "evidence"]},
                ],
            }
        ]
    )

    assert payload_summary["by_source"]["raw_html"]["rows"] == 1
    assert payload_summary["by_source"]["raw_html"]["candidate"] == 1
    assert payload_summary["by_source"]["cleaned_html"]["reject"] == 1
    assert payload_summary["by_source"]["cleaned_html"]["classification_regressions"] == 1
    assert payload_summary["by_source"]["cleaned_html"]["evidence_regressions"] == 1
    assert payload_summary["by_profile"]["baseline_render"]["ocr_mode"] == "eligible_all"
    assert payload_summary["by_profile"]["baseline_render"]["rows"] == 2
    assert payload_summary["by_profile"]["baseline_render"]["reject"] == 1
