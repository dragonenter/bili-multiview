# B站多路直播分屏观看器 — 设计文档

**日期**：2026-05-11
**项目目录**：`/data/codes/lilong/bili-multiview/`
**部署形态**：服务器 nohup 后台 + 公网访问，端口 `8765`

## 1. 目标与范围

提供一个 Web 服务：

- 用户粘贴多个 B 站直播间链接（最多 9 路）
- 浏览器分屏（自适应网格）同时观看
- 单击某一路 → 切换"焦点模式"，该路放大并自动升画质为原画，其他路降为流畅
- 退出焦点 → 恢复网格，统一回到超清画质

**不在本期范围**：弹幕显示、礼物互动、录播下载、回放、登录态。

## 2. 整体架构

```
浏览器 (前端 HTML + flv.js)
   │  ① 粘贴链接 → 解析 room_id
   │  ② 调后端 /api/stream
   ▼
后端 FastAPI (Python)
   │  ③ 后端代发 Referer 调用 B 站 API
   │     getRoomPlayInfo → 返回真实流地址
   ▼
浏览器 flv.js
   │  ④ 直接从 B 站 CDN 拉 FLV 流（CDN 允许跨域）
   ▼
网格 ⇄ 焦点布局切换 + 画质联动
```

**关键设计**：API 走后端代理（B 站校验 Referer），流走浏览器直连 CDN。服务器零流量负担。

## 3. 后端

### 3.1 技术栈

- Python 3.10+
- FastAPI + uvicorn
- httpx（异步 HTTP 客户端）

### 3.2 API

#### `GET /api/stream`

输入：
- `room_id` (str)：原始或真实房间号
- `qn` (int)：画质等级，默认 250
  - 80 流畅、150 高清、250 超清、400 蓝光、10000 原画

输出（JSON）：
```json
{
  "room_id": 12345,
  "real_room_id": 67890,
  "title": "主播标题",
  "uname": "主播昵称",
  "live_status": 1,
  "qn": 10000,
  "accept_qn": [80, 150, 250, 400, 10000],
  "stream_url": "https://xxx.bilivideo.com/live-bvc/.../xxx.flv?...",
  "format": "flv"
}
```

错误码：
- `400`：链接无法解析
- `404`：房间不存在
- `503`：主播未开播 / B 站接口异常

#### `GET /` 与 `/static/*`

托管前端单页与静态资源。

### 3.3 B 站 API 接入

调用：
```
GET https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo
?room_id=<id>&protocol=0,1&format=0,1,2&codec=0,1&qn=<qn>&platform=web&ptype=8
```

请求头：
```
Referer: https://live.bilibili.com
User-Agent: Mozilla/5.0 ...
```

从响应 `data.playurl_info.playurl.stream[*].format[*].codec[*]` 中取首选 codec=0 (AVC)、format=flv 的 `base_url + url_info[0].host + url_info[0].extra`，拼接为完整 FLV 地址。

### 3.4 房间号解析

- 完整链接 `https://live.bilibili.com/12345` → 提取数字
- 纯数字 `12345` → 直接使用
- 短链 `b23.tv/xxx` → 调 `https://b23.tv/xxx` 跟随 302 解析（本期可不支持，错误提示提醒用户用完整链接）
- 短房间号会被 B 站 API 自动映射为真实房间号（响应里有 `real_room_id`）

## 4. 前端

### 4.1 技术栈

- 纯 HTML/CSS/JS（无构建步骤）
- flv.js（本地引入 `static/flv.min.js`）
- 不引入框架，保持轻量

### 4.2 页面结构

```
┌─────────────────────────────────────────────┐
│  顶部工具栏                                 │
│  ┌─────────────────────────┐ [开始观看]    │
│  │ textarea：一行一个链接   │ [清空]        │
│  └─────────────────────────┘ [退出焦点]    │
├─────────────────────────────────────────────┤
│                                             │
│           直播区域（网格 / 焦点）           │
│                                             │
└─────────────────────────────────────────────┘
```

### 4.3 布局规则

**网格态**（按路数自适应）：

| 路数 | 网格 |
|------|------|
| 1 | 1×1 全屏 |
| 2 | 1×2 |
| 3-4 | 2×2 |
| 5-6 | 2×3 |
| 7-9 | 3×3 |

**焦点态**：

```
┌──────────────────────┬──────────┐
│                      │ 缩略 1   │
│                      ├──────────┤
│   焦点路（主区域）   │ 缩略 2   │
│   ~75% 宽度          ├──────────┤
│                      │ ...      │
│                      ├──────────┤
│                      │ 缩略 N   │
└──────────────────────┴──────────┘
```

- 焦点路：占左侧 75% 宽
- 其他路：右侧垂直滚动列表，每个约 200px 宽缩略
- 缩略上单击 → 切换焦点（旧焦点降画质，新焦点升画质）
- 右上角 `×` → 退出焦点

### 4.4 播放器封装

`Player` 类：
- 字段：`roomId`, `currentQn`, `flvPlayer`, `videoEl`, `container`
- 方法：
  - `init()`：首次创建 video 元素 + flv.js 实例
  - `switchQuality(qn)`：销毁旧 flv 实例 → 调 `/api/stream` 取新地址 → 重新 attach
  - `destroy()`：释放 flv 实例与 video 元素

### 4.5 画质联动逻辑

- 初始：每路 qn=250（超清）
- 进入焦点：焦点路 `switchQuality(10000)`，其他路 `switchQuality(80)`
- 切换焦点：旧焦点 `switchQuality(80)`，新焦点 `switchQuality(10000)`
- 退出焦点：所有路 `switchQuality(250)`
- 画质切换会有 1-2s 黑屏，可接受

### 4.6 错误兜底

- 房间未开播 → 该路位置显示"主播未开播"占位卡片
- 流加载失败 → 显示"加载失败，点击重试"
- 链接解析失败 → 输入框下方红色提示

## 5. 部署

### 5.1 启动

```bash
cd /data/codes/lilong/bili-multiview
pip install -r requirements.txt
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8765 > nohup.out 2>&1 &
```

### 5.2 访问

```
http://<server-ip>:8765/
```

### 5.3 README 内容

包含：依赖安装、启动命令、访问方式、常见问题（主播未开播、画质切换闪烁、9 路占内存等）。

## 6. 目录结构

```
/data/codes/lilong/bili-multiview/
├── main.py                # FastAPI 入口
├── bili_api.py            # B站 API 封装 + 房间号解析
├── static/
│   ├── index.html
│   ├── app.js             # 入口逻辑（链接解析、布局切换、焦点逻辑）
│   ├── player.js          # Player 类封装
│   ├── style.css
│   └── flv.min.js         # 本地化引入
├── requirements.txt       # fastapi, uvicorn, httpx
├── README.md
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-11-bili-multiview-design.md  # 本文件
```

## 7. 自测验收清单

实施完成后必须全部通过：

1. **后端单元**：
   - [ ] `/api/stream?room_id=<正在直播的房间号>` 返回真实 FLV URL
   - [ ] 未开播房间返回 503 + 友好提示
   - [ ] 不存在房间返回 404
2. **前端功能**：
   - [ ] 粘贴 1/2/4/9 个链接，布局正确
   - [ ] 链接格式兼容：完整 URL + 纯房间号
   - [ ] 单路点击进入焦点，画质升原画
   - [ ] 焦点态点击其他缩略，焦点切换 + 画质联动
   - [ ] 退出焦点，回到网格 + 所有路恢复超清
   - [ ] 某一路未开播，占位卡片显示
3. **部署验收**：
   - [ ] `nohup` 启动后 `ps` 可见进程
   - [ ] **从外部网络打开 `http://<server-ip>:8765/` 可正常使用**
   - [ ] 服务重启后无残留进程

## 8. 风险与备选

| 风险 | 应对 |
|------|------|
| B 站 API 接口变动 | 把请求集中到 `bili_api.py`，便于热修 |
| Referer 校验变严 | 后端代理已覆盖；极端情况可代理整条流（带宽成本上升） |
| CDN 节点拒绝跨域 | 实测多数 CDN 允许；个别失败的可加后端流代理兜底，本期不实现 |
| 9 路 flv.js 内存超限 | 文档提示用户网格态默认超清而非原画 |
| 画质切换黑屏 | 切换前显示 loading，恢复后淡入 |
