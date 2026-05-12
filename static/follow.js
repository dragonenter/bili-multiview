/* global parseRoomIdLite */
// 关注列表：本地存储 + 后台轮询 B 站状态 + 抽屉 UI

const FOLLOW_STORAGE_KEY = "bili-mv:follow-list";
const POLL_INTERVAL_MS = 30_000;

const followDrawer = document.getElementById("follow-drawer");
const followOverlay = document.getElementById("follow-overlay");
const followBtn = document.getElementById("btn-follow");
const followClose = document.getElementById("follow-close");
const followCount = document.getElementById("follow-count");
const followSummary = document.getElementById("follow-summary-text");
const followInput = document.getElementById("follow-input");
const followAddBtn = document.getElementById("btn-follow-add");
const followListEl = document.getElementById("follow-list");
const btnLoadLive = document.getElementById("btn-load-live");
const followDot = followBtn.querySelector(".follow-dot");

// list = [{uid, room_id, uname, face, area_name}]
// status = {uid_str: {live_status, title, online, ...}}
let followList = [];
let statusMap = {};
let pollTimer = null;
let isOpen = false;

function loadList() {
    try {
        const raw = localStorage.getItem(FOLLOW_STORAGE_KEY);
        followList = raw ? JSON.parse(raw) : [];
    } catch (_) {
        followList = [];
    }
    if (!Array.isArray(followList)) followList = [];
}

function saveList() {
    localStorage.setItem(FOLLOW_STORAGE_KEY, JSON.stringify(followList));
}

function inPlayCount() {
    return followList.filter(f => statusMap[String(f.uid)]?.live_status === 1).length;
}

function updateBadge() {
    const live = inPlayCount();
    const total = followList.length;
    followCount.textContent = `${live}/${total}`;
    followSummary.textContent = `${live} / ${total} 在播`;
    if (live > 0) followDot.classList.add("is-live"); else followDot.classList.remove("is-live");
    btnLoadLive.disabled = live === 0;
}

async function pollStatus() {
    if (followList.length === 0) {
        statusMap = {};
        updateBadge();
        if (isOpen) renderList();
        return;
    }
    try {
        const uids = followList.map(f => f.uid).filter(Boolean);
        const r = await fetch("/api/status", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uids}),
        });
        if (!r.ok) return;
        statusMap = await r.json();
        updateBadge();
        if (isOpen) renderList();
        notifyJustOnline();
    } catch (e) {
        console.warn("[follow] poll failed:", e);
    }
}

let _lastLiveSet = new Set();
function notifyJustOnline() {
    const nowLive = new Set();
    Object.entries(statusMap).forEach(([uid, s]) => {
        if (s.live_status === 1) nowLive.add(uid);
    });
    if (_lastLiveSet.size > 0 && "Notification" in window && Notification.permission === "granted") {
        for (const uid of nowLive) {
            if (!_lastLiveSet.has(uid)) {
                const f = followList.find(x => String(x.uid) === uid);
                const s = statusMap[uid];
                if (f && s) {
                    new Notification(`${f.uname} 开播了`, {
                        body: s.title || "",
                        icon: f.face || undefined,
                    });
                }
            }
        }
    }
    _lastLiveSet = nowLive;
}

function startPolling() {
    if (pollTimer) return;
    pollStatus();
    pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}
function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function fmtOnline(n) {
    if (!n) return "";
    if (n < 10000) return String(n);
    return (n / 10000).toFixed(n < 100000 ? 1 : 0) + "万";
}

function renderList() {
    followListEl.innerHTML = "";
    if (followList.length === 0) {
        const empty = document.createElement("div");
        empty.className = "follow-empty";
        empty.textContent = "还没有关注的主播，粘贴链接添加 👆";
        followListEl.appendChild(empty);
        return;
    }
    // 在播在前，未播在后
    const sorted = [...followList].sort((a, b) => {
        const la = statusMap[String(a.uid)]?.live_status === 1 ? 1 : 0;
        const lb = statusMap[String(b.uid)]?.live_status === 1 ? 1 : 0;
        return lb - la;
    });
    let liveHeaderAdded = false;
    let offHeaderAdded = false;
    for (const f of sorted) {
        const s = statusMap[String(f.uid)];
        const isLive = s?.live_status === 1;
        if (isLive && !liveHeaderAdded) {
            const h = document.createElement("div");
            h.className = "follow-section-head live";
            h.textContent = `在播 (${inPlayCount()})`;
            followListEl.appendChild(h);
            liveHeaderAdded = true;
        }
        if (!isLive && !offHeaderAdded) {
            const h = document.createElement("div");
            h.className = "follow-section-head off";
            h.textContent = `未播 (${followList.length - inPlayCount()})`;
            followListEl.appendChild(h);
            offHeaderAdded = true;
        }
        followListEl.appendChild(renderItem(f, s, isLive));
    }
}

function renderItem(f, s, isLive) {
    const el = document.createElement("div");
    el.className = "follow-item" + (isLive ? " is-live" : " is-off");

    const face = document.createElement("img");
    face.className = "follow-face";
    if (f.face) face.src = f.face + (f.face.includes("?") ? "" : "@80w_80h.webp");
    face.referrerPolicy = "no-referrer";
    face.alt = "";
    el.appendChild(face);

    const meta = document.createElement("div");
    meta.className = "follow-meta";
    const uname = document.createElement("div");
    uname.className = "follow-uname";
    uname.textContent = f.uname || `房间 ${f.room_id}`;
    meta.appendChild(uname);
    const sub = document.createElement("div");
    sub.className = "follow-sub";
    if (isLive) {
        sub.textContent = `${s.title || ""}`;
    } else {
        sub.textContent = "未开播";
    }
    meta.appendChild(sub);
    if (isLive) {
        const stats = document.createElement("div");
        stats.className = "follow-stats";
        const o = fmtOnline(s.online);
        stats.textContent = (o ? `${o} 在看` : "") + (s.area_v2_name || s.area_v2_parent_name ? ` · ${s.area_v2_name || s.area_v2_parent_name}` : "");
        meta.appendChild(stats);
    }
    el.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "follow-actions";
    if (isLive) {
        const addBtn = document.createElement("button");
        addBtn.className = "btn-primary-sm";
        addBtn.textContent = "加入观看";
        addBtn.onclick = () => addToWatch(f.room_id);
        actions.appendChild(addBtn);
    }
    const delBtn = document.createElement("button");
    delBtn.className = "icon-btn-sm";
    delBtn.title = "取消关注";
    delBtn.textContent = "✕";
    delBtn.onclick = () => removeFollow(f.uid);
    actions.appendChild(delBtn);
    el.appendChild(actions);

    return el;
}

// 把指定 room_id 追加到顶部 textarea（去重，9 路上限）
function addToWatch(roomId) {
    const urlsEl = document.getElementById("urls");
    const lines = urlsEl.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (lines.includes(String(roomId))) {
        urlsEl.value = lines.join("\n");
    } else {
        if (lines.length >= 9) {
            alert("已达 9 路上限，先清空或移除几路再加");
            return;
        }
        lines.push(String(roomId));
        urlsEl.value = lines.join("\n");
    }
}

function loadAllLive() {
    const live = followList.filter(f => statusMap[String(f.uid)]?.live_status === 1);
    if (live.length === 0) return;
    const ids = live.slice(0, 9).map(f => f.room_id);
    document.getElementById("urls").value = ids.join("\n");
    document.getElementById("btn-start").click();
    closeDrawer();
}

async function addFollow(input) {
    const text = (input || "").trim();
    if (!text) return;
    followAddBtn.disabled = true;
    followAddBtn.textContent = "查询中…";
    try {
        const r = await fetch(`/api/room?room_id=${encodeURIComponent(text)}`);
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            alert(err.detail || "无法识别该房间号");
            return;
        }
        const meta = await r.json();
        if (!meta.uid) {
            alert("拿不到主播 UID，无法加入关注");
            return;
        }
        if (followList.some(f => f.uid === meta.uid)) {
            alert(`已关注：${meta.uname}`);
            return;
        }
        followList.push({
            uid: meta.uid,
            room_id: meta.real_room_id || meta.room_id,
            uname: meta.uname || `用户 ${meta.uid}`,
            face: meta.face || "",
            area_name: meta.area_name || "",
        });
        saveList();
        followInput.value = "";
        await pollStatus();
        // 请求通知权限（首次添加时）
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }
    } catch (e) {
        alert("添加失败：" + e.message);
    } finally {
        followAddBtn.disabled = false;
        followAddBtn.textContent = "添加";
    }
}

function removeFollow(uid) {
    followList = followList.filter(f => f.uid !== uid);
    saveList();
    pollStatus();
}

function openDrawer() {
    isOpen = true;
    followDrawer.hidden = false;
    followOverlay.hidden = false;
    requestAnimationFrame(() => {
        followDrawer.classList.add("is-open");
        followOverlay.classList.add("is-open");
    });
    renderList();
    pollStatus();
}
function closeDrawer() {
    isOpen = false;
    followDrawer.classList.remove("is-open");
    followOverlay.classList.remove("is-open");
    setTimeout(() => {
        followDrawer.hidden = true;
        followOverlay.hidden = true;
    }, 280);
}

// 事件绑定
followBtn.addEventListener("click", () => isOpen ? closeDrawer() : openDrawer());
followClose.addEventListener("click", closeDrawer);
followOverlay.addEventListener("click", closeDrawer);
followAddBtn.addEventListener("click", () => addFollow(followInput.value));
followInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addFollow(followInput.value); }
});
btnLoadLive.addEventListener("click", loadAllLive);

// 初始化
loadList();
updateBadge();
startPolling();  // 始终轮询，即使抽屉关闭也保持 badge 实时

window.__followApi = { addFollow, removeFollow, loadList: () => followList };
