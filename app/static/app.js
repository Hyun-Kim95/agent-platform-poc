(function () {
  "use strict";

  var state = {
    phase: "idle",
    envelope: null,
    httpError: null,
    selectedRating: null,
    ratingSubmitted: false,
  };

  var els = {
    tenant: document.getElementById("tenant"),
    engine: document.getElementById("engine"),
    query: document.getElementById("query"),
    send: document.getElementById("send"),
    result: document.getElementById("result"),
    badge: document.getElementById("badge"),
    meta: document.getElementById("meta"),
    answer: document.getElementById("answer"),
    preview: document.getElementById("preview"),
    lastFeedback: document.getElementById("last-feedback"),
    citations: document.getElementById("citations"),
    errorBox: document.getElementById("error-box"),
    hitlPanel: document.getElementById("hitl-panel"),
    approve: document.getElementById("approve"),
    revise: document.getElementById("revise"),
    reject: document.getElementById("reject"),
    reviseExtra: document.getElementById("revise-extra"),
    feedback: document.getElementById("feedback"),
    reviseTarget: document.getElementById("revise-target"),
    confirmRevise: document.getElementById("confirm-revise"),
    ratingPanel: document.getElementById("rating-panel"),
    ratingComment: document.getElementById("rating-comment"),
    submitRating: document.getElementById("submit-rating"),
    ratingStatus: document.getElementById("rating-status"),
    loadEval: document.getElementById("load-eval"),
    evalSummary: document.getElementById("eval-summary"),
    evalMarkdown: document.getElementById("eval-markdown"),
    useStream: document.getElementById("use-stream"),
    streamLog: document.getElementById("stream-log"),
    streamBlock: document.getElementById("stream-block"),
    feedbackBlock: document.getElementById("feedback-block"),
    previewBlock: document.getElementById("preview-block"),
    answerBlock: document.getElementById("answer-block"),
    citationsBlock: document.getElementById("citations-block"),
  };

  function setBlockVisible(blockEl, visible) {
    if (!blockEl) return;
    if (visible) blockEl.classList.remove("hidden");
    else blockEl.classList.add("hidden");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function inlineMd(s) {
    s = escapeHtml(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return s;
  }

  /** PoC subset: headings, lists, paragraphs. HTML escaped first. */
  function renderMarkdown(md) {
    var lines = String(md || "").replace(/\r\n/g, "\n").split("\n");
    var html = [];
    var i = 0;
    var listOpen = false;

    function closeList() {
      if (listOpen) {
        html.push("</ul>");
        listOpen = false;
      }
    }

    if (lines[0] === "(draft)") {
      html.push('<p class="draft-label">(draft)</p>');
      i = 1;
      if (lines[1] === "") i = 2;
    }

    for (; i < lines.length; i++) {
      var line = lines[i];
      var m;
      if (/^\s*$/.test(line)) {
        closeList();
        continue;
      }
      m = /^(#{1,3})\s+(.+)$/.exec(line);
      if (m) {
        closeList();
        var level = m[1].length;
        html.push(
          "<h" + level + ">" + inlineMd(m[2]) + "</h" + level + ">"
        );
        continue;
      }
      m = /^[-*]\s+(.+)$/.exec(line);
      if (m) {
        if (!listOpen) {
          html.push("<ul>");
          listOpen = true;
        }
        html.push("<li>" + inlineMd(m[1]) + "</li>");
        continue;
      }
      if (listOpen && /^\s{2,}\S/.test(line)) {
        html.push(
          '<li class="sub">' + inlineMd(line.trim()) + "</li>"
        );
        continue;
      }
      closeList();
      html.push("<p>" + inlineMd(line) + "</p>");
    }
    closeList();
    return html.join("\n");
  }

  function setAnswerMarkdown(text) {
    var t = text || "";
    if (!t.trim()) {
      els.answer.innerHTML = "";
      els.answer.classList.remove("md");
      setBlockVisible(els.answerBlock, false);
      return;
    }
    els.answer.classList.add("md");
    els.answer.innerHTML = renderMarkdown(t);
    setBlockVisible(els.answerBlock, true);
  }

  function setBusy(busy) {
    els.send.disabled = busy;
    els.approve.disabled = busy;
    els.revise.disabled = busy;
    els.reject.disabled = busy;
    els.confirmRevise.disabled = busy;
    els.submitRating.disabled = busy || state.ratingSubmitted;
    els.loadEval.disabled = busy;
  }

  function shortText(s, n) {
    s = s == null ? "" : String(s);
    if (s.length <= n) return s;
    return s.slice(0, n - 1) + "…";
  }

  function renderCitations(list) {
    els.citations.innerHTML = "";
    (list || []).forEach(function (c) {
      var li = document.createElement("li");
      var type = document.createElement("span");
      type.className = "type";
      type.textContent = c.type || "?";
      li.appendChild(type);
      var title = c.title || c.ref || "(no title)";
      li.appendChild(document.createTextNode(shortText(title, 80)));
      if (c.snippet) {
        li.appendChild(
          document.createTextNode(" — " + shortText(c.snippet, 80))
        );
      }
      if (c.ref && /^https?:\/\//.test(c.ref)) {
        li.appendChild(document.createTextNode(" "));
        var a = document.createElement("a");
        a.href = c.ref;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "link";
        li.appendChild(a);
      }
      els.citations.appendChild(li);
    });
  }

  function renderLastFeedback(env) {
    var hitl = env.hitl || {};
    var preview = hitl.preview || {};
    var fb = hitl.last_feedback || preview.last_feedback || "";
    var tgt = hitl.last_revise_target || preview.last_revise_target || "";
    if (!fb) {
      els.lastFeedback.textContent = "";
      setBlockVisible(els.feedbackBlock, false);
      return;
    }
    setBlockVisible(els.feedbackBlock, true);
    els.lastFeedback.textContent =
      "Last revise feedback: " +
      fb +
      (tgt ? "\nrevise_target: " + tgt : "");
  }

  function renderPreview(env) {
    var preview = env.hitl && env.hitl.preview ? env.hitl.preview : null;
    if (!preview) {
      els.preview.textContent = "";
      setBlockVisible(els.previewBlock, false);
      return;
    }
    var parts = [];
    if (preview.data_summary != null && preview.data_summary !== "") {
      parts.push("Data: " + preview.data_summary);
    }
    if (preview.route) {
      parts.push("Route: " + preview.route);
    }
    if (preview.web_titles && preview.web_titles.length) {
      parts.push("Web: " + preview.web_titles.join(" · "));
    } else if (preview.summary && parts.length === 0) {
      parts.push(preview.summary);
    }
    var risks = (preview.risks || []).join("; ");
    if (risks) {
      parts.push("risks: " + risks);
    }
    els.preview.textContent = parts.join("\n");
    setBlockVisible(els.previewBlock, parts.length > 0);
  }

  function syncRatingButtons() {
    var buttons = document.querySelectorAll(".rate-btn");
    buttons.forEach(function (btn) {
      var n = parseInt(btn.getAttribute("data-rating"), 10);
      if (state.selectedRating === n) {
        btn.classList.add("selected");
      } else {
        btn.classList.remove("selected");
      }
      btn.disabled = state.ratingSubmitted;
    });
    els.submitRating.disabled = state.ratingSubmitted;
    els.ratingComment.disabled = state.ratingSubmitted;
  }

  function renderRatingPanel() {
    if (state.phase === "completed" && state.envelope && state.envelope.run_id) {
      els.ratingPanel.classList.remove("hidden");
      syncRatingButtons();
    } else {
      els.ratingPanel.classList.add("hidden");
    }
  }

  function render() {
    els.result.classList.remove("hidden");
    els.badge.className = "badge " + state.phase;
    els.badge.textContent = state.phase;

    if (state.phase === "error") {
      els.hitlPanel.classList.add("hidden");
      els.ratingPanel.classList.add("hidden");
      els.preview.textContent = "";
      els.answer.innerHTML = "";
      els.answer.classList.remove("md");
      els.meta.textContent = "";
      els.lastFeedback.textContent = "";
      els.citations.innerHTML = "";
      setBlockVisible(
        els.streamBlock,
        !!(els.streamLog.textContent || "").trim()
      );
      setBlockVisible(els.feedbackBlock, false);
      setBlockVisible(els.previewBlock, false);
      setBlockVisible(els.answerBlock, false);
      setBlockVisible(els.citationsBlock, false);
      var msg = state.httpError || "Unknown error";
      if (state.envelope && state.envelope.error) {
        msg =
          state.envelope.error.code +
          ": " +
          state.envelope.error.message;
      }
      els.errorBox.textContent = msg;
      return;
    }

    els.errorBox.textContent = "";
    var env = state.envelope || {};
    var meta = env.meta || {};
    els.meta.textContent = [
      "run_id=" + (env.run_id || "-"),
      "trace_id=" + (env.trace_id || "-"),
      "engine=" + (meta.engine || "-"),
      "tenant=" + (meta.tenant_id || "-"),
      "latency_ms=" + (meta.latency_ms != null ? meta.latency_ms : "-"),
      "route=" + (meta.route || "-"),
    ].join(" · ");

    renderLastFeedback(env);
    renderPreview(env);
    setAnswerMarkdown(env.answer || "");
    renderCitations(env.citations);
    setBlockVisible(
      els.citationsBlock,
      (env.citations || []).length > 0
    );

    if (state.phase === "waiting_human") {
      els.hitlPanel.classList.remove("hidden");
    } else {
      els.hitlPanel.classList.add("hidden");
      els.reviseExtra.classList.remove("open");
    }
    renderRatingPanel();
  }

  function applyEnvelope(env) {
    state.envelope = env;
    state.httpError = null;
    state.selectedRating = null;
    state.ratingSubmitted = false;
    els.ratingStatus.textContent = "";
    els.ratingComment.value = "";
    if (env.status === "waiting_human") {
      state.phase = "waiting_human";
    } else if (env.status === "completed") {
      state.phase = "completed";
    } else if (env.status === "failed") {
      state.phase = "error";
    } else {
      state.phase = "error";
      state.httpError = "Unexpected status: " + env.status;
    }
    render();
  }

  async function postJson(url, body) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      var detail = "";
      if (data && data.error && data.error.message) {
        detail = data.error.code + ": " + data.error.message;
      } else if (data && data.detail) {
        detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail);
      }
      var err = new Error(
        "HTTP " + res.status + (detail ? " — " + detail : "")
      );
      err.payload = data;
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function getJson(url) {
    var res = await fetch(url, { method: "GET" });
    var data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      var detail = "";
      if (data && data.error && data.error.message) {
        detail = data.error.code + ": " + data.error.message;
      }
      var err = new Error(
        "HTTP " + res.status + (detail ? " — " + detail : "")
      );
      err.payload = data;
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function appendStreamLog(line) {
    setBlockVisible(els.streamBlock, true);
    els.streamLog.textContent +=
      (els.streamLog.textContent ? "\n" : "") + line;
  }

  function resetStreamLog() {
    els.streamLog.textContent = "";
    setBlockVisible(els.streamBlock, false);
  }

  function parseSseFrames(buffer, onEvent) {
    var parts = buffer.split("\n\n");
    var rest = parts.pop();
    parts.forEach(function (frame) {
      var ev = null;
      var dataRaw = null;
      frame.split("\n").forEach(function (line) {
        if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
        else if (line.indexOf("data:") === 0) dataRaw = line.slice(5).trim();
      });
      if (ev && dataRaw != null) {
        var data = {};
        try {
          data = JSON.parse(dataRaw);
        } catch (e) {
          data = { raw: dataRaw };
        }
        onEvent(ev, data);
      }
    });
    return rest;
  }

  async function sendChatStream(body) {
    resetStreamLog();
    appendStreamLog("→ POST /v1/chat/stream");
    var res = await fetch("/v1/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      throw new Error("HTTP " + res.status + " (stream)");
    }
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buf = "";
    var finalEnv = null;
    while (true) {
      var step = await reader.read();
      if (step.done) break;
      buf += decoder.decode(step.value, { stream: true });
      buf = parseSseFrames(buf, function (ev, data) {
        if (ev === "run") {
          appendStreamLog(
            "run " + (data.run_id || "") + " · " + (data.engine || "")
          );
        } else if (ev === "phase") {
          appendStreamLog("phase: " + (data.phase || "?"));
        } else if (ev === "envelope") {
          finalEnv = data;
          appendStreamLog("envelope status=" + (data.status || "?"));
        } else if (ev === "error") {
          appendStreamLog(
            "error " + (data.code || "") + ": " + (data.message || "")
          );
        } else if (ev === "done") {
          appendStreamLog("done");
        }
      });
    }
    if (!finalEnv) {
      throw new Error("stream ended without envelope");
    }
    applyEnvelope(finalEnv);
  }

  async function sendChat() {
    state.phase = "loading";
    state.httpError = null;
    render();
    setBusy(true);
    try {
      var engine = (els.engine.value || "").trim();
      var body = {
        tenant_id: (els.tenant.value || "demo").trim(),
        query: (els.query.value || "").trim(),
      };
      if (engine) {
        body.engine = engine;
      }
      if (!body.query) {
        throw new Error("query is required");
      }
      if (els.useStream && els.useStream.checked) {
        await sendChatStream(body);
      } else {
        resetStreamLog();
        var env = await postJson("/v1/chat", body);
        applyEnvelope(env);
      }
    } catch (e) {
      state.phase = "error";
      state.envelope = e.payload && e.payload.status ? e.payload : null;
      state.httpError = e.message || String(e);
      render();
    } finally {
      setBusy(false);
    }
  }

  async function sendHitl(decision) {
    if (!state.envelope || !state.envelope.run_id) {
      state.phase = "error";
      state.httpError = "No run_id — send a chat first";
      render();
      return;
    }
    var body = { decision: decision };
    if (decision === "revise") {
      body.feedback = (els.feedback.value || "").trim();
      var target = (els.reviseTarget.value || "").trim();
      if (target) {
        body.revise_target = target;
      }
    }
    state.phase = "loading";
    render();
    setBusy(true);
    try {
      var env = await postJson(
        "/v1/hitl/" + encodeURIComponent(state.envelope.run_id),
        body
      );
      applyEnvelope(env);
    } catch (e) {
      state.phase = "error";
      state.envelope = e.payload && e.payload.status ? e.payload : state.envelope;
      state.httpError = e.message || String(e);
      render();
    } finally {
      setBusy(false);
    }
  }

  async function submitRating() {
    if (!state.envelope || !state.envelope.run_id) {
      els.ratingStatus.textContent = "No run_id";
      return;
    }
    if (!state.selectedRating) {
      els.ratingStatus.textContent = "Select rating 1~5";
      return;
    }
    setBusy(true);
    els.ratingStatus.textContent = "Submitting…";
    try {
      var body = {
        run_id: state.envelope.run_id,
        rating: state.selectedRating,
      };
      var comment = (els.ratingComment.value || "").trim();
      if (comment) {
        body.comment = comment;
      }
      var res = await postJson("/v1/feedback", body);
      state.ratingSubmitted = true;
      els.ratingStatus.textContent =
        "Saved feedback_id=" +
        (res.feedback_id || "-") +
        " · stored_at=" +
        (res.stored_at || "-");
      syncRatingButtons();
    } catch (e) {
      els.ratingStatus.textContent = e.message || String(e);
    } finally {
      setBusy(false);
    }
  }

  async function loadEvalReport() {
    setBusy(true);
    els.evalSummary.textContent = "Loading…";
    els.evalMarkdown.classList.add("hidden");
    try {
      var data = await getJson("/v1/eval/report");
      var s = data.summary || {};
      var lines = [
        "score: " + (s.score_label || "-"),
        "generated: " + (s.generated || "-"),
        "path: " + (data.path || "-"),
      ];
      if (data.rows_preview && data.rows_preview.length) {
        lines.push("rows:");
        data.rows_preview.forEach(function (r) {
          lines.push("  " + r);
        });
      }
      els.evalSummary.textContent = lines.join("\n");
      els.evalMarkdown.textContent = data.markdown || "";
      els.evalMarkdown.classList.remove("hidden");
    } catch (e) {
      els.evalSummary.textContent = e.message || String(e);
      els.evalMarkdown.classList.add("hidden");
    } finally {
      setBusy(false);
    }
  }

  document.querySelectorAll(".rate-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (state.ratingSubmitted) return;
      state.selectedRating = parseInt(btn.getAttribute("data-rating"), 10);
      syncRatingButtons();
    });
  });

  els.send.addEventListener("click", function () {
    sendChat();
  });
  els.approve.addEventListener("click", function () {
    sendHitl("approve");
  });
  els.reject.addEventListener("click", function () {
    sendHitl("reject");
  });
  els.revise.addEventListener("click", function () {
    els.reviseExtra.classList.add("open");
    els.feedback.focus();
  });
  els.confirmRevise.addEventListener("click", function () {
    sendHitl("revise");
  });
  els.submitRating.addEventListener("click", function () {
    submitRating();
  });
  els.loadEval.addEventListener("click", function () {
    loadEvalReport();
  });
})();
