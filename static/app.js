/* global Player */

const stage = document.getElementById("stage");
const btnStart = document.getElementById("btn-start");
const btnClear = document.getElementById("btn-clear");
const btnExitFocus = document.getElementById("btn-exit-focus");
const urlsEl = document.getElementById("urls");

// 画质策略：多路网格态用 150 省带宽 / 单路时全屏用 250；
// 焦点态焦点路 10000，侧栏 80
const QN_GRID_MULTI = 150;
const QN_GRID_SOLO = 250;
const QN_FOCUS_MAIN = 10000;
const QN_FOCUS_OTHER = 80;
const MAX_STREAMS = 9;

let players = [];
let focusedIdx = -1;

function gridQn() {
    return players.length <= 1 ? QN_GRID_SOLO : QN_GRID_MULTI;
}

function parseLines(text) {
    return text.split(/\r?\n/).map(s => s.trim()).filter(Boolean).slice(0, MAX_STREAMS);
}

function clearStage() {
    players.forEach(p => p.destroy());
    players = [];
    focusedIdx = -1;
    stage.className = "grid empty";
    stage.innerHTML = `
        <div class="empty-hint">
            <div class="logo"></div>
            <h2>同屏看多路 B 站直播</h2>
            <p>把直播链接或房间号粘到上方输入框，每行一个，点 <span class="kbd">开始观看</span>。<br/>单击任一路放大并自动升原画。</p>
            <div class="shortcuts">
                <span><span class="kbd">1</span>–<span class="kbd">9</span> 切焦点</span>
                <span><span class="kbd">←</span><span class="kbd">→</span> 上/下一路</span>
                <span><span class="kbd">F</span> 全屏</span>
                <span><span class="kbd">M</span> 静音</span>
                <span><span class="kbd">Esc</span> 退出</span>
            </div>
        </div>`;
    btnExitFocus.hidden = true;
}

function renderGrid() {
    stage.className = `grid count-${players.length}`;
    stage.innerHTML = "";
    players.forEach((p) => {
        const tile = document.createElement("div");
        stage.appendChild(tile);
        p.mount(tile);
        p.onClick = () => enterFocus(players.indexOf(p));
        p.setMuted(true);  // 网格态全静音
        p.load();
    });
    btnExitFocus.hidden = true;
}

// 切焦点：保留 container DOM 节点，仅 reparent，避免销毁正在播放的 video 元素
function enterFocus(idx) {
    if (idx < 0 || idx >= players.length) return;
    focusedIdx = idx;

    const containers = players.map(p => p.container);

    stage.className = "focus";
    stage.innerHTML = "";

    const sidebar = document.createElement("div");
    sidebar.className = "sidebar";

    players.forEach((p, i) => {
        const c = containers[i];
        if (i === idx) {
            c.classList.add("is-focus");
            stage.appendChild(c);
            p.onClick = null;
        } else {
            c.classList.remove("is-focus");
            sidebar.appendChild(c);
            p.onClick = () => enterFocus(players.indexOf(p));
        }
    });

    stage.appendChild(sidebar);

    players.forEach((p, i) => {
        const target = (i === idx) ? QN_FOCUS_MAIN : QN_FOCUS_OTHER;
        p.switchQuality(target);
        p.setMuted(i !== idx);  // 焦点路出声，其他静音
    });

    btnExitFocus.hidden = false;
}

function exitFocus() {
    if (focusedIdx === -1) return;
    focusedIdx = -1;

    // 退全屏
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});

    const containers = players.map(p => p.container);

    stage.className = `grid count-${players.length}`;
    stage.innerHTML = "";

    players.forEach((p, i) => {
        const c = containers[i];
        c.classList.remove("is-focus");
        stage.appendChild(c);
        p.onClick = () => enterFocus(players.indexOf(p));
    });

    const qn = gridQn();
    players.forEach(p => { p.switchQuality(qn); p.setMuted(true); });
    btnExitFocus.hidden = true;
}

async function startWatch() {
    const inputs = parseLines(urlsEl.value);
    if (inputs.length === 0) {
        alert("请至少输入一个直播链接或房间号");
        return;
    }
    clearStage();
    players = inputs.map(input => new Player(input, gridQn()));
    renderGrid();
}

// ============ 键盘快捷键 ============
function isTypingInInput(e) {
    const t = e.target;
    return t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.isContentEditable);
}

document.addEventListener("keydown", (e) => {
    if (isTypingInInput(e)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (players.length === 0) return;

    // 1-9: 直接切焦点
    if (e.key >= "1" && e.key <= "9") {
        const n = parseInt(e.key, 10);
        if (n <= players.length) {
            e.preventDefault();
            enterFocus(n - 1);
        }
        return;
    }

    switch (e.key) {
        case "Escape":
            if (document.fullscreenElement) {
                document.exitFullscreen().catch(() => {});
            } else if (focusedIdx !== -1) {
                exitFocus();
            }
            e.preventDefault();
            break;
        case "f": case "F":
            if (focusedIdx !== -1) {
                const c = players[focusedIdx].container;
                if (!document.fullscreenElement) c.requestFullscreen().catch(() => {});
                else document.exitFullscreen().catch(() => {});
                e.preventDefault();
            }
            break;
        case "m": case "M":
            if (focusedIdx !== -1) {
                players[focusedIdx].toggleMuted();
                e.preventDefault();
            }
            break;
        case "ArrowRight":
            if (focusedIdx !== -1 && players.length > 1) {
                const next = (focusedIdx + 1) % players.length;
                enterFocus(next);
                e.preventDefault();
            }
            break;
        case "ArrowLeft":
            if (focusedIdx !== -1 && players.length > 1) {
                const prev = (focusedIdx - 1 + players.length) % players.length;
                enterFocus(prev);
                e.preventDefault();
            }
            break;
    }
});

btnStart.addEventListener("click", startWatch);
btnClear.addEventListener("click", () => { urlsEl.value = ""; clearStage(); });
btnExitFocus.addEventListener("click", exitFocus);
