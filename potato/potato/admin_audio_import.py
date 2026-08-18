"""Legacy XLS + WAV import helpers for the administrator dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class TranscriptRow:
    item_id: str
    audio_filename: str
    transcript: str
    category: str = "未分类"


@dataclass
class ImportPreview:
    ready: list[TranscriptRow] = field(default_factory=list)
    ready_items: list[dict] = field(default_factory=list)
    audio_paths: dict[str, Path] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    missing_audio: list[str] = field(default_factory=list)
    ignored_ids: list[str] = field(default_factory=list)
    unmatched_audio: list[str] = field(default_factory=list)
    invalid_rows: list[str] = field(default_factory=list)

    @property
    def can_confirm(self) -> bool:
        return bool(self.ready or self.ready_items) and not (
            self.missing_audio
            or self.unmatched_audio
            or self.invalid_rows
        )

    def to_dict(self) -> dict:
        ready_ids = [row.item_id for row in self.ready] + [
            str(item.get("id", "")) for item in self.ready_items
        ]
        return {
            "ready": ready_ids,
            "duplicate_ids": self.duplicate_ids,
            "missing_audio": self.missing_audio,
            "ignored_ids": self.ignored_ids,
            "unmatched_audio": self.unmatched_audio,
            "invalid_rows": self.invalid_rows,
            "can_confirm": self.can_confirm,
        }


def _clean_header(value) -> str:
    return str(value or "").strip()


def _audio_basename(address: str) -> str:
    path = unquote(urlparse(str(address).strip()).path)
    filename = Path(path).name
    if not filename:
        raise ValueError("录音地址中没有文件名")
    if Path(filename).suffix.lower() != ".wav":
        raise ValueError(f"仅支持 WAV 音频：{filename}")
    return filename


def _json_audio_basename(item: dict) -> str:
    audio_value = (
        item.get("audio_url")
        or item.get("audio")
        or item.get("audio_path")
        or item.get("file")
        or f"{item.get('id')}.wav"
    )
    return _audio_basename(str(audio_value))


_TRANSCRIPT_COLUMN_NAMES = ("阿里转译", "预转写", "转写")
_DEFAULT_CATEGORY = "未分类"


def parse_legacy_sheet(sheet) -> list[TranscriptRow]:
    """Parse the original worksheet containing 录音地址 and a transcript column."""
    if sheet.nrows < 2:
        raise ValueError("Excel 中没有可导入的数据")

    headers = {
        _clean_header(sheet.cell_value(0, column)): column
        for column in range(sheet.ncols)
    }
    if "录音地址" not in headers:
        raise ValueError("Excel 缺少列：录音地址")
    transcript_column = next(
        (headers[name] for name in _TRANSCRIPT_COLUMN_NAMES if name in headers),
        None,
    )
    if transcript_column is None:
        raise ValueError("Excel 缺少转写列（阿里转译 / 预转写 / 转写）")
    category_column = headers.get("类别")

    rows = []
    for row_index in range(1, sheet.nrows):
        address = _clean_header(sheet.cell_value(row_index, headers["录音地址"]))
        transcript = _clean_header(sheet.cell_value(row_index, transcript_column))
        if not address and not transcript:
            continue
        if not address or not transcript:
            raise ValueError(f"Excel 第 {row_index + 1} 行录音地址或转写为空")
        filename = _audio_basename(address)
        category = (
            _clean_header(sheet.cell_value(row_index, category_column))
            if category_column is not None
            else ""
        )
        rows.append(TranscriptRow(
            Path(filename).stem,
            filename,
            transcript,
            category or _DEFAULT_CATEGORY,
        ))
    if not rows:
        raise ValueError("Excel 中没有可导入的数据")
    return rows


def apply_category_override(
    rows: list[TranscriptRow], category: str | None
) -> list[TranscriptRow]:
    """Apply a user-supplied category label to every row.

    Blank input leaves the rows untouched (Excel 类别 column, or 未分类).
    """
    category = (category or "").strip()
    if not category:
        return rows
    return [replace(row, category=category) for row in rows]


def parse_legacy_xls(path: os.PathLike | str) -> list[TranscriptRow]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("解析旧版 .xls 需要安装 xlrd>=2.0.1") from exc

    workbook = xlrd.open_workbook(str(path), on_demand=True)
    try:
        return parse_legacy_sheet(workbook.sheet_by_index(0))
    finally:
        workbook.release_resources()


def _wav_duration(path: os.PathLike | str) -> float:
    try:
        byte_rate = None
        data_size = None
        with Path(path).open("rb") as audio:
            if audio.read(4) != b"RIFF":
                raise ValueError("不是 RIFF 文件")
            audio.read(4)
            if audio.read(4) != b"WAVE":
                raise ValueError("不是 WAVE 文件")
            while True:
                chunk_header = audio.read(8)
                if not chunk_header:
                    break
                if len(chunk_header) != 8:
                    raise ValueError("WAV 区块头不完整")
                chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
                if chunk_id == b"fmt ":
                    fmt = audio.read(chunk_size)
                    if len(fmt) < 12:
                        raise ValueError("WAV fmt 区块不完整")
                    byte_rate = struct.unpack_from("<I", fmt, 8)[0]
                elif chunk_id == b"data":
                    data_size = chunk_size
                    audio.seek(chunk_size, 1)
                else:
                    audio.seek(chunk_size, 1)
                if chunk_size % 2:
                    audio.seek(1, 1)
                if byte_rate and data_size is not None:
                    return data_size / byte_rate
        raise ValueError("WAV 缺少 fmt 或 data 区块")
    except (OSError, ValueError, struct.error) as exc:
        raise ValueError(f"无法读取 WAV 音频：{Path(path).name}") from exc


def _split_transcript(transcript: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n+", transcript) if part.strip()]


def build_audio_item(
    row: TranscriptRow,
    audio_path: os.PathLike | str,
    media_url: str,
) -> dict:
    segments_text = _split_transcript(row.transcript)
    if not segments_text:
        raise ValueError(f"录音 {row.item_id} 没有可用转写")

    duration = _wav_duration(audio_path)
    weights = [max(len(text), 1) for text in segments_text]
    total_weight = sum(weights)
    elapsed = 0.0
    segments = []
    for index, (text, weight) in enumerate(zip(segments_text, weights), start=1):
        end = duration if index == len(segments_text) else round(
            elapsed + duration * weight / total_weight, 3
        )
        is_agent = index % 2 == 1
        segments.append({
            "id": f"seg_{index:04d}",
            "start_time": round(elapsed, 3),
            "end_time": round(end, 3),
            "text": text,
            "label": "agent" if is_agent else "caller",
            "speaker_role": "role_1" if is_agent else "role_0",
        })
        elapsed = end

    return {
        "id": row.item_id,
        "sample_id": row.item_id,
        "audio_url": media_url,
        "segments": segments,
        "category": row.category,
        "source_transcript_file": "管理员批量导入",
    }


def _normalise_segment_for_import(segment: dict, index: int) -> dict:
    annotations = segment.get("annotations") if isinstance(segment.get("annotations"), dict) else {}
    return {
        "id": str(segment.get("id") or segment.get("segment_id") or f"seg_{index:04d}"),
        "start_time": float(segment.get("start_time", segment.get("start", 0)) or 0),
        "end_time": float(segment.get("end_time", segment.get("end", 0)) or 0),
        "text": str(segment.get("text", "") or ""),
        "label": str(segment.get("label") or segment.get("speaker") or "agent"),
        "speaker_role": str(segment.get("speaker_role") or ""),
        "annotations": annotations,
    }


def _item_from_json_record(record: dict, default_category: str | None = None) -> dict:
    item_id = str(
        record.get("id")
        or record.get("sample_id")
        or record.get("recording_id")
        or record.get("instance_id")
        or ""
    ).strip()
    if not item_id:
        raise ValueError("JSON 记录缺少 id / recording_id")

    audio_url = str(
        record.get("audio_url")
        or record.get("audio")
        or record.get("audio_path")
        or record.get("file")
        or f"/media/{item_id}.wav"
    ).strip()
    category = (default_category or "").strip() or str(record.get("category") or "未分类").strip() or "未分类"

    transcript = str(record.get("transcript") or "").strip()
    raw_segments = record.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = record.get("transcript_segments")
    if not isinstance(raw_segments, list):
        transcript = transcript or str(record.get("text") or "").strip()
        raw_segments = [{"id": "seg_0001", "start_time": 0, "end_time": 0, "text": transcript, "label": "agent"}] if transcript else []
    if not raw_segments:
        raise ValueError(f"JSON 记录 {item_id} 缺少 segments / transcript")

    segments = [
        _normalise_segment_for_import(segment, index)
        for index, segment in enumerate(raw_segments, start=1)
        if isinstance(segment, dict)
    ]
    if not segments:
        raise ValueError(f"JSON 记录 {item_id} 没有可用分段")
    segments.sort(key=lambda segment: (segment["start_time"], segment["end_time"]))

    item = dict(record)
    item.update({
        "id": item_id,
        "sample_id": str(record.get("sample_id") or item_id),
        "audio_url": audio_url,
        "segments": segments,
        "category": category,
        "transcript": transcript or str(record.get("text") or ""),
        "source_transcript_file": str(record.get("source_transcript_file") or "管理员 JSON 导入"),
    })
    return item


def _segments_need_audio_timing(item: dict) -> bool:
    segments = item.get("segments")
    if not isinstance(segments, list) or not segments:
        return True
    return not any(
        isinstance(segment, dict)
        and isinstance(segment.get("start_time"), (int, float))
        and isinstance(segment.get("end_time"), (int, float))
        and segment.get("end_time") > segment.get("start_time")
        for segment in segments
    )


def _build_json_audio_item(item: dict, audio_path: os.PathLike | str, media_url: str) -> dict:
    if _segments_need_audio_timing(item):
        transcript = str(item.get("transcript") or "")
        if not transcript and isinstance(item.get("segments"), list):
            transcript = "\n\n".join(
                str(segment.get("text") or "").strip()
                for segment in item["segments"]
                if isinstance(segment, dict) and str(segment.get("text") or "").strip()
            )
        row = TranscriptRow(
            str(item["id"]),
            Path(media_url).name,
            transcript,
            str(item.get("category") or _DEFAULT_CATEGORY),
        )
        rebuilt = build_audio_item(row, audio_path, media_url)
        merged = dict(item)
        merged.update({
            "audio_url": media_url,
            "segments": rebuilt["segments"],
            "source_transcript_file": str(item.get("source_transcript_file") or "管理员 JSON 导入"),
        })
        return merged
    updated = dict(item)
    updated["audio_url"] = media_url
    return updated


def _records_from_export_payload(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("JSON 顶层必须是数组或对象")
    for key in ("items", "instances", "recordings", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    final_results = payload.get("final_results")
    if isinstance(final_results, list) and final_results:
        return final_results
    annotations = payload.get("annotations")
    if isinstance(annotations, list) and annotations:
        # 平台导出的标注 JSON：同一录音可能有多个标注员，这里取每条录音第一份
        # 标注作为重新导入任务的初始转写分段。
        first_by_recording = {}
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            recording_id = str(annotation.get("recording_id") or "").strip()
            if recording_id and recording_id not in first_by_recording:
                first_by_recording[recording_id] = {
                    "id": recording_id,
                    "sample_id": recording_id,
                    "audio_url": annotation.get("audio_url") or f"/media/{recording_id}.wav",
                    "segments": annotation.get("segments") or [],
                    "category": annotation.get("category") or "未分类",
                    "source_transcript_file": "管理员 JSON 导入",
                }
        return list(first_by_recording.values())
    raise ValueError("JSON 中没有找到 items / instances / recordings / data / annotations")


def parse_import_json(path: os.PathLike | str, category: str | None = None) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = _records_from_export_payload(payload)
    items = []
    errors = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"第 {index} 条不是对象")
            continue
        try:
            items.append(_item_from_json_record(record, category))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("；".join(errors[:10]))
    if not items:
        raise ValueError("JSON 中没有可导入的数据")
    return items


def preview_json_items(
    items: list[dict],
    existing_ids: set[str],
    audio_paths: list[os.PathLike | str] | None = None,
    media_dir: os.PathLike | str | None = None,
) -> ImportPreview:
    preview = ImportPreview()
    seen = set()
    supplied = {}
    for path_value in audio_paths or []:
        path = Path(path_value)
        supplied[path.name] = path

    rows_by_audio = {}
    for item in items:
        try:
            rows_by_audio.setdefault(_json_audio_basename(item), []).append(item)
        except ValueError as exc:
            preview.invalid_rows.append(str(exc))

    if supplied:
        ignored_seen = set()
        for item in items:
            item_id = str(item.get("id", "")).strip()
            try:
                filename = _json_audio_basename(item)
            except ValueError:
                continue
            if filename not in supplied and item_id not in ignored_seen:
                preview.ignored_ids.append(item_id)
                ignored_seen.add(item_id)

        media_dir_path = Path(media_dir) if media_dir is not None else None
        for filename, audio_path in supplied.items():
            matching_rows = rows_by_audio.get(filename, [])
            if not matching_rows:
                preview.unmatched_audio.append(filename)
                continue
            for extra_item in matching_rows[1:]:
                preview.duplicate_ids.append(str(extra_item.get("id", "")))
            item = dict(matching_rows[0])
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                preview.invalid_rows.append("存在缺少 id 的 JSON 记录")
                continue
            if item_id in seen or item_id in existing_ids or (
                media_dir_path is not None and (media_dir_path / filename).exists()
            ):
                preview.duplicate_ids.append(item_id)
                continue
            try:
                _wav_duration(audio_path)
            except ValueError as exc:
                preview.invalid_rows.append(str(exc))
                continue
            seen.add(item_id)
            preview.ready_items.append(_build_json_audio_item(
                item,
                audio_path,
                f"/media/{filename}",
            ))
            preview.audio_paths[filename] = Path(audio_path)
        return preview

    for item in items:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            preview.invalid_rows.append("存在缺少 id 的 JSON 记录")
            continue
        if item_id in seen or item_id in existing_ids:
            preview.duplicate_ids.append(item_id)
            continue
        seen.add(item_id)
        preview.ready_items.append(item)
    return preview


def apply_batch_metadata(item: dict, batch_meta: dict | None) -> dict:
    if not batch_meta:
        return item
    updated = dict(item)
    updated.update({
        "import_batch_id": batch_meta.get("id"),
        "import_batch_label": batch_meta.get("label"),
        "imported_at": batch_meta.get("imported_at"),
        "import_source": batch_meta.get("source"),
    })
    return updated


def preview_rows(
    rows: list[TranscriptRow],
    audio_paths: list[os.PathLike | str],
    existing_ids: set[str],
    media_dir: os.PathLike | str,
) -> ImportPreview:
    preview = ImportPreview()
    supplied = {}
    for path_value in audio_paths:
        path = Path(path_value)
        supplied[path.name] = path

    rows_by_audio = {}
    for row in rows:
        rows_by_audio.setdefault(row.audio_filename, []).append(row)

    ignored_seen = set()
    for row in rows:
        if row.audio_filename not in supplied and row.item_id not in ignored_seen:
            preview.ignored_ids.append(row.item_id)
            ignored_seen.add(row.item_id)

    media_dir = Path(media_dir)
    for filename, audio_path in supplied.items():
        matching_rows = rows_by_audio.get(filename, [])
        if not matching_rows:
            preview.unmatched_audio.append(filename)
            continue
        # 同一音频在 Excel 中出现多行：保留第一行，其余按重复跳过
        for extra_row in matching_rows[1:]:
            preview.duplicate_ids.append(extra_row.item_id)
        row = matching_rows[0]
        if row.item_id in existing_ids or (media_dir / row.audio_filename).exists():
            preview.duplicate_ids.append(row.item_id)
            continue
        try:
            _wav_duration(audio_path)
        except ValueError as exc:
            preview.invalid_rows.append(str(exc))
            continue
        preview.ready.append(row)
        preview.audio_paths[row.audio_filename] = audio_path
    return preview


def commit_preview(
    preview: ImportPreview,
    data_file: os.PathLike | str,
    media_dir: os.PathLike | str,
    item_manager,
    batch_meta: dict | None = None,
) -> list[dict]:
    if not preview.can_confirm:
        raise ValueError("导入校验未通过")

    data_file = Path(data_file)
    media_dir = Path(media_dir)
    existing = json.loads(data_file.read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        raise ValueError("任务数据文件必须是 JSON 数组")

    imported = []
    for row in preview.ready:
        source = preview.audio_paths[row.audio_filename]
        imported.append(apply_batch_metadata(
            build_audio_item(row, source, f"/media/{row.audio_filename}"),
            batch_meta,
        ))
    for item in preview.ready_items:
        imported.append(apply_batch_metadata(item, batch_meta))

    media_dir.mkdir(parents=True, exist_ok=True)
    staged_files = []
    try:
        staged_destinations = set()
        for row in preview.ready:
            source = preview.audio_paths[row.audio_filename]
            fd, staged_name = tempfile.mkstemp(prefix=".audio-import-", dir=media_dir)
            os.close(fd)
            staged = Path(staged_name)
            shutil.copyfile(source, staged)
            staged_files.append((staged, media_dir / row.audio_filename))
            staged_destinations.add(row.audio_filename)
        for item in preview.ready_items:
            filename = _json_audio_basename(item)
            if filename in staged_destinations or filename not in preview.audio_paths:
                continue
            source = preview.audio_paths[filename]
            fd, staged_name = tempfile.mkstemp(prefix=".audio-import-", dir=media_dir)
            os.close(fd)
            staged = Path(staged_name)
            shutil.copyfile(source, staged)
            staged_files.append((staged, media_dir / filename))
            staged_destinations.add(filename)

        data_file.parent.mkdir(parents=True, exist_ok=True)
        fd, json_temp_name = tempfile.mkstemp(prefix=".items-", suffix=".json", dir=data_file.parent)
        os.close(fd)
        json_temp = Path(json_temp_name)
        json_temp.write_text(
            json.dumps(existing + imported, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for staged, destination in staged_files:
            os.replace(staged, destination)
        os.replace(json_temp, data_file)
        for item in imported:
            item_manager.add_item(item["id"], item)
        return imported
    finally:
        for staged, _ in staged_files:
            if staged.exists():
                staged.unlink()
        if "json_temp" in locals() and json_temp.exists():
            json_temp.unlink()
