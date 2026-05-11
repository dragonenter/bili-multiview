/* global flvjs */
const QN_LABEL = {
    80: "流畅", 150: "高清", 250: "超清", 400: "蓝光", 10000: "原画"
};

class Player {
    constructor(roomInput, initialQn = 250) {
        this.roomInput = roomInput;      // 原始输入（链接或数字）
        this.qn = initialQn;
        this.realRoomId = null;
        this.title = "";
        this.uname = "";
        this.flvPlayer = null;
        this.videoEl = null;
        this.container = null;
        this.label = null;
        this.qnBadge = null;
        this.onClick = null;             // 由 app.js 注入
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
        });
        container.appendChild(this.videoEl);

        this.label = document.createElement("div");
        this.label.className = "tile-label";
        this.label.textContent = `加载中 (${this.roomInput})`;
        container.appendChild(this.label);

        this.qnBadge = document.createElement("div");
        this.qnBadge.className = "tile-qn";
        this.qnBadge.textContent = QN_LABEL[this.qn] || `qn=${this.qn}`;
        container.appendChild(this.qnBadge);

        container.addEventListener("click", () => {
            if (this.onClick) this.onClick(this);
        });
    }

    async load() {
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
        player.load();
        player.play().catch(() => { /* autoplay 被拦截时静音重试 */ });
        this.flvPlayer = player;
    }

    async switchQuality(newQn) {
        if (newQn === this.qn) return;
        this.qn = newQn;
        if (this.qnBadge) this.qnBadge.textContent = QN_LABEL[newQn] || `qn=${newQn}`;
        if (this.container) this.mount(this.container);
        await this.load();
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
        this._destroyFlv();
        if (this.container) this.container.innerHTML = "";
    }
}

window.Player = Player;
window.QN_LABEL = QN_LABEL;
