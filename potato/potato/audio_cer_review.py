"""Character-error-rate helpers for ASR submission quality control."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, Iterable, List, Tuple


def normalize_cer_text(value: Any) -> str:
    """Return text suitable for CER comparison.

    NFKC folds full-width forms, casefold handles Latin case, and Unicode
    punctuation/whitespace are ignored so formatting does not create false
    transcription disagreements.
    """
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(
        char for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def levenshtein_distance(left: str, right: str) -> int:
    """Calculate edit distance using O(min(n, m)) memory."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def pairwise_cer(left: Any, right: Any) -> float:
    """Return symmetric CER for two annotator texts.

    There is no ground-truth side in an annotator pair, so the edit distance is
    divided by the longer normalized text. Two empty texts are identical.
    """
    left_text = normalize_cer_text(left)
    right_text = normalize_cer_text(right)
    denominator = max(len(left_text), len(right_text))
    if denominator == 0:
        return 0.0
    return levenshtein_distance(left_text, right_text) / denominator


def segments_text(segments: Iterable[Dict[str, Any]]) -> str:
    """Join segment text in chronological order without injecting separators."""
    ordered = sorted(
        (segment for segment in segments if isinstance(segment, dict)),
        key=lambda segment: (
            float(segment.get("start_time", 0) or 0),
            float(segment.get("end_time", 0) or 0),
            str(segment.get("id", "")),
        ),
    )
    return "".join(str(segment.get("text", "")) for segment in ordered)


def parse_annotation_segments(value: Any) -> List[Dict[str, Any]]:
    data = json.loads(value) if isinstance(value, str) else value
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise ValueError("标注数据缺少音频片段")
    return [segment for segment in data["segments"] if isinstance(segment, dict)]


def annotation_text(user_state: Any, recording_id: str) -> str:
    labels = user_state.instance_id_to_label_to_value.get(str(recording_id), {})
    for label, value in labels.items():
        schema = getattr(label, "get_schema", lambda: "")()
        name = getattr(label, "get_name", lambda: "")()
        if schema == "transcript_segments" and name == "_data":
            return segments_text(parse_annotation_segments(value))
    raise ValueError("没有找到对应的音频标注")


def find_matching_submissions(
    recording_id: str,
    user_state_manager: Any,
    threshold: float,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Find submitted annotators participating in at least one passing pair."""
    submitted: List[Tuple[str, str]] = []
    for username in sorted(user_state_manager.get_user_ids()):
        state = user_state_manager.get_user_state(username)
        if not state or not state.is_submitted(str(recording_id)):
            continue
        try:
            submitted.append((str(username), annotation_text(state, recording_id)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    matched = set()
    comparisons = []
    for index, (left_user, left_text) in enumerate(submitted):
        for right_user, right_text in submitted[index + 1:]:
            score = pairwise_cer(left_text, right_text)
            passed = score <= threshold
            comparisons.append({
                "annotators": [left_user, right_user],
                "cer": score,
                "passed": passed,
            })
            if passed:
                matched.update((left_user, right_user))
    return sorted(matched), comparisons
