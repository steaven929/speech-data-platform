#!/usr/bin/env python3
"""Export Potato audio annotations as readable JSON."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "annotation_output"


def iter_user_state_files():
    for path in sorted(OUTPUT_DIR.glob("*/user_state.json")):
        if path.parent.name.startswith("."):
            continue
        yield path


def extract_segments(user_state_path: Path):
    with user_state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    user_id = state.get("user_id") or user_state_path.parent.name
    extracted = []

    for instance_id, entries in state.get("instance_id_to_label_to_value", {}).items():
        for key, raw_value in entries:
            if key.get("schema") != "transcript_segments" or key.get("name") != "_data":
                continue
            if not raw_value:
                continue

            payload = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
            for segment in payload.get("segments", []):
                text = segment.get("text", "")
                extracted.append(
                    {
                        "user_id": user_id,
                        "instance_id": instance_id,
                        "segment_id": segment.get("id"),
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "speaker": segment.get("label"),
                        "speaker_readable": {
                            "caller": "来电人",
                            "agent": "坐席",
                        }.get(segment.get("label"), segment.get("label")),
                        "text": text,
                        "text_readable": text,
                    }
                )

    return extracted


def main():
    all_segments = []
    for user_state_path in iter_user_state_files():
        all_segments.extend(extract_segments(user_state_path))

    output_path = OUTPUT_DIR / "readable_annotations.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_segments, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(output_path)


if __name__ == "__main__":
    main()
