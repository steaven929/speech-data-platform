(function () {
  "use strict";

  let statusFilter = "pending";
  let selected = null;
  let items = [];

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
    const data = await request(`/adjudicate/api/audio-reviews?status=${statusFilter}`);
    items = data.items || [];
    renderList();
    if (selected) {
      selected = items.find((item) => item.recording_id === selected.recording_id &&
        item.annotator === selected.annotator) || selected;
      renderEditor();
    }
  }

  function renderList() {
    const list = document.getElementById("direct-review-list");
    if (!items.length) {
      list.innerHTML = '<div class="direct-review-empty-list">当前没有记录</div>';
      return;
    }
    list.innerHTML = items.map((item, index) => `
      <button class="direct-review-item" data-index="${index}">
        <strong>${escapeHtml(item.recording_id)}</strong>
        <span>标注员：${escapeHtml(item.annotator)}</span>
        <span>${item.segment_count} 个片段 · ${statusText(item.review_status)}</span>
      </button>`).join("");
    list.querySelectorAll(".direct-review-item").forEach((button) => {
      button.addEventListener("click", () => {
        selected = items[Number(button.dataset.index)];
        renderEditor();
      });
    });
  }

  const statusText = (status) => ({pending: "待审核", in_progress: "审核中", completed: "已完成"}[status] || status);

  function renderEditor() {
    if (!selected) return;
    document.getElementById("direct-review-empty").hidden = true;
    document.getElementById("direct-review-editor").hidden = false;
    document.getElementById("direct-review-title").textContent =
      `录音 ${selected.recording_id} · 标注员 ${selected.annotator}`;
    document.getElementById("direct-review-audio").src = `/media/${encodeURIComponent(selected.recording_id)}.wav`;
    document.getElementById("direct-review-status").textContent =
      `状态：${statusText(selected.review_status)}${selected.assigned_to ? ` · 审核人：${selected.assigned_to}` : ""}`;
    document.getElementById("direct-review-segments").innerHTML = `
      <table class="direct-review-table"><thead><tr>
        <th>开始时间</th><th>结束时间</th><th>说话人</th><th>转写文本</th><th>方言</th>
      </tr></thead><tbody>${(selected.segments || []).map((segment) => `
        <tr data-id="${escapeHtml(segment.id)}">
          <td><input class="seg-start" type="number" min="0" step="0.001" value="${segment.start_time}"></td>
          <td><input class="seg-end" type="number" min="0" step="0.001" value="${segment.end_time}"></td>
          <td><select class="seg-label"><option value="agent" ${segment.speaker === "agent" ? "selected" : ""}>座席</option><option value="caller" ${segment.speaker === "caller" ? "selected" : ""}>来电人</option></select></td>
          <td><textarea class="seg-text">${escapeHtml(segment.text)}</textarea></td>
          <td><input class="seg-dialect" type="checkbox" ${segment.is_dialect ? "checked" : ""}></td>
        </tr>`).join("")}</tbody></table>`;
    const editable = (selected.review_status === "pending" && !selected.assigned_to)
      || (selected.review_status === "in_progress"
        && selected.assigned_to === window.DIRECT_REVIEW_ADMIN);
    document.querySelectorAll("#direct-review-segments input, #direct-review-segments select, #direct-review-segments textarea")
      .forEach((field) => field.disabled = !editable);
    document.getElementById("direct-review-claim").hidden = selected.review_status !== "pending";
    document.getElementById("direct-review-save").hidden = !editable;
    document.getElementById("direct-review-complete").hidden = !editable;
    document.getElementById("direct-review-reopen").hidden = selected.review_status !== "completed"
      || selected.reviewed_by !== window.DIRECT_REVIEW_ADMIN;
  }

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
      selected = {...selected, ...data};
      await loadQueue();
    } catch (error) {
      alert(error.message);
    }
  }

  document.querySelectorAll(".direct-review-filters button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".direct-review-filters button").forEach((b) => b.classList.remove("active"));
      button.classList.add("active"); statusFilter = button.dataset.status; selected = null;
      document.getElementById("direct-review-editor").hidden = true;
      document.getElementById("direct-review-empty").hidden = false; loadQueue();
    });
  });
  document.getElementById("direct-review-claim").addEventListener("click", () => action(
    "/adjudicate/api/audio-reviews/claim", {method: "POST", body: JSON.stringify({recording_id: selected.recording_id, annotator: selected.annotator})}));
  document.getElementById("direct-review-save").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/${encodeURIComponent(selected.annotator)}`,
    {method: "PUT", body: JSON.stringify({segments: editedSegments()})}));
  document.getElementById("direct-review-complete").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/${encodeURIComponent(selected.annotator)}/complete`, {method: "POST"}));
  document.getElementById("direct-review-reopen").addEventListener("click", () => action(
    `/adjudicate/api/audio-reviews/${encodeURIComponent(selected.recording_id)}/${encodeURIComponent(selected.annotator)}/reopen`, {method: "POST"}));

  loadQueue().catch((error) => { document.getElementById("direct-review-list").textContent = error.message; });
})();
