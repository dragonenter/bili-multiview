/* global Player */

const stage = document.getElementById("stage");
const btnStart = document.getElementById("btn-start");
const btnClear = document.getElementById("btn-clear");
const btnExitFocus = document.getElementById("btn-exit-focus");
const urlsEl = document.getElementById("urls");

const QN_GRID = 250;       // 网格态默认超清
const QN_FOCUS_MAIN = 10000;
const QN_FOCUS_OTHER = 80;
const MAX_STREAMS = 9;

let players = [];          // Player[]
let focusedIdx = -1;       // -1 表示网格态

function parseLines(text) {
    return text.split(/\r?\n/).map(s => s.trim()).filter(Boolean).slice(0, MAX_STREAMS);
}

function clearStage() {
    players.forEach(p => p.destroy());
    players = [];
    focusedIdx = -1;
    stage.className = "grid";
    stage.innerHTML = "";
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
        p.load();
    });
    btnExitFocus.hidden = true;
}

// 切焦点：保留 player 的 container DOM 节点，只重新 parent，避免销毁正在播放的 video 元素。
// 然后只对画质变化的 player 触发 switchQuality（其内部会 remount + reload）。
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
    });

    btnExitFocus.hidden = false;
}

function exitFocus() {
    if (focusedIdx === -1) return;
    focusedIdx = -1;

    const containers = players.map(p => p.container);

    stage.className = `grid count-${players.length}`;
    stage.innerHTML = "";

    players.forEach((p, i) => {
        const c = containers[i];
        c.classList.remove("is-focus");
        stage.appendChild(c);
        p.onClick = () => enterFocus(players.indexOf(p));
    });

    players.forEach(p => p.switchQuality(QN_GRID));
    btnExitFocus.hidden = true;
}

async function startWatch() {
    const inputs = parseLines(urlsEl.value);
    if (inputs.length === 0) {
        alert("请至少输入一个直播链接或房间号");
        return;
    }
    clearStage();
    players = inputs.map(input => new Player(input, QN_GRID));
    renderGrid();
}

btnStart.addEventListener("click", startWatch);
btnClear.addEventListener("click", () => { urlsEl.value = ""; clearStage(); });
btnExitFocus.addEventListener("click", exitFocus);
