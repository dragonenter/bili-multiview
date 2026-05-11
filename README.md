# bili-multiview · B站多路直播分屏观看器

最多 9 路 B 站直播同屏观看；点击任意一路最大化并自动升原画，其余路自动降为流畅。

## 快速开始

```bash
cd /data/codes/lilong/bili-multiview
bash start.sh             # 默认 8765 端口
# 或自定义端口：
PORT=9000 bash start.sh
```

浏览器访问：`http://<服务器IP>:8765/`

停止：
```bash
bash stop.sh
```

## 使用方法

1. 在顶部 textarea 一行粘贴一个 B 站直播链接或房间号，最多 9 行：
   ```
   https://live.bilibili.com/12345
   67890
   ```
2. 点"开始观看" → 视频按数量自适应网格播放（1/2/4/6/9 格）
3. 单击任一路 → 切换到焦点模式，该路放大并升原画，其余路缩侧栏并降流畅
4. 焦点模式下点 sidebar 任一路 → 焦点切换
5. 顶部"退出焦点" → 回到网格

## 画质联动策略

| 状态 | 焦点路 | 其他路 |
|------|--------|--------|
| 网格态 | 超清 (qn=250) | 超清 (qn=250) |
| 焦点态 | 原画 (qn=10000) | 流畅 (qn=80) |

切换画质时会有 1-2 秒黑屏，属于正常重连。

## 技术架构

- 后端 FastAPI 代理 B 站 `getRoomPlayInfo` 接口（自带 Referer 绕开校验），返回真实 CDN FLV 流地址
- 浏览器 flv.js 直接拉 CDN 流，服务器不中转视频流量
- 焦点切换通过 DOM 重新挂载（reparent）保留正在播放的视频元素，仅画质变化的实例触发重连
- 9 路 flv.js 实例约占用浏览器 400MB 内存

## API

- `GET /api/stream?room_id=<id>&qn=<qn>` → JSON
  - 200：`{stream_url, real_room_id, title, uname, qn, accept_qn, format, ...}`
  - 400：链接无法解析
  - 503：主播未开播
  - 502：B 站接口异常（含 HTTP 5xx / 网络错误）

## 开发与测试

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -v
```

19 个后端单元测试（房间号解析 9 个 + B站 API 4 个 + FastAPI 端点 5 个 + httpx 错误包装 1 个），全部通过即视为后端就绪。前端用浏览器冒烟测试见下方"自测清单"。

## 已知限制

- 不支持 `b23.tv` 短链，请使用完整 `live.bilibili.com` 链接或房间号
- 不支持登录态弹幕、礼物互动、录播下载（本期范围外）
- 同时 9 路对带宽和浏览器内存有要求，画质过高可能卡顿

## 故障排查

- 服务起不来：查看 `nohup.out`
- 公网打不开：检查服务器防火墙是否开放对应端口
- 视频不播放：右键 inspect → console 看 flv.js 报错；可能是 B 站 CDN 偶发 403，刷新页面或换房间重试

## 自测清单

后端：
- `/api/stream?room_id=<在线>` 返回 200 + 合法 stream_url
- `/api/stream?room_id=invalid` 返回 400
- `/api/stream?room_id=<未开播>` 返回 503

前端（浏览器）：
- 粘贴 1 个链接 → 单路全屏播放
- 粘贴 2 个 → 1×2 布局
- 粘贴 4 个 → 2×2 布局
- 粘贴 9 个 → 3×3 布局
- 单击任一路 → 进入焦点 + 升原画 + 其余降流畅
- 焦点态点 sidebar 切焦点 → 画质联动
- 退出焦点 → 回到网格 + 所有恢复超清
- 未开播房间显示"主播未开播"占位
- 非法字符串显示错误占位

部署：
- 从外部公网 IP 访问 `http://<server-ip>:8765/` 可正常使用
- `bash stop.sh && bash start.sh` 重启无残留进程
