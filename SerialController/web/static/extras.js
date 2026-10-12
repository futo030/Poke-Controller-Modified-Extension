"use strict";
// こまごました機能: メニュー(表示・ヘルプ)、右クリックのメニュー、プレビュー上の Ctrl 操作(座標と色・範囲の保存)、
// ガイドと文章の表示、通知の確認、音量メーター、プリセットの書き出し、プロファイルの追加

window.extras = (function () {
  const byId = (id) => document.getElementById(id);
  const VIEW_KEY = "pokecon-view";
  // topPreview: 右側のパネルを下に置いたときの、プレビューの幅(px。null なら自動)
  // left: 左の列の幅(px。null なら自動)、previewWidth: プレビューの幅(px。null なら列の幅に合わせる)、
  // quality: 送る映像の幅の上限(px。0 は取り込みサイズのまま。null ならサーバーの今の値のまま)
  const DEFAULT_VIEW = { theme: "auto", panel: "right", mini: false, hide: [], swap: false, left: null, previewWidth: null, quality: null, sideLeft: null, topPreview: null };
  // 左の列・右の列の幅の下限(px)
  const COLUMN_MIN_WIDTH = 320;
  // 下に置いたパネルの、左側・右側の幅の下限(px)
  const SIDE_MIN_WIDTH = 240;
  // 選べるプレビューの幅(px)
  const PREVIEW_WIDTHS = [480, 640, 960, 1280, 1920];
  const OUTPUT_HEIGHT_KEY = "pokecon-output-height";
  // Output#1 の高さの下限(px)と、出力の枠のうち Output#1 以外(見出し・タブ・Output#2 の最小の高さ)に残す高さ(px)
  const OUTPUT_MIN_HEIGHT = 40;
  const OUTPUT_OTHER_HEIGHT = 150;
  // 表示・非表示を切り替えられる部品: [名前, 表示する文字]
  const PARTS = [
    ["commands", "コマンドの一覧"],
    ["output", "Output"],
    ["softcon", "Software-Controller"],
    ["manual", "手動操作"],
  ];
  let view = loadView();
  // プレビュー上の Ctrl+ドラッグ: null / {named, start, end}
  let rangeDrag = null;
  let onViewerCopy = null;
  let qualitySent = false;
  let introductionChecked = false;
  // コントローラーの設定の、最後に受け取った状態
  let setupState = null;

  // ---------------------------------------------------------------- メニュー

  // items: {label, action, disabled, checked} / "-"(区切り線) / {title: 見出し}
  function showMenu(items, x, y) {
    const menu = byId("popup-menu");
    menu.replaceChildren();
    for (const item of items) {
      if (item === "-") {
        menu.append(document.createElement("hr"));
      } else if (item.title) {
        const title = document.createElement("div");
        title.className = "menu-title";
        title.textContent = item.title;
        menu.append(title);
      } else {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", item.checked === undefined ? "menuitem" : "menuitemcheckbox");
        if (item.checked !== undefined) button.setAttribute("aria-checked", String(item.checked));
        button.textContent = (item.checked === undefined ? "" : item.checked ? "✓ " : "　 ") + item.label;
        button.disabled = Boolean(item.disabled);
        button.addEventListener("click", () => {
          if (!item.keepOpen) hideMenu();
          item.action();
        });
        menu.append(button);
      }
    }
    menu.hidden = false;
    // 画面からはみ出さない位置に置く
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(x, window.innerWidth - rect.width - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(y, window.innerHeight - rect.height - 4))}px`;
    const first = menu.querySelector("button:not(:disabled)");
    if (first) first.focus();
  }

  function hideMenu() {
    const menu = byId("popup-menu");
    if (!menu.hidden) {
      menu.hidden = true;
      if (document.activeElement && menu.contains(document.activeElement)) document.activeElement.blur();
    }
  }

  function menuBelow(button, items) {
    const rect = button.getBoundingClientRect();
    showMenu(items, rect.left, rect.bottom + 2);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(() => window.prompt("コピーしてください", text));
    } else {
      window.prompt("コピーしてください", text);
    }
  }

  // ---------------------------------------------------------------- 文章・ガイドの表示

  // fixed: 枠の高さを決めておく(中身を切り替えても、枠の大きさが変わらないようにする)
  function openViewer(title, content, copyable = null, fixed = false) {
    byId("viewer").querySelector(".viewer").classList.toggle("fixed", fixed);
    byId("viewer-title").textContent = title;
    byId("viewer-body").replaceChildren(content);
    byId("viewer-copy").hidden = copyable === null;
    onViewerCopy = copyable;
    byId("viewer").hidden = false;
    byId("viewer-close").focus();
    sendFocus();
  }

  function closeViewer() {
    byId("viewer").hidden = true;
    byId("viewer-body").replaceChildren();
    document.activeElement.blur();
    sendFocus();
  }

  // masked: フォルダーの場所を隠した文字(あれば、「マスクしてコピー」のボタンを出す。環境の診断)
  function showText(title, text, note, masked) {
    const box = document.createElement("div");
    if (masked) {
      const button = document.createElement("button");
      button.type = "button";
      button.id = "masked-copy";
      button.textContent = "マスクしてコピー";
      button.title = "フォルダーの場所(ユーザー名など)を *** にして、コピーします";
      button.addEventListener("click", () => copyText(masked));
      const row = document.createElement("p");
      row.append(button, " フォルダーの場所(ユーザー名など)を隠して、コピーします。そのままコピーするときは、上の「コピー」。");
      box.append(row);
    }
    if (note) {
      const paragraph = document.createElement("p");
      paragraph.style.whiteSpace = "pre-wrap";
      paragraph.textContent = note;
      box.append(paragraph);
    }
    const pre = document.createElement("pre");
    pre.textContent = text;
    box.append(pre);
    openViewer(title, box, () => copyText(text));
  }

  async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${response.status}`);
    return (await response.text()).replace(/^﻿/, "");
  }

  // Instruction Manual: 「# 見出し」で1項目。## 小見出し / - 箇条書き / ``` コード / ![..](画像) / 文章
  function parseManual(text) {
    const topics = [];
    let inCode = false;
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        inCode = !inCode;
      } else if (inCode) {
        if (topics.length) topics[topics.length - 1].lines.push(["code", line.replace(/\s+$/, "")]);
      } else if (trimmed.startsWith("# ")) {
        topics.push({ title: trimmed.slice(2).trim(), lines: [] });
      } else if (trimmed === "" || !topics.length) {
        continue;
      } else if (trimmed.startsWith("![") && trimmed.endsWith(")") && trimmed.includes("](")) {
        topics[topics.length - 1].lines.push(["img", trimmed.slice(trimmed.indexOf("](") + 2, -1).trim()]);
      } else if (trimmed.startsWith("## ")) {
        topics[topics.length - 1].lines.push(["h", trimmed.slice(3).trim()]);
      } else if (trimmed.startsWith("- ")) {
        topics[topics.length - 1].lines.push(["li", trimmed.slice(2).trim()]);
      } else {
        topics[topics.length - 1].lines.push(["p", trimmed]);
      }
    }
    return topics;
  }

  // 文章の中の URL(かっこ・日本語の文字・空白の手前まで。Manual.py と同じ決まり)
  const URL_PATTERN = /https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+/g;

  function appendWithLinks(element, text) {
    // 文字を入れる。URL は、新しいタブで開くリンクにする
    let position = 0;
    for (const found of text.matchAll(URL_PATTERN)) {
      const url = found[0].replace(/[.,;:]+$/, "");
      element.append(text.slice(position, found.index));
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = url;
      element.append(link);
      position = found.index + url.length;
    }
    element.append(text.slice(position));
  }

  function renderLines(target, lines, imageBase) {
    let list = null;
    let code = null;
    for (const [kind, text] of lines) {
      if (kind !== "li") list = null;
      if (kind !== "code") code = null;
      if (kind === "li") {
        if (list === null) {
          list = document.createElement("ul");
          target.append(list);
        }
        const item = document.createElement("li");
        appendWithLinks(item, text);
        list.append(item);
      } else if (kind === "code") {
        if (code === null) {
          code = document.createElement("pre");
          target.append(code);
        }
        code.textContent += (code.textContent ? "\n" : "") + text;
      } else if (kind === "img") {
        // 画像の名前に、フォルダの区切りは使えない
        if (!/^[^/\\]+$/.test(text)) continue;
        const image = document.createElement("img");
        image.src = `${imageBase}/${encodeURIComponent(text)}`;
        image.alt = "";
        image.loading = "lazy";
        target.append(image);
      } else {
        const element = document.createElement(kind === "h" ? "h4" : "p");
        if (kind === "h") element.textContent = text;
        else appendWithLinks(element, text);
        // 「【重要】」で始まる文章は、赤い文字で表示する(Introduction.py と同じ決まり)
        if (kind === "p" && text.startsWith("【重要】")) element.classList.add("important");
        target.append(element);
      }
    }
  }

  async function showManual() {
    let topics;
    try {
      // Web 版のマニュアルに、スクリプトの書き方の説明(どちらの画面でも同じ文章)を足す
      topics = parseManual(await fetchText("/assets/manual/manual_web.md"));
      const common = parseManual(await fetchText("/assets/manual/scripting.md"));
      const index = topics.findIndex((topic) => topic.title === "Web 版で使えないもの");
      topics.splice(index >= 0 ? index : topics.length, 0, ...common);
    } catch (error) {
      showText("Instruction Manual", "Instruction Manual の文章を読み込めませんでした。");
      return;
    }
    const box = document.createElement("div");
    box.className = "guide";
    const nav = document.createElement("nav");
    const body = document.createElement("div");
    const show = (index) => {
      [...nav.children].forEach((button, i) => button.setAttribute("aria-current", String(i === index)));
      body.replaceChildren();
      const title = document.createElement("h3");
      title.textContent = topics[index].title;
      body.append(title);
      renderLines(body, topics[index].lines, "/assets/manual");
      byId("viewer-body").scrollTop = 0;
    };
    topics.forEach((topic, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = topic.title;
      button.addEventListener("click", () => show(index));
      nav.append(button);
    });
    box.append(nav, body);
    openViewer("Instruction Manual", box, null, true);
    if (topics.length) show(0);
  }

  // 機能紹介: 「# 見出し」で1ページ。![..](画像) / - 箇条書き / 文章
  async function showIntroduction() {
    let pages;
    try {
      pages = parseManual(await fetchText("/assets/introduction/introduction_web.md"));
    } catch (error) {
      showText("機能紹介", "機能紹介の文章を読み込めませんでした。");
      return;
    }
    const box = document.createElement("div");
    box.className = "guide pages";
    const body = document.createElement("div");
    const pager = document.createElement("div");
    pager.className = "guide-pager";
    const previous = document.createElement("button");
    previous.type = "button";
    previous.textContent = "< 前へ";
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "次へ >";
    const count = document.createElement("span");
    let index = 0;
    const show = () => {
      body.replaceChildren();
      const title = document.createElement("h3");
      title.textContent = pages[index].title;
      body.append(title);
      // 画像を先に、文章を後に表示する
      renderLines(body, pages[index].lines.filter(([kind]) => kind === "img"), "/assets/introduction");
      renderLines(body, pages[index].lines.filter(([kind]) => kind !== "img"), "/assets/introduction");
      count.textContent = `${index + 1} / ${pages.length}`;
      byId("viewer-body").scrollTop = 0;
      previous.disabled = index === 0;
      next.disabled = index === pages.length - 1;
    };
    previous.addEventListener("click", () => {
      index -= 1;
      show();
    });
    next.addEventListener("click", () => {
      index += 1;
      show();
    });
    // 「今後は表示しない」: OK を押したときに保存する(チェックを外して OK を押すと、次回の起動時にまた表示する)
    const hide = document.createElement("label");
    const hideBox = document.createElement("input");
    hideBox.type = "checkbox";
    hideBox.checked = state ? !state.tools.show_introduction : false;
    hide.append(hideBox, " 今後は表示しない");
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "primary";
    ok.textContent = "OK";
    ok.addEventListener("click", () => {
      if (role === "operator") send("tool", { op: "introduction_hidden", hidden: hideBox.checked });
      closeViewer();
    });
    hideBox.disabled = role !== "operator";
    pager.append(previous, count, next, hide, ok);
    box.append(body, pager);
    openViewer("機能紹介", box, null, true);
    if (pages.length) show();
  }

  // 起動時(このページを開いて最初に状態を受け取ったとき)に、機能紹介を表示する
  function showIntroductionAtStartup() {
    if (introductionChecked || !state) return;
    introductionChecked = true;
    if (role === "operator" && state.tools.show_introduction) showIntroduction();
  }

  // ---------------------------------------------------------------- コントローラーのボタンの割り当ての設定

  function renderSetup(setup) {
    const modal = byId("controller-setup");
    if (!setup.active) {
      modal.hidden = true;
      if (setup.error) window.alert(setup.error);
      sendFocus();
      return;
    }
    const done = setup.phase === "done";
    const preparing = setup.phase === "preparing";
    byId("setup-device").textContent = `コントローラー: ${setup.device}`;
    byId("setup-file").textContent = `保存先: ${setup.file} (${setup.exists ? "既存のファイルを更新" : "新規作成"})`;
    byId("setup-progress").textContent = done ? "設定が終わりました" : preparing ? "" : `${setup.index + 1} / ${setup.total}  ${setup.label}`;
    byId("setup-instruction").textContent = setup.instruction;
    byId("setup-current").textContent =
      done || preparing ? "" : `現在の割り当て: ${setup.current}${setup.current_changed ? "" : " (変更なし)"}`;
    byId("setup-inputs").textContent = preparing ? "" : `入力中: ${setup.inputs.length ? setup.inputs.join(", ") : "なし"}`;
    byId("setup-summary-wrap").hidden = !done;
    let note = setup.error || "";
    if (done) {
      const body = byId("setup-summary").tBodies[0];
      body.replaceChildren(
        ...setup.summary.map((item) => {
          const row = document.createElement("tr");
          const label = document.createElement("td");
          label.textContent = item.label;
          const value = document.createElement("td");
          value.textContent = item.value + (item.changed ? "" : " (変更なし)");
          row.append(label, value);
          return row;
        })
      );
      if (setup.duplicates.length) note = `同じ入力が複数に割り当てられています: ${setup.duplicates.join(" / ")}`;
    }
    byId("setup-status").textContent = note;
    byId("setup-back").disabled = preparing || !setup.can_back;
    byId("setup-skip").hidden = done;
    byId("setup-clear").hidden = done;
    byId("setup-skip").disabled = preparing;
    byId("setup-clear").disabled = preparing;
    byId("setup-save").hidden = !done;
    byId("setup-save").textContent = setup.exists ? "更新して終了" : "保存";
    byId("setup-cancel").textContent = done && setup.exists ? "更新せずに終了" : "中止";
    setupState = setup;
    if (modal.hidden) {
      modal.hidden = false;
      byId("setup-cancel").focus();
      sendFocus();
    }
  }

  function setupControllerSetup() {
    byId("controller-setup-open").addEventListener("click", () => send("controller_setup", { op: "start" }));
    for (const op of ["back", "skip", "clear", "save"]) {
      byId(`setup-${op}`).addEventListener("click", () => send("controller_setup", { op }));
    }
    byId("setup-cancel").addEventListener("click", () => {
      // 割り当てを変えていて、まだ保存の確認まで進んでいない場合は、確かめてから中止する
      const asking = setupState && setupState.changed && setupState.phase !== "done";
      if (asking && !window.confirm("設定を保存せずに終了しますか？")) return;
      send("controller_setup", { op: "cancel" });
    });
    byId("notify-windows-test").addEventListener("click", () => send("tool", { op: "notify_windows" }));
  }

  function showQuestionForm(defaults) {
    const form = document.createElement("form");
    form.className = "question-form";
    const note = document.createElement("p");
    note.className = "wide";
    note.style.whiteSpace = "pre-wrap";
    note.textContent = defaults.title;
    form.append(note);
    const fields = [
      ["program", "プログラム名：", "input", defaults.program],
      ["developer", "制作者様：", "input", defaults.developer],
      ["question", "質問内容(経緯などは簡潔に)", "textarea", ""],
      ["tried", "試したこと(詳しく)", "textarea", ""],
    ];
    const inputs = {};
    for (const [name, text, tag, value] of fields) {
      const label = document.createElement("label");
      label.textContent = text;
      const input = document.createElement(tag);
      if (tag === "input") input.type = "text";
      input.value = value;
      input.id = `question-${name}`;
      label.htmlFor = input.id;
      inputs[name] = input;
      form.append(label, input);
    }
    const buttons = document.createElement("div");
    buttons.className = "wide dialogue-buttons";
    const ok = document.createElement("button");
    ok.type = "submit";
    ok.className = "primary";
    ok.textContent = "OK";
    const status = document.createElement("span");
    status.id = "question-status";
    status.className = "status";
    buttons.append(ok, status);
    form.append(buttons);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      status.textContent = "";
      send("tool", { op: "question", ...Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])) });
    });
    openViewer("質問テンプレート", form);
    inputs.question.focus();
  }

  // ---------------------------------------------------------------- 表示(テーマ・配置)

  function loadView() {
    try {
      return { ...DEFAULT_VIEW, ...JSON.parse(localStorage.getItem(VIEW_KEY) || "{}") };
    } catch (error) {
      return { ...DEFAULT_VIEW };
    }
  }

  function applyView(save = true) {
    const root = document.documentElement;
    if (view.theme === "auto") delete root.dataset.theme;
    else root.dataset.theme = view.theme;
    document.body.classList.toggle("panel-bottom", view.panel === "bottom");
    document.body.classList.toggle("mini", Boolean(view.mini));
    for (const [name] of PARTS) document.body.classList.toggle(`hide-${name}`, view.hide.includes(name));
    applySwap();
    applySizes();
    if (save) {
      try {
        localStorage.setItem(VIEW_KEY, JSON.stringify(view));
      } catch (error) {
        // 保存できない場合も、表示は切り替える
      }
    }
    requestDraw();
    if (window.softcon) window.softcon.draw();
  }

  // コマンドの一覧と Software-Controller の位置を入れ替える(入れ替えた状態かどうかを、設定に合わせる)
  function applySwap() {
    const softcon = document.querySelector(".softcon");
    const commands = document.querySelector(".commands");
    const swapped = commands.parentElement.classList.contains("preview-column");
    if (Boolean(view.swap) === swapped) return;
    const marker = document.createComment("swap");
    softcon.replaceWith(marker);
    commands.replaceWith(softcon);
    marker.replaceWith(commands);
    // 右の列(下に置いたパネル)の中の境目の線は、Output のすぐ前に置く
    const output = document.querySelector(".side-column .output");
    output.before(byId("side-sash"));
    document.body.classList.toggle("swapped", Boolean(view.swap));
  }

  // 左の列の幅と、プレビューの幅を反映する
  function applySizes() {
    const main = document.querySelector("main");
    if (view.left) main.style.setProperty("--left-width", `${view.left}px`);
    else main.style.removeProperty("--left-width");
    const root = document.documentElement;
    if (view.previewWidth) root.style.setProperty("--preview-width", `${view.previewWidth}px`);
    else root.style.removeProperty("--preview-width");
    // 右側のパネルを下に置いたときの、プレビューの幅
    if (view.topPreview) root.style.setProperty("--top-preview", `${clampTopPreview(view.topPreview)}px`);
    else root.style.removeProperty("--top-preview");
    // 下に置いたパネルの、左側の幅
    const side = document.querySelector(".side-column");
    side.classList.toggle("split", Boolean(view.sideLeft));
    if (view.sideLeft) side.style.setProperty("--side-left", `${view.sideLeft}px`);
    else side.style.removeProperty("--side-left");
  }

  // 右側のパネルを下に置いたときの、プレビューの幅の範囲(操作の部品の幅を残す)
  function clampTopPreview(width) {
    const column = document.querySelector(".preview-column");
    const limit = Math.max(COLUMN_MIN_WIDTH, column.clientWidth - COLUMN_MIN_WIDTH - 12);
    return Math.round(Math.min(Math.max(width, COLUMN_MIN_WIDTH), limit));
  }

  // 右側のパネルを下に置いたときの、プレビューと操作の部品の間の境目の線
  function setupTopSash() {
    const sash = byId("top-sash");
    let drag = null;
    sash.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      capturePointer(sash, event);
      drag = { x: event.clientX, width: byId("preview").getBoundingClientRect().width };
      sash.classList.add("dragging");
    });
    sash.addEventListener("pointermove", (event) => {
      if (drag === null) return;
      view.topPreview = clampTopPreview(drag.width + event.clientX - drag.x);
      applySizes();
      requestDraw();
    });
    const finish = (event) => {
      if (drag === null) return;
      drag = null;
      sash.classList.remove("dragging");
      if (sash.hasPointerCapture(event.pointerId)) sash.releasePointerCapture(event.pointerId);
      applyView();
    };
    sash.addEventListener("pointerup", finish);
    sash.addEventListener("pointercancel", finish);
    sash.addEventListener("dblclick", () => setView({ topPreview: null }));
    // ウィンドウを小さくしたときに、操作の部品が狭くなりすぎないようにする
    window.addEventListener("resize", () => {
      if (view.topPreview) applySizes();
    });
  }

  // 下に置いたパネルの中の、左右の境目の線
  function setupSideSash() {
    const sash = byId("side-sash");
    const side = document.querySelector(".side-column");
    let drag = null;
    sash.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      capturePointer(sash, event);
      drag = { x: event.clientX, width: side.firstElementChild.getBoundingClientRect().width };
      sash.classList.add("dragging");
    });
    sash.addEventListener("pointermove", (event) => {
      if (drag === null) return;
      const limit = Math.max(SIDE_MIN_WIDTH, side.getBoundingClientRect().width - SIDE_MIN_WIDTH - 20);
      view.sideLeft = Math.round(Math.min(Math.max(drag.width + event.clientX - drag.x, SIDE_MIN_WIDTH), limit));
      applySizes();
    });
    const finish = (event) => {
      if (drag === null) return;
      drag = null;
      sash.classList.remove("dragging");
      if (sash.hasPointerCapture(event.pointerId)) sash.releasePointerCapture(event.pointerId);
      applyView();
    };
    sash.addEventListener("pointerup", finish);
    sash.addEventListener("pointercancel", finish);
    sash.addEventListener("dblclick", () => setView({ sideLeft: null }));
  }

  // 設定の枠の開閉(見出しの「設定」ボタン)
  function setupSettingsPanel() {
    const panel = byId("settings");
    const button = byId("menu-settings");
    const sync = () => button.setAttribute("aria-expanded", String(panel.open));
    button.addEventListener("click", () => {
      panel.open = !panel.open;
    });
    byId("settings-close").addEventListener("click", () => {
      panel.open = false;
    });
    panel.addEventListener("toggle", sync);
    sync();
  }

  function clampLeft(width) {
    const main = document.querySelector("main");
    const style = getComputedStyle(main);
    const inner = main.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    return Math.round(Math.min(Math.max(width, COLUMN_MIN_WIDTH), Math.max(COLUMN_MIN_WIDTH, inner - COLUMN_MIN_WIDTH - 12)));
  }

  function setupMainSash() {
    const sash = byId("main-sash");
    const main = document.querySelector("main");
    let drag = null;
    sash.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      capturePointer(sash, event);
      drag = { x: event.clientX, width: document.querySelector(".preview-column").getBoundingClientRect().width };
      sash.classList.add("dragging");
    });
    sash.addEventListener("pointermove", (event) => {
      if (drag === null) return;
      view.left = clampLeft(drag.width + event.clientX - drag.x);
      // 列の幅を自分で変えたら、プレビューは列の幅に合わせる
      view.previewWidth = null;
      applySizes();
      requestDraw();
    });
    const finish = (event) => {
      if (drag === null) return;
      drag = null;
      sash.classList.remove("dragging");
      if (sash.hasPointerCapture(event.pointerId)) sash.releasePointerCapture(event.pointerId);
      applyView();
    };
    sash.addEventListener("pointerup", finish);
    sash.addEventListener("pointercancel", finish);
    sash.addEventListener("dblclick", () => setView({ left: null, previewWidth: null }));
    // ウィンドウを小さくしたときに、右の列が狭くなりすぎないようにする
    window.addEventListener("resize", () => {
      if (view.left && clampLeft(view.left) !== view.left) {
        main.style.setProperty("--left-width", `${clampLeft(view.left)}px`);
      }
    });
  }

  // プレビューを決まった幅にする(左の列も、その幅が入る大きさにする)
  function setPreviewWidth(width) {
    if (width === null) {
      setView({ previewWidth: null, topPreview: null });
      return;
    }
    // 大きさを選んだら、境目の線で決めた幅(右側のパネルを下に置いたとき)は使わない
    const changes = { previewWidth: width, topPreview: null };
    if (view.panel === "right") changes.left = clampLeft(width + 24);
    setView(changes);
  }

  function qualityLabel(width) {
    return width === 0 ? "取り込みサイズのまま" : `幅 ${width}px まで`;
  }

  function setQuality(width) {
    view.quality = width;
    applyView();
    send("preview_quality", { width });
  }

  function setView(changes) {
    view = { ...view, ...changes };
    applyView();
  }

  function previewAspect() {
    if (!state) return 16 / 9;
    const [width, height] = state.camera.capture_size;
    return width / height;
  }

  function viewMenuItems() {
    const themes = [
      ["auto", "自動 (OS の設定)"],
      ["light", "ライト"],
      ["dark", "ダーク"],
    ];
    return [
      { title: "テーマ" },
      ...themes.map(([value, label]) => ({ label, checked: view.theme === value, action: () => setView({ theme: value }) })),
      "-",
      { title: "プレビューの大きさ (境目の線のドラッグでも変えられます)" },
      { label: "列の幅に合わせる", checked: !view.previewWidth, action: () => setPreviewWidth(null) },
      ...PREVIEW_WIDTHS.map((width) => ({
        label: `${width} x ${Math.round(width / previewAspect())}`,
        checked: view.previewWidth === width,
        action: () => setPreviewWidth(width),
      })),
      "-",
      { title: "プレビューの画質 (送る映像の大きさ)" },
      ...((state && state.preview_max_width_choices) || []).map((width) => ({
        label: qualityLabel(width),
        checked: state.preview_max_width === width,
        action: () => setQuality(width),
        disabled: role !== "operator",
      })),
      "-",
      { title: "右側のパネルの位置" },
      { label: "右", checked: view.panel === "right", action: () => setView({ panel: "right" }) },
      { label: "下", checked: view.panel === "bottom", action: () => setView({ panel: "bottom" }) },
      "-",
      {
        label: "コマンドの一覧と Software-Controller の位置を入れ替える",
        checked: Boolean(view.swap),
        action: () => setView({ swap: !view.swap }),
      },
      "-",
      { title: "表示する部品" },
      ...PARTS.map(([name, label]) => ({
        label,
        checked: !view.hide.includes(name),
        action: () => setView({ hide: view.hide.includes(name) ? view.hide.filter((item) => item !== name) : [...view.hide, name] }),
      })),
      "-",
      { label: "ミニ画面 (プレビューと Start だけ)", checked: Boolean(view.mini), action: () => setView({ mini: !view.mini }) },
      "-",
      { label: "Controller Simulator (大きいコントローラー)", action: () => window.simulator && window.simulator.open(), disabled: !window.simulator },
      "-",
      {
        label: "画面のリセット",
        action: () => {
          view = { ...DEFAULT_VIEW };
          setOutputHeight(null);
          saveOutputHeight();
          applyView();
        },
      },
    ];
  }

  function helpMenuItems() {
    const links = state ? state.tools.links : {};
    const operator = role === "operator";
    return [
      { label: "Instruction Manual", action: showManual },
      { label: "機能紹介", action: showIntroduction },
      { label: "更新履歴表示", action: () => send("tool", { op: "changelog" }), disabled: !operator },
      { label: "Poke-Controller Guide", action: () => window.open(links.guide, "_blank", "noopener") },
      { label: "Github", action: () => window.open(links.github, "_blank", "noopener") },
      "-",
      { label: "質問テンプレート", action: () => send("tool", { op: "question_defaults" }), disabled: !operator },
      { label: "環境の診断", action: () => send("tool", { op: "diagnostics" }), disabled: !operator },
      {
        label: "アップデート確認",
        disabled: !operator,
        action: () => {
          if (window.confirm("Poke-Controller Modified Extension の更新を確認しますか?")) send("tool", { op: "update" });
        },
      },
      { label: "LICENSE", action: () => send("tool", { op: "license" }), disabled: !operator },
    ];
  }

  // ---------------------------------------------------------------- 右クリックのメニュー

  function commandOf(item) {
    // 一覧の行 -> {command_type, name}(ショートカットが未設定の行などは null)
    const name = item.dataset.name;
    if (commandType === "Python" || commandType === "Mcu") return { command_type: commandType, name };
    if (commandType === "History") {
      const entry = state.history.find((history) => history.name === name);
      return entry ? { command_type: entry.class, name } : null;
    }
    const shortcut = state.shortcuts.find((item2) => shortcutLabel(item2) === name);
    return shortcut && shortcut.class !== "None" ? { command_type: shortcut.class, name: shortcut.name } : null;
  }

  function commandMenuItems(command) {
    const operator = role === "operator";
    const open = (how) => () => send("tool", { op: "open_command", how, ...command });
    const items = [
      { label: "Open file", action: open("file"), disabled: !operator },
      ...(state.tools.windows
        ? [
            { label: "Open with...", action: open("with"), disabled: !operator },
            { label: "Open folder", action: open("folder"), disabled: !operator },
          ]
        : []),
      "-",
      { label: "Copy path", action: () => send("tool", { op: "command_path", ...command }), disabled: !operator },
      "-",
      { title: "Shortcut に設定" },
      ...state.shortcuts.map((shortcut) => ({
        label: `#${shortcut.num}${shortcut.class === "None" ? "" : `: ${shortcut.name}`}`.slice(0, 48),
        action: () => send("shortcut", { op: "set", num: shortcut.num, ...command }),
        disabled: !operator,
      })),
    ];
    if (commandType === "History") {
      items.unshift(
        { label: "Delete", action: () => send("tool", { op: "history_delete", ...command }), disabled: !operator },
        {
          label: "Delete (ALL)",
          disabled: !operator,
          action: () => {
            if (window.confirm(`すべての履歴(${state.history.length}件)を削除しますか？`)) send("tool", { op: "history_clear" });
          },
        },
        "-"
      );
    }
    return items;
  }

  function captureMenuItems(link) {
    const path = link.dataset.capture;
    const operator = role === "operator";
    return [
      { label: "Open (ブラウザで表示)", action: () => window.open(link.href, "_blank", "noopener") },
      { label: "Open (PC のアプリで開く)", action: () => send("tool", { op: "open_image", path }), disabled: !operator },
      ...(state.tools.windows
        ? [
            { label: "Open with...", action: () => send("tool", { op: "open_image", path, how: "with" }), disabled: !operator },
            { label: "Open folder", action: () => send("tool", { op: "open_image", path, how: "folder" }), disabled: !operator },
          ]
        : []),
      "-",
      { label: "Copy path", action: () => copyText(path) },
    ];
  }

  function setupContextMenus() {
    byId("command-list").addEventListener("contextmenu", (event) => {
      const item = event.target.closest("li[data-name]");
      if (!item) return;
      event.preventDefault();
      selectCommand(item.dataset.name);
      const command = commandOf(item);
      if (command) showMenu(commandMenuItems(command), event.clientX, event.clientY);
    });
    for (const area of [1, 2]) {
      byId(`output-${area}`).addEventListener("contextmenu", (event) => {
        const link = event.target.closest("a[data-capture]");
        if (!link) return;
        event.preventDefault();
        showMenu(captureMenuItems(link), event.clientX, event.clientY);
      });
    }
    byId("tag-filter").addEventListener("click", (event) => {
      const tags = JSON.parse(event.currentTarget.dataset.tags || "[]");
      const selected = tagFilter[commandType];
      const toggle = (tag) => () => {
        tagFilter[commandType] = selected.includes(tag) ? selected.filter((item) => item !== tag) : [...selected, tag];
        render();
        // 続けて選べるよう、メニューを開き直す
        byId("tag-filter").click();
      };
      menuBelow(event.currentTarget, [
        { label: "すべてのタグ (絞り込まない)", checked: selected.length === 0, action: () => ((tagFilter[commandType] = []), render()) },
        "-",
        ...tags.map((tag) => ({ label: tag, checked: selected.includes(tag), action: toggle(tag), keepOpen: true })),
      ]);
    });
    document.addEventListener("pointerdown", (event) => {
      if (!byId("popup-menu").hidden && !byId("popup-menu").contains(event.target) && !event.target.closest("#tag-filter, .menu-button")) hideMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!byId("popup-menu").hidden) {
        hideMenu();
        event.stopPropagation();
      } else if (!byId("viewer").hidden) {
        closeViewer();
        event.stopPropagation();
      }
    }, true);
    window.addEventListener("blur", hideMenu);
  }

  // ---------------------------------------------------------------- プレビュー上の Ctrl 操作

  function previewPoint(event) {
    const rect = byId("stream").getBoundingClientRect();
    return {
      x: Math.min(Math.max(event.clientX - rect.left, 0), rect.width),
      y: Math.min(Math.max(event.clientY - rect.top, 0), rect.height),
      width: rect.width,
      height: rect.height,
    };
  }

  function toCapture(point) {
    const [captureWidth, captureHeight] = state.camera.capture_size;
    return [Math.floor((point.x * captureWidth) / point.width), Math.floor((point.y * captureHeight) / point.height)];
  }

  function setupPreviewCtrl() {
    // Ctrl を押している間の左ボタンの操作は、プレビュー上のほかの操作(スティックなど)より先に受け取る
    const preview = byId("preview");
    const stop = (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    preview.addEventListener(
      "pointerdown",
      (event) => {
        if (!event.ctrlKey || event.button !== 0 || role !== "operator" || !state) return;
        stop(event);
        const point = previewPoint(event);
        if (event.shiftKey || event.altKey) {
          // Ctrl+Shift+ドラッグ: 範囲を保存 / Ctrl+Alt+ドラッグ: 範囲を、名前を付けて保存
          capturePointer(preview, event);
          rangeDrag = { named: event.altKey, start: point, end: point };
          requestDraw();
        } else {
          // Ctrl+クリック: その位置の座標と色を、出力画面に表示する
          const [x, y] = toCapture(point);
          send("tool", { op: "pixel", x, y });
        }
      },
      true
    );
    preview.addEventListener(
      "pointermove",
      (event) => {
        if (rangeDrag === null) return;
        stop(event);
        rangeDrag.end = previewPoint(event);
        requestDraw();
      },
      true
    );
    const finish = (event) => {
      if (rangeDrag === null) return;
      stop(event);
      if (preview.hasPointerCapture(event.pointerId)) preview.releasePointerCapture(event.pointerId);
      const { named, start } = rangeDrag;
      const end = event.type === "pointercancel" ? null : previewPoint(event);
      rangeDrag = null;
      requestDraw();
      if (end === null) return;
      const [x1, y1] = toCapture({ ...end, x: Math.min(start.x, end.x), y: Math.min(start.y, end.y) });
      const [x2, y2] = toCapture({ ...end, x: Math.max(start.x, end.x), y: Math.max(start.y, end.y) });
      const data = { op: "capture", area: [x1, y1, x2, y2] };
      if (named) {
        const name = window.prompt("名前を付けて保存 (Template フォルダに保存します。「/」でフォルダを分けられます)", "");
        if (name === null || name.trim() === "") return;
        data.name = name.trim();
      }
      send("tool", data);
    };
    preview.addEventListener("pointerup", finish, true);
    preview.addEventListener("pointercancel", finish, true);
  }

  function drawOverlay(context) {
    if (rangeDrag === null) return;
    const { start, end } = rangeDrag;
    context.save();
    context.lineWidth = 3;
    context.strokeStyle = "red";
    context.strokeRect(Math.min(start.x, end.x), Math.min(start.y, end.y), Math.abs(end.x - start.x), Math.abs(end.y - start.y));
    context.restore();
  }

  // ---------------------------------------------------------------- 設定の追加分

  function setStatus(id, text, ok = false) {
    const element = byId(id);
    if (!element) return;
    element.textContent = text || "";
    element.classList.toggle("ok", ok);
  }

  function setupSettings() {
    byId("discord-check").addEventListener("click", () => send("tool", { op: "check_discord" }));
    byId("line-check").addEventListener("click", () => send("tool", { op: "check_line" }));
    byId("color-preset-save").addEventListener("click", () => {
      setStatus("colors-status", "");
      send("tool", { op: "color_preset", controller: byId("color-type").value, name: byId("color-preset-name").value });
    });
    byId("profile-add").addEventListener("click", () => {
      setStatus("profile-status", "");
      const bat = byId("profile-bat-row").hidden ? "" : byId("profile-bat").value;
      send("tool", { op: "profile_add", name: byId("profile-name").value, copy: byId("profile-copy").checked, bat });
    });
    setupOutputSash();
  }

  // Output#1 と #2 の境目の線をドラッグして、Output#1 の高さを変える(高さは覚えておく)
  function setOutputHeight(height) {
    const output = byId("output-1");
    if (height === null) {
      // 元に戻す(#1 と #2 で半分ずつ)
      output.style.height = "";
      output.style.flex = "";
      return;
    }
    // Output#2 が見えなくならない範囲に収める
    const panel = output.parentElement.getBoundingClientRect().height;
    const limit = Math.max(OUTPUT_MIN_HEIGHT, panel - OUTPUT_OTHER_HEIGHT);
    output.style.height = `${Math.round(Math.min(Math.max(height, OUTPUT_MIN_HEIGHT), limit))}px`;
    output.style.flex = "0 0 auto";
  }

  function saveOutputHeight() {
    try {
      const height = byId("output-1").style.height;
      if (height) localStorage.setItem(OUTPUT_HEIGHT_KEY, height);
      else localStorage.removeItem(OUTPUT_HEIGHT_KEY);
    } catch (error) {
      // 保存できない場合も、高さは変えられる
    }
  }

  function setupOutputSash() {
    const sash = byId("output-sash");
    const output = byId("output-1");
    let drag = null;
    try {
      const saved = parseFloat(localStorage.getItem(OUTPUT_HEIGHT_KEY));
      if (saved > 0) {
        output.style.height = `${saved}px`;
        output.style.flex = "0 0 auto";
      }
    } catch (error) {
      // 覚えていない場合
    }
    sash.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      capturePointer(sash, event);
      drag = { y: event.clientY, height: output.getBoundingClientRect().height };
      sash.classList.add("dragging");
    });
    sash.addEventListener("pointermove", (event) => {
      if (drag !== null) setOutputHeight(drag.height + event.clientY - drag.y);
    });
    const finish = (event) => {
      if (drag === null) return;
      drag = null;
      sash.classList.remove("dragging");
      if (sash.hasPointerCapture(event.pointerId)) sash.releasePointerCapture(event.pointerId);
      saveOutputHeight();
    };
    sash.addEventListener("pointerup", finish);
    sash.addEventListener("pointercancel", finish);
    sash.addEventListener("dblclick", () => {
      setOutputHeight(null);
      saveOutputHeight();
    });
  }

  function render(operator) {
    if (!state) return;
    const profiles = state.tools.profiles;
    // uv の環境では、起動用の bat の形を選べる
    byId("profile-bat-row").hidden = !state.tools.uv_environment;
    byId("profile-list").textContent = `今のプロファイル: ${profiles.current}${profiles.read_only ? " (設定を保存しません)" : ""} / 一覧: ${profiles.names.join(", ")}`;
    for (const id of ["discord-check", "line-check", "color-preset-save", "color-preset-name", "profile-add", "profile-name", "profile-copy"]) {
      byId(id).disabled = !operator;
    }
    byId("preview-hint").hidden = !operator;
    byId("controller-setup-open").disabled = !operator || state.command.state !== "idle";
    byId("notify-windows-test").disabled = !operator;
    if (!operator) byId("controller-setup").hidden = true;
    showIntroductionAtStartup();
    // 覚えている画質を、操作できるようになったときにサーバーへ伝える
    if (operator && view.quality !== null && state.preview_max_width !== view.quality && !qualitySent) {
      qualitySent = true;
      send("preview_quality", { width: view.quality });
    }
    if (!operator) qualitySent = false;
  }

  function handle(message) {
    if (message.type === "controller_setup") {
      renderSetup(message.setup);
    } else if (message.type === "meter") {
      const meter = message.meter;
      byId("audio-meter").value = meter ? meter.percent : 0;
      byId("audio-meter-text").textContent = meter ? meter.text : "";
    } else if (message.type === "tool_result") {
      if (message.op === "question_defaults") {
        showQuestionForm(message.defaults);
      } else if (message.op === "update") {
        const texts = { 0: "更新はありませんでした。", 1: "最新版が公開されています。Github のページを開きます。" };
        window.alert(texts[message.result] || "確認できませんでした。");
        if (message.result === "1") window.open(state.tools.links.github, "_blank", "noopener");
      } else if (message.op === "command_path") {
        copyText(message.text);
      } else if (message.op === "color_preset") {
        setStatus("colors-status", message.text, true);
        byId("color-preset-name").value = "";
      } else if (message.op === "profile_add") {
        setStatus("profile-status", message.text, true);
        byId("profile-name").value = "";
      } else if (message.title) {
        showText(message.title, message.text, message.note, message.masked);
      }
    } else if (message.type === "tool_error") {
      if (message.op === "question") setStatus("question-status", message.message);
      else if (message.op === "color_preset") setStatus("colors-status", message.message);
      else if (message.op === "profile_add") setStatus("profile-status", message.message);
    }
  }

  byId("menu-view").addEventListener("click", (event) => menuBelow(event.currentTarget, viewMenuItems()));
  byId("menu-help").addEventListener("click", (event) => menuBelow(event.currentTarget, helpMenuItems()));
  byId("viewer-close").addEventListener("click", closeViewer);
  byId("viewer-copy").addEventListener("click", () => onViewerCopy && onViewerCopy());
  byId("viewer").addEventListener("pointerdown", (event) => {
    if (event.target === byId("viewer")) closeViewer();
  });
  setupContextMenus();
  setupPreviewCtrl();
  setupSettings();
  setupMainSash();
  setupTopSash();
  setupSideSash();
  setupSettingsPanel();
  setupControllerSetup();
  applyView(false);

  return { render, handle, drawOverlay, showMenu, hideMenu };
})();
