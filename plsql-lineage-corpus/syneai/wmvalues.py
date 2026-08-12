"""webMethods ``Values`` binary codec for ``IRTNODE_PROPERTY`` blobs.

The lineage-critical part of a JDBC adapter node - which database, which schema,
which table, which columns, and what expression is applied on the way in - lives
only inside a base64 binary blob, not in the surrounding XML. A lineage engine
that cannot decode it cannot see any of that. So the corpus has to encode it.

**Read `docs/WM-VALUES-FORMAT.md` before trusting these bytes.** Exactly one
33-byte fragment of a real blob was available, which pins the preamble, the
string tag, and the UTF-16LE/little-endian string encoding. Everything else -
integers, booleans, arrays, nested records - is a declared convention, not an
observation. Byte compatibility with a real Integration Server is unverified.

The tag table and preamble are the only place that assumption lives:

    python3 -m syneai.wmvalues --self-test          # what can be checked, is
    python3 -m syneai.wmvalues --verify <file>      # check against a real blob
"""

from __future__ import annotations

import argparse
import base64
import pathlib
import re
import struct
import sys

# --- observed ----------------------------------------------------------------

#: First 8 bytes of the sample blob. Their individual meaning is not known, so
#: they are treated as an opaque literal rather than given an invented reading.
PREAMBLE = bytes((0x0B, 0x04, 0x00, 0x00, 0x00, 0x01, 0x05, 0x01))

#: The implementation class name the sample blob carries as its first string.
IMPL_CLASS = "com.wm.data.ISMemDataImpl"

#: The exact 33 bytes decoded from the fragment quoted in docs/PLAN-EAI.md.
#: Any change to PREAMBLE, the string tag, or the string encoding breaks this.
SAMPLE_PREFIX = base64.b64decode("CwQAAAABBQEEGQBjAG8AbQAuAHcAbQAuAGQAYQB0AGEA")

# --- tag table (convention - see WM-VALUES-FORMAT.md section 3.2) ------------

TAG_NULL = 0x01
TAG_INT = 0x02
TAG_BOOL = 0x03
TAG_STRING = 0x04  # observed
TAG_STRING_ARRAY = 0x05
TAG_RECORD = 0x06
TAG_RECORD_ARRAY = 0x07

TAGS = {
    TAG_NULL: "null",
    TAG_INT: "int32",
    TAG_BOOL: "boolean",
    TAG_STRING: "string",
    TAG_STRING_ARRAY: "string[]",
    TAG_RECORD: "record",
    TAG_RECORD_ARRAY: "record[]",
}

MAX_STRING_CHARS = 0xFFFF


class WmValuesError(ValueError):
    """Raised with a byte offset so a decode failure points at the bad tag."""

    def __init__(self, message: str, offset: int) -> None:
        super().__init__(f"offset {offset} (0x{offset:X}): {message}")
        self.offset = offset


# --- encoding ----------------------------------------------------------------


def _enc_string(text: str) -> bytes:
    payload = text.encode("utf-16-le")
    if len(text) > MAX_STRING_CHARS:
        raise ValueError(f"string too long for a uint16 length field: {len(text)} chars")
    return bytes((TAG_STRING,)) + struct.pack("<H", len(text)) + payload


def _enc_key(name: str) -> bytes:
    return _enc_string(name)


def _enc_value(value) -> bytes:
    if value is None:
        return bytes((TAG_NULL,))
    if isinstance(value, bool):
        return bytes((TAG_BOOL, 1 if value else 0))
    if isinstance(value, int):
        return bytes((TAG_INT,)) + struct.pack("<i", value)
    if isinstance(value, str):
        return _enc_string(value)
    if isinstance(value, dict):
        return bytes((TAG_RECORD,)) + _enc_record_body(value)
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(v, dict) for v in value):
            out = bytes((TAG_RECORD_ARRAY,)) + struct.pack("<I", len(value))
            for v in value:
                out += _enc_record_body(v)
            return out
        out = bytes((TAG_STRING_ARRAY,)) + struct.pack("<I", len(value))
        for v in value:
            out += bytes((TAG_NULL,)) if v is None else _enc_string(str(v))
        return out
    raise TypeError(f"unsupported value type: {type(value).__name__}")


def _enc_record_body(record: dict) -> bytes:
    out = struct.pack("<I", len(record))
    for key, value in record.items():
        out += _enc_key(str(key)) + _enc_value(value)
    return out


def encode(record: dict, impl_class: str = IMPL_CLASS) -> bytes:
    """Encode a mapping into a ``Values`` blob."""

    return PREAMBLE + _enc_string(impl_class) + _enc_record_body(record)


def encode_b64(record: dict, impl_class: str = IMPL_CLASS) -> str:
    return base64.b64encode(encode(record, impl_class)).decode("ascii")


# --- decoding ----------------------------------------------------------------


class _Reader:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise WmValuesError(f"need {n} bytes, only {len(self.data) - self.pos} left",
                                self.pos)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]


def _dec_string(r: _Reader) -> str:
    at = r.pos
    tag = r.u8()
    if tag != TAG_STRING:
        raise WmValuesError(
            f"expected string tag 0x{TAG_STRING:02X}, got 0x{tag:02X}"
            f" ({TAGS.get(tag, 'unknown')})", at)
    count = r.u16()
    return r.take(count * 2).decode("utf-16-le")


def _dec_value(r: _Reader):
    at = r.pos
    tag = r.u8()
    if tag == TAG_NULL:
        return None
    if tag == TAG_BOOL:
        return bool(r.u8())
    if tag == TAG_INT:
        return r.i32()
    if tag == TAG_STRING:
        count = r.u16()
        return r.take(count * 2).decode("utf-16-le")
    if tag == TAG_STRING_ARRAY:
        n = r.u32()
        out = []
        for _ in range(n):
            if r.data[r.pos] == TAG_NULL:
                r.pos += 1
                out.append(None)
            else:
                out.append(_dec_string(r))
        return out
    if tag == TAG_RECORD:
        return _dec_record_body(r)
    if tag == TAG_RECORD_ARRAY:
        return [_dec_record_body(r) for _ in range(r.u32())]
    raise WmValuesError(f"unknown tag 0x{tag:02X}", at)


def _dec_record_body(r: _Reader) -> dict:
    out: dict = {}
    for _ in range(r.u32()):
        key = _dec_string(r)
        out[key] = _dec_value(r)
    return out


def decode(data: bytes) -> tuple[dict, str]:
    """Decode a ``Values`` blob. Returns ``(record, impl_class)``."""

    if not data.startswith(PREAMBLE):
        raise WmValuesError(
            "preamble mismatch: expected "
            + " ".join(f"{b:02X}" for b in PREAMBLE)
            + ", got " + " ".join(f"{b:02X}" for b in data[:len(PREAMBLE)]), 0)
    r = _Reader(data)
    r.pos = len(PREAMBLE)
    impl_class = _dec_string(r)
    record = _dec_record_body(r)
    if r.pos != len(data):
        raise WmValuesError(f"{len(data) - r.pos} trailing bytes after the record",
                            r.pos)
    return record, impl_class


def decode_b64(text: str) -> tuple[dict, str]:
    cleaned = "".join(text.split())
    return decode(base64.b64decode(cleaned + "=" * (-len(cleaned) % 4)))


# --- self-test ---------------------------------------------------------------

_SELF_TEST_RECORD = {
    "serviceTemplateName": "com.wm.adapter.wmjdbc.services.Insert",
    "connectionName": "SYN_DbConn.ORA:SYNWMS_LOCAL_01",
    "tables.realSchemaName": "SYNIF",
    "tables.tableName": "IF_ITEM_RCV",
    "tables.columnInfo": [
        "ITEM_CD\nVARCHAR2(30) NOT NULL\n12\n1\n",
        "ITEM_NM\nVARCHAR2(200)\n12\n0\n",
        "UNIT_WGT\nNUMBER(13,3)\n3\n0\n",
    ],
    "update.column": ["ITEM_CD", "ITEM_NM", "UNIT_WGT"],
    "update.inputField": ["ITEM_CD", "ITEM_NM", "UNIT_WGT"],
    "update.expression": ["?", "SYNCRYPT.FN_ENC(?)", "?"],
    "batchSize": 1000,
    "useBatchUpdate": True,
    "select.refColumn": None,
    "joins": [{"leftColumn": "ITEM_CD", "rightColumn": "ITM_CODE"}],
    "nested": {"a": "1", "b": [None, "x"]},
}


def self_test(verbose: bool = True) -> bool:
    checks: list[tuple[str, bool, str]] = []

    blob = encode(_SELF_TEST_RECORD)
    prefix_ok = blob[:len(SAMPLE_PREFIX)] == SAMPLE_PREFIX
    checks.append((
        "prefix_matches_sample", prefix_ok,
        "선두 33바이트가 실제 표본과 일치" if prefix_ok else
        "expected " + " ".join(f"{b:02X}" for b in SAMPLE_PREFIX[:12]) + " ... got "
        + " ".join(f"{b:02X}" for b in blob[:12])))

    try:
        record, impl = decode(blob)
        decode_ok, detail = True, f"{len(record)} keys, impl={impl}"
    except WmValuesError as exc:
        record, impl = {}, ""
        decode_ok, detail = False, str(exc)
    checks.append(("decode", decode_ok, detail))

    values_ok = decode_ok and record == _SELF_TEST_RECORD
    checks.append(("roundtrip_values", values_ok,
                   "" if values_ok else "decoded record differs from the original"))

    bytes_ok = decode_ok and encode(record, impl) == blob
    checks.append(("roundtrip_bytes", bytes_ok,
                   "" if bytes_ok else "re-encoded bytes differ"))

    b64_ok = decode_b64(encode_b64(_SELF_TEST_RECORD))[0] == _SELF_TEST_RECORD
    checks.append(("base64_stable", b64_ok, ""))

    empty_ok = decode(encode({}))[0] == {}
    checks.append(("empty_record", empty_ok, ""))

    long_text = "한글" * 500
    long_ok = decode(encode({"k": long_text}))[0]["k"] == long_text
    checks.append(("utf16_multibyte", long_ok, ""))

    if verbose:
        print("wmvalues 자체 검사")
        print("-" * 66)
        for name, ok, detail in checks:
            print(f"  {name:<24} {'OK ' if ok else 'FAIL'}  {detail}")
        print("-" * 66)
        print("  주의: 실제 webMethods 디코더와의 호환성은 검증되지 않았다.")
        print("        docs/WM-VALUES-FORMAT.md 참고.")
    return all(ok for _, ok, _ in checks)


# --- verification against a real blob ----------------------------------------

_PROP_RE = re.compile(
    r'<value\s+name="IRTNODE_PROPERTY"\s*>(.*?)</value>', re.S | re.I)


def extract_blobs(text: str) -> list[str]:
    """Pull candidate base64 blobs out of a node.ndf or a plain text file."""

    hits = [m.group(1) for m in _PROP_RE.finditer(text)]
    if hits:
        return hits
    stripped = "".join(text.split())
    if stripped and re.fullmatch(r"[A-Za-z0-9+/=]+", stripped):
        return [stripped]
    return []


def verify_file(path: pathlib.Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    blobs = extract_blobs(text)
    if not blobs:
        print(f"{path}: IRTNODE_PROPERTY 값을 찾지 못했습니다.")
        return 1

    failures = 0
    for i, b64 in enumerate(blobs):
        cleaned = "".join(b64.split())
        raw = base64.b64decode(cleaned + "=" * (-len(cleaned) % 4))
        print(f"\n[{i + 1}/{len(blobs)}] {len(raw):,} bytes")
        head = " ".join(f"{b:02X}" for b in raw[:16])
        print(f"  선두 16바이트  {head}")
        print(f"  전문 일치      {'예' if raw.startswith(PREAMBLE) else '아니오'}")
        try:
            record, impl = decode(raw)
        except WmValuesError as exc:
            print(f"  디코딩         실패 - {exc}")
            print("  → 태그 표가 실제 포맷과 다릅니다. "
                  "docs/WM-VALUES-FORMAT.md 3.2 를 수정하십시오.")
            failures += 1
            continue
        print(f"  디코딩         성공 - impl={impl}, {len(record)} keys")
        again = encode(record, impl)
        if again == raw:
            print("  왕복 일치      예  → 규약이 실제 포맷과 맞습니다.")
        else:
            at = next((n for n, (a, b) in enumerate(zip(again, raw)) if a != b),
                      min(len(again), len(raw)))
            print(f"  왕복 일치      아니오 - 첫 차이 offset {at} (0x{at:X})")
            failures += 1
        for key in ("tables.realSchemaName", "tables.tableName", "connectionName",
                    "serviceTemplateName"):
            if key in record:
                print(f"    {key:<26} {record[key]}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="syneai.wmvalues",
                                 description="webMethods Values 블롭 인/디코더")
    ap.add_argument("--self-test", action="store_true",
                    help="검증 가능한 항목만 확인 (실제 호환성은 확인 불가)")
    ap.add_argument("--verify", metavar="FILE",
                    help="실제 node.ndf 또는 base64 파일과 대조")
    ap.add_argument("--dump", metavar="FILE", help="블롭을 디코딩해 키/값 출력")
    args = ap.parse_args(argv)

    if args.verify:
        return verify_file(pathlib.Path(args.verify))
    if args.dump:
        text = pathlib.Path(args.dump).read_text(encoding="utf-8", errors="replace")
        for b64 in extract_blobs(text):
            record, impl = decode_b64(b64)
            print(f"impl={impl}")
            for k, v in record.items():
                print(f"  {k} = {v!r}")
        return 0
    ok = self_test()
    return 0 if ok or not args.self_test else 1


if __name__ == "__main__":
    sys.exit(main())
