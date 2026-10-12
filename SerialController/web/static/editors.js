"use strict";
// 設定の編集: 目隠し(Mask)、タッチスクリーンの範囲、キーコンフィグ、本体の色、通知先(Discord / LINE)
// 値の確認と保存はサーバー(services/editor_service.py)が行い、ここでは入力と表示だけを行う

window.editors = (function () {
  const byId = (id) => document.getElementById(id);
  let operator = false;
  // 一覧を作り直すかを決めるための、前回の内容
  let masksJson = "";
  let colorsJson = "";
  let selectedMask = null;
  // プレビュー上のドラッグで範囲を指定している最中か: null / {kind: "mask" / "touch", start, end}
  let dragMode = null;
  // キーコンフィグ: サーバーから受け取った内容と、編集中の対応
  let keymap = null;
  let keymapDraft = {};
  let keymapConsole = null;
  let discordLoaded = false;
  // 読み込みを頼んで、返事を待っているか
  let keymapRequested = false;
  let discordRequested = false;

  function setStatus(id, text, ok = false) {
    const element = byId(id);
    element.textContent = text || "";
    element.classList.toggle("ok", ok);
  }

  function focusedIn(element) {
    return element.contains(document.activeElement) && document.activeElement !== document.body;
  }

  // ---------------------------------------------------------------- 目隠し(Mask)

  function maskCell(index, name, mask) {
    const cell = document.createElement("td");
    let input;
    if (name === "shape") {
      input = document.createElement("select");
      input.append(...state.masks.shapes.map((shape) => new Option(shape, shape)));
      input.value = mask.shape;
    } else {
      input = document.createElement("input");
      if (name === "enabled") {
        input.type = "checkbox";
        input.checked = mask.enabled;
      } else if (name === "color") {
        input.type = "color";
        input.value = mask.color;
      } else {
        input.type = "number";
        input.value = mask[name];
      }
    }
    input.setAttribute("aria-label", `目隠し ${index + 1} の ${name}`);
    input.disabled = !operator;
    input.addEventListener("change", () => {
      let value = input.type === "checkbox" ? input.checked : input.value;
      if (input.type === "number") value = Number(value);
      send("mask", { op: "update", index, values: { [name]: value } });
      input.blur();
    });
    input.addEventListener("focus", () => selectMask(index));
    cell.append(input);
    return cell;
  }

  function selectMask(index) {
    selectedMask = index;
    for (const row of byId("mask-table").tBodies[0].rows) {
      row.classList.toggle("selected", Number(row.dataset.index) === index);
    }
    requestDraw();
  }

  function renderMasks() {
    const masks = state.masks;
    const section = byId("mask-settings");
    if (document.activeElement !== byId("mask-show")) byId("mask-show").checked = masks.show;
    if (document.activeElement !== byId("mask-apply")) byId("mask-apply").checked = masks.apply_to_capture;
    const shape = byId("mask-shape");
    if (!shape.options.length) shape.append(...masks.shapes.map((name) => new Option(name, name)));
    byId("mask-file-list").replaceChildren(...masks.files.map((name) => new Option(name, name)));
    for (const element of section.querySelectorAll("button, input, select")) element.disabled = !operator;
    byId("mask-add").textContent = dragMode && dragMode.kind === "mask" ? "取り消す" : "追加 (プレビューをドラッグ)";
    byId("mask-add").classList.toggle("active", Boolean(dragMode && dragMode.kind === "mask"));

    // 一覧は、内容が変わったときだけ作り直す(入力中の欄を書き換えないように)
    const json = JSON.stringify([masks.items, operator]);
    const body = byId("mask-table").tBodies[0];
    if (json === masksJson || focusedIn(body)) return;
    masksJson = json;
    if (selectedMask !== null && selectedMask >= masks.items.length) selectedMask = null;
    body.replaceChildren();
    if (!masks.items.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 8;
      cell.className = "empty";
      cell.textContent = "目隠しはありません";
      return;
    }
    masks.items.forEach((mask, index) => {
      const row = body.insertRow();
      row.dataset.index = index;
      row.classList.toggle("selected", index === selectedMask);
      for (const name of ["shape", "x1", "y1", "x2", "y2", "color", "enabled"]) row.append(maskCell(index, name, mask));
      const cell = row.insertCell();
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "small";
      remove.textContent = "削除";
      remove.disabled = !operator;
      remove.addEventListener("click", () => {
        if (selectedMask === index) selectedMask = null;
        send("mask", { op: "delete", index });
      });
      cell.append(remove);
      row.addEventListener("click", () => selectMask(index));
    });
    requestDraw();
  }

  function setupMasks() {
    byId("mask-show").addEventListener("change", (event) => send("mask", { op: "options", show: event.target.checked }));
    byId("mask-apply").addEventListener("change", (event) =>
      send("mask", { op: "options", apply_to_capture: event.target.checked })
    );
    byId("mask-add").addEventListener("click", () => toggleDrag("mask"));
    const fileName = () => byId("mask-file-name").value.trim();
    byId("mask-save").addEventListener("click", () => {
      setStatus("mask-status", "");
      send("mask", { op: "save", name: fileName() });
    });
    byId("mask-load-replace").addEventListener("click", () => {
      setStatus("mask-status", "");
      send("mask", { op: "load", name: fileName(), replace: true });
    });
    byId("mask-load-add").addEventListener("click", () => {
      setStatus("mask-status", "");
      send("mask", { op: "load", name: fileName(), replace: false });
    });
  }

  // ---------------------------------------------------------------- タッチスクリーンの範囲

  const TOUCH_IDS = ["touch-x1", "touch-y1", "touch-x2", "touch-y2"];

  function renderTouch() {
    const area = state.touchscreen_area;
    const [width, height] = state.camera.capture_size;
    TOUCH_IDS.forEach((id, index) => {
      const input = byId(id);
      input.disabled = !operator;
      input.max = index % 2 === 0 ? width : height;
      if (document.activeElement !== input && area) input.value = area[index];
    });
    byId("touch-apply").disabled = !operator;
    const draw = byId("touch-draw");
    draw.disabled = !operator;
    draw.textContent = dragMode && dragMode.kind === "touch" ? "取り消す" : "プレビューをドラッグして指定";
    draw.classList.toggle("active", Boolean(dragMode && dragMode.kind === "touch"));
  }

  function setupTouch() {
    byId("touch-apply").addEventListener("click", () => {
      setStatus("touchscreen-status", "");
      send("touchscreen", { area: TOUCH_IDS.map((id) => Number(byId(id).value)) });
    });
    byId("touch-draw").addEventListener("click", () => toggleDrag("touch"));
  }

  // ---------------------------------------------------------------- プレビュー上のドラッグで範囲を指定する

  function toggleDrag(kind) {
    dragMode = dragMode && dragMode.kind === kind ? null : { kind, start: null, end: null };
    render(operator);
    requestDraw();
  }

  function previewPoint(event) {
    const rect = byId("stream").getBoundingClientRect();
    return {
      x: Math.min(Math.max(event.clientX - rect.left, 0), rect.width),
      y: Math.min(Math.max(event.clientY - rect.top, 0), rect.height),
      width: rect.width,
      height: rect.height,
    };
  }

  function setupPreviewDrag() {
    // 範囲を指定している間は、プレビュー上のほかの操作(スティック・タッチ)より先に受け取る
    const preview = byId("preview");
    const stop = (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    preview.addEventListener(
      "pointerdown",
      (event) => {
        if (dragMode === null || !operator || event.button !== 0) return;
        stop(event);
        capturePointer(preview, event);
        dragMode.start = dragMode.end = previewPoint(event);
        requestDraw();
      },
      true
    );
    preview.addEventListener(
      "pointermove",
      (event) => {
        if (dragMode === null || dragMode.start === null) return;
        stop(event);
        dragMode.end = previewPoint(event);
        requestDraw();
      },
      true
    );
    const finish = (event) => {
      if (dragMode === null || dragMode.start === null) return;
      stop(event);
      if (preview.hasPointerCapture(event.pointerId)) preview.releasePointerCapture(event.pointerId);
      const { kind, start } = dragMode;
      const end = event.type === "pointercancel" ? null : previewPoint(event);
      dragMode = null;
      if (end !== null) {
        // 表示上の位置を、カメラ画像の上の座標にする
        const [captureWidth, captureHeight] = state.camera.capture_size;
        const toX = (x) => Math.round((x * captureWidth) / end.width);
        const toY = (y) => Math.round((y * captureHeight) / end.height);
        const area = [toX(Math.min(start.x, end.x)), toY(Math.min(start.y, end.y)), toX(Math.max(start.x, end.x)), toY(Math.max(start.y, end.y))];
        if (kind === "mask") {
          setStatus("mask-status", "");
          send("mask", { op: "add", shape: byId("mask-shape").value, x1: area[0], y1: area[1], x2: area[2], y2: area[3] });
        } else {
          setStatus("touchscreen-status", "");
          send("touchscreen", { area });
        }
      }
      render(operator);
      requestDraw();
    };
    preview.addEventListener("pointerup", finish, true);
    preview.addEventListener("pointercancel", finish, true);
  }

  // プレビューの上に重ねて描くもの(app.js の draw から呼ばれる)
  function drawOverlay(context, width, height) {
    if (!state) return;
    const [captureWidth, captureHeight] = state.camera.capture_size;
    const settingsOpen = byId("settings").open;
    context.save();
    context.lineWidth = 2;
    // 選択中の目隠しの枠(設定を開いている間だけ)
    const mask = settingsOpen && selectedMask !== null ? state.masks.items[selectedMask] : null;
    if (mask) {
      context.setLineDash([6, 4]);
      context.strokeStyle = "#ff3bd4";
      context.strokeRect(
        (mask.x1 * width) / captureWidth,
        (mask.y1 * height) / captureHeight,
        ((mask.x2 - mask.x1) * width) / captureWidth,
        ((mask.y2 - mask.y1) * height) / captureHeight
      );
    }
    // タッチスクリーンの範囲(範囲を指定している間)
    if (dragMode && dragMode.kind === "touch" && state.touchscreen_area) {
      const area = state.touchscreen_area;
      context.setLineDash([2, 4]);
      context.strokeStyle = "yellow";
      context.strokeRect(
        (area[0] * width) / captureWidth,
        (area[1] * height) / captureHeight,
        ((area[2] - area[0]) * width) / captureWidth,
        ((area[3] - area[1]) * height) / captureHeight
      );
    }
    // ドラッグ中の範囲
    if (dragMode && dragMode.start !== null) {
      const { start, end } = dragMode;
      context.setLineDash([6, 4]);
      context.strokeStyle = dragMode.kind === "mask" ? "#ff3bd4" : "yellow";
      const x = Math.min(start.x, end.x);
      const y = Math.min(start.y, end.y);
      const w = Math.abs(end.x - start.x);
      const h = Math.abs(end.y - start.y);
      if (dragMode.kind === "mask" && byId("mask-shape").value === "Ellipse") {
        context.beginPath();
        context.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
        context.stroke();
      } else {
        context.strokeRect(x, y, w, h);
      }
    }
    context.restore();
  }

  // ---------------------------------------------------------------- キーコンフィグ

  function isKeymapChanged() {
    return keymap !== null && JSON.stringify(keymapDraft) !== JSON.stringify(keymap.keymaps);
  }

  function renderKeymap() {
    const section = byId("keymap-settings");
    for (const element of section.querySelectorAll("button, select, input")) element.disabled = !operator || keymap === null;
    if (keymap === null) return;
    const select = byId("keymap-console");
    if (!select.options.length) {
      select.append(...keymap.consoles.map((item) => new Option(item, item)));
      keymapConsole = keymap.current;
      select.value = keymapConsole;
    }
    byId("keymap-save").disabled = !operator || !isKeymapChanged();
    byId("keymap-reload").disabled = !operator || !isKeymapChanged();
    const grid = byId("keymap-grid");
    if (grid.dataset.console === keymapConsole && grid.dataset.version === String(keymap.version)) {
      // 欄は作り直さず、値と、変更した欄の印だけを合わせる
      for (const input of grid.querySelectorAll("input")) {
        const name = input.dataset.name;
        input.value = keymapDraft[keymapConsole][name];
        input.classList.toggle("changed", keymapDraft[keymapConsole][name] !== keymap.keymaps[keymapConsole][name]);
      }
      return;
    }
    grid.dataset.console = keymapConsole;
    grid.dataset.version = String(keymap.version);
    grid.replaceChildren();
    for (const column of keymap.buttons[keymapConsole]) {
      for (const [text, name] of column) {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "text";
        input.readOnly = true;
        input.dataset.name = name;
        input.value = keymapDraft[keymapConsole][name];
        input.disabled = !operator;
        input.setAttribute("aria-label", `${keymapConsole} ${text}`);
        // 欄を選んでいる間、次に押したキーを読み取る(キーは、アプリを動かしている PC 側で読む)
        input.addEventListener("focus", () => send("keymap", { op: "capture", start: true, field: `${keymapConsole}|${name}` }));
        input.addEventListener("blur", () => send("keymap", { op: "capture", start: false }));
        label.append(text, input);
        grid.append(label);
      }
    }
  }

  function loadKeymap(data) {
    keymap = data;
    keymap.version = (keymap.version || 0) + Date.now();
    keymapDraft = JSON.parse(JSON.stringify(data.keymaps));
    if (keymapConsole === null) keymapConsole = data.current;
  }

  function setupKeymap() {
    byId("keymap-console").addEventListener("change", (event) => {
      keymapConsole = event.target.value;
      render(operator);
    });
    byId("keymap-save").addEventListener("click", () => {
      setStatus("keymap-status", "");
      send("keymap", { op: "save", keymaps: keymapDraft });
    });
    byId("keymap-reload").addEventListener("click", () => {
      setStatus("keymap-status", "");
      send("keymap", { op: "get" });
    });
  }

  // ---------------------------------------------------------------- 本体の色

  function currentColorType() {
    return state.colors.types.find((type) => type.name === byId("color-type").value) || state.colors.types[0];
  }

  function renderColors() {
    const section = byId("color-settings");
    const typeSelect = byId("color-type");
    if (!typeSelect.options.length) {
      typeSelect.append(...state.colors.types.map((type) => new Option(type.name, type.name)));
      // 初めは、表示中の Software-Controller の種類を選ぶ
      const layout = state.softcon.layout ? state.softcon.layout.name : "";
      const match = state.colors.types.find((type) => layout.startsWith(type.name));
      if (match) typeSelect.value = match.name;
    }
    const type = currentColorType();
    const json = JSON.stringify([type, operator]);
    if (json !== colorsJson && !focusedIn(byId("color-inputs"))) {
      colorsJson = json;
      const inputs = byId("color-inputs");
      inputs.replaceChildren();
      for (const [key, text] of type.keys) {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "color";
        input.value = type.colors[key].toLowerCase();
        input.addEventListener("change", () => {
          setStatus("colors-status", "");
          send("colors", { controller: type.name, colors: { [key]: input.value } });
        });
        label.append(text, input);
        inputs.append(label);
      }
      const preset = byId("color-preset");
      preset.replaceChildren(new Option("(選択してください)", ""), ...type.presets.map((item, index) => new Option(item.name, String(index))));
      const current = type.presets.findIndex((item) =>
        type.keys.every(([key]) => item.colors[key].toLowerCase() === type.colors[key].toLowerCase())
      );
      preset.value = current >= 0 ? String(current) : "";
    }
    for (const element of section.querySelectorAll("select, input")) element.disabled = !operator;
  }

  function setupColors() {
    byId("color-type").addEventListener("change", () => render(operator));
    byId("color-preset").addEventListener("change", (event) => {
      const type = currentColorType();
      const preset = type.presets[Number(event.target.value)];
      if (event.target.value !== "" && preset) {
        setStatus("colors-status", "");
        send("colors", { controller: type.name, colors: preset.colors });
      }
      event.target.blur();
    });
  }

  // ---------------------------------------------------------------- 通知先(Discord / LINE)

  const DISCORD_FIELDS = ["webhook_url", "username", "avatar_url"];

  function showDiscord(data) {
    discordLoaded = true;
    byId("discord-names").replaceChildren(...data.names.map((name) => new Option(name, name)));
    const name = byId("discord-name");
    name.value = data.selected;
    // 既定の通知先が未設定の間は、名前を変えられない(既定の通知先は必ず作る)
    name.readOnly = !data.default_set;
    name.dataset.names = JSON.stringify(data.names);
    for (const field of DISCORD_FIELDS) byId(`discord-${field}`).value = data.values[field];
    byId("discord-delete").disabled = !operator || !data.names.includes(data.selected) || data.selected === data.default_name;
    if (data.saved) setStatus("discord-status", "保存しました。", true);
    else if (!data.default_set) setStatus("discord-status", `${data.default_name} が未設定です。先に設定してください。`, true);
  }

  function renderNotify() {
    for (const id of ["discord-settings", "line-settings"]) {
      for (const element of byId(id).querySelectorAll("button, input")) {
        if (element.id !== "discord-delete") element.disabled = !operator;
      }
    }
    if (!operator) byId("discord-delete").disabled = true;
    if (document.activeElement !== byId("line-token") && !byId("line-status").classList.contains("saved")) {
      setStatus("line-status", state.line_token_set ? "トークンは設定済みです。" : "トークンは未設定です。", true);
    }
  }

  function setupNotify() {
    const name = byId("discord-name");
    name.addEventListener("change", () => {
      // 登録済みの名前を入力・選択した場合は、その設定を表示する
      const names = JSON.parse(name.dataset.names || "[]");
      if (names.includes(name.value.trim())) send("discord", { op: "get", name: name.value.trim() });
    });
    byId("discord-show-url").addEventListener("change", (event) => {
      byId("discord-webhook_url").type = event.target.checked ? "text" : "password";
    });
    byId("discord-save").addEventListener("click", () => {
      setStatus("discord-status", "");
      const values = Object.fromEntries(DISCORD_FIELDS.map((field) => [field, byId(`discord-${field}`).value]));
      send("discord", { op: "save", name: name.value, values });
    });
    byId("discord-delete").addEventListener("click", () => {
      if (!window.confirm(`通知先「${name.value.trim()}」を削除しますか？`)) return;
      setStatus("discord-status", "");
      send("discord", { op: "delete", name: name.value });
    });
    byId("line-save").addEventListener("click", () => {
      byId("line-status").classList.remove("saved");
      setStatus("line-status", "");
      send("line", { token: byId("line-token").value });
    });
  }

  // ---------------------------------------------------------------- まとめ

  // 設定を開いたときに、サーバーから読み込むもの(Webhook URL などは、状態の知らせには含まれない)
  function loadOnDemand() {
    if (!operator || !byId("settings").open) return;
    if (keymap === null && !keymapRequested) {
      keymapRequested = true;
      send("keymap", { op: "get" });
    }
    if (!discordLoaded && !discordRequested) {
      discordRequested = true;
      send("discord", { op: "get" });
    }
  }

  function render(isOperator) {
    if (operator && !isOperator) {
      // 操作できなくなった: 読み込んだ内容を捨てる(もう一度操作できるようになったら、読み込み直す)
      dragMode = null;
      keymap = null;
      discordLoaded = false;
      keymapRequested = discordRequested = false;
      for (const field of DISCORD_FIELDS) byId(`discord-${field}`).value = "";
    }
    operator = isOperator;
    if (!state) return;
    renderMasks();
    renderTouch();
    renderKeymap();
    renderColors();
    renderNotify();
    loadOnDemand();
  }

  // サーバーからの返事
  function handle(message) {
    if (message.type === "keymap") {
      loadKeymap(message.keymap);
      if (message.saved) setStatus("keymap-status", "保存しました。", true);
      render(operator);
    } else if (message.type === "key_captured") {
      const [consoleName, name] = String(message.field).split("|");
      if (keymap !== null && keymapDraft[consoleName] && name in keymapDraft[consoleName]) {
        keymapDraft[consoleName][name] = message.key;
        // 続けて別のキーを読み取れるようにする(欄を選んだままの場合)
        const input = byId("keymap-grid").querySelector(`input[data-name="${name}"]`);
        if (input && document.activeElement === input && consoleName === keymapConsole) {
          send("keymap", { op: "capture", start: true, field: message.field });
        }
        render(operator);
      }
    } else if (message.type === "discord") {
      showDiscord(message.discord);
    } else if (message.type === "line_saved") {
      byId("line-token").value = "";
      setStatus("line-status", "保存しました。", true);
      byId("line-status").classList.add("saved");
    } else if (message.type === "edit_error") {
      const id = { mask: "mask-status", touchscreen: "touchscreen-status", keymap: "keymap-status", colors: "colors-status", discord: "discord-status", line: "line-status" }[message.action];
      if (id) setStatus(id, message.message);
    }
  }

  setupMasks();
  setupTouch();
  setupPreviewDrag();
  setupKeymap();
  setupColors();
  setupNotify();
  byId("settings").addEventListener("toggle", () => {
    loadOnDemand();
    requestDraw();
  });

  return { render, handle, drawOverlay };
})();
