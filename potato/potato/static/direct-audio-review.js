(function () {
  "use strict";

  let statusFilter = "in_progress";
  let selected = null;
  let selectedGroup = null;
  let viewingOriginal = false;
  let items = [];
  let activeSegmentStop = null;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  async function request(url, options = {}) {
    const response = await fetch(url, {
      headers: {"Content-Type": "application/json"}, ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
    return data;
  }

  async function loadQueue() {
    const params = new URLSearchParams({status: statusFilter});
    const methodSelect = document.getElementById("direct-review-final-method");
    if (statusFilter === "completed" && methodSelect && methodSelect.value) {
      params.set("final_method", methodSelect.value);
    }
    const data = await request(`/adjudicate/api/audio-reviews?${params.toString()}`);
    const previousRecording = selected && selected.recording_id;
    const previousAnnotator = selected && selected.annotator;
    items = statusFilter === "completed" && data.grouped
      ? (data.recordings || []) : (data.items || []);
    renderList();
    if (previousRecording && statusFilter === "completed") {
      selectedGroup = items.find((item) => item.recording_id === previousRecording) || null;
      selected = selectedGroup && selectedGroup.final_result;
      viewingOriginal = false;
    } else if (previousRecording) {
      selected = items.find((item) => item.recording_id === previousRecording &&
        item.annotator === previousAnnotator) || null;
      selectedGroup = null;
    }
    if (selected || selectedGroup) {
      renderEditor();
    } else if (previousRecording) {
      resetEditor();
    }
  }

  const formatPercent = (value) => Number.isFinite(value)
    ? `${(value * 100).toFixed(2)}%` : "—";

  const formatTime = (value) => value ? new Date(value).toLocaleString() : "未记录";

  const methodText = (method) => ({
    pair_cer: "系统双人 CER 自动通过",
    three_way_medoid: "系统三人自动选择",
    manual: "管理员人工定稿",
  }[method] || "已定稿");

  function resetEditor() {
    clearSegmentPlayback();
    document.getElementById("direct-review-editor").hidden = true;
    document.getElementById("direct-review-empty").hidden = false;
  }

  function clearSegmentPlayback() {
    const audio = document.getElementById("direct-review-audio");
    if (audio && activeSegmentStop) {
      audio.removeEventListener("timeupdate", activeSegmentStop);
    }
    activeSegmentStop = null;
    document.querySelectorAll(".direct-review-segment-play.active")
      .forEach((button) => button.classList.remove("active"));
  }

  async function playSegment(start, end, button) {
    const audio = document.getElementById("direct-review-audio");
    if (!audio || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      alert("片段时间无效，无法播放。");
      return;
    }
    clearSegmentPlayback();
    if (button) button.classList.add("active");
    activeSegmentStop = () => {
      if (audio.currentTime >= end) {
        audio.pause();
        clearSegmentPlayback();
      }
    };
    audio.addEventListener("timeupdate", activeSegmentStop);
    audio.currentTime = start;
    try {
      await audio.play();
    } catch (error) {
      clearSegmentPlayback();
      alert("音频无法播放，请先确认浏览器允许播放录音。");
    }
  }

  function renderList() {
    const list = document.getElementById("direct-review-list");
    if (!items.length) {
      list.innerHTML = '<div class="direct-review-empty-list">当前没有记录</div>';
      return;
    }
    list.innerHTML = items.map((item, index) => {
      if (statusFilter === "completed" && item.final_status) {
        const finalLine = item.final_status === "ready"
          ? `<span class="direct-review-final-source">最终结果：标注员 ${escapeHtml(item.final_annotator)}</span>`
          : `<span class="direct-review-error-text">${escapeHtml(item.final_error || "最终稿数据异常")}</span>`;
        const cerLine = Number.isFinite(item.minimum_cer)
          ? ` · 最低 CER ${formatPercent(item.minimum_cer)}` : "";
        return `<button class="direct-review-item" data-index="${index}">
          <strong>${escapeHtml(item.recording_id)}</strong>
          ${finalLine}
          <span>${escapeHtml(methodText(item.final_method))}${cerLine}</span>
          <span>定稿时间：${escapeHtml(item.finalized_at || "未记录")}</span>
        </button>`;
      }
      return `<button class="direct-review-item" data-index="${index}">
          <strong>${escapeHtml(item.recording_id)}</strong>
          <span>推送时间：${escapeHtml(formatTime(item.pushed_at || item.submitted_at))}</span>
          <span>标注员：${escapeHtml(item.annotator)}</span>
          <span>${item.segment_count} 个片段 · ${statusText(item.review_status)}</span>
        </button>`;
    }).join("");
    list.querySelectorAll(".direct-review-item").forEach((button) => {
      button.addEventListener("click", () => {
        const entry = items[Number(button.dataset.index)];
        selectedGroup = statusFilter === "completed" && entry.final_status ? entry : null;
        selected = selectedGroup ? selectedGroup.final_result : entry;
        viewingOriginal = false;
        renderEditor();
      });
    });
  }

  const statusText = (status) => ({in_progress: "审核中", completed: "已完成"}[status] || status);

  function renderDecision() {
    const panel = document.getElementById("direct-review-decision");
    if (!selectedGroup) {
      panel.hidden = true;
      panel.innerHTML = "";
      return;
    }
    panel.hidden = false;
    if (selectedGroup.final_status !== "ready") {
      panel.innerHTML = `<strong class="direct-review-error-text">最终稿数据异常</strong>
        <div>系统没有找到唯一、有效的最终稿，请重新打开该录音进行人工确认。</div>`;
      return;
    }
    const comparisons = (selectedGroup.comparisons || []).map((row) =>
      `<div>${escapeHtml((row.annotators || []).join(" - "))} CER：${formatPercent(row.cer)}</div>`
    ).join("");
    const scores = Object.entries(selectedGroup.scores || {}).map(([annotator, score]) =>
      `<div>标注员 ${escapeHtml(annotator)} 总差异：${formatPercent(score)}</div>`
    ).join("");
    panel.innerHTML = `
      <strong>${escapeHtml(methodText(selectedGroup.final_method))}</strong>
      <div class="direct-review-decision-grid">
        <div>最终稿：标注员 ${escapeHtml(selectedGroup.final_annotator)}</div>
        <div>定稿时间：${escapeHtml(selectedGroup.finalized_at || "未记录")}</div>
        ${comparisons}${scores}
      </div>
      <div>${escapeHtml(selectedGroup.selection_reason || "系统已保存该录音的唯一最终结果")}</div>`;
  }

  function renderAlternatives() {
    const container = document.getElementById("direct-review-alternatives");
    const group = selectedGroup || selected;
    if (!group || !(group.original_results || []).length) {
      container.innerHTML = "";
      return;
    }
    const originalResults = group.original_results;
    container.innerHTML = `<details class="direct-review-alternatives">
      <summary>查看另外 ${originalResults.length} 份原始标注（仅供参考）</summary>
      <div class="direct-review-alternative-buttons">
        ${group.final_result ? `<button type="button" data-final="true" class="${viewingOriginal ? "" : "active"}">最终结果 · ${escapeHtml(group.final_annotator)}</button>` : ""}
        ${!group.final_result ? `<button type="button" data-primary="true" class="${viewingOriginal ? "" : "active"}">审核候选 · ${escapeHtml(group.annotator)}</button>` : ""}
        ${originalResults.map((row, index) => `<button type="button" data-original-index="${index}" class="${viewingOriginal && selected && selected.annotator === row.annotator ? "active" : ""}">原始标注 · ${escapeHtml(row.annotator)}</button>`).join("")}
      </div>
    </details>`;
    const finalButton = container.querySelector("[data-final]");
    if (finalButton) finalButton.addEventListener("click", () => {
      selected = group.final_result;
      viewingOriginal = false;
      renderEditor();
    });
    const primaryButton = container.querySelector("[data-primary]");
    if (primaryButton) primaryButton.addEventListener("click", () => {
      selected = group;
      viewingOriginal = false;
      renderEditor();
    });
    container.querySelectorAll("[data-original-index]").forEach((button) => {
      button.addEventListener("click", () => {
        selected = originalResults[Number(button.dataset.originalIndex)];
        viewingOriginal = true;
        renderEditor();
      });
    });
  }

  function renderEditor() {
    if (!selected && !selectedGroup) return;
    clearSegmentPlayback();
    document.getElementById("direct-review-empty").hidden = true;
    document.getElementById("direct-review-editor").hidden = false;
    renderDecision();
    if (!selected) {
      document.getElementById("direct-review-title").textContent = `录音 ${selectedGroup.recording_id}`;
      document.getElementById("direct-review-status").innerHTML = '<span class="direct-review-error-text">最终稿数据异常</span>';
      document.getElementById("direct-review-audio").src = `/media/${encodeURIComponent(selectedGroup.recording_id)}.wav`;
      document.getElementById("direct-review-segments").innerHTML = "";
      renderAlternatives();
      document.querySelectorAll(".direct-review-actions button").forEach((button) => button.hidden = true);
      return;
    }
    const finalView = Boolean(selectedGroup && !viewingOriginal && selected.is_final_result);
    document.getElementById("direct-review-title").textContent =
      `录音 ${selected.recording_id} · 标注员 ${selected.annotator}`;
    document.getElementById("direct-review-audio").src = `/media/${encodeURIComponent(selected.recording_id)}.wav`;
    const systemReview = ["cer", "pair_cer", "three_way_medoid"].includes(selected.review_method);
    const reviewerText = systemReview
      ? ` · 系统 CER 自动通过${Number.isFinite(selected.cer_score) ? `（${(selected.cer_score * 100).toFixed(2)}%）` : ""}`
      : (selected.reviewed_by ? ` · 最近审核人：${selected.reviewed_by}` : "");
    const workflowText = selected.workflow_stage
      ? ` · ${workflowStatusText(selected.workflow_stage)}` : "";
    const pushedText = selected.pushed_at || selected.submitted_at
      ? ` · 推送时间：${formatTime(selected.pushed_at || selected.submitted_at)}` : "";
    const resultBadge = selectedGroup
      ? (finalView
        ? '<span class="direct-review-final-badge">最终结果</span>'
        : '<span class="direct-review-reference-badge">原始标注，仅供参考</span>')
      : "";
    document.getElementById("direct-review-status").innerHTML =
      `${resultBadge}状态：${escapeHtml(statusText(selected.review_status))}${escapeHtml(workflowText)}${escapeHtml(reviewerText)}${escapeHtml(pushedText)}`;
    document.getElementById("direct-review-segments").innerHTML = `
      <table class="direct-review-table"><thead><tr>
        <th>播放</th><th>开始时间</th><th>结束时间</th><th>说话人</th><th>转写文本</th><th>方言</th>
      </tr></thead><tbody>${(selected.segments || []).map((segment) => `
        <tr data-id="${escapeHtml(segment.id)}">
          <td><button type="button" class="direct-review-segment-play" title="播放本片段" aria-label="播放本片段"><i class="fas fa-play" aria-hidden="true"></i></button></td>
          <td><input class="seg-start" type="number" min="0" step="0.001" value="${segment.start_time}"></td>
          <td><input class="seg-end" type="number" min="0" step="0.001" value="${segment.end_time}"></td>
          <td><select class="seg-label"><option value="agent" ${segment.speaker === "agent" ? "selected" : ""}>座席</option><option value="caller" ${segment.speaker === "caller" ? "selected" : ""}>来电人</option></select></td>
          <td><textarea class="seg-text">${escapeHtml(segment.text)}</textarea></td>
          <td><input class="seg-dialect" type="checkbox" ${segment.is_dialect ? "checked" : ""}></td>
        </tr>`).join("")}</tbody></table>`;
    renderAlternatives();
    const editable = selected.review_status === "in_progress";
    document.querySelectorAll("#direct-review-segments input, #direct-review-segments select, #direct-review-segments textarea")
      .forEach((field) => field.disabled = !editable);
    document.getElementById("direct-review-save").hidden = !editable;
    document.getElementById("direct-review-complete").hidden = !editable;
    document.getElementById("direct-review-reopen").hidden = selected.review_status !== "completed" || Boolean(selectedGroup && !selectedGroup.final_result);
    document.getElementById("direct-review-retry-third").hidden =
      selected.workflow_stage !== "waiting_third_assignment";
    document.querySelectorAll(".direct-review-segment-play").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest("tr");
        playSegment(
          Number(row.querySelector(".seg-start").value),
          Number(row.querySelector(".seg-end").value),
          button
        );
      });
    });
  }

  const workflowStatusText = (stage) => ({
    awaiting_initial_assignment: "等待首轮分配",
    awaiting_pair_submissions: "首轮标注中",
    waiting_third_assignment: "等待第三人",
    awaiting_third_submission: "第二轮标注中",
    auto_finalized: "系统已自动仲裁",
    needs_manual_review: "待人工审核",
    manual_finalized: "管理员已定稿",
  }[stage] || stage);

  function editedSegments() {
    return Array.from(document.querySelectorAll("#direct-review-segments tbody tr")).map((row) => ({
      id: row.dataset.id,
      start_time: Number(row.querySelector(".seg-start").value),
      end_time: Number(row.querySelector(".seg-end").value),
      label: row.querySelector(".seg-label").value,
      text: row.querySelector(".seg-text").value,
      annotations: {dialect: row.querySelector(".seg-dialect").checked},
    }));
  }

  async function action(path, options = {}) {
    try {
      const data = await request(path, options);
      if (selected) selected = {...selected, ...data};
      await loadQueue();
    } catch (error) {
      alert(error.message);
    }
  }

  document.querySelectorAll(".direct-review-filters button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".direct-review-filters button").forEach((b) => b.classList.remove("active"));
      button.classList.add("active"); statusFilter = button.dataset.status; selected = null;
      selectedGroup = null; viewingOriginal = false;
      const methodFilter = document.getElementById("direct-review-method-filter");
      if (methodFilter) methodFilter.hidden = statusFilter !== "completed";
      resetEditor(); loadQueue();
    });
  });
  const methodSelect = document.getElementById("direct-review-final-method");
  if (methodSelect) {
    methodSelect.addEventListener("change", () => {
      if (statusFilter !== "completed") return;
      selected = null; selectedGroup = null; viewingOriginal = false;
      resetEditor(); loadQueue();
    });
  }
  document.getElementById("direct-review-save").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/${encodeURIComponent(selected.annotator)}`,
    {method: "PUT", body: JSON.stringify({segments: editedSegments()})}));
  document.getElementById("direct-review-complete").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/${encodeURIComponent(selected.annotator)}/complete`, {method: "POST"}));
  document.getElementById("direct-review-reopen").addEventListener("click", () => {
    const target = selectedGroup && selectedGroup.final_result
      ? selectedGroup.final_result : selected;
    return action(
      `/adjudicate/api/audio-reviews/${encodeURIComponent(target.recording_id)}/${encodeURIComponent(target.annotator)}/reopen`,
      {method: "POST"});
  });
  document.getElementById("direct-review-retry-third").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/retry-third`, {method: "POST"}));

  loadQueue().catch((error) => { document.getElementById("direct-review-list").textContent = error.message; });
})();
