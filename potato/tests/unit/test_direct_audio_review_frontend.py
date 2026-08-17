from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_in_progress_audio_reviews_are_editable_without_cer_stage():
    script = (ROOT / "potato" / "static" / "direct-audio-review.js").read_text(
        encoding="utf-8"
    )

    assert 'const editable = selected.review_status === "in_progress";' in script
    assert 'selected.workflow_stage === "needs_manual_review"' not in script


def test_direct_audio_review_frontend_has_segment_playback_and_method_filter():
    script = (ROOT / "potato" / "static" / "direct-audio-review.js").read_text(
        encoding="utf-8"
    )
    template = (ROOT / "potato" / "templates" / "adjudication.html").read_text(
        encoding="utf-8"
    )

    assert "direct-review-segment-play" in script
    assert "timeupdate" in script
    assert "audio.currentTime = start;" in script
    assert 'params.set("final_method", methodSelect.value);' in script
    assert 'id="direct-review-final-method"' in template
    assert "管理员人工定稿" in script
    for method in ("pair_cer", "three_way_medoid", "manual"):
        assert method in template
