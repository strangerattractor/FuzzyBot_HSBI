window.addEventListener("load", () => {
  // Must match the proxy server
  //const API_BASE = "http://127.0.0.1:8000";
  const API_BASE = window.location.origin;
  const DEMO_MODE = (() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("demo")) return false;
    const raw = (params.get("demo") || "1").toLowerCase();
    return raw === "" || raw === "1" || raw === "true" || raw === "yes";
  })();
  const UI_SCALE = (() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("scale")) return 1;
    const raw = params.get("scale") || "";
    const value = Number.parseFloat(raw);
    if (!Number.isFinite(value) || value <= 0) return 1;
    return Math.min(1.5, Math.max(0.4, value));
  })();
  const PROMPT_PREFIX = "[guest@usr000 ~]$ ";
  const ASSISTANT_PREFIX = "[FuzzyBot ~] ";
  const INTRO_STREAM_TEXT = [
    "FuzzyBot_Help.Me ist ein experimenteller Chatbot auf dem KI-Cluster der HSBI, der transparenter machen soll, wie Chatbots mit Zusatzwissen im Hintergrund arbeiten.",
    "Gleichzeitig demonstriert er, wie ein Chatbot aufgebaut sein koennte, der bei der Arbeit mit dem KI-Cluster unterstuetzt.",
    "",
    "Stelle deine Fragen mit der \u2328 Bildschirmtastatur unten und schicke sie mit SEND ab.",
    ...(DEMO_MODE
      ? ["", "DEMO MODUS: Antworten sind simuliert (keine echte LLM-Verbindung)."]
      : [])
  ].join("\n");


  // ==== System Prompt fuer das Apertus-Modell ====
  const SYSTEM_PROMPT = `
Du bist ein hilfreicher Chatbot fuer das KI-Cluster der Hochschule Bielefeld (HSBI).
Kontext: FuzzyBot_Help.Me ist eine Live-Installation (Touchscreen & Web) von Max Schweder. Sie erforscht, wie das Cluster gestalterisch genutzt werden kann, wie offene Modelle (Apertus-8B-Instruct) ressourcenschonend betrieben und mit studiengangsspezifischen Materialien angereichert werden. Das Interface macht Hintergrundprozesse sichtbar und dokumentiert technische und organisatorische Schritte fuer Training und moegliche Live-Einsaetze.
Deine Hauptaufgabe ist es, Nutzer*innen bei allen Fragen zur Arbeit auf dem Cluster zu unterstuetzen
(zum Beispiel Login, SSH, Tunneling, Slurm-Jobs und Queues, GPU-/CPU-Knoten, Speicher, Module/Software und typische Fehlermeldungen).

Antworte kurz, klar und in moeglichst einfacher Sprache.
Benutze die Sprache, die der/die Nutzer*in verwendet.
Wenn du etwas nicht sicher weisst, sag das ehrlich und schlage sinnvolle naechste Schritte vor
(z.B. einen Befehl zum Nachschauen oder eine passende Dokumentation).
Gib keine Anleitungen zu illegalen oder gefaehrlichen Handlungen und halte dich an die Regeln der HSBI.
`.trim();
  // ==============================================
  const DEMO_RESPONSES = [
    "DEMO: Der LLM-Server laeuft auf einem GPU-Knoten, der via Slurm-Job reserviert wird.",
    "DEMO: Fuer einen dauerhaften Dienst laeuft der Server in einer tmux-Session auf dem Login-Node, die den Slurm-Job startet.",
    "DEMO: Der Client auf der VM leitet Anfragen an den GPU-Node weiter und zeigt RAG-Kontext an."
  ];
  const DEMO_RAG_HITS = [
    {
      doc_id: "demo-cluster-cheatsheet.pdf",
      page: 2,
      text: "GPU-Nodes muessen per salloc angefordert werden; danach mit srun in den Job wechseln."
    },
    {
      doc_id: "demo-ops-notes.pdf",
      page: 5,
      text: "tmux auf dem Login-Node haelt den Job-Start offen, auch wenn SSH getrennt wird."
    }
  ];
  let demoResponseIndex = 0;


  const term           = document.getElementById("terminal");
  const requestConsole = document.getElementById("request-console");
  const ragConsole     = document.getElementById("rag-console");
  const kbToggle       = document.getElementById("kb-toggle");
  const kbContainer    = document.getElementById("simple-keyboard");
  const introOverlay   = document.getElementById("intro-overlay");
  const introButton    = document.getElementById("intro-continue");
  const resetButton    = document.getElementById("reset-button");
  const idleBar        = document.getElementById("idle-progress");
  const introCard      = document.querySelector(".intro-card");
  const aboutSteps     = Array.from(document.querySelectorAll(".about-step"));
  const paneRequest    = document.getElementById("pane-request");
  const paneRag        = document.getElementById("pane-rag");
  const paneChat       = document.getElementById("pane-chat");

  if (!term || !requestConsole || !ragConsole) {
    console.error("Missing required DOM nodes; aborting init.");
    return;
  }
  if (UI_SCALE !== 1 && document.body) {
    const ratio = 100 / UI_SCALE;
    if ("zoom" in document.body.style) {
      document.body.style.zoom = String(UI_SCALE);
      document.body.style.width = `${ratio}%`;
      document.body.style.height = `${ratio}vh`;
    } else {
      document.documentElement.style.fontSize = `${16 * UI_SCALE}px`;
    }
  }
  // Clear any server-rendered placeholders so the JS can take over.
  term.innerHTML = "";

  // Prompt element for the console (original style)
  const promptEl = document.createElement("div");
  promptEl.id = "prompt";

  // Hier wird der System Prompt an das Modell geschickt
  let messages = [
    { role: "system", content: SYSTEM_PROMPT }
  ];

  let currentInput = "";
  let ready   = true;
  let waiting = false;
  let canInteract = true;
  let typedStepTriggered = false;
  let activeAboutStep = null;
  let aboutStepSwitchTimer = null;
  let lastAboutStepSwitch = 0;
  let step3QueueTimer = null;
  const MIN_STEP_HOLD = 500; // ms minimum visual hold per step
  let waitingIndicatorTimer = null;
  const IDLE_TIMEOUT_MS = 300000; // 5 minutes
  const MAX_CHAT_LINES = 1200; // rolling buffer (~10 pages)
  const PREVIEW_CHAR_LIMIT = 60000; // cap for preview panes (shows tail)
  const MAX_MESSAGE_HISTORY = 200; // keep last N non-system messages
  let idleDeadline = 0;
  let idleRaf = null;
  let idleTriggered = false;
  let introStreamPlayed = false;

  const paneMap = {
    2: paneRequest,
    3: paneRag,
    4: paneChat
  };

  // For highlighting / RAG view
  let lastUserText = "";

  // For streaming assistant responses
  let currentAssistantNode = null;

  // Simple state machine for keyboard panel visibility
  const uiState = {
    keyboardVisible: false
  };

  let virtualKeyboard = null;
  const keyboardState = {
    layoutName: "default",
    capsLock: false,
    shiftActive: false
  };

  function setKeyboardLayout(layoutName) {
    keyboardState.layoutName = layoutName;
    if (virtualKeyboard) {
      virtualKeyboard.setOptions({ layoutName });
    }
  }

  function computeLayout() {
    const useShiftLayer = keyboardState.capsLock ^ keyboardState.shiftActive;
    return useShiftLayer ? "shift" : "default";
  }

  function applyLayoutFromModifiers() {
    setKeyboardLayout(computeLayout());
  }

  function handleCapsToggle() {
    keyboardState.capsLock = !keyboardState.capsLock;
    applyLayoutFromModifiers();
  }

  function handleShiftPress() {
    keyboardState.shiftActive = true;
    applyLayoutFromModifiers();
  }

  function releaseShiftIfNeeded() {
    if (!keyboardState.shiftActive) return;
    keyboardState.shiftActive = false;
    applyLayoutFromModifiers();
  }

  function performReset() {
    window.location.reload();
  }

  function updateIdleBar(fraction) {
    if (!idleBar) return;
    const clamped = Math.min(1, Math.max(0, fraction));
    idleBar.style.transform = `scaleX(${clamped})`;
  }

  function resetIdleTimer() {
    idleTriggered = false;
    idleDeadline = performance.now() + IDLE_TIMEOUT_MS;
    updateIdleBar(1);
  }

  function tickIdle(now) {
    const remaining = Math.max(0, idleDeadline - now);
    const fraction = Math.min(1, Math.max(0, remaining / IDLE_TIMEOUT_MS));
    updateIdleBar(fraction);

    if (!idleTriggered && remaining <= 0) {
      idleTriggered = true;
      performReset();
      return;
    }

    idleRaf = requestAnimationFrame(tickIdle);
  }

  function startIdleTimer() {
    resetIdleTimer();
    if (!idleRaf) {
      idleRaf = requestAnimationFrame(tickIdle);
    }
  }

  function stopIdleTimer() {
    if (idleRaf) {
      cancelAnimationFrame(idleRaf);
      idleRaf = null;
    }
  }

  function ensureVirtualKeyboard() {
    if (virtualKeyboard || !kbContainer || !window.SimpleKeyboard) return;
    const SimpleKeyboard = window.SimpleKeyboard.default;
    virtualKeyboard = new SimpleKeyboard(".simple-keyboard", {
      onChange: onKeyboardChange,
      onKeyPress: onKeyboardKeyPress,
      layoutName: keyboardState.layoutName,
      layout: {
        default: [
          "^ 1 2 3 4 5 6 7 8 9 0 ß ´ {bksp}",
          "{tab} q w e r t z u i o p ü +",
          "{caps} a s d f g h j k l ö ä # {enter}",
          "{shift} < y x c v b n m , . - {shift}",
          "{space}"
        ],
        shift: [
          "° ! \" § $ % & / ( ) = ? ` {bksp}",
          "{tab} Q W E R T Z U I O P Ü *",
          "{caps} A S D F G H J K L Ö Ä ' {enter}",
          "{shift} > Y X C V B N M ; : _ {shift}",
          "{space}"
        ]
      },
      display: {
        "{bksp}": "←",
        "{enter}": "SEND",
        "{tab}": "↹",
        "{caps}": "⇪",
        "{shift}": "⇧",
        "{space}": "Space"
      },
      buttonTheme: [
        {
          class: "hg-send",
          buttons: "{enter}"
        }
      ],
      theme: "hg-theme-default"
    });
    virtualKeyboard.setInput(currentInput);
    applyLayoutFromModifiers();
  }

  function onKeyboardChange(input) {
    currentInput = input;
    renderPrompt();
    if (!typedStepTriggered && ready) {
      typedStepTriggered = true;
      setHighlightedStep(1);
    }
  }

  function onKeyboardKeyPress(button) {
    if (button === "{enter}") {
      sendFromCurrentInput();
      setKeyboardVisible(false);
      if (virtualKeyboard) virtualKeyboard.setInput("");
      releaseShiftIfNeeded();
      applyLayoutFromModifiers();
      return;
    }

    if (button === "{shift}") {
      handleShiftPress();
      return;
    }

    if (button === "{caps}") {
      handleCapsToggle();
      return;
    }
    // For normal keys, immediately release any held shift so layout snaps back
    releaseShiftIfNeeded();
    if (!typedStepTriggered && ready) {
      typedStepTriggered = true;
      setHighlightedStep(1);
    }
  }

  function applyKeyboardState() {
    const visible = uiState.keyboardVisible;
    document.body.classList.toggle("keyboard-visible", visible);
    if (kbToggle) {
      kbToggle.setAttribute("aria-pressed", visible ? "true" : "false");
    }
    const panel = document.getElementById("keyboard-panel");
    if (panel) {
      panel.setAttribute("aria-hidden", visible ? "false" : "true");
    }
    if (visible) {
      ensureVirtualKeyboard();
      if (virtualKeyboard) virtualKeyboard.setInput(currentInput);
    }
    applyLayoutFromModifiers();
  }

  function setKeyboardVisible(isVisible) {
    if (uiState.keyboardVisible === isVisible) return;
    uiState.keyboardVisible = isVisible;
    applyKeyboardState();
    updateInteractionState();
  }

  function toggleKeyboardVisible() {
    setKeyboardVisible(!uiState.keyboardVisible);
  }

  function setHighlightedStep(stepNumber) {
    if (!aboutSteps || aboutSteps.length === 0) return;
    if (stepNumber === activeAboutStep) return;

    const now = Date.now();
    const elapsed = now - lastAboutStepSwitch;
    const applyStep = () => {
      activeAboutStep = stepNumber;
      lastAboutStepSwitch = Date.now();
      aboutSteps.forEach((el) => {
        if (stepNumber && el.dataset.step === String(stepNumber)) {
          el.classList.add("highlight-step");
        } else {
          el.classList.remove("highlight-step");
        }
      });
      Object.values(paneMap).forEach((pane) => pane?.classList.remove("highlight-panel"));
      if (paneMap[stepNumber]) {
        paneMap[stepNumber].classList.add("highlight-panel");
      }
    };

    if (aboutStepSwitchTimer) {
      clearTimeout(aboutStepSwitchTimer);
      aboutStepSwitchTimer = null;
    }

    if (elapsed >= MIN_STEP_HOLD) {
      applyStep();
    } else {
      aboutStepSwitchTimer = setTimeout(applyStep, MIN_STEP_HOLD - elapsed);
    }
  }

  function updateInteractionState() {
    const next = ready && !waiting;
    canInteract = next;

    if (kbToggle) {
      const cta = next && !uiState.keyboardVisible;
      kbToggle.classList.toggle("chat-cta", cta);
      kbToggle.classList.toggle("hidden-during-stream", waiting);
    }

    if (promptEl) {
      promptEl.classList.toggle("input-blocked", !next);
    }
  }

  function dismissIntroOverlay() {
    if (introOverlay) {
      introOverlay.classList.add("intro-exit");
    }
    if (introCard) {
      introCard.classList.add("intro-exit");
      const finalize = () => {
        introOverlay?.classList.add("is-hidden");
        introOverlay?.classList.remove("intro-exit");
        introCard.classList.remove("intro-exit");
        introCard.removeEventListener("animationend", finalize);
      };
      introCard.addEventListener("animationend", finalize);
      // Fallback in case animationend doesn't fire
      setTimeout(finalize, 1200);
    } else if (introOverlay) {
      introOverlay.classList.add("is-hidden");
    }
    term.focus();
  }

  // ----- Helpers for highlighting -----
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function pruneTermLines() {
    if (!term) return;
    const maxLines = MAX_CHAT_LINES;
    let lineCount = term.childElementCount - 1; // exclude prompt
    while (lineCount > maxLines && term.firstChild && term.firstChild !== promptEl) {
      term.removeChild(term.firstChild);
      lineCount = term.childElementCount - 1;
    }
  }

  function trimMessageHistory() {
    if (!messages || messages.length <= 1) return;
    const systemMsg = messages[0];
    const rest = messages.slice(1);
    if (rest.length > MAX_MESSAGE_HISTORY) {
      messages = [systemMsg, ...rest.slice(rest.length - MAX_MESSAGE_HISTORY)];
    }
  }

  function buildQueryTokens(queryText) {
    const stopwords = new Set([
      "der","die","das","und","ein","eine","mit","auf","im","in","von",
      "the","and"
    ]);
    const seen = new Set();
    return (queryText || "")
      .toLowerCase()
      .split(/[^\p{L}\p{N}]+/u)
      .map((t) => t.trim())
      .filter((t) => t.length >= 3 && !stopwords.has(t) && !seen.has(t) && (seen.add(t), true));
  }

  function truncatePlain(str) {
    if (!str) return "";
    return str.length > PREVIEW_CHAR_LIMIT
      ? str.slice(0, PREVIEW_CHAR_LIMIT) + "\n// ... truncated for preview ..."
      : str;
  }

  function highlightTokens(text, rawTokens) {
    if (!text) return "";

    const tokens = [];
    const seen = new Set();
    (rawTokens || []).forEach((token) => {
      const normalized = (token || "").toLowerCase();
      if (normalized.length >= 3 && !seen.has(normalized)) {
        seen.add(normalized);
        tokens.push(normalized);
      }
    });

    if (tokens.length === 0) return escapeHtml(text);

    const lower = text.toLowerCase();
    const ranges = [];

    tokens.forEach((token) => {
      let idx = lower.indexOf(token);
      while (idx !== -1) {
        ranges.push([idx, idx + token.length]);
        idx = lower.indexOf(token, idx + token.length);
      }
    });

    if (ranges.length === 0) return escapeHtml(text);

    ranges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [];
    ranges.forEach((range) => {
      const last = merged[merged.length - 1];
      if (!last || range[0] > last[1]) {
        merged.push(range);
      } else if (range[1] > last[1]) {
        last[1] = range[1];
      }
    });

    let cursor = 0;
    let result = "";
    merged.forEach(([start, end]) => {
      if (cursor < start) {
        result += escapeHtml(text.slice(cursor, start));
      }
      result += `<span class="rag-highlight">${escapeHtml(text.slice(start, end))}</span>`;
      cursor = end;
    });
    if (cursor < text.length) {
      result += escapeHtml(text.slice(cursor));
    }
    return result;
  }

  // ----- Top-left console: show payload being sent -----
  function showPayload(payload) {
    let text = JSON.stringify(payload, null, 2);
    if (text.length > PREVIEW_CHAR_LIMIT) {
      text = "// ... truncated for preview ...\n" + text.slice(-PREVIEW_CHAR_LIMIT);
    }
    requestConsole.textContent = text;
    requestConsole.scrollTop = requestConsole.scrollHeight;
  }


  // ----- Top-right console: show RAG header + chunks + user question -----
  function showRagHits(hits, ragUserMessage) {
    const htmlLines = [];

    const queryTokens = buildQueryTokens(lastUserText || "");
    setHighlightedStep(3);

    htmlLines.push("// RAG-ergaenzte Nutzerfrage, die fuer diese Antwort verwendet wird:");
    htmlLines.push("");
    htmlLines.push("Benutze den folgenden Kontext, wenn er relevant fuer die Nutzer*innenfrage ist:");
    htmlLines.push("");

    if (!hits || !Array.isArray(hits) || hits.length === 0) {
      htmlLines.push("// Kein RAG-Kontext fuer diese Anfrage genutzt.");
      htmlLines.push("");
      htmlLines.push("Nutzerfrage:");
      htmlLines.push(escapeHtml(lastUserText || ""));
      if (ragUserMessage) {
        htmlLines.push("");
        htmlLines.push("RAG-augmentierte Nutzerfrage:");
        htmlLines.push(escapeHtml(truncatePlain(ragUserMessage)));
      }
      let html = htmlLines.join("\n");
      if (html.length > PREVIEW_CHAR_LIMIT) {
        html += "\n// ... truncated for preview ...";
      }
      ragConsole.innerHTML = html;
      ragConsole.scrollTop = ragConsole.scrollHeight;
      return;
    }

    for (const [idx, h] of hits.entries()) {
      const docId = h.doc_id ?? "unbekannt";
      const page  = (h.page !== undefined && h.page !== null) ? h.page : "?";
      const text  = truncatePlain(h.text || "");

      const header = `#${idx + 1} [${docId} p.${page}]`;
      htmlLines.push(escapeHtml(header));

      const bodyHtml = highlightTokens(text, queryTokens);
      htmlLines.push(bodyHtml);
      htmlLines.push(""); // blank line between chunks
    }

    htmlLines.push("");
    htmlLines.push("Nutzerfrage:");
    htmlLines.push(escapeHtml(lastUserText || ""));
    if (ragUserMessage) {
      htmlLines.push("");
      htmlLines.push("RAG-augmentierte Nutzerfrage:");
      htmlLines.push(escapeHtml(truncatePlain(ragUserMessage)));
    }

    let html = htmlLines.join("\n");
    if (html.length > PREVIEW_CHAR_LIMIT) {
      html += "\n// ... truncated for preview ...";
    }
    ragConsole.innerHTML = html;
    ragConsole.scrollTop = ragConsole.scrollHeight;
  }


  // ----- Bottom console: chat log -----
  function print(line = "", extraClass = "") {
    const div = document.createElement("div");
    div.className = extraClass ? `line ${extraClass}` : "line";
    div.textContent = line;
    term.insertBefore(div, promptEl);
    pruneTermLines();
    term.scrollTop = term.scrollHeight;
  }

  function renderPrompt() {
    if (waiting) return;
    promptEl.textContent = PROMPT_PREFIX + currentInput;
    term.scrollTop = term.scrollHeight;
  }

  function setWaiting(isWaiting) {
    waiting = isWaiting;
    if (waiting) {
      promptEl.classList.add("waiting");
      promptEl.textContent = "... warte auf Antwort des Modells ...";
      startWaitingIndicator();
    } else {
      promptEl.classList.remove("waiting");
      renderPrompt();
      stopWaitingIndicator();
    }
    term.scrollTop = term.scrollHeight;
    updateInteractionState();
  }

  function insertBlankLine() {
    const blank = document.createElement("div");
    blank.className = "line spacer-line";
    blank.textContent = "\u00A0"; // non-breaking space so it renders height
    term.insertBefore(blank, promptEl);
    term.scrollTop = term.scrollHeight;
  }

  function clearTerminal() {
    if (!term) return;
    term.innerHTML = "";
    currentAssistantNode = null;
    term.appendChild(promptEl);
    renderPrompt();
  }

  function playIntroStream() {
    if (introStreamPlayed) return;
    introStreamPlayed = true;
    clearTerminal();
    const prevVisibility = promptEl.style.visibility;
    promptEl.style.visibility = "hidden";
    const text = INTRO_STREAM_TEXT;
    startAssistantMessage(ASSISTANT_PREFIX);
    let idx = 0;
    const speedMs = 10; // faster stream
    const ticker = () => {
      if (!currentAssistantNode) {
        startAssistantMessage(ASSISTANT_PREFIX);
      }
      const chunk = text.slice(idx, idx + 1);
      if (chunk) {
        appendAssistantText(chunk);
        idx += 1;
        setTimeout(ticker, speedMs);
      } else {
        finishAssistantMessage();
        promptEl.style.visibility = prevVisibility;
        renderPrompt();
      }
    };
    ticker();
  }

  function startAssistantMessage(prefix = ASSISTANT_PREFIX) {
    currentAssistantNode = document.createElement("div");
    currentAssistantNode.className = "line model-line";
    currentAssistantNode.textContent = prefix;
    term.insertBefore(currentAssistantNode, promptEl);
    term.scrollTop = term.scrollHeight;
  }

  function appendAssistantText(text) {
    if (!currentAssistantNode) {
      startAssistantMessage(ASSISTANT_PREFIX);
    }
    currentAssistantNode.textContent += text;
    term.scrollTop = term.scrollHeight;
  }

  function finishAssistantMessage() {
    if (currentAssistantNode) {
      insertBlankLine();
      currentAssistantNode = null;
    }
  }

  function startWaitingIndicator() {
    stopWaitingIndicator();
    let visible = false;
    waitingIndicatorTimer = setInterval(() => {
      visible = !visible;
      if (visible) {
        print("--- Waiting for Model Response ---");
      }
    }, 800);
  }

  function stopWaitingIndicator() {
    if (waitingIndicatorTimer) {
      clearInterval(waitingIndicatorTimer);
      waitingIndicatorTimer = null;
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function buildDemoRagUserMessage(userText) {
    const contextLines = DEMO_RAG_HITS.map((hit) => {
      return `[${hit.doc_id} p.${hit.page}] ${hit.text}`;
    });

    return [
      "DEMO MODE: This is simulated context (no real retrieval).",
      "",
      "Use the following context if relevant:",
      "",
      ...contextLines,
      "",
      "User question:",
      userText
    ].join("\n");
  }

  async function sendDemoMessage(payload, text) {
    const responseText = DEMO_RESPONSES[demoResponseIndex % DEMO_RESPONSES.length];
    demoResponseIndex += 1;

    const ragUserMessage = buildDemoRagUserMessage(text);
    setHighlightedStep(3);
    showRagHits(DEMO_RAG_HITS, ragUserMessage);

    await sleep(350);
    setWaiting(false);
    setHighlightedStep(4);
    startAssistantMessage(ASSISTANT_PREFIX);

    for (let i = 0; i < responseText.length; i += 1) {
      appendAssistantText(responseText[i]);
      await sleep(8);
    }

    if (responseText) {
      messages.push({ role: "assistant", content: responseText });
      trimMessageHistory();
    }

    finishAssistantMessage();
    setHighlightedStep(null);
    ready = true;
    currentInput = "";
    setWaiting(false);
  }

  async function sendMessage(text) {
    ready = false;
    updateInteractionState();
    lastUserText = text; // for highlighting in RAG view
    messages.push({ role: "user", content: text });
    trimMessageHistory();

    const payload = {
      model: "Apertus-8B-Instruct-2509",
      messages: messages,
      max_tokens: 2056,
      temperature: 0.7,
      top_p: 0.95,
      stream: true
    };

    // Update the top-left console with the full payload we send
    showPayload(payload);

    if (DEMO_MODE) {
      await sendDemoMessage(payload, text);
      return;
    }

    let assistantText = "";

    const controller = new AbortController();
    const fetchTimeout = setTimeout(
      () => controller.abort("stream timed out"),
      120000
    );

    try {
      const res = await fetch(API_BASE + "/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      if (!res.ok || !res.body) {
        const txt = await res.text().catch(() => "");
        print("");
        print("FEHLER> " + res.status + " " + txt, "error-line");
        showRagHits([], null);
        insertBlankLine();
        return;
      }
      // Server accepted request; retrieval/processing starts
      setHighlightedStep(3);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer    = "";
      let done      = false;
      let streamingStarted = false;

      while (!done) {
        const { value, done: doneChunk } = await reader.read();
        if (doneChunk) break;

        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // incomplete chunk stays in buffer

        for (const part of parts) {
          const lines = part.split("\n").filter(Boolean);

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;

            const dataStr = line.slice(5).trim();
            if (!dataStr) continue;

            if (dataStr === "[DONE]") {
              done = true;
              break;
            }

            let obj;
            try {
              obj = JSON.parse(dataStr);
            } catch (e) {
              console.error("Bad JSON from SSE:", dataStr);
              continue;
            }

            // First SSE event received -> stop showing "... waiting for model response ..."
            if (!streamingStarted) {
              setWaiting(false);
              streamingStarted = true;
              setHighlightedStep(4);
            }

            const choice = obj.choices && obj.choices[0];
            const delta  = choice && choice.delta ? choice.delta : {};

            // 1) META EVENT: RAG info + RAG-augmented user message
            if (obj.rag_hits || obj.rag_user_message) {
              const hits = obj.rag_hits || [];
              const ragMsg = obj.rag_user_message || null;
              showRagHits(hits, ragMsg);    // only in RAG pane, not in chat
              continue;
            }

            // 2) TOKEN EVENT: streaming content
            const token = delta.content;

            if (token) {
              setHighlightedStep(4);
              appendAssistantText(token);
              assistantText += token;
            }

            // 3) END EVENT
            if (choice && choice.finish_reason === "stop") {
              done = true;
              break;
            }
          }

          if (done) break;
        }
      }

    } catch (err) {
      print("");
      const errMsg = err && err.name === "AbortError"
        ? "Zeitüberschreitung bei der Anfrage."
        : err;
      print("FEHLER> " + errMsg, "error-line");
      showRagHits([], null);
      insertBlankLine();
    } finally {
      clearTimeout(fetchTimeout);
      if (assistantText) {
        messages.push({ role: "assistant", content: assistantText });
        trimMessageHistory();
      }
      finishAssistantMessage();
      setHighlightedStep(null);
      ready = true;
      currentInput = "";
      setWaiting(false);
    }
  }

  // ----- Shared "send" helper -----
  function sendFromCurrentInput() {
    if (!ready) return;
    const text = (currentInput || "").trim();
    if (!text) return;

    print(PROMPT_PREFIX + text);
    insertBlankLine();
    setHighlightedStep(2);
    if (step3QueueTimer) {
      clearTimeout(step3QueueTimer);
      step3QueueTimer = null;
    }
    step3QueueTimer = setTimeout(() => {
      if (activeAboutStep === 2) {
        setHighlightedStep(3);
      }
    }, MIN_STEP_HOLD + 100);

    // clear both sources of truth
    currentInput = "";
    if (virtualKeyboard) virtualKeyboard.setInput("");

    setWaiting(true);
    sendMessage(text);
    if (uiState.keyboardVisible) {
      setKeyboardVisible(false);
    }
    typedStepTriggered = false;
  }

  // ----- Physical keyboard input into "terminal" (original behavior) -----
  window.addEventListener("keydown", (e) => {
    if (document.activeElement !== term) return;

    if (!ready) {
      e.preventDefault();
      return;
    }

    if (e.key === "Backspace") {
      e.preventDefault();
      currentInput = currentInput.slice(0, -1);
      renderPrompt();
      if (uiState.keyboardVisible && virtualKeyboard) {
        virtualKeyboard.setInput(currentInput);
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      sendFromCurrentInput();
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      currentInput += e.key;
      renderPrompt();
      if (uiState.keyboardVisible && virtualKeyboard) {
        virtualKeyboard.setInput(currentInput);
      }
    }
  });

  // Init bottom console
  term.appendChild(promptEl);
  renderPrompt();
  term.focus();
  term.addEventListener("click", () => {
    term.focus();
  });

  // Allow pasting text into the console when focused
  term.addEventListener("paste", (e) => {
    e.preventDefault();
    const text = (e.clipboardData && e.clipboardData.getData("text")) ||
                 (window.clipboardData && window.clipboardData.getData("Text")) ||
                 "";
    if (!text) return;
    currentInput += text;
    renderPrompt();
    if (uiState.keyboardVisible && virtualKeyboard) {
      virtualKeyboard.setInput(currentInput);
    }
    if (!typedStepTriggered && ready) {
      typedStepTriggered = true;
      setHighlightedStep(1);
    }
  });

  // Keyboard toggle wiring
  if (kbToggle) {
    kbToggle.addEventListener("click", () => {
      toggleKeyboardVisible();
    });
  }

  if (introButton) {
    introButton.addEventListener("click", () => {
      dismissIntroOverlay();
      playIntroStream();
    });
  }

  if (resetButton) {
    resetButton.addEventListener("click", () => {
      performReset();
    });
  }

  ["pointerdown", "keydown", "touchstart"].forEach((evt) => {
    window.addEventListener(
      evt,
      () => {
        resetIdleTimer();
      },
      { capture: true, passive: true }
    );
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopIdleTimer();
    } else {
      resetIdleTimer();
      startIdleTimer();
    }
  });

  applyKeyboardState();
  updateInteractionState();
  startIdleTimer();

  // Init top consoles
  requestConsole.textContent =
    "// Vorschau der gesendeten Anfrage erscheint hier, sobald du die erste Nachricht schickst.\n";
  requestConsole.scrollTop = requestConsole.scrollHeight;
  ragConsole.textContent =
    "// Abgerufener RAG-Kontext (Top-k Abschnitte + Nutzerfrage) wird hier angezeigt.\n";
  ragConsole.scrollTop = ragConsole.scrollHeight;

});
