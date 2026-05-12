"""danmaku 模块的协议层单元测试（纯函数）。WS / SSE 集成靠真实接口验证。"""
import struct
import zlib

from danmaku import (
    _pack_packet,
    _parse_packets,
    _parse_business_msg,
    _sign_wbi,
    HEADER_LEN,
    OP_AUTH,
    OP_NOTIFICATION,
)


def test_pack_packet_header_layout():
    body = b'{"x":1}'
    pkt = _pack_packet(OP_AUTH, body, protover=1)
    total, hlen, ver, op, seq = struct.unpack(">IHHII", pkt[:HEADER_LEN])
    assert total == HEADER_LEN + len(body)
    assert hlen == HEADER_LEN
    assert ver == 1
    assert op == OP_AUTH
    assert seq == 1
    assert pkt[HEADER_LEN:] == body


def test_parse_packets_single():
    body = b'{"cmd":"DANMU_MSG","info":[[0,0,0,16777215],"hello",["xxx","u"]]}'
    pkt = _pack_packet(OP_NOTIFICATION, body, protover=0)
    out = _parse_packets(pkt)
    assert len(out) == 1
    op, ver, b = out[0]
    assert op == OP_NOTIFICATION
    assert b == body


def test_parse_packets_zlib_nested():
    # 构造两个内层 packet 串联，外层 zlib 压缩
    inner1 = _pack_packet(OP_NOTIFICATION, b'{"cmd":"X"}', protover=0)
    inner2 = _pack_packet(OP_NOTIFICATION, b'{"cmd":"Y"}', protover=0)
    compressed = zlib.compress(inner1 + inner2)
    outer = _pack_packet(OP_NOTIFICATION, compressed, protover=2)
    out = _parse_packets(outer)
    assert len(out) == 2
    bodies = [o[2] for o in out]
    assert b'{"cmd":"X"}' in bodies
    assert b'{"cmd":"Y"}' in bodies


def test_parse_business_msg_danmu():
    # B 站实际 DANMU_MSG 格式：info[0]=模式, info[1]=文本, info[2]=[uid, uname,...]
    body = b'{"cmd":"DANMU_MSG","info":[[0,1,25,16711680,0,0,0,""],"hi",[1,"sender",0,0,0]]}'
    msg = _parse_business_msg(body)
    assert msg == {"type": "danmu", "text": "hi", "uname": "sender", "color": 16711680}


def test_parse_business_msg_with_suffix():
    body = b'{"cmd":"DANMU_MSG:4:0:2:2:2:0","info":[[0,0,0,16777215],"x",[1,"u",0]]}'
    msg = _parse_business_msg(body)
    assert msg is not None
    assert msg["type"] == "danmu"
    assert msg["text"] == "x"
    assert msg["uname"] == "u"


def test_parse_business_msg_gift():
    body = '{"cmd":"SEND_GIFT","data":{"uname":"a","giftName":"星辰","num":3}}'.encode("utf-8")
    msg = _parse_business_msg(body)
    assert msg == {"type": "gift", "uname": "a", "gift_name": "星辰", "num": 3}


def test_parse_business_msg_ignored():
    msg = _parse_business_msg(b'{"cmd":"UNKNOWN_THING","data":{}}')
    assert msg is None


def test_sign_wbi_adds_wts_and_w_rid():
    signed = _sign_wbi({"id": 6, "type": 0}, "a" * 32)
    assert "wts" in signed
    assert "w_rid" in signed
    assert len(signed["w_rid"]) == 32  # md5 hex
    # 原始参数保留
    assert signed["id"] == "6"
    assert signed["type"] == "0"
