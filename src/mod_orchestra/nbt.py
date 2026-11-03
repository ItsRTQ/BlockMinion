"""Minimal NBT writer (gzip, big-endian) — enough for Minecraft structure templates. stdlib only."""
from __future__ import annotations
import gzip
import struct

TAG_END, TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG, TAG_FLOAT, TAG_DOUBLE, TAG_BYTE_ARRAY, TAG_STRING, TAG_LIST, TAG_COMPOUND, TAG_INT_ARRAY = range(12)


class Int(int): pass
class Short(int): pass
class Byte(int): pass
class Long(int): pass
class Float(float): pass
class Double(float): pass


def _tag_type(v) -> int:
    if isinstance(v, Byte): return TAG_BYTE
    if isinstance(v, Short): return TAG_SHORT
    if isinstance(v, Long): return TAG_LONG
    if isinstance(v, bool): return TAG_BYTE
    if isinstance(v, Int) or isinstance(v, int): return TAG_INT
    if isinstance(v, Float): return TAG_FLOAT
    if isinstance(v, float): return TAG_DOUBLE
    if isinstance(v, str): return TAG_STRING
    if isinstance(v, dict): return TAG_COMPOUND
    if isinstance(v, (list, tuple)): return TAG_LIST
    if isinstance(v, bytes): return TAG_BYTE_ARRAY
    raise TypeError(f"unsupported NBT value {type(v)}")


def _write_payload(out: bytearray, t: int, v) -> None:
    if t == TAG_BYTE: out += struct.pack(">b", int(v))
    elif t == TAG_SHORT: out += struct.pack(">h", int(v))
    elif t == TAG_INT: out += struct.pack(">i", int(v))
    elif t == TAG_LONG: out += struct.pack(">q", int(v))
    elif t == TAG_FLOAT: out += struct.pack(">f", float(v))
    elif t == TAG_DOUBLE: out += struct.pack(">d", float(v))
    elif t == TAG_BYTE_ARRAY: out += struct.pack(">i", len(v)) + v
    elif t == TAG_STRING:
        b = v.encode("utf-8"); out += struct.pack(">H", len(b)) + b
    elif t == TAG_LIST:
        items = list(v)
        et = _tag_type(items[0]) if items else TAG_END
        out += struct.pack(">bi", et, len(items))
        for it in items: _write_payload(out, et, it)
    elif t == TAG_COMPOUND:
        for k, val in v.items():
            vt = _tag_type(val); kb = k.encode("utf-8")
            out += struct.pack(">bH", vt, len(kb)) + kb
            _write_payload(out, vt, val)
        out += b"\x00"
    else:
        raise TypeError(t)


def dumps(root: dict, name: str = "") -> bytes:
    """Serialize a compound as a gzipped NBT file (what Minecraft reads for structures)."""
    out = bytearray(); nb = name.encode("utf-8")
    out += struct.pack(">bH", TAG_COMPOUND, len(nb)) + nb
    _write_payload(out, TAG_COMPOUND, root)
    return gzip.compress(bytes(out), mtime=0)


def structure_template(blocks: list[tuple[int, int, int, str]], size: tuple[int, int, int], data_version: int = 3955) -> bytes:
    """A structure template from (x, y, z, 'minecraft:stone' | 'mod:block[prop=val]') entries. Air is omitted.
    data_version 3955 = 1.21.1."""
    palette: list[dict] = []; index: dict[str, int] = {}
    entries = []
    for x, y, z, state in blocks:
        if state not in index:
            name, _, props = state.partition("[")
            entry: dict = {"Name": name}
            if props:
                entry["Properties"] = {k: v for k, v in (kv.split("=") for kv in props.rstrip("]").split(","))}
            index[state] = len(palette); palette.append(entry)
        entries.append({"pos": [Int(x), Int(y), Int(z)], "state": Int(index[state])})
    root = {"DataVersion": Int(data_version), "size": [Int(size[0]), Int(size[1]), Int(size[2])], "palette": palette, "blocks": entries, "entities": []}
    return dumps(root)
