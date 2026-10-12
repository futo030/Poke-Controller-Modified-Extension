"use strict";
// Web ブラウザ版の画面。サーバー(web/server.py)と WebSocket でやり取りする

const $ = (id) => document.getElementById(id);

// 出力画面に残す行数の上限
const OUTPUT_MAX_LINES = 5000;
// マウスでのスティック操作: いっぱいに倒す距離(px)と、送る間隔(ms)
const STICK_RADIUS = 60;
const STICK_INTERVAL_MS = 40;
// 切断したときに、つなぎ直すまでの時間(ms)
const RECONNECT_MS = 1500;
const CAPTURE_PREFIX = "capture succeeded: ";

let socket = null;
let role = "viewer";
let state = null;
let commandType = "Python";
let selectedCommand = { Python: null, Mcu: null, History: null, Shortcut: null };
// 絞り込みに使うタグ(選んだタグのいずれかを持つコマンドを残す)
let tagFilter = { Python: [], Mcu: [], History: [], Shortcut: [] };
let dialogue = null;
const dialogueQueue = [];
const shapes = [];
// 出力画面の行数(「出力画面の番号-ページ」ごと)
const outputLines = {};
// outview.js(Serial / Log / Note タブ)の読み込みが終わる前に、サーバーから届いた知らせ
const pendingViewMessages = [];
// マウスで操作中のスティック: {side, x, y(押した位置), knobX, knobY}
let stick = null;
let touching = false;
let lastStickSent = 0;
// 画面の「終了」でアプリを終了したか(終了した後は、つなぎ直さない)
let exited = false;
// History の並び順(true: 実行した日時の新しい順)
let historyDescending = true;

// ドラッグ中、部品の外へ出ても、その部品でマウスの動きを受け取り続けるようにする
function capturePointer(element, event) {
  try {
    element.setPointerCapture(event.pointerId);
  } catch (error) {
    // 受け取り続けられない場合も、部品の上での操作は続けられる
  }
}

// ---------------------------------------------------------------- 通信

function send(action, data = {}) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action, ...data }));
  }
}

function connect() {
  socket = new WebSocket(`ws://${location.host}/ws`);
  socket.addEventListener("open", () => {
    $("connection").hidden = true;
    sendFocus();
  });
  socket.addEventListener("message", (event) => handle(JSON.parse(event.data)));
  socket.addEventListener("close", () => {
    $("connection").hidden = false;
    setRole("viewer");
    closeDialogue(null);
    dialogueQueue.length = 0;
    if (exited) {
      $("connection").hidden = true;
      return;
    }
    setTimeout(connect, RECONNECT_MS);
  });
}

function handle(message) {
  switch (message.type) {
    case "hello":
      // 映像は、つなぐたびに読み込み直す(Realtime がオフの場合は、状態を反映するときに止める)
      $("stream").src = `/stream.mjpg?t=${Date.now()}`;
      delete $("stream").dataset.paused;
      setRole(message.role);
      setState(message.state);
      break;
    case "state":
      setState(message.state);
      break;
    case "role":
      setRole(message.role);
      sendFocus();
      break;
    case "output":
      writeOutput(message.area, message.clear, message.parts, message.page || 0);
      break;
    case "serial":
    case "log":
    case "note":
      // Serial タブ(機器へ送ったデータ)、Log タブ(ログ)、Note タブ(メモ)
      // (outview.js の読み込みが終わる前に届いた分は、取っておいて、読み込みが終わったときに渡す)
      if (window.outview) window.outview.handle(message);
      else pendingViewMessages.push(message);
      break;
    case "overlay":
      addShape(message);
      break;
    case "dialogue":
      if (role === "operator") {
        dialogueQueue.push(message.dialogue);
        showNextDialogue();
      }
      break;
    case "dialogue_close":
      closeDialogue(message.id);
      break;
    case "exit":
      // アプリが終了する: 映像の受信をやめて、終了したことを表示する
      exited = true;
      $("stream").removeAttribute("src");
      $("exited").hidden = false;
      break;
    default:
      // 設定の編集(目隠し・キーコンフィグ・通知先など)や、こまごました操作への返事
      if (window.editors) window.editors.handle(message);
      if (window.extras) window.extras.handle(message);
      if (window.tools) window.tools.handle(message);
  }
}

// ---------------------------------------------------------------- 状態の表示

function setRole(newRole) {
  role = newRole;
  $("role").hidden = role === "operator";
  render();
}

function setState(newState) {
  state = newState;
  render();
}

function chip(element, text, kind) {
  element.textContent = text;
  element.className = `chip ${kind}`;
}

function render() {
  if (!state) return;
  const operator = role === "operator";
  const command = state.command;
  const running = command.state !== "idle";
  document.title = state.app;
  $("app-name").textContent = state.app;
  chip($("profile"), `profile: ${state.profile}`, "ok");
  chip(
    $("serial-status"),
    state.serial.connected ? `Serial: COM${state.serial.port} (${state.serial.format})` : `Serial: 未接続 (COM${state.serial.port})`,
    state.serial.connected ? "ok" : "warning"
  );
  const [width, height] = state.camera.capture_size;
  chip(
    $("camera-status"),
    state.camera.opened ? `Camera: ${state.camera.source} ${width}x${height}` : `Camera: 映像なし (${state.camera.source})`,
    state.camera.opened ? "ok" : "warning"
  );

  // Status の欄(設定の画面のいちばん上。今つながっている機器と、実行中のコマンド)
  for (const [key, text] of Object.entries(state.status || {})) {
    const element = $(`status-${key}`);
    if (element && element.textContent !== text) element.textContent = text;
  }

  // 一覧を先に作る(選択中のコマンドが決まる)
  renderCommands();

  $("exit-app").disabled = !operator;
  // プレビューの縦横比は、取り込みサイズと同じにする
  document.documentElement.style.setProperty("--preview-aspect", String(width / height));

  const start = $("start");
  start.textContent = running ? "Stop" : "Start";
  start.disabled = !operator || command.state === "stopping" || (!running && !selectedCommand[commandType]) || (!running && state.input.recording);
  const pause = $("pause");
  pause.textContent = command.paused ? "Restart" : "Pause";
  pause.disabled = !operator || command.state !== "running" || !command.can_pause;
  $("reload").disabled = !operator || running;
  $("running-name").textContent = running ? `${command.state === "stopping" ? "停止中" : command.paused ? "一時停止中" : "実行中"}: ${command.name}` : "";

  const input = state.input;
  $("use-keyboard").checked = input.keyboard_enabled;
  $("use-controller").checked = input.controller_active;
  $("right-mouse-label").textContent = input.touchscreen ? "右ドラッグ: タッチスクリーン" : "右ドラッグ: Rスティック";
  const record = $("record");
  record.classList.toggle("recording", input.recording);
  record.textContent = input.recording ? "Recording" : "Record";
  record.disabled = !operator || (running && !input.recording);
  for (const id of ["use-keyboard", "use-left-mouse", "use-right-mouse", "release-all"]) $(id).disabled = !operator;
  $("use-controller").disabled = !operator || running;
  for (const button of document.querySelectorAll("[data-clear]")) button.disabled = !operator;

  $("output-label-1").textContent = state.stdout_destination === "1" ? "Output#1 (Stdout)" : "Output#1";
  $("output-label-2").textContent = state.stdout_destination === "2" ? "Output#2 (Stdout)" : "Output#2";
  renderOutputPages(operator);
  renderPreviewState(operator);
  renderSettings();
  if (window.softcon) window.softcon.setLayout(state.softcon.layout, operator);
  if (window.simulator) window.simulator.render(operator);
  renderShortcutBar(operator);
  if (window.editors) window.editors.render(operator);
  if (window.extras) window.extras.render(operator);
  if (window.tools) window.tools.render(operator);
}

// ---------------------------------------------------------------- ショートカット

function shortcutLabel(shortcut) {
  return `#${shortcut.num}  ${shortcut.class === "None" ? "(未設定)" : shortcut.name}`;
}

function selectedShortcut() {
  return state.shortcuts.find((shortcut) => shortcutLabel(shortcut) === selectedCommand.Shortcut) || null;
}

// ショートカットに設定する対象: 選択中のコマンドの {command_type, name}(無ければ null)
function selectedCommandEntry() {
  const name = selectedCommand[commandType];
  if (!name || commandType === "Shortcut") return null;
  if (commandType === "History") {
    const entry = state.history.find((item) => item.name === name);
    return entry ? { command_type: entry.class, name } : null;
  }
  return { command_type: commandType, name };
}

function renderShortcutBar(operator) {
  const select = $("shortcut-num");
  if (!select.options.length) {
    select.replaceChildren(...state.shortcuts.map((shortcut) => new Option(`#${shortcut.num}`, String(shortcut.num))));
  }
  const shortcut = selectedShortcut();
  if (commandType === "Shortcut" && shortcut && document.activeElement !== select) select.value = String(shortcut.num);
  for (const option of select.options) {
    const item = state.shortcuts[Number(option.value) - 1];
    option.textContent = item.class === "None" ? `#${item.num}` : `#${item.num}: ${item.name}`;
  }
  select.disabled = !operator;
  $("shortcut-set").disabled = !operator || selectedCommandEntry() === null;
  $("shortcut-clear").disabled = !operator || state.shortcuts[Number(select.value) - 1].class === "None";
}

// ---------------------------------------------------------------- 設定

// 候補の一覧(options の名前) -> [値, 表示する文字] の並びにする関数
const OPTION_ITEMS = {
  cameras: (items) => items.map((item) => [String(item.id), item.label]),
  ports: (items) => items.map((item) => [String(item.number), item.label]),
  audio_inputs: (items) => items.map((item) => [item.name, item.label]),
};
let optionsJson = {};

function settingValue(element) {
  const kind = element.dataset.kind;
  if (kind === "bool") return element.checked;
  if (kind === "int") return parseInt(element.value, 10);
  if (kind === "float") return parseFloat(element.value);
  return element.value;
}

function renderSettings() {
  const settings = state.settings;
  if (!settings) return;
  const operator = role === "operator";
  const { values, options } = settings;
  $("show-windows-label").hidden = !options.windows_supported;
  $("audio-settings").disabled = !options.audio_available;
  for (const element of document.querySelectorAll("[data-setting]")) {
    const name = element.dataset.setting;
    const value = values[name];
    element.disabled = !operator;
    // 候補の一覧(変わったときだけ作り直す)
    const key = element.dataset.options;
    if (key) {
      if (key === "softcon_layouts") options[key] = state.softcon.layouts;
      const items = options[key] === null ? [] : (OPTION_ITEMS[key] || ((list) => list.map((item) => [String(item), String(item)])))(options[key]);
      // 今の値が候補に無い場合(接続されていないポートなど)も、選択肢として表示する
      if (value !== null && value !== undefined && !items.some(([itemValue]) => itemValue === String(value))) {
        items.push([String(value), name === "com_port" ? `COM${value} (未検出)` : String(value)]);
      }
      const json = JSON.stringify(items);
      if (optionsJson[name] !== json) {
        optionsJson[name] = json;
        element.replaceChildren(...items.map(([itemValue, label]) => new Option(label, itemValue)));
      }
    }
    if (element.dataset.range) {
      [element.min, element.max] = options[element.dataset.range];
    }
    // 操作中の部品は、値を書き換えない
    if (document.activeElement === element) continue;
    if (element.dataset.kind === "bool") element.checked = Boolean(value);
    else element.value = String(value);
  }
  for (const output of document.querySelectorAll("[data-output]")) {
    const input = document.querySelector(`[data-setting="${output.dataset.output}"]`);
    output.textContent = input.value;
  }
  for (const button of document.querySelectorAll("#settings [data-action]")) button.disabled = !operator;
}

function setupSettings() {
  for (const element of document.querySelectorAll("[data-setting]")) {
    element.addEventListener("change", () => {
      if (element.dataset.confirm && !window.confirm(element.dataset.confirm.replaceAll("\\n", "\n"))) {
        // キャンセルした場合は、表示を元に戻す
        element.blur();
        render();
        return;
      }
      send("setting", { name: element.dataset.setting, value: settingValue(element) });
      element.blur();
    });
    if (element.type === "range") {
      element.addEventListener("input", () => {
        const output = document.querySelector(`[data-output="${element.dataset.setting}"]`);
        if (output) output.textContent = element.value;
      });
    }
  }
  for (const button of document.querySelectorAll("#settings [data-action]")) {
    button.addEventListener("click", () => {
      const action = button.dataset.action;
      send(action, action === "serial" ? { connect: button.dataset.connect === "1" } : {});
    });
  }
}

// ---------------------------------------------------------------- コマンドの一覧

function directoryTagsLast(tags) {
  const plain = tags.filter((tag) => !tag.startsWith("@")).sort();
  const directory = tags.filter((tag) => tag.startsWith("@")).sort();
  return [...plain, ...directory];
}

function renderCommands() {
  const isShortcut = commandType === "Shortcut";
  const isHistory = commandType === "History" || isShortcut;
  // History は、実行した日時の新しい順に並べる(タグの欄には、実行した日時を表示する)。
  // Shortcut は、番号の順に並べる(タグの欄には、コマンドの種別を表示する)
  let commands = state.commands[commandType] || [];
  if (isShortcut) {
    commands = state.shortcuts.map((shortcut) => ({
      name: shortcutLabel(shortcut),
      tags: shortcut.class === "None" ? [] : [shortcut.class],
    }));
  } else if (isHistory) {
    commands = [...state.history]
      .sort((a, b) => (historyDescending ? b.last_run.localeCompare(a.last_run) : a.last_run.localeCompare(b.last_run)))
      .map((entry) => ({ name: entry.name, tags: [entry.last_run] }));
  }
  $("tag-filter").hidden = isHistory;
  $("command-sort").hidden = isHistory;
  $("history-sort").hidden = commandType !== "History";
  $("history-sort").textContent = historyDescending ? "Last Run ▼" : "Last Run ▲";
  // タグの候補(無くなったタグは、絞り込みから外す)
  const tags = isHistory ? [] : directoryTagsLast([...new Set(commands.flatMap((command) => command.tags))]);
  tagFilter[commandType] = tagFilter[commandType].filter((tag) => tags.includes(tag));
  const selectedTags = tagFilter[commandType];
  $("tag-filter").textContent = selectedTags.length ? `Tags ▾ (フィルタ: ${selectedTags.length})` : "Tags ▾";
  $("tag-filter").classList.toggle("active", selectedTags.length > 0);
  $("tag-filter").dataset.tags = JSON.stringify(tags);

  const text = $("command-filter").value.trim().toLowerCase();
  const sort = isHistory ? "default" : $("command-sort").value;
  let rows = commands.filter(
    (command) =>
      (!selectedTags.length || command.tags.some((tag) => selectedTags.includes(tag))) &&
      (!text || command.name.toLowerCase().includes(text))
  );
  if (sort.startsWith("name")) {
    rows = [...rows].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  } else if (sort.startsWith("mtime")) {
    const mtimes = state.tools.mtimes[commandType] || {};
    rows = [...rows].sort((a, b) => (mtimes[a.name] || 0) - (mtimes[b.name] || 0));
  } else if (sort.startsWith("usage")) {
    // 回数が同じものは、多い順でも少ない順でも、既定の順のまま並べる
    const usage = state.tools.usage[commandType] || {};
    const sign = sort.endsWith("desc") ? -1 : 1;
    rows = [...rows].sort((a, b) => sign * ((usage[a.name] || 0) - (usage[b.name] || 0)));
  }
  if (sort.endsWith("desc") && !sort.startsWith("usage")) rows.reverse();
  if (!rows.some((command) => command.name === selectedCommand[commandType])) {
    selectedCommand[commandType] = rows.length ? rows[0].name : null;
  }
  const list = $("command-list");
  if (!rows.length) {
    const item = document.createElement("li");
    item.className = "empty";
    item.textContent = commands.length ? "該当するコマンドがありません" : commandType === "History" ? "履歴がありません" : "コマンドがありません";
    list.replaceChildren(item);
    return;
  }
  list.replaceChildren(
    ...rows.map((command) => {
      const item = document.createElement("li");
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(command.name === selectedCommand[commandType]));
      item.dataset.name = command.name;
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = command.name;
      const tagText = document.createElement("span");
      tagText.className = "tags";
      tagText.textContent = command.tags.join(", ");
      item.append(name, tagText);
      return item;
    })
  );
}

function selectCommand(name) {
  selectedCommand[commandType] = name;
  render();
}

function startSelected() {
  const name = selectedCommand[commandType];
  if (role === "operator" && name && state.command.state === "idle") {
    if (commandType === "Shortcut") {
      const shortcut = selectedShortcut();
      if (shortcut) send("shortcut", { op: "start", num: shortcut.num });
      return;
    }
    // History の場合は、履歴に記録されている種別(Python / Mcu)で開始する
    const entry = state.history.find((item) => item.name === name);
    send("start", { command_type: commandType === "History" ? entry.class : commandType, name });
  }
}

// ---------------------------------------------------------------- 出力画面

function appendText(target, text) {
  // 「capture succeeded: (パス)」の行は、パスの部分を画像へのリンクにする
  for (const piece of text.split(/(\n)/)) {
    const index = piece.indexOf(CAPTURE_PREFIX);
    if (piece === "\n" || index < 0) {
      target.append(piece);
      continue;
    }
    const path = piece.slice(index + CAPTURE_PREFIX.length);
    target.append(piece.slice(0, index + CAPTURE_PREFIX.length));
    const link = document.createElement("a");
    link.textContent = path;
    link.href = `/api/capture?path=${encodeURIComponent(path)}`;
    link.dataset.capture = path;
    link.target = "_blank";
    link.rel = "noopener";
    target.append(link);
  }
}

// 出力画面(番号とページ)の、文字を書き込む部品(無ければ作る)
function outputElement(area, page) {
  const id = `output-${area}-p${page}`;
  let element = $(id);
  if (!element) {
    element = document.createElement("pre");
    element.id = id;
    element.tabIndex = 0;
    element.hidden = page !== activeOutputPage();
    $(`output-${area}`).append(element);
  }
  return element;
}

function activeOutputPage() {
  return state ? state.output_page || 0 : 0;
}

function renderOutputPages(operator) {
  const tabs = $("output-tabs");
  const count = state.output_pages || 1;
  // (outview.js の読み込みが終わる前に作ったタブには、Serial / Log / Note がないので、作り直す)
  const needsExtraTabs = Boolean(window.outview) && !tabs.querySelector("[data-view]");
  if (tabs.querySelectorAll("[data-page]").length !== count || needsExtraTabs) {
    tabs.replaceChildren(
      ...Array.from({ length: count }, (_, page) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.setAttribute("role", "tab");
        tab.dataset.page = page;
        tab.textContent = `Page ${page + 1}`;
        tab.addEventListener("click", () => {
          // Serial / Log タブを見ていた場合は、ページの表示に戻す
          if (window.outview) window.outview.show("pages");
          if (role === "operator") send("output_page", { page });
        });
        return tab;
      }),
      // ページの後ろに、Serial / Log のタブと、検索のボタンを並べる
      ...(window.outview ? window.outview.tabButtons() : [])
    );
  }
  const active = activeOutputPage();
  const showingPages = !window.outview || window.outview.currentView() === "pages";
  for (const tab of tabs.querySelectorAll("[data-page]")) {
    const selected = Number(tab.dataset.page) === active;
    tab.setAttribute("aria-selected", String(selected && showingPages));
    // 閲覧のみのブラウザでも、今のページのタブは押せる(Serial / Log タブから、ページの表示に戻るため)
    tab.disabled = !operator && !selected;
  }
  if (window.outview) window.outview.render(operator);
  let changed = false;
  for (const area of [1, 2]) {
    for (let page = 0; page < count; page++) {
      const element = outputElement(area, page);
      const show = page === active;
      if (element.hidden === show) {
        element.hidden = !show;
        // 表示したページは、最後の行が見える位置にする
        if (show) element.scrollTop = element.scrollHeight;
        changed = true;
      }
    }
  }
  // ページを変えたときは、検索の印を、表示しているページに付け直す
  if (changed && window.outview) window.outview.refreshSearch(false);
}

function renderPreviewState(operator) {
  // Realtime がオフの間は、映像を受け取らない
  const realtime = state.settings.values.is_show_realtime;
  const image = $("stream");
  $("preview-paused").hidden = realtime;
  if (!realtime && image.getAttribute("src")) {
    image.dataset.paused = "1";
    image.removeAttribute("src");
  } else if (realtime && image.dataset.paused === "1") {
    delete image.dataset.paused;
    image.src = `/stream.mjpg?t=${Date.now()}`;
  }
  for (const id of ["capture", "open-captures", "send-line", "send-discord"]) $(id).disabled = !operator;
}

function writeOutput(area, clear, parts, page = 0) {
  const target = outputElement(area, page);
  const key = `${area}-${page}`;
  const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 24;
  if (clear) {
    target.replaceChildren();
    outputLines[key] = 0;
  }
  outputLines[key] = outputLines[key] || 0;
  for (const part of parts) {
    if (part.link !== null && part.link !== undefined) {
      const link = document.createElement("a");
      link.textContent = part.text;
      link.dataset.link = part.link;
      link.tabIndex = 0;
      target.append(link);
    } else {
      appendText(target, part.text);
    }
    outputLines[key] += (part.text.match(/\n/g) || []).length;
  }
  // 行数が上限を超えたら、古い方から消す
  while (outputLines[key] > OUTPUT_MAX_LINES && target.firstChild) {
    outputLines[key] -= (target.firstChild.textContent.match(/\n/g) || []).length;
    target.firstChild.remove();
  }
  if (atBottom) target.scrollTop = target.scrollHeight;
}

// ---------------------------------------------------------------- 認識した位置の表示

function addShape(message) {
  if (message.kind === "delete") {
    removeTag(message.tag);
  } else {
    shapes.push({ ...message, expires: message.ms === null ? null : performance.now() + message.ms });
  }
  requestDraw();
}

function removeTag(tag) {
  for (let i = shapes.length - 1; i >= 0; i--) {
    if (shapes[i].tag === tag) shapes.splice(i, 1);
  }
}

let drawRequested = false;
function requestDraw() {
  if (!drawRequested) {
    drawRequested = true;
    requestAnimationFrame(draw);
  }
}

function draw() {
  drawRequested = false;
  const canvas = $("overlay");
  const image = $("stream");
  const width = image.clientWidth;
  const height = image.clientHeight;
  const scale = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);

  // 表示する時間が過ぎたものを消す(同じ tag のものは一緒に消す)
  const now = performance.now();
  for (const tag of shapes.filter((shape) => shape.expires !== null && shape.expires <= now).map((shape) => shape.tag)) {
    removeTag(tag);
  }
  for (const shape of shapes) {
    const ratioX = width / shape.capture[0];
    const ratioY = height / shape.capture[1];
    if (shape.kind === "rect") {
      context.lineWidth = 4.5;
      context.strokeStyle = "white";
      context.strokeRect((shape.x1 - 1) * ratioX, (shape.y1 - 1) * ratioY, (shape.x2 - shape.x1 + 2) * ratioX, (shape.y2 - shape.y1 + 2) * ratioY);
      context.lineWidth = 2.5;
      context.strokeStyle = shape.color;
      context.strokeRect(shape.x1 * ratioX, shape.y1 * ratioY, (shape.x2 - shape.x1) * ratioX, (shape.y2 - shape.y1) * ratioY);
    } else if (shape.kind === "text") {
      context.font = `${shape.size}pt "UD デジタル 教科書体 NP-B", "BIZ UDGothic", sans-serif`;
      context.fillStyle = shape.color;
      context.textAlign = "center";
      context.textBaseline = "middle";
      // tkinter 版と同じ位置(文字列の中心を、文字数に応じて右へずらす)
      context.fillText(shape.text, (shape.x - 1) * ratioX + 0.3528 * shape.size * shape.text.length, (shape.y - 1) * ratioY);
    }
  }
  if (stick) {
    const color = stick.side === "left" ? "cyan" : "red";
    context.lineWidth = 1.5;
    context.strokeStyle = color;
    context.beginPath();
    context.arc(stick.x, stick.y, STICK_RADIUS, 0, Math.PI * 2);
    context.stroke();
    context.fillStyle = color;
    context.beginPath();
    context.arc(stick.knobX, stick.knobY, STICK_RADIUS / 10, 0, Math.PI * 2);
    context.fill();
  }
  if (touching && state && state.input.touchscreen_ratio) {
    const [startX, startY, endX, endY] = state.input.touchscreen_ratio;
    context.lineWidth = 1.5;
    context.setLineDash([6, 4]);
    context.strokeStyle = "yellow";
    context.strokeRect(startX * width, startY * height, (endX - startX) * width, (endY - startY) * height);
    context.setLineDash([]);
  }
  // 目隠し・タッチスクリーンの範囲の、編集中の表示
  if (window.editors) window.editors.drawOverlay(context, width, height);
  if (window.extras) window.extras.drawOverlay(context, width, height);
  if (shapes.some((shape) => shape.expires !== null)) requestDraw();
}

// ---------------------------------------------------------------- プレビュー上のマウス操作

function position(event) {
  const rect = $("stream").getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top, width: rect.width, height: rect.height };
}

function sendTouch(event) {
  const point = position(event);
  send("touch", { x: point.x / point.width, y: point.y / point.height });
}

function moveStick(event, force = false) {
  const point = position(event);
  const dx = point.x - stick.x;
  const dy = stick.y - point.y;
  const distance = Math.hypot(dx, dy);
  const magnitude = Math.min(1, distance / STICK_RADIUS);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const reach = Math.min(distance, STICK_RADIUS * 1.1);
  stick.knobX = stick.x + (distance ? (dx / distance) * reach : 0);
  stick.knobY = stick.y - (distance ? (dy / distance) * reach : 0);
  const now = performance.now();
  if (force || now - lastStickSent >= STICK_INTERVAL_MS) {
    lastStickSent = now;
    send("stick", { side: stick.side, angle, magnitude });
  }
  requestDraw();
}

function setupPreviewMouse() {
  const preview = $("preview");
  preview.addEventListener("contextmenu", (event) => event.preventDefault());
  preview.addEventListener("pointerdown", (event) => {
    if (role !== "operator" || !state || stick || touching) return;
    const left = event.button === 0 && $("use-left-mouse").checked;
    const right = event.button === 2 && $("use-right-mouse").checked;
    if (!left && !right) return;
    event.preventDefault();
    capturePointer(preview, event);
    if (right && state.input.touchscreen) {
      touching = true;
      sendTouch(event);
      requestDraw();
      return;
    }
    const point = position(event);
    stick = { side: left ? "left" : "right", x: point.x, y: point.y, knobX: point.x, knobY: point.y };
    requestDraw();
  });
  preview.addEventListener("pointermove", (event) => {
    if (touching) sendTouch(event);
    else if (stick) moveStick(event);
  });
  const release = (event) => {
    if (touching) {
      touching = false;
      send("touch_release");
    } else if (stick) {
      send("stick_release", { side: stick.side });
      stick = null;
    } else {
      return;
    }
    if (preview.hasPointerCapture(event.pointerId)) preview.releasePointerCapture(event.pointerId);
    requestDraw();
  };
  preview.addEventListener("pointerup", release);
  preview.addEventListener("pointercancel", release);
}

// ---------------------------------------------------------------- キーボードの受け付け

function isTyping() {
  // 入力欄や一覧を使っている間(どこかの部品にフォーカスがある間)と、ダイアログ・画面をふさぐツールの画面の表示中
  const element = document.activeElement;
  if (window.tools && window.tools.isModalOpen()) return true;
  return dialogue !== null || (element !== null && element !== document.body);
}

function isKeyboardActive() {
  return role === "operator" && state !== null && state.input.keyboard_enabled && !isTyping();
}

function sendFocus() {
  // キーボードでの手動操作は、この画面が前面にあり、入力欄を使っていない間だけ受け付ける
  send("focus", { focused: document.hasFocus() && !isTyping() });
}

// ---------------------------------------------------------------- ダイアログ

function fieldElement(field) {
  const box = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = field.name;
  box.append(legend);
  let read = null;
  if (field.kind === "check") {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = field.value;
    input.setAttribute("aria-label", field.name);
    box.append(input);
    read = () => input.checked;
  } else if (field.kind === "entry") {
    const input = document.createElement("input");
    input.type = "text";
    input.value = field.value;
    input.setAttribute("aria-label", field.name);
    box.append(input);
    read = () => input.value;
  } else if (field.kind === "combo") {
    const select = document.createElement("select");
    select.setAttribute("aria-label", field.name);
    const options = field.options.includes(field.value) ? field.options : [field.value, ...field.options];
    select.append(...options.map((option) => new Option(option, option)));
    select.value = field.value;
    box.append(select);
    read = () => select.value;
  } else if (field.kind === "radio") {
    const group = document.createElement("div");
    group.className = "radios";
    const name = `radio-${Math.random().toString(36).slice(2)}`;
    for (const option of field.options) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = name;
      input.value = option;
      input.checked = option === field.value;
      label.append(input, ` ${option}`);
      group.append(label);
    }
    box.append(group);
    read = () => {
      const checked = group.querySelector("input:checked");
      return checked ? checked.value : field.value;
    };
  } else if (field.kind === "scale") {
    const row = document.createElement("div");
    row.className = "scale";
    const output = document.createElement("output");
    const input = document.createElement("input");
    input.type = "range";
    input.min = field.min;
    input.max = field.max;
    input.step = field.digits === 0 ? 1 : Math.pow(10, -field.digits);
    input.value = field.value;
    input.setAttribute("aria-label", field.name);
    const show = () => {
      const value = Number(input.value);
      output.textContent = field.digits === 0 ? String(Math.trunc(value)) : String(parseFloat(value.toFixed(field.digits)));
    };
    input.addEventListener("input", show);
    show();
    row.append(output, input);
    box.append(row);
    // 動かしていない場合は、初期値をそのまま返す(tkinter 版と同じ)
    let moved = false;
    input.addEventListener("input", () => (moved = true));
    read = () => (moved ? Number(input.value) : field.value);
  } else if (field.kind === "spin") {
    const input = document.createElement("input");
    input.type = "text";
    input.value = field.value;
    input.setAttribute("aria-label", field.name);
    const list = document.createElement("datalist");
    list.id = `spin-${Math.random().toString(36).slice(2)}`;
    list.append(...field.options.map((option) => new Option(option, option)));
    input.setAttribute("list", list.id);
    box.append(input, list);
    read = () => input.value;
  }
  return { element: box, read };
}

function showNextDialogue() {
  if (dialogue !== null || !dialogueQueue.length) return;
  const request = dialogueQueue.shift();
  const readers = [];
  const fields = $("dialogue-fields");
  fields.replaceChildren();
  let column = document.createElement("div");
  column.className = "dialogue-column";
  fields.append(column);
  for (const field of request.fields) {
    if (field.kind === "next") {
      column = document.createElement("div");
      column.className = "dialogue-column";
      fields.append(column);
      continue;
    }
    const { element, read } = fieldElement(field);
    column.append(element);
    if (read) readers.push(read);
  }
  $("dialogue-title").textContent = request.title;
  $("dialogue-desc").textContent = request.desc || "";
  $("dialogue-desc").hidden = !request.desc;
  $("dialogue-buttons-top").hidden = ![1, 3].includes(request.pos);
  $("dialogue-buttons-bottom").hidden = ![2, 3].includes(request.pos);
  dialogue = { id: request.id, readers };
  $("dialogue").hidden = false;
  const first = fields.querySelector("input, select");
  (first || $("dialogue-form").querySelector("button")).focus();
  sendFocus();
}

function answerDialogue(ok) {
  if (dialogue === null) return;
  send("dialogue", { id: dialogue.id, ok, values: ok ? dialogue.readers.map((read) => read()) : [] });
  closeDialogue(dialogue.id);
}

function closeDialogue(id) {
  // id が null の場合は、表示中のものを閉じる
  const index = dialogueQueue.findIndex((request) => request.id === id);
  if (index >= 0) dialogueQueue.splice(index, 1);
  if (dialogue !== null && (id === null || dialogue.id === id)) {
    dialogue = null;
    $("dialogue").hidden = true;
    sendFocus();
    showNextDialogue();
  }
}

// ---------------------------------------------------------------- 画面の部品の操作

function setup() {
  $("start").addEventListener("click", () => {
    if (state.command.state === "idle") startSelected();
    else send("stop");
  });
  $("pause").addEventListener("click", () => send(state.command.paused ? "resume" : "pause"));
  $("reload").addEventListener("click", () => send("reload"));
  $("record").addEventListener("click", () => send("record"));
  $("release-all").addEventListener("click", () => {
    // コマンドの実行中は、動きに影響することがあるので、行ってよいかを確かめる
    const running = state !== null && state.command.state !== "idle";
    const warning =
      "コマンドを実行中です。\nすべての入力を離すと、コマンドが押したままにしている入力も離れるので、実行中のコマンドの動きに影響することがあります。\n" +
      "(コマンドは止まりません。止めるには Stop を押してください)\n\nすべての入力を離しますか?";
    if (running && !window.confirm(warning)) return;
    send("release_all");
  });
  $("use-keyboard").addEventListener("change", (event) => send("keyboard", { enabled: event.target.checked }));
  $("use-controller").addEventListener("change", (event) => send("controller", { enabled: event.target.checked }));
  for (const button of document.querySelectorAll("[data-clear]")) {
    button.addEventListener("click", () => send("clear", { area: Number(button.dataset.clear) }));
  }
  for (const tab of document.querySelectorAll(".tabs button")) {
    tab.addEventListener("click", () => {
      commandType = tab.dataset.type;
      for (const other of document.querySelectorAll(".tabs button")) {
        other.setAttribute("aria-selected", String(other === tab));
      }
      render();
    });
  }
  $("shortcut-num").addEventListener("change", render);
  $("shortcut-set").addEventListener("click", () => {
    const entry = selectedCommandEntry();
    if (entry) send("shortcut", { op: "set", num: Number($("shortcut-num").value), ...entry });
  });
  $("shortcut-clear").addEventListener("click", () => send("shortcut", { op: "clear", num: Number($("shortcut-num").value) }));
  $("command-filter").addEventListener("input", render);
  $("exit-app").addEventListener("click", () => {
    const running = state && state.command.state !== "idle" ? " (実行中のコマンドは停止します)" : "";
    if (window.confirm(`Poke Controllerを終了しますか？${running}`)) send("exit");
  });
  $("command-sort").addEventListener("change", render);
  $("history-sort").addEventListener("click", () => {
    historyDescending = !historyDescending;
    render();
  });
  $("capture").addEventListener("click", () => send("tool", { op: "capture" }));
  $("open-captures").addEventListener("click", () => send("tool", { op: "open_captures" }));
  $("send-line").addEventListener("click", () => send("tool", { op: "send_image", target: "line" }));
  $("send-discord").addEventListener("click", () => send("tool", { op: "send_image", target: "discord" }));
  const list = $("command-list");
  list.addEventListener("click", (event) => {
    const item = event.target.closest("li[data-name]");
    if (item) selectCommand(item.dataset.name);
  });
  list.addEventListener("dblclick", (event) => {
    if (event.target.closest("li[data-name]")) startSelected();
  });
  list.addEventListener("keydown", (event) => {
    const items = [...list.querySelectorAll("li[data-name]")];
    const index = items.findIndex((item) => item.dataset.name === selectedCommand[commandType]);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = items[Math.min(Math.max(index + (event.key === "ArrowDown" ? 1 : -1), 0), items.length - 1)];
      if (next) {
        selectCommand(next.dataset.name);
        list.querySelector('li[aria-selected="true"]').scrollIntoView({ block: "nearest" });
      }
    } else if (event.key === "Enter") {
      startSelected();
    }
  });
  for (const area of [1, 2]) {
    const output = $(`output-${area}`);
    const run = (event) => {
      const link = event.target.closest("a[data-link]");
      if (link && role === "operator") send("link", { id: Number(link.dataset.link) });
    };
    output.addEventListener("click", run);
    output.addEventListener("keydown", (event) => {
      if (event.key === "Enter") run(event);
    });
  }
  $("dialogue-form").addEventListener("submit", (event) => {
    event.preventDefault();
    answerDialogue(true);
  });
  for (const button of document.querySelectorAll("[data-cancel]")) {
    button.addEventListener("click", () => answerDialogue(false));
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "F5" || event.key === "F6") {
      // F5: コマンドの一覧を読み込み直す / F6: 選択中のコマンドを開始する(これまでのウィンドウの画面と同じ)
      // (ページの再読み込みは、Ctrl+R でできます)
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault();
      if (role !== "operator" || state === null || dialogue !== null) return;
      // 画面をふさぐツールの画面(タグの編集など)を開いている間は、受け付けない
      if (window.tools && window.tools.isModalOpen()) return;
      if (event.key === "F5") {
        if (state.command.state === "idle") send("reload");
      } else if (state.command.state !== "idle") {
        writeOutput(Number(state.stdout_destination) || 1, false, [{ text: "Command is now working!\n", link: null }], activeOutputPage());
      } else if (commandType === "Python" || commandType === "Mcu") {
        startSelected();
      }
    } else if (event.key === "Escape" && dialogue !== null) {
      answerDialogue(false);
    } else if (event.key === "Escape" && role === "operator" && state !== null && state.command.state === "running") {
      // Esc: 実行中のコマンドを止める(これまでのウィンドウの画面と同じ)
      send("stop");
    } else if (isKeyboardActive() && !event.ctrlKey && !event.metaKey && !event.altKey && !/^(Tab|F\d+)$/.test(event.key)) {
      // キーボードでの手動操作中は、キーでページが動かないようにする(スペースや矢印キーでのスクロールなど)
      event.preventDefault();
    }
  });
  // ボタンやチェックを押した後は、フォーカスを外す(キーボードでの手動操作のキーで、ボタンが押されないように)
  document.addEventListener("click", (event) => {
    const element = event.target.closest("button, input[type=checkbox], [role=tab]");
    if (element && !element.closest("#dialogue")) element.blur();
  });
  window.addEventListener("focus", sendFocus);
  window.addEventListener("blur", sendFocus);
  document.addEventListener("focusin", sendFocus);
  document.addEventListener("focusout", () => setTimeout(sendFocus, 0));
  window.addEventListener("resize", requestDraw);
  $("stream").addEventListener("load", requestDraw);
  setupSettings();
  setupPreviewMouse();
  connect();
}

setup();
