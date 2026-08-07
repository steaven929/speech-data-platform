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
    audio_paths: dict[str, Path] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    missing_audio: list[str] = field(default_factory=list)
    ignored_ids: list[str] = field(default_factory=list)
    unmatched_audio: list[str] = field(default_factory=list)
    invalid_rows: list[str] = field(default_factory=list)

    @property
    def can_confirm(self) -> bool:
        return bool(self.ready) and not (
            self.duplicate_ids
            or self.missing_audio
            or self.unmatched_audio
            or self.invalid_rows
        )

    def to_dict(self) -> dict:
        return {
            "ready": [row.item_id for row in self.ready],
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
        if len(matching_rows) > 1:
            preview.duplicate_ids.append(matching_rows[0].item_id)
            continue
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
        imported.append(build_audio_item(row, source, f"/media/{row.audio_filename}"))

    media_dir.mkdir(parents=True, exist_ok=True)
    staged_files = []
    try:
        for row in preview.ready:
            source = preview.audio_paths[row.audio_filename]
            fd, staged_name = tempfile.mkstemp(prefix=".audio-import-", dir=media_dir)
            os.close(fd)
            staged = Path(staged_name)
            shutil.copyfile(source, staged)
            staged_files.append((staged, media_dir / row.audio_filename))

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
