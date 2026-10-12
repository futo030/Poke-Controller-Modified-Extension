"use strict";
// ツールの画面: タグの編集、新しいスクリプトのひな形(新しい自動化スクリプトをつくる)、Keyboard(Switch のキーボード画面への入力)、
// モニター(複数起動をまとめて見る)。どれも、操作できるブラウザだけが使える

window.tools = (function () {
  const byId = (id) => document.getElementById(id);
  // 入力の途中で、サーバーに問い合わせるまでの待ち時間(ms)
  const PREVIEW_DELAY_MS = 150;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(text, onClick, className) {
    const node = element("button", className, text);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function showModal(id) {
    byId(id).hidden = false;
    sendFocus();
  }

  function hideModal(id) {
    byId(id).hidden = true;
    if (document.activeElement) document.activeElement.blur();
    sendFocus();
  }

  // 画面をふさぐツールの画面を開いているか(開いている間は、キーボードでの手動操作を受け付けない)
  function isModalOpen() {
    return document.querySelector(".tool-window:not([hidden])") !== null;
  }

  function setMessage(id, text, ok = false) {
    const node = byId(id);
    node.textContent = text || "";
    node.classList.toggle("ok", ok);
  }

  // ---------------------------------------------------------------- タグの編集

  const TAG_FOLDER_PREFIX = "@";
  // サーバーから届いた内容: {types, commands: {種類: [{name, tags, folder_tags, editable, reason}]}}
  let tagState = null;
  let tagType = "Python";
  const tagSelected = {};
  // 保存していない変更: キー(種類 + 改行 + 名前) -> タグの一覧
  const tagPending = new Map();
  let tagSaving = false;

  function tagKey(type, name) {
    return `${type}\n${name}`;
  }

  function tagRows(type) {
    return tagState ? tagState.commands[type] || [] : [];
  }

  function tagsOf(type, row) {
    const pending = tagPending.get(tagKey(type, row.name));
    return pending ? [...pending] : [...row.tags];
  }

  function sameTags(a, b) {
    return a.length === b.length && a.every((tag, index) => tag === b[index]);
  }

  function selectedTagRow() {
    return tagRows(tagType).find((row) => row.name === tagSelected[tagType]) || null;
  }

  // その種類のコマンドで使っているタグ(保存していない変更を含む。フォルダーのタグは除く)
  function knownTags(type) {
    const known = new Set();
    for (const row of tagRows(type)) {
      if (row.editable) tagsOf(type, row).forEach((tag) => known.add(tag));
    }
    return [...known].sort();
  }

  // 入力されたタグを確かめる(サーバーでも、同じ決まりで確かめる)。使えない理由を返す(使えるなら空文字)
  function checkTag(tag, current) {
    if (!tag) return "タグを入力してください。";
    if ([...tag].some((c) => c.charCodeAt(0) < 0x20 || c === "\x7f")) return "タグに、改行やタブは使えません。";
    if (tag.startsWith(TAG_FOLDER_PREFIX)) return `「${TAG_FOLDER_PREFIX}」で始まるタグは、フォルダーの名前から自動で付くタグなので、足せません。`;
    if (current.includes(tag)) return `「${tag}」は、すでに付いています。`;
    return "";
  }

  function renderTagList() {
    const list = byId("tag-editor-list");
    const text = byId("tag-editor-filter").value.trim().toLowerCase();
    const rows = tagRows(tagType).filter((row) => {
      if (!text) return true;
      const tags = [...tagsOf(tagType, row), ...row.folder_tags];
      return row.name.toLowerCase().includes(text) || tags.some((tag) => tag.toLowerCase().includes(text));
    });
    // (読み込みが終わるまでは、初めに選ぶコマンドを、そのまま覚えておく)
    if (tagState && !rows.some((row) => row.name === tagSelected[tagType])) tagSelected[tagType] = rows.length ? rows[0].name : null;
    if (!rows.length) {
      list.replaceChildren(element("li", "empty", tagState ? "該当するコマンドがありません" : "読み込んでいます..."));
      return;
    }
    list.replaceChildren(
      ...rows.map((row) => {
        const item = element("li", row.editable ? "" : "locked");
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", String(row.name === tagSelected[tagType]));
        item.dataset.name = row.name;
        const mark = !row.editable ? "⚠ " : tagPending.has(tagKey(tagType, row.name)) ? "● " : "";
        item.append(element("span", "name", mark + row.name), element("span", "tags", [...tagsOf(tagType, row), ...row.folder_tags].join(", ")));
        return item;
      })
    );
  }

  function renderTagDetail(message = "") {
    const row = selectedTagRow();
    const tagsBox = byId("tag-editor-tags");
    const suggestBox = byId("tag-editor-suggest");
    const editable = Boolean(row && row.editable) && !tagSaving;
    byId("tag-editor-new").disabled = !editable;
    byId("tag-editor-add-button").disabled = !editable;
    if (!row) {
      byId("tag-editor-name").textContent = tagState ? "コマンドを選んでください。" : "";
      tagsBox.replaceChildren();
      suggestBox.replaceChildren();
      setMessage("tag-editor-message", message);
      return;
    }
    byId("tag-editor-name").textContent = row.name;
    const tags = tagsOf(tagType, row);
    tagsBox.replaceChildren(
      ...tags.map((tag) => {
        const chip = button(`${tag}  ×`, () => removeTag(tag));
        chip.disabled = !editable;
        return chip;
      }),
      ...row.folder_tags.map((tag) => {
        const chip = button(`${tag} (フォルダー)`, () => {});
        chip.disabled = true;
        return chip;
      })
    );
    const suggestions = editable ? knownTags(tagType).filter((tag) => !tags.includes(tag)) : [];
    suggestBox.replaceChildren(...suggestions.map((tag) => button(`+ ${tag}`, () => addTag(tag))));
    setMessage("tag-editor-message", message || (row.editable ? "" : `このコマンドのタグは編集できません。${row.reason}`));
  }

  function renderTagStatus(text) {
    const count = tagPending.size;
    byId("tag-editor-status").textContent = text || (count ? `変更 ${count} 件` : "変更はありません");
    byId("tag-editor-save").disabled = !count || tagSaving;
    byId("tag-editor-revert").disabled = !count || tagSaving;
  }

  function renderTagEditor(message = "", status = "") {
    const select = byId("tag-editor-type");
    const types = tagState ? tagState.types : ["Python", "Mcu"];
    if (select.options.length !== types.length) select.replaceChildren(...types.map((type) => new Option(type, type)));
    select.value = tagType;
    renderTagList();
    renderTagDetail(message);
    renderTagStatus(status);
    renderTagBulk();
  }

  // 一括変更で選べるタグ(表示している種類で、編集できるコマンドが使っているタグ)を、今の状態に合わせる
  function renderTagBulk() {
    const select = byId("tag-bulk-tag");
    const known = knownTags(tagType);
    const current = known.includes(select.value) ? select.value : known[0] || "";
    select.replaceChildren(...known.map((tag) => new Option(tag, tag)));
    select.value = current;
    const disabled = !known.length || tagSaving;
    for (const id of ["tag-bulk-tag", "tag-bulk-new", "tag-bulk-rename", "tag-bulk-delete"]) byId(id).disabled = disabled;
  }

  // タグの一覧の中の old を、replacement に置き換える(null なら、取り除く)。
  // replacement がすでにある場合は、old を取り除くだけにする(同じタグが 2 つにならないように)
  function replaceTag(tags, old, replacement) {
    if (!tags.includes(old)) return [...tags];
    if (replacement === null || tags.includes(replacement)) return tags.filter((tag) => tag !== old);
    return tags.map((tag) => (tag === old ? replacement : tag));
  }

  // 表示している種類のすべてのコマンドで、タグ old を replacement に変える(保存はしない)。
  // 戻り値: [変えたコマンドの数, 編集できないので変えなかったコマンドの数]
  function replaceTagEverywhere(old, replacement) {
    let changed = 0;
    let skipped = 0;
    for (const row of tagRows(tagType)) {
      const tags = tagsOf(tagType, row);
      if (!tags.includes(old)) continue;
      if (!row.editable) {
        skipped += 1;
        continue;
      }
      const next = replaceTag(tags, old, replacement);
      const key = tagKey(tagType, row.name);
      if (sameTags(next, row.tags)) tagPending.delete(key);
      else tagPending.set(key, next);
      changed += 1;
    }
    return [changed, skipped];
  }

  function showBulkResult(text, changed, skipped) {
    if (skipped) text += ` 編集できない ${skipped} 件は、変えていません。`;
    if (changed) text += " 「保存」を押すまでは、ファイルを書き換えません(「元に戻す」で取り消せます)。";
    setMessage("tag-bulk-message", text, true);
  }

  function renameTagEverywhere() {
    const old = byId("tag-bulk-tag").value;
    if (!old || tagSaving) return;
    const input = byId("tag-bulk-new");
    const name = input.value.trim();
    const error = !name ? "新しい名前を入力してください。" : name === old ? "今と同じ名前です。" : checkTag(name, []);
    if (error) {
      setMessage("tag-bulk-message", error);
      return;
    }
    const [changed, skipped] = replaceTagEverywhere(old, name);
    input.value = "";
    renderTagEditor();
    if (knownTags(tagType).includes(name)) byId("tag-bulk-tag").value = name;
    showBulkResult(`${changed} 件のコマンドで、「${old}」を「${name}」に変えました。`, changed, skipped);
  }

  function deleteTagEverywhere() {
    const old = byId("tag-bulk-tag").value;
    if (!old || tagSaving) return;
    const [changed, skipped] = replaceTagEverywhere(old, null);
    renderTagEditor();
    showBulkResult(`${changed} 件のコマンドから、「${old}」を外しました。`, changed, skipped);
  }

  function setTags(row, tags) {
    const key = tagKey(tagType, row.name);
    if (sameTags(tags, row.tags)) tagPending.delete(key);
    else tagPending.set(key, tags);
    renderTagEditor();
  }

  function addTag(text) {
    const row = selectedTagRow();
    if (!row || !row.editable || tagSaving) return;
    const input = byId("tag-editor-new");
    const tag = (text === undefined ? input.value : text).trim();
    const tags = tagsOf(tagType, row);
    const error = checkTag(tag, [...tags, ...row.folder_tags]);
    if (error) {
      renderTagDetail(error);
      return;
    }
    input.value = "";
    setTags(row, [...tags, tag]);
  }

  function removeTag(tag) {
    const row = selectedTagRow();
    if (!row || !row.editable || tagSaving) return;
    setTags(row, tagsOf(tagType, row).filter((item) => item !== tag));
  }

  function saveTags() {
    if (!tagPending.size || tagSaving) return;
    tagSaving = true;
    const changes = [...tagPending.entries()].map(([key, tags]) => {
      const [type, name] = key.split("\n");
      return { command_type: type, name, tags };
    });
    renderTagEditor("", "保存しています...");
    send("tags", { op: "save", changes });
  }

  // サーバーから、読み取った内容(と、保存の結果)が届いた
  function onTags(message) {
    tagState = message.state;
    const isSaveResult = message.saved !== undefined;
    tagSaving = false;
    if (isSaveResult) {
      // 書き込めなかっただけのもの(kept)は、変更を残す。それ以外は、保存できたか、読み直したので、変更を消す
      const kept = new Set((message.kept || []).map(([type, name]) => tagKey(type, name)));
      for (const key of [...tagPending.keys()]) {
        if (!kept.has(key)) tagPending.delete(key);
      }
    }
    // なくなったコマンド・編集できなくなったコマンド・変更がなくなったものは、変更から外す
    for (const [key, tags] of [...tagPending.entries()]) {
      const [type, name] = key.split("\n");
      const row = tagRows(type).find((item) => item.name === name);
      if (!row || !row.editable || sameTags(tags, row.tags)) tagPending.delete(key);
    }
    const saved = isSaveResult && message.saved && !message.failures.length ? `${message.saved} 件のコマンドのタグを保存しました` : "";
    renderTagEditor("", saved);
    const selected = byId("tag-editor-list").querySelector('li[aria-selected="true"]');
    if (selected) selected.scrollIntoView({ block: "nearest" });
    if (isSaveResult && message.failures.length) {
      window.alert(
        "次のコマンドのタグは、保存できませんでした。\n\n" +
          message.failures.join("\n") +
          "\n\n「書き換えられています」と出たファイルは、今の内容を読み直しました。もう一度、編集してください。"
      );
    }
  }

  function openTagEditor() {
    if (!byId("tag-editor").hidden) return;
    tagState = null;
    tagSaving = false;
    tagPending.clear();
    // メインの画面で選んでいる種類とコマンドを、初めに表示する
    tagType = commandType === "Mcu" ? "Mcu" : "Python";
    tagSelected[tagType] = selectedCommand[tagType];
    byId("tag-editor-filter").value = "";
    byId("tag-editor-new").value = "";
    renderTagEditor();
    showModal("tag-editor");
    byId("tag-editor-filter").focus();
    send("tags", { op: "load" });
  }

  function closeTagEditor() {
    if (byId("tag-editor").hidden) return;
    if (tagPending.size && !window.confirm(`保存していない変更が ${tagPending.size} 件あります。保存せずに閉じますか?`)) return;
    tagPending.clear();
    hideModal("tag-editor");
  }

  function setupTagEditor() {
    byId("tag-editor-close").addEventListener("click", closeTagEditor);
    byId("tag-editor-type").addEventListener("change", (event) => {
      tagType = event.target.value;
      renderTagEditor();
    });
    byId("tag-editor-filter").addEventListener("input", () => renderTagEditor());
    byId("tag-editor-list").addEventListener("click", (event) => {
      const item = event.target.closest("li[data-name]");
      if (!item) return;
      tagSelected[tagType] = item.dataset.name;
      renderTagEditor();
    });
    byId("tag-editor-list").addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      event.preventDefault();
      const items = [...byId("tag-editor-list").querySelectorAll("li[data-name]")];
      const index = items.findIndex((item) => item.dataset.name === tagSelected[tagType]);
      const next = items[Math.min(Math.max(index + (event.key === "ArrowDown" ? 1 : -1), 0), items.length - 1)];
      if (!next) return;
      tagSelected[tagType] = next.dataset.name;
      renderTagEditor();
      byId("tag-editor-list").querySelector('li[aria-selected="true"]').scrollIntoView({ block: "nearest" });
    });
    byId("tag-editor-add").addEventListener("submit", (event) => {
      event.preventDefault();
      addTag();
    });
    byId("tag-bulk-rename").addEventListener("click", renameTagEverywhere);
    byId("tag-bulk-delete").addEventListener("click", deleteTagEverywhere);
    byId("tag-bulk-new").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      renameTagEverywhere();
    });
    byId("tag-editor-save").addEventListener("click", saveTags);
    byId("tag-editor-revert").addEventListener("click", () => {
      tagPending.clear();
      renderTagEditor();
    });
  }

  // ---------------------------------------------------------------- 新しいスクリプトのひな形(新しい自動化スクリプトをつくる)

  const SCRIPT_FIELDS = ["script-name", "script-author", "script-file", "script-folder", "script-template"];
  // 画像の保存先を、ファイル名に合わせて自動で入れているか(利用者が書き換えたら、合わせるのをやめる)
  let templateFollows = true;
  let scriptPreviewTimer = null;
  let scriptPreviewSeq = 0;
  let scriptCreating = false;

  function scriptSpec() {
    const useBridge = byId("script-bridge-yes").checked;
    return {
      name: byId("script-name").value,
      author: byId("script-author").value,
      file_name: byId("script-file").value,
      folder: byId("script-folder").value,
      use_bridge: useBridge,
      template_folder: byId("script-template").value,
      // スクリプト格納場所の中に置けるのは、BridgeFunctions を使用する場合だけ
      template_location: useBridge ? byId("script-location").value : "template",
    };
  }

  function requestScriptPreview() {
    setMessage("script-message", "");
    clearTimeout(scriptPreviewTimer);
    scriptPreviewTimer = setTimeout(() => {
      scriptPreviewSeq += 1;
      send("script", { op: "preview", seq: scriptPreviewSeq, ...scriptSpec() });
    }, PREVIEW_DELAY_MS);
  }

  function fillDatalist(id, values) {
    byId(id).replaceChildren(...values.map((value) => new Option(value, value)));
  }

  function onScriptBridgeChanged() {
    const location = byId("script-location");
    location.disabled = !byId("script-bridge-yes").checked;
    if (location.disabled) location.value = "template";
    requestScriptPreview();
  }

  function onScript(message) {
    if (message.form) {
      // 前に作ったときの作成者名を、初めの値にする
      if (!byId("script-author").value) byId("script-author").value = message.form.author;
      fillDatalist("script-folders", message.form.folders);
      fillDatalist("script-templates", message.form.template_folders);
    } else if (message.preview !== undefined) {
      if (message.seq === scriptPreviewSeq) byId("script-preview").textContent = message.preview;
    } else if (message.error) {
      scriptCreating = false;
      byId("script-create").disabled = false;
      setMessage("script-message", message.error);
    } else if (message.created) {
      scriptCreating = false;
      byId("script-create").disabled = false;
      hideModal("script-creator");
      // 絞り込みで隠れていなければ、作ったコマンドを選んだ状態にする(Start を押せば、すぐ試せる)
      const tab = document.querySelector('.commands .tabs button[data-type="Python"]');
      if (tab) tab.click();
      selectCommand(message.created.command_name);
    }
  }

  function openScriptCreator() {
    if (!byId("script-creator").hidden) return;
    for (const id of SCRIPT_FIELDS) byId(id).value = "";
    byId("script-bridge-no").checked = true;
    byId("script-location").value = "template";
    byId("script-location").disabled = true;
    byId("script-preview").textContent = "";
    byId("script-create").disabled = false;
    templateFollows = true;
    scriptCreating = false;
    setMessage("script-message", "");
    showModal("script-creator");
    byId("script-name").focus();
    send("script", { op: "open" });
  }

  function closeScriptCreator() {
    if (!byId("script-creator").hidden) hideModal("script-creator");
  }

  function setupScriptCreator() {
    for (const id of SCRIPT_FIELDS) byId(id).addEventListener("input", requestScriptPreview);
    byId("script-file").addEventListener("input", () => {
      if (templateFollows) byId("script-template").value = byId("script-file").value.trim();
    });
    byId("script-template").addEventListener("input", () => {
      // ファイル名と同じ間は、合わせ続ける
      templateFollows = byId("script-template").value.trim() === byId("script-file").value.trim();
    });
    byId("script-bridge-yes").addEventListener("change", onScriptBridgeChanged);
    byId("script-bridge-no").addEventListener("change", onScriptBridgeChanged);
    byId("script-location").addEventListener("change", requestScriptPreview);
    byId("script-cancel").addEventListener("click", closeScriptCreator);
    byId("script-form").addEventListener("submit", (event) => {
      event.preventDefault();
      if (scriptCreating) return;
      scriptCreating = true;
      byId("script-create").disabled = true;
      setMessage("script-message", "");
      send("script", { op: "create", ...scriptSpec() });
    });
  }

  // ---------------------------------------------------------------- Keyboard

  // サーバーから届いた配置: {pages: [{id, label, kana}], rows: {ページ: 行}, small_rows: {ページ: 行}}
  let keyboardLayout = null;
  let keyboardPage = "hiragana";
  let keyboardSmall = false;
  let keyboardPreviewTimer = null;

  function keyboardAuto() {
    return byId("kb-auto").checked;
  }

  function keyboardPageInfo() {
    return keyboardLayout ? keyboardLayout.pages.find((page) => page.id === keyboardPage) : null;
  }

  function setKeyboardStatus(status) {
    setMessage("kb-status", status.text, !status.error);
  }

  function renderKeyboard() {
    if (!keyboardLayout) return;
    const info = keyboardPageInfo();
    const small = keyboardSmall && info.kana;
    const rows = (small ? keyboardLayout.small_rows : keyboardLayout.rows)[keyboardPage];
    byId("kb-pages").replaceChildren(
      ...keyboardLayout.pages.map((page) => {
        const node = button(page.label, () => showKeyboardPage(page.id), "kb-side");
        node.classList.toggle("selected", page.id === keyboardPage);
        return node;
      })
    );
    byId("kb-small").disabled = !info.kana;
    byId("kb-small").classList.toggle("selected", small);
    byId("kb-sync").disabled = !keyboardAuto();
    const grid = byId("kb-grid");
    grid.replaceChildren();
    rows.forEach((cells, row) => {
      cells.forEach((cell, column) => {
        const key = button(cell ? cell.c : "", () => send("switch_keyboard", { op: "press", page: keyboardPage, small, row, column, auto: keyboardAuto() }), "kb-key");
        key.disabled = !cell || !cell.ok;
        if (!cell) key.classList.add("empty");
        grid.append(key);
      });
    });
  }

  function showKeyboardPage(page) {
    const changed = page !== keyboardPage;
    keyboardPage = page;
    keyboardSmall = false;
    renderKeyboard();
    // Switch 側の入力モードも、このページに合わせる(自動で切り替える設定のときだけ。サーバーが決める)
    if (changed) send("switch_keyboard", { op: "page", page, auto: keyboardAuto() });
  }

  function renderKeyboardNote() {
    const lines = ["・送れるのは、半角の英数字・記号と、かな・カナです(漢字は送れません)。"];
    if (keyboardAuto()) {
      lines.push(
        "・ひらがな・カタカナ・英数字が混ざっていても、Switch 側の入力モードを切り替えながら、そのとおりに打ちます。",
        "・最後に打った部分は、確定の前の状態(下線)で残ります。改行 (Enter) で確定します。"
      );
    } else {
      lines.push(
        "・かな・カナは、ローマ字に直して送ります。Switch 側を、ローマ字入力の「かな」または「カナ」にしておいてください。",
        "・半角の英数字を送るときは、Switch 側を、英字のモードにしておいてください。"
      );
    }
    byId("kb-note").textContent = lines.join("\n");
  }

  function requestKeyboardPreview() {
    clearTimeout(keyboardPreviewTimer);
    keyboardPreviewTimer = setTimeout(() => {
      send("switch_keyboard", { op: "preview", text: byId("kb-text").value, auto: keyboardAuto() });
    }, PREVIEW_DELAY_MS);
  }

  function showKeyboardTab(name) {
    const isText = name === "text";
    byId("kb-tab-keys").setAttribute("aria-selected", String(!isText));
    byId("kb-tab-text").setAttribute("aria-selected", String(isText));
    byId("kb-keys-panel").hidden = isText;
    byId("kb-text-panel").hidden = !isText;
    if (isText) byId("kb-text").focus();
  }

  function onSwitchKeyboard(message) {
    if (message.layout) {
      keyboardLayout = message.layout;
      renderKeyboard();
    }
    if (message.status) setKeyboardStatus(message.status);
    if (message.preview !== undefined && message.text === byId("kb-text").value) byId("kb-preview").textContent = message.preview;
    if (message.sent) {
      // 受け付けられたら、入力欄を空にする
      byId("kb-text").value = "";
      byId("kb-preview").textContent = "";
    }
  }

  function openSwitchKeyboard() {
    if (!byId("switch-keyboard").hidden) return;
    byId("switch-keyboard").hidden = false;
    showKeyboardTab("keys");
    renderKeyboardNote();
    renderKeyboard();
    send("switch_keyboard", { op: "open" });
  }

  function closeSwitchKeyboard() {
    byId("switch-keyboard").hidden = true;
    sendFocus();
  }

  function setupSwitchKeyboard() {
    byId("switch-keyboard-close").addEventListener("click", closeSwitchKeyboard);
    byId("kb-tab-keys").addEventListener("click", () => showKeyboardTab("keys"));
    byId("kb-tab-text").addEventListener("click", () => showKeyboardTab("text"));
    byId("kb-small").addEventListener("click", () => {
      keyboardSmall = !keyboardSmall;
      renderKeyboard();
    });
    byId("kb-sync").addEventListener("click", () => send("switch_keyboard", { op: "sync", page: keyboardPage }));
    for (const name of ["backspace", "space", "enter"]) {
      byId(`kb-${name}`).addEventListener("click", () => send("switch_keyboard", { op: "special", name }));
    }
    byId("kb-ok").addEventListener("click", () => send("switch_keyboard", { op: "ok" }));
    byId("kb-auto").addEventListener("change", () => {
      send("switch_keyboard", { op: "forget" });
      renderKeyboard();
      renderKeyboardNote();
      requestKeyboardPreview();
    });
    byId("kb-text").addEventListener("input", requestKeyboardPreview);
    byId("kb-text-form").addEventListener("submit", (event) => {
      event.preventDefault();
      send("switch_keyboard", { op: "text", text: byId("kb-text").value, auto: keyboardAuto(), enter: byId("kb-send-enter").checked });
    });
  }

  // ---------------------------------------------------------------- モニター

  const MONITOR_KEY = "pokecon-monitor";
  const MONITOR_MAX = 12;
  const MONITOR_DEFAULT = { count: 4, fps: 5, assignments: [], areas: [] };
  const MONITOR_AREAS = ["Stdout", "#1", "#2"];
  const MONITOR_STATES = { idle: "待機", running: "実行中", paused: "一時停止", stopping: "停止中" };
  // 頼む映像の幅の刻み(枠の大きさが少し変わるたびに頼み直さないように、刻みに切り上げる)
  const MONITOR_WIDTH_STEP = 64;
  // 映像の頼み直しと、プロファイルの一覧の更新の間隔(ms)
  const MONITOR_SLOW_MS = 1000;
  const MONITOR_NAMES_TICKS = 3;
  let monitorSettings = loadMonitorSettings();
  let monitorNames = [];
  // プロファイルごとの、届いた内容: {connected, state, outputs: {1, 2}, jpeg}
  const monitorData = {};
  // 枠ごとの部品
  let monitorTiles = [];
  let monitorExpanded = null;
  let monitorTimer = null;
  let monitorTicks = 0;
  let monitorVideo = "";

  function loadMonitorSettings() {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(MONITOR_KEY) || "{}");
    } catch (error) {
      saved = {};
    }
    const settings = { ...MONITOR_DEFAULT, ...saved };
    const list = (values, fallback) => Array.from({ length: MONITOR_MAX }, (_, index) => (Array.isArray(values) && values[index] !== undefined ? values[index] : fallback));
    settings.assignments = list(settings.assignments, "").map((name) => (typeof name === "string" ? name : ""));
    settings.areas = list(settings.areas, 0).map((area) => (MONITOR_AREAS[area] ? area : 0));
    settings.count = clampNumber(settings.count, 1, MONITOR_MAX, MONITOR_DEFAULT.count);
    settings.fps = clampNumber(settings.fps, 2, 30, MONITOR_DEFAULT.fps);
    return settings;
  }

  function saveMonitorSettings() {
    try {
      localStorage.setItem(MONITOR_KEY, JSON.stringify(monitorSettings));
    } catch (error) {
      // 保存できない場合も、表示は続ける
    }
  }

  function clampNumber(value, low, high, fallback) {
    const number = Math.round(Number(value));
    return Number.isFinite(number) ? Math.min(Math.max(number, low), high) : fallback;
  }

  function monitorColumns(count) {
    if (count <= 1) return 1;
    if (count <= 4) return 2;
    if (count <= 9) return 3;
    return 4;
  }

  function shownMonitorProfiles() {
    return [...new Set(monitorSettings.assignments.slice(0, monitorSettings.count).filter((name) => name))];
  }

  function sendMonitorProfiles() {
    const shown = shownMonitorProfiles();
    for (const name of Object.keys(monitorData)) {
      if (!shown.includes(name)) delete monitorData[name];
    }
    send("monitor", { op: "profiles", names: shown });
  }

  // 表示している映像の大きさに合った幅と、毎秒の枚数を頼む(前に頼んだものと同じなら、頼まない)
  function requestMonitorVideo(force = false) {
    const widths = monitorTiles.map((tile) => tile.image.parentElement.clientWidth);
    const width = Math.ceil(Math.max(128, ...widths) / MONITOR_WIDTH_STEP) * MONITOR_WIDTH_STEP;
    const video = `${monitorSettings.fps}/${width}`;
    if (!force && video === monitorVideo) return;
    monitorVideo = video;
    send("monitor", { op: "video", fps: monitorSettings.fps, width });
  }

  function monitorAct(profile, name) {
    if (profile) send("monitor", { op: "action", profile, name });
  }

  function buildMonitorTiles() {
    const grid = byId("monitor-grid");
    const count = monitorSettings.count;
    grid.style.setProperty("--monitor-columns", String(monitorColumns(count)));
    monitorExpanded = null;
    monitorTiles = [];
    grid.replaceChildren();
    for (let index = 0; index < count; index += 1) {
      const box = element("div", "monitor-tile");
      const head = element("div", "monitor-head");
      const profile = element("select");
      profile.setAttribute("aria-label", "プロファイル");
      profile.addEventListener("change", () => {
        monitorSettings.assignments[index] = profile.value;
        saveMonitorSettings();
        sendMonitorProfiles();
        renderMonitorTile(monitorTiles[index]);
      });
      const area = element("select");
      area.setAttribute("aria-label", "表示する Output");
      area.replaceChildren(...MONITOR_AREAS.map((name, value) => new Option(name, String(value))));
      area.value = String(monitorSettings.areas[index]);
      area.addEventListener("change", () => {
        monitorSettings.areas[index] = Number(area.value);
        saveMonitorSettings();
        renderMonitorTile(monitorTiles[index]);
      });
      const stateLabel = element("span", "monitor-state");
      head.append(profile, area, stateLabel);
      const command = element("div", "monitor-command");
      const preview = element("div", "monitor-preview");
      preview.title = "ダブルクリックで、拡大表示を切り替えます";
      const image = element("img");
      image.alt = "";
      image.draggable = false;
      const note = element("span", "monitor-note");
      preview.append(image, note);
      preview.addEventListener("dblclick", () => {
        monitorExpanded = monitorExpanded === index ? null : index;
        monitorTiles.forEach((tile, i) => {
          tile.box.classList.toggle("expanded", monitorExpanded === i);
          tile.box.hidden = monitorExpanded !== null && monitorExpanded !== i;
        });
        requestMonitorVideo();
      });
      const output = element("pre", "monitor-output");
      const buttons = element("div", "monitor-buttons");
      const name = () => monitorSettings.assignments[index];
      const play = button("▶", () => monitorAct(name(), "play"));
      play.title = "待機中: 選んでいるコマンドを開始 / 一時停止中: 再開";
      const pause = button("⏸", () => monitorAct(name(), "pause"));
      pause.title = "一時停止";
      const stop = button("■", () => monitorAct(name(), "stop"));
      stop.title = "停止";
      const front = button("前面に表示", () => monitorAct(name(), "front"));
      buttons.append(play, pause, stop, front);
      box.append(head, command, preview, output, buttons);
      grid.append(box);
      monitorTiles.push({ index, box, profile, area, stateLabel, command, image, note, output, play, pause, stop, front, shownJpeg: undefined, shownOutput: null });
    }
    fillMonitorProfiles();
    monitorTiles.forEach(renderMonitorTile);
  }

  function fillMonitorProfiles() {
    for (const tile of monitorTiles) {
      if (document.activeElement === tile.profile) continue;
      const assigned = monitorSettings.assignments[tile.index];
      const names = monitorNames.includes(assigned) || !assigned ? monitorNames : [...monitorNames, assigned];
      tile.profile.replaceChildren(new Option("(未選択)", ""), ...names.map((name) => new Option(name, name)));
      tile.profile.value = assigned;
    }
  }

  function renderMonitorTile(tile) {
    const profile = monitorSettings.assignments[tile.index];
    const data = profile ? monitorData[profile] : null;
    const connected = Boolean(data && data.connected);
    const tileState = connected ? data.state : {};
    const name = tileState.state || "";
    tile.stateLabel.textContent = MONITOR_STATES[name] ? `● ${MONITOR_STATES[name]}` : "";
    tile.stateLabel.dataset.state = name;
    if (!connected) tile.command.textContent = "";
    else if (name === "idle" || !name) tile.command.textContent = tileState.selected ? `(選択中: ${tileState.selected})` : "";
    else tile.command.textContent = tileState.command || "";
    tile.play.disabled = !connected || !(name === "paused" || tileState.can_start);
    tile.pause.disabled = !connected || !tileState.can_pause;
    tile.stop.disabled = !connected || !(name === "running" || name === "paused");
    tile.front.disabled = !connected;
    // 映像
    const jpeg = connected ? data.jpeg || null : null;
    if (jpeg !== tile.shownJpeg) {
      tile.shownJpeg = jpeg;
      if (jpeg) tile.image.src = `data:image/jpeg;base64,${jpeg}`;
      else tile.image.removeAttribute("src");
      tile.image.hidden = !jpeg;
    }
    if (!profile) tile.note.textContent = "プロファイルを選んでください";
    else if (!connected) tile.note.textContent = "起動していません\n(--monitor を付けて起動すると、表示されます)";
    else tile.note.textContent = jpeg ? "" : "映像がありません\n(カメラを開いていません)";
    // Output: 「Stdout」なら、相手の print の出力先の出力画面(切れる前の Output は、読み返せるように残す)
    const area = monitorSettings.areas[tile.index] || (tileState.stdout_area === 2 ? 2 : 1);
    const text = data && data.outputs[area] ? data.outputs[area] : "";
    if (text !== tile.shownOutput) {
      tile.shownOutput = text;
      tile.output.textContent = text;
      tile.output.scrollTop = tile.output.scrollHeight;
    }
  }

  function renderMonitorProfile(profile) {
    for (const tile of monitorTiles) {
      if (monitorSettings.assignments[tile.index] === profile) renderMonitorTile(tile);
    }
    const running = monitorTiles.filter((tile) => {
      const data = monitorData[monitorSettings.assignments[tile.index]];
      return data && data.connected;
    }).length;
    byId("monitor-summary").textContent = `起動中 ${running} / ${monitorTiles.length}`;
  }

  function monitorTargets(action) {
    return shownMonitorProfiles().filter((profile) => {
      const data = monitorData[profile];
      if (!data || !data.connected) return false;
      const name = data.state.state;
      return action === "play" ? name === "paused" || Boolean(data.state.can_start) : name === "running" || name === "paused";
    });
  }

  // まとめての操作: 対象を確かめてもらってから、それぞれに頼む
  function monitorAskAll(label, action, verb) {
    const targets = monitorTargets(action);
    if (!targets.length) {
      byId("monitor-status").textContent = `${label}: 対象のウィンドウがありません`;
      return;
    }
    const lines = targets.map((profile) => {
      const tileState = monitorData[profile].state;
      const command = tileState.state !== "idle" ? tileState.command : tileState.selected;
      const note = tileState.state === "paused" && action === "play" ? "(一時停止中 → 再開)" : "";
      return `・${profile}: ${command || "(コマンドなし)"}${note}`;
    });
    if (!window.confirm(`次の ${targets.length} 個のウィンドウで、コマンドを${verb}します。よろしいですか?\n\n${lines.join("\n")}`)) {
      byId("monitor-status").textContent = `${label}: 取り消しました`;
      return;
    }
    monitorPendingAll = { label, verb };
    send("monitor", { op: "action_all", name: action, profiles: targets });
  }

  let monitorPendingAll = null;

  function onMonitor(message) {
    if (message.type === "monitor_info") {
      monitorNames = message.names;
      fillMonitorProfiles();
    } else if (message.type === "monitor") {
      const data = monitorData[message.profile] || { outputs: {}, jpeg: null };
      data.connected = message.connected;
      data.state = message.state || {};
      for (const [area, text] of Object.entries(message.outputs || {})) data.outputs[area] = text;
      if (!message.connected) data.jpeg = null;
      monitorData[message.profile] = data;
      if (!byId("monitor").hidden) renderMonitorProfile(message.profile);
    } else if (message.type === "monitor_frame") {
      const data = monitorData[message.profile];
      if (!data) return;
      data.jpeg = message.jpeg;
      if (!byId("monitor").hidden) renderMonitorProfile(message.profile);
    } else if (message.type === "monitor_result") {
      if (message.all && monitorPendingAll) {
        byId("monitor-status").textContent = `${monitorPendingAll.label}: ${message.count} 個のウィンドウに、${monitorPendingAll.verb}を頼みました`;
        monitorPendingAll = null;
      } else if (message.text) {
        byId("monitor-status").textContent = message.text;
      }
    }
  }

  function monitorTick() {
    monitorTicks += 1;
    requestMonitorVideo();
    if (monitorTicks % MONITOR_NAMES_TICKS === 0) send("monitor", { op: "names" });
  }

  function openMonitor() {
    if (!byId("monitor").hidden) return;
    byId("monitor-count").value = String(monitorSettings.count);
    byId("monitor-fps").value = String(monitorSettings.fps);
    byId("monitor-status").textContent = "";
    for (const name of Object.keys(monitorData)) delete monitorData[name];
    showModal("monitor");
    buildMonitorTiles();
    send("monitor", { op: "open" });
    sendMonitorProfiles();
    requestMonitorVideo(true);
    monitorTicks = 0;
    monitorTimer = setInterval(monitorTick, MONITOR_SLOW_MS);
  }

  function closeMonitor() {
    if (byId("monitor").hidden) return;
    clearInterval(monitorTimer);
    monitorTimer = null;
    send("monitor", { op: "close" });
    byId("monitor-grid").replaceChildren();
    monitorTiles = [];
    hideModal("monitor");
  }

  function setupMonitor() {
    byId("monitor-close").addEventListener("click", closeMonitor);
    byId("monitor-count").addEventListener("change", (event) => {
      monitorSettings.count = clampNumber(event.target.value, 1, MONITOR_MAX, monitorSettings.count);
      event.target.value = String(monitorSettings.count);
      saveMonitorSettings();
      buildMonitorTiles();
      sendMonitorProfiles();
      requestMonitorVideo();
    });
    byId("monitor-fps").addEventListener("change", (event) => {
      monitorSettings.fps = clampNumber(event.target.value, 2, 30, monitorSettings.fps);
      event.target.value = String(monitorSettings.fps);
      saveMonitorSettings();
      requestMonitorVideo();
    });
    byId("monitor-start-all").addEventListener("click", () => monitorAskAll("All Start", "play", "開始"));
    byId("monitor-stop-all").addEventListener("click", () => monitorAskAll("All Stop", "stop", "停止"));
  }

  // ---------------------------------------------------------------- メニューと、全体

  // 一覧で選んでいるコマンドを、サーバーに知らせる(補助ツールのモニターからの再生で、始めるコマンドになる)
  let selectionSocket = null;
  let selectionSent = null;

  function sendSelection(operator) {
    if (!operator || !socket || socket.readyState !== WebSocket.OPEN) {
      selectionSent = null;
      return;
    }
    const entry = JSON.stringify(selectedCommandEntry() || {});
    if (socket === selectionSocket && entry === selectionSent) return;
    selectionSocket = socket;
    selectionSent = entry;
    send("select", JSON.parse(entry));
  }

  function menuItems() {
    const operator = role === "operator";
    return [
      { label: "タグを編集...", action: openTagEditor, disabled: !operator },
      { label: "新しい自動化スクリプトをつくる", action: openScriptCreator, disabled: !operator },
      "-",
      { label: "Keyboard (Switch のキーボード画面に文字を打つ)", action: openSwitchKeyboard, disabled: !operator },
      { label: "モニター (複数起動をまとめて見る)", action: openMonitor, disabled: !operator },
    ];
  }

  function render(operator) {
    if (!state) return;
    sendSelection(operator);
    if (operator) return;
    // 操作できなくなったら、ツールの画面を閉じる(保存していない変更は、捨てる)
    tagPending.clear();
    for (const id of ["tag-editor", "script-creator", "switch-keyboard"]) byId(id).hidden = true;
    closeMonitor();
  }

  function handle(message) {
    if (message.type === "tags") onTags(message);
    else if (message.type === "script") onScript(message);
    else if (message.type === "switch_keyboard") onSwitchKeyboard(message);
    else if (message.type.startsWith("monitor")) onMonitor(message);
  }

  byId("menu-tools").addEventListener("click", (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    window.extras.showMenu(menuItems(), rect.left, rect.bottom + 2);
  });
  // Esc: 開いているツールの画面を閉じる(実行中のコマンドは、止めない)
  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key !== "Escape" || !isModalOpen() || !byId("popup-menu").hidden) return;
      event.stopPropagation();
      if (!byId("script-creator").hidden) closeScriptCreator();
      else if (!byId("tag-editor").hidden) closeTagEditor();
      else closeMonitor();
    },
    true
  );
  setupTagEditor();
  setupScriptCreator();
  setupSwitchKeyboard();
  setupMonitor();

  return { render, handle, isModalOpen, openTagEditor, openScriptCreator, openSwitchKeyboard, openMonitor };
})();
