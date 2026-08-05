import json

from potato.audio_cer_review import (
    find_matching_submissions,
    normalize_cer_text,
    pairwise_cer,
)
from potato.item_state_management import Label


class _State:
    def __init__(self, recording_id, text, submitted=True):
        value = json.dumps({"segments": [{
            "id": "s1", "start_time": 0, "end_time": 1, "text": text,
        }]})
        self.instance_id_to_label_to_value = {
            recording_id: {Label("transcript_segments", "_data"): value}
        }
        self._submitted = submitted

    def is_submitted(self, _recording_id):
        return self._submitted


class _Manager:
    def __init__(self, states):
        self.states = states

    def get_user_ids(self):
        return self.states.keys()

    def get_user_state(self, username):
        return self.states[username]


def test_normalization_ignores_formatting_but_keeps_characters():
    assert normalize_cer_text("ＡＢ，你 好！") == "ab你好"
    assert pairwise_cer("你好，世界", "你好世界") == 0


def test_pairwise_cer_uses_longer_text_as_symmetric_denominator():
    assert pairwise_cer("abcdefghij", "abcdefghiX") == 0.1


def test_only_submitted_annotators_in_passing_pairs_are_matched():
    manager = _Manager({
        "a": _State("rec", "这是一段正确文本"),
        "b": _State("rec", "这是一段正确文木"),
        "c": _State("rec", "完全不同的内容"),
        "draft": _State("rec", "这是一段正确文本", submitted=False),
    })
    matched, comparisons = find_matching_submissions("rec", manager, 0.15)
    assert matched == ["a", "b"]
    assert len(comparisons) == 3
