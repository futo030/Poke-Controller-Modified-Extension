"use strict";

// 出力画面の Serial タブ(機器へ送ったデータ)、Log タブ(コンソールに出ているログ)、Note タブ(メモ)、文字の検索。
// - Serial / Log / Note タブは、このブラウザだけの表示の切り替え(出力ページは、変えない)
// - Note は、操作できるブラウザだけが書き込める。書き換えてから少し待って、サーバーに保存する(プロファイルごと)
// - 届いた文字は溜めておき、そのタブを表示している間だけ画面に書く(表示していない間は、画面の処理を増やさない)
// - 検索は、表示しているタブの出力画面が対象(Page は Output#1 と #2)。Ctrl+F(出力画面にフォーカスがあるとき)か、🔍 で開く

window.outview = (function () {
  const byId = (id) => document.getElementById(id);
  // 画面に残す行数の上限(超えた分は、古い方から消す)
  const MAX_LINES = 10000;
  // Log のレベルの分け方(低い順)と、絞り込みの設定を覚える場所
  const LEVELS = ["debug", "info", "warning", "error"];
  const LEVEL_KEY = "pokecon-log-level";
  // 検索: 印を付ける数の上限(これより多い場合は、新しい方から、この数だけ)と、打ってから検索するまでの待ち時間(ms)
  const SEARCH_MAX_HITS = 2000;
  const SEARCH_DELAY_MS = 150;
  // Note: 書き換えてから、保存するまでの待ち時間(ms)
  const NOTE_SAVE_DELAY_MS = 1000;

  // 今の表示("pages": Page 1〜3 / "serial" / "log" / "note")
  let view = "pages";
  let operator = false;
  // タブごとの、まだ画面に書いていない分([[レベルの分け方, 文字], ...])と、画面にある行数
  const panes = {
    serial: { pending: [], lines: 0, id: "serial-text" },
    log: { pending: [], lines: 0, id: "log-text" },
  };

  // タブの名前と、その表示の見出し
  const VIEW_LABELS = { serial: "Serial", log: "Log", note: "Note" };
  const VIEW_TITLES = { serial: "Serial Monitor", log: "Log", note: "Note" };

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // 保存できない設定のブラウザでは、覚えないだけ
    }
  }

  // ---------------------------------------------------------------- タブ

  // 出力ページのタブの後ろに並べる部品(Serial / Log のタブと、検索のボタン)。app.js が、タブを作るときに呼ぶ
  function tabButtons() {
    const buttons = Object.entries(VIEW_LABELS).map(([name, label]) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.dataset.view = name;
      tab.textContent = label;
      tab.addEventListener("click", () => show(name));
      return tab;
    });
    const search = document.createElement("button");
    search.type = "button";
    search.id = "output-search-open";
    search.className = "output-search-open";
    search.title = "出力画面の文字を検索します (出力画面をクリックしてから Ctrl+F でも開けます)";
    search.textContent = "🔍";
    search.addEventListener("click", () => openSearch());
    return [...buttons, search];
  }

  function currentView() {
    return view;
  }

  function show(name) {
    if (view === name) return;
    view = name;
    render();
    refreshSearch(false);
  }

  // 表示を、今の状態に合わせる(app.js の描き直しの後にも呼ばれる)
  function render(isOperator) {
    if (isOperator !== undefined) operator = isOperator;
    const pages = view === "pages";
    for (const element of document.querySelectorAll("[data-pages-part]")) element.hidden = !pages;
    byId("extra-view").hidden = pages;
    for (const tab of document.querySelectorAll("#output-tabs [data-view]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.view === view));
    }
    // ページのタブの印は、ページを表示している間だけ付ける
    for (const tab of document.querySelectorAll("#output-tabs [data-page]")) {
      tab.setAttribute("aria-selected", String(pages && Number(tab.dataset.page) === activeOutputPage()));
    }
    setNoteEditable();
    if (pages) return;
    byId("extra-label").textContent = VIEW_TITLES[view];
    byId("log-level-label").hidden = view !== "log";
    byId("note-status").hidden = view !== "note";
    byId("extra-clear").hidden = view === "note";
    byId("extra-clear").disabled = !operator;
    for (const [name, pane] of Object.entries(panes)) byId(pane.id).hidden = name !== view;
    byId("note-text").hidden = view !== "note";
    if (panes[view]) flush(view);
  }

  // ---------------------------------------------------------------- 書き込み

  function countLines(text) {
    let count = 0;
    for (let index = text.indexOf("\n"); index !== -1; index = text.indexOf("\n", index + 1)) count += 1;
    return count;
  }

  // 届いた分を溜める。そのタブを表示していれば、すぐ画面に書く
  function add(name, entries, clear) {
    const pane = panes[name];
    if (clear) {
      pane.pending = [];
      pane.lines = 0;
      byId(pane.id).replaceChildren();
    }
    for (const entry of entries) {
      if (entry[1]) pane.pending.push(entry);
    }
    // 表示していない間に溜まりすぎた分は、古い方から捨てる(表示する行数の上限と同じ)
    if (pane.pending.length > MAX_LINES) pane.pending.splice(0, pane.pending.length - MAX_LINES);
    if (view === name) flush(name);
  }

  // 溜まった分を、画面に書く(レベルごとに、色を変える部品に入れる)
  function flush(name) {
    const pane = panes[name];
    if (!pane.pending.length) return;
    const target = byId(pane.id);
    const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 24;
    const fragment = document.createDocumentFragment();
    for (const [group, text] of pane.pending) {
      const span = document.createElement("span");
      if (group) span.className = `lv-${group}`;
      span.textContent = text;
      span.dataset.lines = countLines(text);
      pane.lines += Number(span.dataset.lines);
      fragment.append(span);
    }
    pane.pending = [];
    target.append(fragment);
    while (pane.lines > MAX_LINES && target.firstChild && target.firstChild !== target.lastChild) {
      pane.lines -= Number(target.firstChild.dataset.lines);
      target.firstChild.remove();
    }
    if (atBottom) target.scrollTop = target.scrollHeight;
  }

  function handle(message) {
    if (message.type === "serial") {
      add("serial", message.text ? [["", message.text]] : [], Boolean(message.clear));
    } else if (message.type === "log") {
      add("log", message.segments || [], Boolean(message.clear));
    } else if (message.type === "note") {
      receiveNote(message);
    }
  }

  // ---------------------------------------------------------------- Note

  let noteSaveTimer = null;
  // サーバーに保存してある内容(これと違う間は「保存していません」)
  let noteSaved = "";

  // 書き込めるのは、操作できるブラウザだけ。文字だけを書き込める欄にする(使えないブラウザでは、ふつうの書き込める欄にして、
  // 貼り付けるときに、文字だけを取り出す)
  function setNoteEditable() {
    const note = byId("note-text");
    if (!operator) {
      note.contentEditable = "false";
      return;
    }
    if (note.contentEditable === "plaintext-only" || note.contentEditable === "true") return;
    try {
      note.contentEditable = "plaintext-only";
    } catch (error) {
      note.contentEditable = "true";
    }
    if (note.contentEditable !== "plaintext-only") note.contentEditable = "true";
  }

  // Note の欄の中身を、文字にする。ブラウザは、改行を <br> で持ち、改行で終わるときは、最後にもう 1 つ <br> を置く
  // (最後の行にカーソルを置けるようにするため)。その 1 つは、改行に数えない
  function noteText() {
    let text = "";
    const visit = (parent) => {
      for (const node of parent.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          text += node.data;
        } else if (node.nodeName === "BR") {
          text += "\n";
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          // (文字だけを書き込める欄にできなかったブラウザでは、行を <div> で持つことがある)
          if (text && !text.endsWith("\n")) text += "\n";
          visit(node);
        }
      }
    };
    visit(byId("note-text"));
    return text.endsWith("\n") ? text.slice(0, -1) : text;
  }

  // Note の欄に、文字を入れる(noteText と同じ形: 行の間は <br>、改行で終わるときは、<br> をもう 1 つ)
  function setNoteText(text) {
    const nodes = [];
    text.split("\n").forEach((line, index) => {
      if (index > 0) nodes.push(document.createElement("br"));
      if (line) nodes.push(document.createTextNode(line));
    });
    if (text.endsWith("\n")) nodes.push(document.createElement("br"));
    byId("note-text").replaceChildren(...nodes);
  }

  function showNoteStatus() {
    const status = byId("note-status");
    if (!operator) status.textContent = "閲覧のみ";
    else status.textContent = noteText() === noteSaved ? "保存済み" : "保存していません...";
  }

  // サーバーから、Note の内容が届いた(開いたとき、または、保存された後)
  function receiveNote(message) {
    const note = byId("note-text");
    noteSaved = message.text || "";
    // 自分が書いている途中は、書き換えない(打っている文字や、カーソルの位置を壊さない)
    const editing = operator && document.activeElement === note;
    if (!editing && noteText() !== noteSaved) {
      setNoteText(noteSaved);
      refreshSearch(true);
    }
    showNoteStatus();
  }

  function saveNote() {
    window.clearTimeout(noteSaveTimer);
    noteSaveTimer = null;
    if (!operator) return;
    const text = noteText();
    if (text === noteSaved) return;
    sendAction("note_save", { text });
  }

  function onNoteInput() {
    showNoteStatus();
    window.clearTimeout(noteSaveTimer);
    noteSaveTimer = window.setTimeout(saveNote, NOTE_SAVE_DELAY_MS);
  }

  // ---------------------------------------------------------------- Log のレベルの絞り込み

  function applyLevel(level) {
    const value = LEVELS.includes(level) ? level : LEVELS[0];
    byId("log-level").value = value;
    byId("log-text").dataset.level = value;
    refreshSearch(true);
  }

  // ---------------------------------------------------------------- 検索

  const supportsHighlight = typeof window.Highlight === "function" && window.CSS && CSS.highlights;
  let hits = [];
  let truncated = false;
  let current = -1;
  let searchTimer = null;

  function searchOpen() {
    return !byId("output-search").hidden;
  }

  // 検索の対象の部品(今のタブで、表示しているもの。上から順)
  function searchTargets() {
    if (view === "note") return [byId("note-text")];
    if (view !== "pages") return [byId(panes[view].id)];
    return [...document.querySelectorAll("#output-1 pre, #output-2 pre")].filter((pre) => !pre.hidden && pre.offsetParent !== null);
  }

  // 大文字と小文字を区別するか(初めは、区別しない。「Aa」のボタンで切り替える)
  let matchCase = false;

  // 部品の中から、query を含む所をすべて探す(隠している行は対象にしない)
  function findAll(target, query) {
    const nodes = [];
    const starts = [];
    let text = "";
    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeType !== Node.TEXT_NODE) {
        // Note の改行(<br>)。行をまたいで一致しないように、改行として数える(どの文字の部品にも、属さない)
        if (node.nodeName === "BR") text += "\n";
        continue;
      }
      // レベルの絞り込みで隠している行(表示されていない部品の中の文字)は、飛ばす
      if (node.parentElement !== target && node.parentElement.offsetParent === null) continue;
      nodes.push(node);
      starts.push(text.length);
      text += node.data;
    }
    const found = [];
    const haystack = matchCase ? text : text.toLowerCase();
    const needle = matchCase ? query : query.toLowerCase();
    // 位置(全体の文字の中の番号)を、その文字のある部品と、その中の番号に直す
    const locate = (offset, isEnd) => {
      let low = 0;
      let high = nodes.length - 1;
      while (low < high) {
        const middle = (low + high + 1) >> 1;
        if (starts[middle] <= offset) low = middle;
        else high = middle - 1;
      }
      // 終わりの位置が、部品の境目にあるときは、前の部品の終わりにする
      if (isEnd && low > 0 && starts[low] === offset) low -= 1;
      return [nodes[low], offset - starts[low]];
    };
    for (let index = haystack.indexOf(needle); index !== -1; index = haystack.indexOf(needle, index + needle.length)) {
      const range = document.createRange();
      range.setStart(...locate(index, false));
      range.setEnd(...locate(index + needle.length, true));
      found.push(range);
    }
    return found;
  }

  function clearHighlights() {
    if (supportsHighlight) {
      CSS.highlights.delete("search-hit");
      CSS.highlights.delete("search-current");
    }
  }

  function comparePosition(a, b) {
    return a.compareBoundaryPoints(Range.START_TO_START, b);
  }

  // 検索し直して、印を付け直す。anchor: 前の「今の位置」(その近くを選び直す。null なら、いちばん新しい一致を選ぶ)
  function collect(anchor, step) {
    const query = byId("output-search-text").value;
    hits = [];
    truncated = false;
    clearHighlights();
    if (query) {
      const targets = searchTargets();
      for (const target of targets) {
        for (const range of findAll(target, query)) hits.push({ range, target });
      }
      if (hits.length > SEARCH_MAX_HITS) {
        hits = hits.slice(-SEARCH_MAX_HITS);
        truncated = true;
      }
      const order = new Map(targets.map((target, index) => [target, index]));
      const usable = anchor && order.has(anchor.target) && anchor.range.startContainer.isConnected;
      if (!hits.length) {
        current = -1;
      } else if (!usable) {
        current = hits.length - 1;
      } else {
        // 前の位置と同じ一致か、それより後ろで、いちばん近い一致
        const isBefore = (hit) =>
          hit.target === anchor.target ? comparePosition(hit.range, anchor.range) < 0 : order.get(hit.target) < order.get(anchor.target);
        let after = hits.findIndex((hit) => !isBefore(hit));
        if (after === -1) after = hits.length;
        const same = after < hits.length && hits[after].target === anchor.target && comparePosition(hits[after].range, anchor.range) === 0;
        if (!step) current = Math.min(after, hits.length - 1);
        else if (same) current = (after + step + hits.length) % hits.length;
        else current = ((step < 0 ? after - 1 : after) + hits.length) % hits.length;
      }
    } else {
      current = -1;
    }
    showCurrent();
  }

  function showCurrent() {
    const label = byId("output-search-count");
    if (!byId("output-search-text").value) {
      label.textContent = "";
    } else if (!hits.length) {
      label.textContent = "0 件";
    } else {
      const hit = hits[current];
      if (supportsHighlight) {
        CSS.highlights.set("search-hit", new Highlight(...hits.map((item) => item.range)));
        CSS.highlights.set("search-current", new Highlight(hit.range));
      } else {
        // 印を付けられないブラウザでは、今の位置を、選んだ状態にして見せる
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(hit.range.cloneRange());
      }
      // 今の位置が見える所まで、その出力画面をスクロールする
      const box = hit.range.getBoundingClientRect();
      const frame = hit.target.getBoundingClientRect();
      if (box.top < frame.top || box.bottom > frame.bottom) {
        hit.target.scrollTop += box.top - frame.top - hit.target.clientHeight / 2;
      }
      label.textContent = `${current + 1}/${hits.length}${truncated ? "+" : ""}`;
    }
  }

  function refreshSearch(keepPosition) {
    if (!searchOpen()) return;
    window.clearTimeout(searchTimer);
    collect(keepPosition && current >= 0 ? hits[current] : null, 0);
  }

  function moveSearch(step) {
    if (!searchOpen()) return;
    window.clearTimeout(searchTimer);
    // 出力が増えているかもしれないので、検索し直してから動く
    collect(current >= 0 ? hits[current] : null, step);
  }

  function openSearch() {
    const input = byId("output-search-text");
    const selected = String(window.getSelection() || "");
    if (!searchOpen()) byId("output-search").hidden = false;
    // 1 行の中で文字を選んでいれば、その文字を検索する
    if (selected.trim() && !selected.includes("\n") && document.querySelector(".panel.output").contains(window.getSelection().anchorNode)) {
      input.value = selected;
    }
    input.focus();
    input.select();
    refreshSearch(false);
  }

  function closeSearch() {
    if (!searchOpen()) return;
    window.clearTimeout(searchTimer);
    const hadFocus = byId("output-search").contains(document.activeElement);
    byId("output-search").hidden = true;
    hits = [];
    current = -1;
    clearHighlights();
    // フォーカスを出力画面に戻す(続けて Ctrl+F で開き直せるように)
    const targets = searchTargets();
    if (hadFocus && targets.length) targets[0].focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- 準備

  let sendAction = () => {};

  function setup(send) {
    sendAction = send;
    byId("extra-clear").addEventListener("click", () => {
      if (panes[view]) send("clear_view", { view });
    });
    const note = byId("note-text");
    note.addEventListener("input", onNoteInput);
    // 欄から出たとき・ページを閉じるときは、待たずに保存する
    note.addEventListener("blur", saveNote);
    window.addEventListener("pagehide", saveNote);
    note.addEventListener("paste", (event) => {
      // 文字だけを書き込める欄にできなかったブラウザでは、貼り付けるものから、文字だけを取り出す
      if (note.contentEditable !== "true") return;
      event.preventDefault();
      document.execCommand("insertText", false, (event.clipboardData || window.clipboardData).getData("text"));
    });
    byId("log-level").replaceChildren(
      new Option("すべて (DEBUG 以上)", "debug"),
      new Option("INFO 以上", "info"),
      new Option("WARNING 以上", "warning"),
      new Option("ERROR 以上", "error")
    );
    byId("log-level").addEventListener("change", (event) => {
      storageSet(LEVEL_KEY, event.target.value);
      applyLevel(event.target.value);
    });
    applyLevel(storageGet(LEVEL_KEY));

    const input = byId("output-search-text");
    input.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => refreshSearch(false), SEARCH_DELAY_MS);
    });
    byId("output-search").addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        // (Esc は、画面全体では「コマンドの停止」なので、検索の欄の中では、そちらに渡さない)
        event.preventDefault();
        event.stopPropagation();
        closeSearch();
      } else if (event.key === "Enter" && event.target === input) {
        event.preventDefault();
        moveSearch(event.shiftKey ? 1 : -1);
      } else if (event.key.toLowerCase() === "f" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        event.stopPropagation();
        input.select();
      }
    });
    byId("output-search-case").addEventListener("click", (event) => {
      matchCase = !matchCase;
      event.currentTarget.setAttribute("aria-pressed", String(matchCase));
      event.currentTarget.title = matchCase
        ? "大文字と小文字を区別しない (今は、区別する)"
        : "大文字と小文字を区別する (今は、区別しない)";
      refreshSearch(true);
    });
    byId("output-search-previous").addEventListener("click", () => moveSearch(-1));
    byId("output-search-next").addEventListener("click", () => moveSearch(1));
    byId("output-search-close").addEventListener("click", closeSearch);
    // 出力画面にフォーカスがあるときの Ctrl+F は、ブラウザの検索の代わりに、この検索を開く
    document.querySelector(".panel.output").addEventListener("keydown", (event) => {
      if (event.key.toLowerCase() !== "f" || !(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
      event.preventDefault();
      openSearch();
    });
    render();
  }

  // (app.js の send は、先に読み込まれている)
  setup(send);
  // このファイルの読み込みが終わる前に、サーバーから届いていた分を受け取る
  for (const message of pendingViewMessages.splice(0)) handle(message);
  return { handle, render, tabButtons, currentView, show, refreshSearch };
})();

// このファイルの読み込みが終わる前に、画面を描いていた場合は、Serial / Log / Note のタブを足すために、描き直す
if (state !== null) renderOutputPages(role === "operator");
