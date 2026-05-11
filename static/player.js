/* global flvjs */
const QN_LABEL = {
    80: "流畅", 150: "高清", 250: "超清", 400: "蓝光", 10000: "原画"
};

// 按短边像素分级；返回 [显示文本, 等级 class]
function resolutionTier(w, h) {
    if (!w || !h) return ["", ""];
    const short = Math.min(w, h);
    let tier;
    if (short >= 2160) tier = "tier-4k";
    else if (short >= 1440) tier = "tier-2k";
    else if (short >= 1080) tier = "tier-1080";
    else if (short >= 720) tier = "tier-720";
    else tier = "tier-low";
    return [`${w}×${h}`, tier];
}

class Player {
    constructor(roomInput, initialQn = 250) {
        this.roomInput = roomInput;
        this.qn = initialQn;
        this.realRoomId = null;
        this.title = "";
        this.uname = "";
        this.flvPlayer = null;
        this.videoEl = null;
        this.container = null;
        this.label = null;
        this.qnBadge = null;
        this.resBadge = null;
        this.muteBadge = null;
        this.onClick = null;
        this._reconnectCount = 0;
        this._reconnectTimer = null;
        this._destroyed = false;
    }

    mount(container) {
        this.container = container;
        container.classList.add("tile", "is-loading");
        container.classList.remove("is-error", "is-offline", "is-focus");
        container.innerHTML = "";

        this.videoEl = document.createElement("video");
        this.videoEl.muted = true;
        this.videoEl.autoplay = true;
        this.videoEl.playsInline = true;
        this.videoEl.addEventListener("playing", () => {
            if (this.container) this.container.classList.remove("is-loading");
            this._reconnectCount = 0;  // 重置重连计数
        });
        this.videoEl.addEventListener("loadedmetadata", () => this._updateResolution());
        this.videoEl.addEventListener("resize", () => this._updateResolution());
        container.appendChild(this.videoEl);

        this.label = document.createElement("div");
        this.label.className = "tile-label";
        this.label.textContent = `加载中 (${this.roomInput})`;
        container.appendChild(this.label);

        this.qnBadge = document.createElement("div");
        this.qnBadge.className = "tile-qn";
        this.qnBadge.textContent = QN_LABEL[this.qn] || `qn=${this.qn}`;
        container.appendChild(this.qnBadge);

        this.resBadge = document.createElement("div");
        this.resBadge.className = "tile-res";
        container.appendChild(this.resBadge);

        this.muteBadge = document.createElement("div");
        this.muteBadge.className = "tile-mute";
        this.muteBadge.title = "静音中";
        container.appendChild(this.muteBadge);
        this._updateMuteBadge();

        container.addEventListener("click", () => {
            if (this.onClick) this.onClick(this);
        });
    }

    async load() {
        if (this._destroyed) return;
        try {
            const params = new URLSearchParams({
                room_id: this.roomInput,
                qn: String(this.qn),
            });
            const r = await fetch(`/api/stream?${params}`);
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                this._showPlaceholder(
                    r.status === 503 ? "主播未开播" : (err.detail || `加载失败 (${r.status})`),
                    r.status === 503 ? "is-offline" : "is-error",
                );
                return;
            }
            const info = await r.json();
            this.realRoomId = info.real_room_id;
            this.title = info.title;
            this.uname = info.uname;
            this.qn = info.qn;
            if (this.label) this.label.textContent = `${this.uname} · ${this.title}`;
            if (this.qnBadge) this.qnBadge.textContent = QN_LABEL[this.qn] || `qn=${this.qn}`;
            this._attachFlv(info.stream_url);
        } catch (e) {
            this._showPlaceholder(`错误: ${e.message}`, "is-error");
        }
    }

    _attachFlv(streamUrl) {
        if (!window.flvjs || !flvjs.isSupported()) {
            this._showPlaceholder("浏览器不支持 flv.js", "is-error");
            return;
        }
        this._destroyFlv();
        if (!this.videoEl) return;
        const player = flvjs.createPlayer({
            type: "flv",
            url: streamUrl,
            isLive: true,
            hasAudio: true,
            hasVideo: true,
        }, {
            enableWorker: false,
            enableStashBuffer: false,
            stashInitialSize: 128,
        });
        player.attachMediaElement(this.videoEl);
        player.on(flvjs.Events.ERROR, (errType, errDetail) => {
            console.warn(`[Player ${this.roomInput}] flv error:`, errType, errDetail);
            this._scheduleReconnect();
        });
        player.load();
        player.play().catch(() => { /* autoplay 静音重试 */ });
        this.flvPlayer = player;
    }

    // 流断了 / CDN expires 过期 → 指数退避重连
    _scheduleReconnect() {
        if (this._destroyed || this._reconnectTimer) return;
        const delay = Math.min(3000 * Math.pow(2, this._reconnectCount), 30000);
        this._reconnectCount += 1;
        if (this.container) this.container.classList.add("is-loading");
        if (this.label) this.label.textContent = `重连中…(${this._reconnectCount}) ${this.uname || this.roomInput}`;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            if (this._destroyed) return;
            this.load();  // 重新拉 stream URL（CDN 地址会刷新）+ reattach flv
        }, delay);
    }

    async switchQuality(newQn) {
        if (newQn === this.qn) return;
        const wasMuted = this.videoEl ? this.videoEl.muted : true;
        this.qn = newQn;
        if (this.qnBadge) this.qnBadge.textContent = QN_LABEL[newQn] || `qn=${newQn}`;
        if (this.container) this.mount(this.container);
        if (this.videoEl) this.videoEl.muted = wasMuted;
        this._updateMuteBadge();
        await this.load();
    }

    setMuted(muted) {
        if (this.videoEl) this.videoEl.muted = muted;
        this._updateMuteBadge();
    }

    toggleMuted() {
        if (!this.videoEl) return;
        this.setMuted(!this.videoEl.muted);
    }

    _updateMuteBadge() {
        if (!this.muteBadge || !this.videoEl) return;
        if (this.videoEl.muted) {
            this.muteBadge.classList.add("is-muted");
            this.muteBadge.classList.remove("is-live");
        } else {
            this.muteBadge.classList.add("is-live");
            this.muteBadge.classList.remove("is-muted");
        }
    }

    _showPlaceholder(text, cls) {
        this._destroyFlv();
        if (!this.container) return;
        this.container.classList.remove("is-error", "is-offline", "is-loading");
        this.container.classList.add(cls);
        if (this.videoEl) { this.videoEl.remove(); this.videoEl = null; }
        const p = document.createElement("div");
        p.className = "placeholder";
        p.textContent = `${this.roomInput}\n${text}`;
        this.container.appendChild(p);
    }

    _destroyFlv() {
        if (this.flvPlayer) {
            try {
                this.flvPlayer.pause();
                this.flvPlayer.unload();
                this.flvPlayer.detachMediaElement();
                this.flvPlayer.destroy();
            } catch (_) { /* ignore */ }
            this.flvPlayer = null;
        }
    }

    destroy() {
        this._destroyed = true;
        if (this._reconnectTimer) { clearTimeout(this._reconnectTimer); this._reconnectTimer = null; }
        this._destroyFlv();
        if (this.container) this.container.innerHTML = "";
    }

    _updateResolution() {
        if (!this.videoEl || !this.resBadge) return;
        const [text, tier] = resolutionTier(this.videoEl.videoWidth, this.videoEl.videoHeight);
        this.resBadge.className = "tile-res " + tier;
        this.resBadge.textContent = text;
    }
}

window.Player = Player;
window.QN_LABEL = QN_LABEL;
