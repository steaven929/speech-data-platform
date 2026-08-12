from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_in_progress_audio_reviews_are_editable_without_cer_stage():
    script = (ROOT / "potato" / "static" / "direct-audio-review.js").read_text(
        encoding="utf-8"
    )

    assert 'const editable = selected.review_status === "in_progress";' in script
    assert 'selected.workflow_stage === "needs_manual_review"' not in script
