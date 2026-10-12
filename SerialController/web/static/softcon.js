"use strict";
// Software-Controller(画面上のコントローラー)。
// レイアウト(図形と部品)はサーバーから受け取り、ここでは描画と、押した・離した・固定したことの知らせだけを行う。
// 操作の決まりは、これまでのウィンドウの画面(ControllerLayouts.py)と同じ:
// - 左クリック: 押している間だけ入力する。HOLD がオン、または Shift を押しながら離すと、押しっぱなしで固定する
// - 右クリック(スティックは右ドラッグ): 押しっぱなしで固定する。固定中のボタンをもう一度押すと解除する
// - HOLD ボタン: HOLD のオン・オフ。黄色のときに押すと、オフにして固定をすべて解除する

// canvas: 描く先、action: サーバーに送る操作の名前("pad": Software-Controller / "pad2": Controller Simulator)
function createPad(canvas, action) {
  const context = canvas.getContext("2d");
  // スティック・タッチの位置を送る間隔(ms)と、タッチ画面の画像を描き直す間隔(ms)
  const SEND_INTERVAL_MS = 40;
  const TOUCH_IMAGE_INTERVAL_MS = 66;
  // フォントの大きさ(pt)を px にする倍率
  const POINT_TO_PX = 96 / 72;

  let layout = null;
  let layoutJson = "";
  let enabled = false;
  // タグ -> 今の色(図形 / 文字)。無いタグは、レイアウトの色のまま
  let shapeFills = {};
  let textFills = {};
  let holdMode = false;
  let locked = new Set();
  let lockedSticks = new Set();
  // 押している入力: {kind: "button" / "stick" / "stick_lock" / "touch", tag}
  let active = null;
  let tilted = {};
  let touchMark = null;
  let lastSent = 0;
  let pending = null;
  let touchTimer = null;

  function pad(op, data = {}) {
    send(action, { op, ...data });
  }

  // 位置を続けて送る操作は、間隔を空けて送る(最後の位置は必ず送る)
  function padThrottled(op, data) {
    const now = performance.now();
    if (now - lastSent >= SEND_INTERVAL_MS) {
      lastSent = now;
      pending = null;
      pad(op, data);
    } else {
      pending = { op, data };
    }
  }

  function flushPending() {
    if (pending !== null) {
      pad(pending.op, pending.data);
      pending = null;
    }
  }

  function reset() {
    shapeFills = {};
    textFills = {};
    holdMode = false;
    locked = new Set();
    lockedSticks = new Set();
    active = null;
    tilted = {};
    touchMark = null;
    pending = null;
  }

  function setLayout(newLayout, operator) {
    const json = JSON.stringify(newLayout);
    if (json !== layoutJson || (enabled && !operator)) {
      // レイアウトが変わった / 操作できなくなった: サーバー側で入力はすべて離されている
      layoutJson = json;
      layout = JSON.parse(json);
      reset();
      if (touchTimer !== null) clearInterval(touchTimer);
      touchTimer = layout && layout.touch ? setInterval(draw, TOUCH_IMAGE_INTERVAL_MS) : null;
    }
    enabled = operator;
    canvas.style.opacity = enabled ? "1" : "0.6";
    draw();
  }

  // ---------------------------------------------------------------- 描画

  function mainTag(shape) {
    return shape.tags.length ? shape.tags[0] : null;
  }

  function fillOf(shape) {
    const tag = mainTag(shape);
    if (tag !== null) {
      if (shape.tags.includes(`${tag}:shape`) && shapeFills[tag]) return shapeFills[tag];
      if (shape.tags.includes(`${tag}:text`) && textFills[tag]) return textFills[tag];
    }
    return shape.fill;
  }

  function drawTouchImage(shape) {
    // タッチスクリーンの範囲のカメラ画像(プレビューの映像から切り出す)。描けた場合は true
    const image = document.getElementById("stream");
    const ratio = state && state.input.touchscreen_ratio;
    if (!ratio || !image.naturalWidth) return false;
    const [width, height] = layout.touch.size;
    const sx = ratio[0] * image.naturalWidth;
    const sy = ratio[1] * image.naturalHeight;
    const sw = (ratio[2] - ratio[0]) * image.naturalWidth;
    const sh = (ratio[3] - ratio[1]) * image.naturalHeight;
    if (sw <= 0 || sh <= 0) return false;
    try {
      context.drawImage(image, sx, sy, sw, sh, shape.coords[0], shape.coords[1], width, height);
    } catch (error) {
      return false;
    }
    return true;
  }

  function draw() {
    if (!layout) return;
    const scale = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(layout.width * scale) || canvas.height !== Math.round(layout.height * scale)) {
      canvas.width = Math.round(layout.width * scale);
      canvas.height = Math.round(layout.height * scale);
    }
    canvas.style.width = `${layout.width}px`;
    canvas.style.height = `${layout.height}px`;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.fillStyle = layout.background;
    context.fillRect(0, 0, layout.width, layout.height);
    let hasTouchImage = false;
    layout.shapes.forEach((shape, index) => {
      const c = shape.coords;
      const fill = fillOf(shape);
      if (shape.type === "image") {
        hasTouchImage = drawTouchImage(shape);
        return;
      }
      if (shape.type === "text") {
        let text = shape.text;
        let x = c[0];
        let y = c[1];
        let color = fill;
        context.textAlign = "center";
        context.textBaseline = "middle";
        if (layout.touch && index === layout.touch.text) {
          if (touchMark !== null) {
            // タッチ中は、座標を左上に表示する
            text = `(${touchMark.x}, ${touchMark.y})`;
            x = layout.touch.origin[0] + 6;
            y = layout.touch.origin[1] + 4;
            color = layout.colors.touch_mark;
            context.textAlign = "left";
            context.textBaseline = "top";
          } else if (hasTouchImage) {
            // カメラ画像の表示中は「Touch Screen」の文字を出さない
            return;
          }
        }
        context.font = `bold ${(shape.font_size || 9) * POINT_TO_PX}px "Segoe UI", "Yu Gothic UI", sans-serif`;
        context.fillStyle = color || "#ffffff";
        context.fillText(text, x, y);
        return;
      }
      context.beginPath();
      if (shape.type === "rect") {
        context.rect(c[0], c[1], c[2] - c[0], c[3] - c[1]);
      } else if (shape.type === "roundrect") {
        context.roundRect(c[0], c[1], c[2] - c[0], c[3] - c[1], shape.radius);
      } else if (shape.type === "oval") {
        context.ellipse((c[0] + c[2]) / 2, (c[1] + c[3]) / 2, (c[2] - c[0]) / 2, (c[3] - c[1]) / 2, 0, 0, Math.PI * 2);
      } else if (shape.type === "polygon") {
        context.moveTo(c[0], c[1]);
        for (let i = 2; i < c.length; i += 2) context.lineTo(c[i], c[i + 1]);
        context.closePath();
      }
      if (fill) {
        context.fillStyle = fill;
        context.fill();
      }
      if (shape.outline) {
        context.strokeStyle = shape.outline;
        context.stroke();
      }
    });
    if (touchMark !== null) {
      context.lineWidth = 2;
      context.strokeStyle = layout.colors.touch_mark;
      context.beginPath();
      context.arc(touchMark.px, touchMark.py, 5, 0, Math.PI * 2);
      context.stroke();
    }
  }

  function setColor(tag, fill, textFill) {
    shapeFills[tag] = fill;
    if (textFill) textFills[tag] = textFill;
  }

  function restoreColor(tag) {
    delete shapeFills[tag];
    delete textFills[tag];
  }

  // ---------------------------------------------------------------- 押しっぱなしの固定

  function hasLocks() {
    return locked.size > 0 || lockedSticks.size > 0;
  }

  function updateHoldButton() {
    if (!layout.hold) return;
    if (holdMode || hasLocks()) setColor("hold_toggle", layout.colors.lock, layout.colors.lock_text);
    else restoreColor("hold_toggle");
  }

  function lock(tag) {
    if (layout.buttons[tag].kind === "hat") {
      // 十字キーは1方向しか入力できないので、固定中の十字キーは解除する
      for (const other of [...locked]) {
        if (layout.buttons[other].kind === "hat") unlock(other);
      }
    }
    locked.add(tag);
    setColor(tag, layout.colors.lock, layout.colors.lock_text);
    pad("hold", { tag });
    updateHoldButton();
  }

  function unlock(tag) {
    locked.delete(tag);
    restoreColor(tag);
    pad("hold_end", { tag });
    updateHoldButton();
  }

  function moveKnob(tag, dx, dy) {
    const info = layout.sticks[tag];
    const [cx, cy] = info.center;
    const r = info.knob_radius;
    layout.shapes[info.knob].coords = [cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r];
    if (info.label !== null) layout.shapes[info.label].coords = [cx + dx, cy + dy];
  }

  function lockStick(tag) {
    // 倒したままにする(つまみもその位置に残す)
    flushPending();
    lockedSticks.add(tag);
    setColor(tag, layout.colors.lock, layout.colors.lock_text);
    updateHoldButton();
  }

  function releaseStick(tag) {
    pending = null;
    lockedSticks.delete(tag);
    tilted[tag] = false;
    moveKnob(tag, 0, 0);
    restoreColor(tag);
    pad("center", { tag });
    updateHoldButton();
  }

  function releaseAll() {
    for (const tag of [...locked]) unlock(tag);
    for (const tag of [...lockedSticks]) releaseStick(tag);
  }

  function toggleHold() {
    // 黄色(HOLD がオン、または固定中の入力がある)なら、オフにして全て解除する
    holdMode = !(holdMode || hasLocks());
    if (!holdMode) releaseAll();
    updateHoldButton();
  }

  // ---------------------------------------------------------------- 入力

  function tilt(tag, point, force) {
    const info = layout.sticks[tag];
    let dx = point.x - info.center[0];
    let dy = point.y - info.center[1];
    let distance = Math.hypot(dx, dy);
    if (distance > info.range) {
      dx = (dx * info.range) / distance;
      dy = (dy * info.range) / distance;
      distance = info.range;
    }
    moveKnob(tag, dx, dy);
    const magnitude = distance / info.range;
    tilted[tag] = magnitude >= layout.stick_deadzone;
    // 画面の y は下が正なので反転する
    const data = { tag, angle: (Math.atan2(-dy, dx) * 180) / Math.PI, magnitude };
    if (force) {
      lastSent = performance.now();
      pending = null;
      pad("tilt", data);
    } else {
      padThrottled("tilt", data);
    }
  }

  function touch(point, force) {
    const [ox, oy] = layout.touch.origin;
    const [width, height] = layout.touch.size;
    const [touchWidth, touchHeight] = layout.touch_size;
    // 表示上の位置(画面内に収める)
    const dx = Math.min(Math.max(point.x - ox, 0), width);
    const dy = Math.min(Math.max(point.y - oy, 0), height);
    // 送る座標(320x240)に換算する。(0, 0) は離した状態を表すので、1以上の座標にする
    const x = Math.min(Math.max(Math.round((dx * touchWidth) / width), 1), touchWidth);
    const y = Math.min(Math.max(Math.round((dy * touchHeight) / height), 1), touchHeight);
    touchMark = { px: ox + dx, py: oy + dy, x, y };
    if (force) {
      lastSent = performance.now();
      pending = null;
      pad("touch", { x, y });
    } else {
      padThrottled("touch", { x, y });
    }
  }

  function contains(shape, x, y) {
    const c = shape.coords;
    if (shape.type === "oval") {
      const rx = (c[2] - c[0]) / 2;
      const ry = (c[3] - c[1]) / 2;
      return ((x - (c[0] + c[2]) / 2) / rx) ** 2 + ((y - (c[1] + c[3]) / 2) / ry) ** 2 <= 1;
    }
    if (shape.type === "rect" || shape.type === "roundrect") {
      return c[0] <= x && x <= c[2] && c[1] <= y && y <= c[3];
    }
    if (shape.type === "image") {
      const [width, height] = layout.touch.size;
      return c[0] <= x && x <= c[0] + width && c[1] <= y && y <= c[1] + height;
    }
    return false;
  }

  // その位置にある部品: {kind: "button" / "stick" / "touch" / "hold", tag}(無ければ null)
  function hit(point) {
    for (let i = layout.shapes.length - 1; i >= 0; i--) {
      const shape = layout.shapes[i];
      const tag = mainTag(shape);
      if (tag === null || !contains(shape, point.x, point.y)) continue;
      if (tag in layout.buttons) return { kind: "button", tag };
      if (tag in layout.sticks) return { kind: "stick", tag };
      if (tag === "touch") return { kind: "touch", tag };
      if (tag === "hold_toggle") return { kind: "hold", tag };
    }
    return null;
  }

  function position(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) * layout.width) / rect.width,
      y: ((event.clientY - rect.top) * layout.height) / rect.height,
    };
  }

  function onLeftPress(target, point) {
    if (target.kind === "hold") {
      toggleHold();
    } else if (target.kind === "button") {
      if (locked.has(target.tag)) {
        // 固定中のボタンをもう一度押したら解除する
        unlock(target.tag);
        return;
      }
      active = { kind: "button", tag: target.tag };
      setColor(target.tag, layout.colors.active, layout.colors.button_text);
      pad("press", { tag: target.tag });
    } else if (target.kind === "stick") {
      // 固定中のスティックは、押し直したら通常の操作に戻す
      lockedSticks.delete(target.tag);
      updateHoldButton();
      active = { kind: "stick", tag: target.tag };
      setColor(target.tag, layout.colors.active, layout.colors.button_text);
      tilt(target.tag, point, true);
    } else if (target.kind === "touch") {
      active = { kind: "touch", tag: "touch" };
      touch(point, true);
    }
  }

  function onRightPress(target, point) {
    if (!layout.hold) return;
    if (target.kind === "button") {
      if (locked.has(target.tag)) unlock(target.tag);
      else lock(target.tag);
    } else if (target.kind === "stick") {
      // 右ドラッグ: 離した位置で固定する
      lockedSticks.delete(target.tag);
      active = { kind: "stick_lock", tag: target.tag };
      setColor(target.tag, layout.colors.active, layout.colors.button_text);
      tilt(target.tag, point, true);
    }
  }

  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  canvas.addEventListener("pointerdown", (event) => {
    if (!enabled || !layout || active !== null || (event.button !== 0 && event.button !== 2)) return;
    event.preventDefault();
    const point = position(event);
    const target = hit(point);
    if (target === null) return;
    if (event.button === 0) onLeftPress(target, point);
    else onRightPress(target, point);
    if (active !== null) capturePointer(canvas, event);
    draw();
  });

  canvas.addEventListener("pointermove", (event) => {
    if (active === null) return;
    if (active.kind === "stick" || active.kind === "stick_lock") tilt(active.tag, position(event), false);
    else if (active.kind === "touch") touch(position(event), false);
    else return;
    draw();
  });

  function onRelease(event, cancelled) {
    if (active === null) return;
    const { kind, tag } = active;
    // 右ドラッグ中は右ボタン、それ以外は左ボタンを離したときに処理する
    if (!cancelled && event.button !== (kind === "stick_lock" ? 2 : 0)) return;
    active = null;
    const shouldLock = !cancelled && layout.hold && (holdMode || event.shiftKey);
    if (kind === "stick_lock") {
      if (tilted[tag] && !cancelled) lockStick(tag);
      else releaseStick(tag);
    } else if (kind === "button") {
      if (shouldLock) {
        lock(tag);
      } else {
        restoreColor(tag);
        pad("release", { tag });
      }
    } else if (kind === "stick") {
      if (shouldLock && tilted[tag]) lockStick(tag);
      else releaseStick(tag);
    } else if (kind === "touch") {
      pending = null;
      touchMark = null;
      pad("touch_end");
    }
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    draw();
  }

  canvas.addEventListener("pointerup", (event) => onRelease(event, false));
  canvas.addEventListener("pointercancel", (event) => onRelease(event, true));
  // 送っていない最後の位置を送る
  setInterval(() => {
    if (pending !== null && performance.now() - lastSent >= SEND_INTERVAL_MS) {
      lastSent = performance.now();
      flushPending();
    }
  }, SEND_INTERVAL_MS);

  return { setLayout, draw };
}

window.softcon = createPad(document.getElementById("softcon"), "pad");

// Controller Simulator: 大きいレイアウトのコントローラーを、別の枠に表示する
window.simulator = (function () {
  const viewer = document.getElementById("simulator");
  const select = document.getElementById("simulator-layout");
  const pad = createPad(document.getElementById("simulator-canvas"), "pad2");

  function render(operator) {
    if (viewer.hidden || !state) return;
    const names = state.simulator.layouts;
    if (select.options.length !== names.length) select.replaceChildren(...names.map((name) => new Option(name, name)));
    if (document.activeElement !== select) select.value = state.simulator.layout.name;
    select.disabled = !operator;
    pad.setLayout(state.simulator.layout, operator);
  }

  function open() {
    viewer.hidden = false;
    render(role === "operator");
  }

  function close() {
    // 閉じるときは、押したまま・固定中の入力を離す
    send("pad2", { op: "release_all" });
    viewer.hidden = true;
  }

  select.addEventListener("change", () => {
    send("setting", { name: "controller_layout", value: select.value });
    select.blur();
  });
  document.getElementById("simulator-close").addEventListener("click", close);
  return { open, close, render };
})();
