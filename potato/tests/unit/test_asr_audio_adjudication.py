import json
import subprocess
from pathlib import Path

from potato.adjudication import (
    AdjudicationDecision,
    AdjudicationItem,
    AdjudicationManager,
)


ROOT = Path(__file__).parents[2]


def make_manager(tmp_path):
    manager = AdjudicationManager(
        {
            "output_annotation_dir": str(tmp_path / "annotation_output"),
            "annotation_schemes": [
                {
                    "annotation_type": "audio_annotation",
                    "name": "transcript_segments",
                }
            ],
            "adjudication": {
                "enabled": True,
                "adjudicator_users": ["admin"],
                "show_all_items": True,
            },
        }
    )
    return manager


def test_audio_adoption_is_saved_as_complete_segments(tmp_path):
    manager = make_manager(tmp_path)
    user2_segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.2,
            "label": "caller",
            "text": "你好",
            "annotations": {},
        },
        {
            "id": "segment_2",
            "start_time": 1.3,
            "end_time": 2.5,
            "label": "agent",
            "text": "您好",
            "annotations": {},
        },
    ]
    tester_segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.1,
            "label": "caller",
            "text": "你好",
            "annotations": {},
        }
    ]
    manager.queue["recording_1"] = AdjudicationItem(
        instance_id="recording_1",
        annotations={
            "user2": {
                "transcript_segments": json.dumps(
                    {"segments": user2_segments}, ensure_ascii=False
                )
            },
            "annotator_a": {
                "transcript_segments": json.dumps(
                    {"segments": tester_segments}, ensure_ascii=False
                )
            },
        },
        span_annotations={},
        behavioral_data={},
        agreement_scores={"transcript_segments": 0.0},
        overall_agreement=0.0,
        num_annotators=2,
    )
    decision = AdjudicationDecision(
        instance_id="recording_1",
        adjudicator_id="admin",
        timestamp="2026-07-31T00:00:00",
        label_decisions={
            "transcript_segments": {
                "adopted_annotations": [
                    {"annotator": "user2", "idx": "0", "type": "audio"},
                    {"annotator": "user2", "idx": "1", "type": "audio"},
                ]
            }
        },
        span_decisions=[],
        source={"transcript_segments": "adjudicator"},
        confidence="high",
        notes="full review",
        error_taxonomy=[],
    )

    assert manager.submit_decision(decision) is True

    saved = manager.get_decision("recording_1")
    assert saved.label_decisions["transcript_segments"] == {
        "segments": user2_segments
    }
    decisions_file = (
        tmp_path / "annotation_output" / "adjudication" / "decisions.json"
    )
    persisted = json.loads(decisions_file.read_text(encoding="utf-8"))
    assert persisted["decisions"][0]["label_decisions"]["transcript_segments"] == {
        "segments": user2_segments
    }


def test_audio_data_label_is_unwrapped_for_the_review_page(tmp_path):
    manager = make_manager(tmp_path)
    segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.2,
            "label": "caller",
            "text": "你好",
        }
    ]

    serialized = manager._serialize_labels(
        {
            FakeLabel("transcript_segments", "_data"): json.dumps(
                {"segments": segments}, ensure_ascii=False
            )
        }
    )

    assert serialized["transcript_segments"] == {"segments": segments}


class FakeLabel:
    def __init__(self, schema, name):
        self.schema = schema
        self.name = name

    def get_schema(self):
        return self.schema

    def get_name(self):
        return self.name


def test_audio_review_form_renders_segment_transcript_text():
    forms_script = ROOT / "potato" / "static" / "adjudication-forms.js"
    node_script = r"""
const fs = require("fs");
global.window = {};
global.document = {
  createElement: function () {
    return {
      innerHTML: "",
      set textContent(value) {
        this.innerHTML = String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;");
      }
    };
  }
};
eval(fs.readFileSync(process.argv[1], "utf8"));
const html = window.AdjudicationForms.renderForm(
  {name: "transcript_segments", annotation_type: "audio_annotation"},
  {
    user2: {
      transcript_segments: {
        segments: [{
          label: "caller",
          start_time: 1.2,
          end_time: 2.8,
          text: "需要显示的转写文本"
        }]
      }
    }
  },
  {},
  {show_annotator_names: true, fast_decision_warning_ms: 0},
  {}
);
process.stdout.write(html);
"""

    result = subprocess.run(
        ["node", "-e", node_script, str(forms_script)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "需要显示的转写文本" in result.stdout
