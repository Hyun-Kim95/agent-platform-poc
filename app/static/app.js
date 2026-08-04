(function () {
  "use strict";

  var state = {
    phase: "idle", // idle | loading | waiting_human | completed | error
    envelope: null,
    httpError: null,
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
  };

  function setBusy(busy) {
    els.send.disabled = busy;
    els.approve.disabled = busy;
    els.revise.disabled = busy;
    els.reject.disabled = busy;
    els.confirmRevise.disabled = busy;
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
      li.appendChild(document.createTextNode(shortText(title, 100)));
      if (c.snippet) {
        li.appendChild(
          document.createTextNode(" — " + shortText(c.snippet, 120))
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
      els.lastFeedback.classList.add("hidden");
      els.lastFeedback.textContent = "";
      return;
    }
    els.lastFeedback.classList.remove("hidden");
    els.lastFeedback.textContent =
      "Last revise feedback: " +
      fb +
      (tgt ? "\nrevise_target: " + tgt : "");
  }

  function renderPreview(env) {
    var preview = env.hitl && env.hitl.preview ? env.hitl.preview : null;
    if (!preview) {
      els.preview.textContent = "";
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
  }

  function render() {
    els.result.classList.remove("hidden");
    els.badge.className = "badge " + state.phase;
    els.badge.textContent = state.phase;

    if (state.phase === "error") {
      els.hitlPanel.classList.add("hidden");
      els.preview.textContent = "";
      els.answer.textContent = "";
      els.meta.textContent = "";
      els.lastFeedback.classList.add("hidden");
      els.citations.innerHTML = "";
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
    els.answer.textContent = env.answer || "";
    renderCitations(env.citations);

    if (state.phase === "waiting_human") {
      els.hitlPanel.classList.remove("hidden");
    } else {
      els.hitlPanel.classList.add("hidden");
      els.reviseExtra.classList.remove("open");
    }
  }

  function applyEnvelope(env) {
    state.envelope = env;
    state.httpError = null;
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
      if (data && data.detail) {
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
      var env = await postJson("/v1/chat", body);
      applyEnvelope(env);
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
})();
