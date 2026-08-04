import json
import struct
import wave

import pytest


class FakeSheet:
    def __init__(self, rows):
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(row) for row in rows)

    def cell_value(self, row, column):
        return self._rows[row][column]


def write_silent_wav(path, seconds=4, rate=8000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(seconds * rate))


def write_alaw_wav(path, seconds=2, rate=8000):
    data = b"\xd5" * int(seconds * rate)
    fmt = struct.pack("<HHIIHH", 6, 1, rate, rate, 1, 8)
    riff_size = 4 + (8 + len(fmt)) + (8 + len(data))
    path.write_bytes(
        b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
        + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )


def test_parse_legacy_sheet_reads_original_columns_and_audio_basename():
    from potato.admin_audio_import import parse_legacy_sheet

    sheet = FakeSheet([
        ["", "录音地址", "阿里转译"],
        [1, "http://internal/voice/10001.wav", "客服您好。\n\n来电人你好。"],
    ])

    rows = parse_legacy_sheet(sheet)

    assert len(rows) == 1
    assert rows[0].item_id == "10001"
    assert rows[0].audio_filename == "10001.wav"
    assert rows[0].transcript == "客服您好。\n\n来电人你好。"


def test_build_audio_item_splits_paragraphs_and_allocates_continuous_time(tmp_path):
    from potato.admin_audio_import import TranscriptRow, build_audio_item

    audio_path = tmp_path / "10001.wav"
    write_silent_wav(audio_path, seconds=4)
    row = TranscriptRow("10001", "10001.wav", "甲甲。\n\n乙乙乙。")

    item = build_audio_item(row, audio_path, "/media/10001.wav")

    assert item["id"] == "10001"
    assert item["audio_url"] == "/media/10001.wav"
    assert [segment["text"] for segment in item["segments"]] == ["甲甲。", "乙乙乙。"]
    assert [segment["label"] for segment in item["segments"]] == ["agent", "caller"]
    assert item["segments"][0]["start_time"] == 0
    assert item["segments"][0]["end_time"] == pytest.approx(4 * 3 / 7, abs=0.001)
    assert item["segments"][1]["start_time"] == item["segments"][0]["end_time"]
    assert item["segments"][1]["end_time"] == 4


def test_build_audio_item_reads_alaw_wav_duration_without_decoding(tmp_path):
    from potato.admin_audio_import import TranscriptRow, build_audio_item

    audio_path = tmp_path / "alaw.wav"
    write_alaw_wav(audio_path, seconds=2)
    item = build_audio_item(
        TranscriptRow("alaw", "alaw.wav", "一段转写"),
        audio_path,
        "/media/alaw.wav",
    )

    assert item["segments"][0]["end_time"] == 2


def test_preview_uses_uploaded_audio_as_subset_and_ignores_other_excel_rows(tmp_path):
    from potato.admin_audio_import import TranscriptRow, preview_rows

    present = tmp_path / "10001.wav"
    write_silent_wav(present)
    rows = [
        TranscriptRow("10001", "10001.wav", "内容一"),
        TranscriptRow("10002", "10002.wav", "内容二"),
        TranscriptRow("10003", "10003.wav", "内容三"),
    ]

    preview = preview_rows(rows, [present], {"10002"}, tmp_path / "media")

    assert [entry.item_id for entry in preview.ready] == ["10001"]
    assert preview.duplicate_ids == []
    assert preview.missing_audio == []
    assert preview.ignored_ids == ["10002", "10003"]
    assert preview.can_confirm is True


def test_preview_rejects_uploaded_audio_that_has_no_excel_row(tmp_path):
    from potato.admin_audio_import import TranscriptRow, preview_rows

    unknown = tmp_path / "unknown.wav"
    write_silent_wav(unknown)

    preview = preview_rows(
        [TranscriptRow("10001", "10001.wav", "内容")],
        [unknown],
        set(),
        tmp_path / "media",
    )

    assert preview.ready == []
    assert preview.unmatched_audio == ["unknown.wav"]
    assert preview.can_confirm is False


def test_commit_preview_appends_json_copies_audio_and_registers_runtime_item(tmp_path):
    from potato.admin_audio_import import TranscriptRow, commit_preview, preview_rows

    source = tmp_path / "10001.wav"
    write_silent_wav(source)
    media_dir = tmp_path / "media"
    data_file = tmp_path / "items.json"
    data_file.write_text(json.dumps([{"id": "old"}]), encoding="utf-8")
    preview = preview_rows(
        [TranscriptRow("10001", "10001.wav", "客服。\n\n来电人。")],
        [source],
        set(),
        media_dir,
    )

    class ItemManager:
        def __init__(self):
            self.items = {}

        def add_item(self, item_id, item):
            self.items[item_id] = item

    manager = ItemManager()
    imported = commit_preview(preview, data_file, media_dir, manager)

    saved = json.loads(data_file.read_text(encoding="utf-8"))
    assert [item["id"] for item in saved] == ["old", "10001"]
    assert (media_dir / "10001.wav").is_file()
    assert manager.items["10001"] == imported[0]


def test_commit_preview_writes_nothing_when_preview_has_errors(tmp_path):
    from potato.admin_audio_import import TranscriptRow, commit_preview, preview_rows

    data_file = tmp_path / "items.json"
    data_file.write_text("[]", encoding="utf-8")
    preview = preview_rows(
        [TranscriptRow("missing", "missing.wav", "内容")],
        [],
        set(),
        tmp_path / "media",
    )

    with pytest.raises(ValueError, match="校验未通过"):
        commit_preview(preview, data_file, tmp_path / "media", object())

    assert data_file.read_text(encoding="utf-8") == "[]"
    assert not (tmp_path / "media").exists()
