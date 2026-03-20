(function () {
  const runForm = document.getElementById("run-form");
  const runPrompt = document.getElementById("run-prompt");
  const runTask = document.getElementById("run-task");
  const runInput = document.getElementById("run-input");
  const runBtn = document.getElementById("run-btn");
  const runResult = document.getElementById("run-result");

  const uploadForm = document.getElementById("upload-form");
  const uploadResult = document.getElementById("upload-result");
  const uploadBtn = document.getElementById("upload-btn");
  const uploadDemoBtn = document.getElementById("upload-demo-btn");

  function setUploadLoading(loading) {
    uploadBtn.disabled = loading;
    uploadDemoBtn.disabled = loading;
  }

  uploadForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const fileInput = document.getElementById("upload-files");
    const files = fileInput.files;
    if (!files || files.length === 0) {
      setResult(uploadResult, "Выберите хотя бы один файл.", true);
      return;
    }
    setResult(uploadResult, "Загружаем…", false, true);
    setUploadLoading(true);
    try {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
      }
      const res = await fetch("/rag/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setResult(uploadResult, data.detail || "Ошибка " + res.status, true);
        return;
      }
      if (data.error) {
        setResult(
          uploadResult,
          "Загрузка выполнена, индексация не удалась: " + data.error,
          true
        );
        return;
      }
      let msg = "Загружено файлов: " + data.files_count + ". " + (data.message || "");
      if (data.ingest_docs_indexed != null) {
        msg += " Проиндексировано документов: " + data.ingest_docs_indexed + ", чанков: " + (data.ingest_chunks_indexed ?? "—") + ".";
      }
      setResult(uploadResult, msg, false);
    } catch (err) {
      setResult(uploadResult, "Ошибка сети: " + err.message, true);
    } finally {
      setUploadLoading(false);
    }
  });

  uploadDemoBtn.addEventListener("click", async function () {
    setResult(uploadResult, "Индексируем демо…", false, true);
    setUploadLoading(true);
    try {
      const res = await fetch("/rag/ingest", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setResult(uploadResult, data.detail || "Ошибка " + res.status, true);
        return;
      }
      setResult(
        uploadResult,
        "Демо проиндексировано. Документов: " + (data.docs_indexed ?? "—") + ", чанков: " + (data.chunks_indexed ?? "—") + ".",
        false
      );
    } catch (err) {
      setResult(uploadResult, "Ошибка сети: " + err.message, true);
    } finally {
      setUploadLoading(false);
    }
  });

  function setResult(el, text, isError, loading) {
    el.textContent = text;
    el.className = "result" + (loading ? " loading" : "") + (isError ? " error" : "");
  }

  function setResultHtml(el, html, isError) {
    el.innerHTML = html;
    el.className = "result" + (isError ? " error" : "");
  }

  function setRunLoading(loading) {
    if (!runBtn) return;
    runBtn.disabled = loading;
    if (runPrompt) runPrompt.disabled = loading;
  }

  function prettyJson(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_e) {
      return String(value);
    }
  }

  function renderRunResponse(promptKey, data) {
    if (!data || typeof data !== "object") {
      return '<div class="run-generic"><pre class="json">' + esc(String(data ?? "")) + "</pre></div>";
    }

    if (promptKey === "classify_v1") {
      const label = data.label ?? "—";
      const confidence = typeof data.confidence === "number" ? data.confidence : null;
      const rationale = data.rationale ?? "";

      const pct = confidence == null ? null : Math.round(Math.max(0, Math.min(1, confidence)) * 100);
      const bar = pct == null
        ? ""
        : '<div class="confidence">' +
            '<div class="confidence-label">Уверенность: <b>' + esc(String(pct)) + "%</b></div>" +
            '<div class="confidence-bar" role="progressbar" aria-valuenow="' + esc(String(pct)) + '" aria-valuemin="0" aria-valuemax="100">' +
              '<div class="confidence-fill" style="width:' + esc(String(pct)) + '%"></div>' +
            "</div>" +
          "</div>";

      return (
        '<div class="run-classify">' +
          '<div class="run-row">' +
            '<div>Label: <span class="badge badge-' + esc(String(label)) + '">' + esc(String(label)) + "</span></div>" +
          "</div>" +
          bar +
          (rationale ? '<div class="run-rationale"><div class="muted">Обоснование</div><div>' + esc(String(rationale)) + "</div></div>" : "") +
        "</div>"
      );
    }

    if (promptKey === "extract_v1") {
      const entities = Array.isArray(data.entities) ? data.entities : [];
      const summary = data.summary ?? "";

      const entHtml = entities.length === 0
        ? '<div class="muted">Сущности не найдены.</div>'
        : '<ul class="entities">' +
            entities
              .map(function (e) {
                const t = e && typeof e === "object" ? (e.type ?? "") : "";
                const v = e && typeof e === "object" ? (e.value ?? "") : "";
                return '<li><span class="entity-type">' + esc(String(t)) + '</span><span class="entity-sep">:</span><span class="entity-value">' + esc(String(v)) + "</span></li>";
              })
              .join("") +
          "</ul>";

      return (
        '<div class="run-extract">' +
          '<div class="muted">Entities</div>' +
          entHtml +
          '<div class="muted" style="margin-top:0.75rem">Summary</div>' +
          '<div class="summary">' + esc(String(summary)) + "</div>" +
        "</div>"
      );
    }

    return '<div class="run-generic"><pre class="json">' + esc(prettyJson(data)) + "</pre></div>";
  }

  function esc(s) {
    if (s == null) return "";
    const t = String(s);
    return t
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadPrompts() {
    if (!runPrompt) return;
    runPrompt.innerHTML = '<option value="" disabled selected>Загружаем…</option>';
    try {
      const res = await fetch("/prompts");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        runPrompt.innerHTML = '<option value="" disabled selected>Ошибка загрузки</option>';
        setResult(runResult, (data && data.detail) ? data.detail : "Не удалось загрузить список промптов (HTTP " + res.status + ")", true);
        return;
      }
      const prompts = Array.isArray(data.prompts) ? data.prompts : [];
      if (prompts.length === 0) {
        runPrompt.innerHTML = '<option value="" disabled selected>Промптов нет</option>';
        return;
      }

      const opts = prompts
        .map(function (p) {
          const name = p && typeof p === "object" ? (p.name ?? "") : "";
          const version = p && typeof p === "object" ? (p.version ?? "") : "";
          const key = String(name) + "_" + String(version);
          return '<option value="' + esc(key) + '">' + esc(key) + "</option>";
        })
        .join("");
      runPrompt.innerHTML = '<option value="" disabled>Выберите промпт…</option>' + opts;
      runPrompt.value = prompts[0].name + "_" + prompts[0].version;
    } catch (err) {
      runPrompt.innerHTML = '<option value="" disabled selected>Ошибка загрузки</option>';
      setResult(runResult, "Ошибка сети при загрузке промптов: " + err.message, true);
    }
  }

  if (runForm) {
    loadPrompts();

    runForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      const promptKey = (runPrompt && runPrompt.value) ? runPrompt.value : "";
      if (!promptKey) {
        setResult(runResult, "Выберите промпт.", true);
        return;
      }

      const task = (runTask && runTask.value) ? runTask.value.trim() : "";
      const rawInput = (runInput && runInput.value) ? runInput.value.trim() : "";
      if (!rawInput) {
        setResult(runResult, "Введите входные данные.", true);
        return;
      }

      let inputPayload = rawInput;
      if (rawInput[0] === "{" || rawInput[0] === "[" || rawInput === "null" || rawInput === "true" || rawInput === "false" || /^-?\d/.test(rawInput)) {
        try {
          inputPayload = JSON.parse(rawInput);
        } catch (_e) {
          inputPayload = rawInput;
        }
      }

      setResult(runResult, "Запускаем…", false, true);
      setRunLoading(true);
      try {
        const res = await fetch("/run/" + encodeURIComponent(promptKey), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task: task, input: inputPayload }),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          const msg =
            data && data.detail
              ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
              : "Ошибка " + res.status;
          setResult(runResult, msg, true);
          return;
        }
        setResultHtml(runResult, renderRunResponse(promptKey, data), false);
      } catch (err) {
        setResult(runResult, "Ошибка сети: " + err.message, true);
      } finally {
        setRunLoading(false);
      }
    });
  }

  const searchForm = document.getElementById("search-form");
  const searchResult = document.getElementById("search-result");
  const searchBtn = document.getElementById("search-btn");

  searchForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const q = document.getElementById("search-query").value.trim();
    const k = document.getElementById("search-k").value || "5";
    setResult(searchResult, "Ищем…", false, true);
    searchBtn.disabled = true;
    try {
      const res = await fetch(
        "/rag/search?q=" + encodeURIComponent(q) + "&k=" + encodeURIComponent(k)
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const msg = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "Ошибка " + res.status;
        setResult(searchResult, msg, true);
        return;
      }
      const hits = Array.isArray(data) ? data : [];
      if (hits.length === 0) {
        setResult(searchResult, "Ничего не найдено.", false);
        return;
      }
      const html = hits
        .map(
          (h) =>
            '<div class="hit">' +
            '<div class="title">' + esc(h.doc_title || "—") + "</div>" +
            '<div class="path">' + esc(h.path) + "</div>" +
            '<div class="preview">' + esc(h.text_preview) + "</div>" +
            (h.score != null ? '<div class="score">' + esc(String(h.score)) + "</div>" : "") +
            "</div>"
        )
        .join("");
      setResultHtml(searchResult, html, false);
    } catch (err) {
      setResult(searchResult, "Ошибка сети: " + err.message, true);
    } finally {
      searchBtn.disabled = false;
    }
  });

  const askForm = document.getElementById("ask-form");
  const askResult = document.getElementById("ask-result");
  const askBtn = document.getElementById("ask-btn");

  askForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const question = document.getElementById("ask-question").value.trim();
    if (!question) {
      setResult(askResult, "Введите вопрос.", true);
      return;
    }
    setResult(askResult, "Отправляем вопрос…", false, true);
    askBtn.disabled = true;
    try {
      const res = await fetch("/rag/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const msg = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "Ошибка " + res.status;
        setResult(askResult, msg, true);
        return;
      }
      const parts = [];
      parts.push('<div class="answer-block">' + esc(data.answer || "") + "</div>");
      if (data.confidence != null) {
        parts.push("<div>Уверенность: " + esc(String(data.confidence)) + "</div>");
      }
      if (data.status) {
        parts.push("<div>Статус: " + esc(data.status) + "</div>");
      }
      if (data.sources && data.sources.length > 0) {
        parts.push('<div class="sources">Источники:<br>');
        data.sources.forEach(function (s) {
          parts.push(
            '<div class="source">' +
              '<span class="doc-title">' + esc(s.doc_title) + "</span>" +
              (s.relevance != null ? " (релевантность: " + esc(String(s.relevance)) + ")" : "") +
              '<div class="quote">' + esc(s.quote) + "</div>" +
              "</div>"
          );
        });
        parts.push("</div>");
      }
      setResultHtml(askResult, parts.join(""), false);
    } catch (err) {
      setResult(askResult, "Ошибка сети: " + err.message, true);
    } finally {
      askBtn.disabled = false;
    }
  });
})();
