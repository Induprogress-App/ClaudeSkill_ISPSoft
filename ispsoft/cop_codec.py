#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cop_codec.py - odczyt i edycja plikow .cop (siec CANopen z CANopen Builder, ISPSoft) bez GUI.

Tylko biblioteka standardowa Pythona 3. Opis formatu: FORMAT_COP.md.

Polecenia:
  dump   plik.cop [D_zapisu D_odczytu]   czytelny opis sieci (master, wezly, Auto SDO, PDO, mapowanie na rejestry);
                                 z poczatkami obszarow, np. 25032 24032, podaje adresy D
  decode plik.cop [plik.json]     rozklad na JSON (domyslnie plik.cop.json)
  encode plik.json plik.cop       zlozenie pliku .cop z JSON
  check  plik.cop                 test: rozklad -> zlozenie daje identyczny plik
"""
import sys
import os
import json
import struct

CP = "cp1250"            # strona kodowa napisow
N_NODES = 128            # sloty wezlow 0..127
N_PDO_SLOTS = 16         # sloty PDO w wezle: Tx1,Rx1,Tx2,Rx2,... (8 par)
N_MAP = 32               # pojemnosc tablicy mapowania w slocie PDO
N_SDO = 20               # pojemnosc tablicy Auto SDO
SDO_SIZE = 20
FIELDS_LEN = 57          # pola identyfikacyjne tuz przed nazwa wezla
TRAIL_LEN = 76           # stala koncowka rekordu wezla (z wyjatkiem ostatniego)
MASTER_HB_POS = 0x37     # pozycja czasu heartbeat mastera w naglowku

# --- wartosci domyslne pustego wezla ("Unknow Device") ---
DEF_PRE_VENDOR = "0a000000881300000a0000000a00000005000000000100c8"
DEF_TRAIL = ("00000000000000000000000000000000680100000101140000000a00000010270000102700001027"
             "000000000000000000000000010000008000000000401c460000803f0000803f00401c46")


class CopError(Exception):
    pass


UNI_MARK = bytes([0xFF, 0xFE, 0xFF])   # znacznik napisu Unicode w zapisie MFC
UNI = False   # True: napisy w Unicode (znacznik FF FE FF, UTF-16LE) - zapis nowszego ISPSoft


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def take(self, n):
        if self.p + n > len(self.d):
            raise CopError("plik za krotki (pozycja %d, potrzeba %d bajtow)" % (self.p, n))
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def pstr(self):
        if UNI:
            if self.take(3) != UNI_MARK:
                raise CopError("brak znacznika napisu Unicode (pozycja %d)" % (self.p - 3))
            n = self.u8()
            if n == 255:
                raise CopError("napis dluzszy niz 254 znaki (nieobslugiwane)")
            return self.take(2 * n).decode("utf-16-le")
        n = self.u8()
        return self.take(n).decode(CP)


def pstr(s):
    if UNI:
        if len(s) > 254:
            raise CopError("napis za dlugi: %r" % s)
        return UNI_MARK + bytes([len(s)]) + s.encode("utf-16-le")
    b = s.encode(CP)
    if len(b) > 254:
        raise CopError("napis za dlugi: %r" % s)
    return bytes([len(b)]) + b


def hx(b):
    return b.hex()


# ---------------------------------------------------------------- rozklad

def parse_slot(r, tx):
    s = {}
    if tx:
        s["cob"], s["event_timer"], s["index"], s["inhibit_timer"] = struct.unpack("<IIII", r.take(16))
    else:
        s["cob"], s["index"] = struct.unpack("<II", r.take(8))
    s["type"] = r.u8()
    cnt = r.u8()
    if cnt > N_MAP:
        raise CopError("za duzo wpisow mapowania: %d" % cnt)
    maps = []
    stale = []
    for e in range(N_MAP):
        bits, sub, idx = struct.unpack("<BBH", r.take(4))
        name = r.pstr()
        ent = {"index": idx, "sub": sub, "bits": bits, "name": name}
        if e < cnt:
            maps.append(ent)
        else:
            stale.append(ent)
    while stale and not (stale[-1]["bits"] or stale[-1]["sub"] or stale[-1]["index"] or stale[-1]["name"]):
        stale.pop()
    if stale:
        s["stale_map"] = stale   # stare wpisy za licznikiem (pozostalosc po usunieciu z PDO)
    s["map"] = maps
    return s


def parse_node(r, k, first):
    n = {"id": k}
    n["pre_vendor"] = hx(r.take(9 if first else 24))
    n["vendor_id"] = r.u32(); n["check_vendor"] = r.u32()
    n["device_type"] = r.u32(); n["check_device_type"] = r.u32()
    n["product_code"] = r.u32(); n["check_product"] = r.u32()
    n["revision"] = r.u32(); n["check_revision"] = r.u32()
    n["emergency_cob"] = r.u32()
    n["nodeguard_cob"] = r.u32()
    n["guard_time_ms"] = r.u32()
    n["lifetime_factor"] = r.u8()
    n["producer_ms"] = r.u32()
    n["consumer_ms"] = r.u32()
    n["heartbeat"] = r.u32()
    n["name"] = r.pstr()
    n["eds_name"] = r.pstr()
    n["flag_a"] = r.u8()
    n["flag_b"] = r.u8()
    cnt = r.u8()
    if cnt > N_SDO:
        raise CopError("za duzo wpisow Auto SDO: %d" % cnt)
    sdo = []
    stale = []
    for i in range(N_SDO):
        idx, sub, ln, z1, val, z2 = struct.unpack("<HHIIII", r.take(SDO_SIZE))
        if i < cnt:
            if z1 or z2:
                raise CopError("Auto SDO: niezerowe pola rezerwowe (nieobslugiwane)")
            sdo.append({"index": idx, "sub": sub, "len": ln, "data": val})
        else:
            stale.append({"index": idx, "sub": sub, "len": ln, "data": val, "r1": z1, "r2": z2})
    while stale and not any(stale[-1].values()):
        stale.pop()
    if stale:
        n["stale_sdo"] = stale   # stare wpisy za licznikiem (pozostalosc po usunieciu z Auto SDO)
    n["auto_sdo"] = sdo
    n["pre_pdo"] = hx(r.take(13))
    r.take(2)  # liczby skonfigurowanych PDO Tx/Rx - wyliczane przy skladaniu
    slots = []
    for s in range(N_PDO_SLOTS):
        sl = parse_slot(r, s % 2 == 0)
        sl["nr"] = s // 2 + 1
        sl["dir"] = "Tx" if s % 2 == 0 else "Rx"
        slots.append(sl)
    n["slots"] = slots
    return n


def parse(data):
    global UNI
    UNI = data[:3] == UNI_MARK
    r = Reader(data)
    m = {"unicode": UNI}
    m["title"] = r.pstr()
    m["hdr1"] = hx(r.take(6))
    m["hdr_strs"] = [r.pstr() for _ in range(6)]
    m["hdr2"] = hx(r.take(27))
    m["heartbeat_ms"] = r.u32()
    m["name"] = r.pstr()
    m["flag"] = r.u8()
    m["baud_code"] = r.u8()
    m["sync_cob"] = r.u32()
    m["cycle_ms"] = r.u32()
    m["work_mode"] = r.u8()
    m["ident"] = r.pstr()
    nodes = []
    for k in range(N_NODES):
        n = parse_node(r, k, k == 0)
        last = (k == N_NODES - 1)
        t = r.take(len(data) - r.p if last else TRAIL_LEN)
        # 4 pierwsze liczby koncowki: przesuniecie danych wezla w obrazie wejsc (odczyt, od D24xxx) i wyjsc
        # (zapis, od D25xxx) w bajtach, potem liczba bajtow Tx i Rx (wyliczane przy skladaniu)
        n["in_offset"], n["out_offset"] = struct.unpack("<II", t[:8])
        n["trail"] = hx(t[16:])
        nodes.append(n)
    return {"master": m, "nodes": nodes}


# ---------------------------------------------------------------- skladanie

def slot_bits(sl):
    return sum(e["bits"] for e in sl["map"])


def build_slot(sl, tx):
    out = bytearray()
    if tx:
        out += struct.pack("<IIII", sl["cob"], sl.get("event_timer", 0), sl["index"], sl.get("inhibit_timer", 0))
    else:
        out += struct.pack("<II", sl["cob"], sl["index"])
    maps = sl["map"]
    if len(maps) > N_MAP:
        raise CopError("za duzo wpisow mapowania (max %d)" % N_MAP)
    out += bytes([sl["type"], len(maps)])
    allm = maps + sl.get("stale_map", [])
    if len(allm) > N_MAP:
        raise CopError("za duzo wpisow mapowania z wpisami stale_map (max %d)" % N_MAP)
    for e in range(N_MAP):
        if e < len(allm):
            m = allm[e]
            out += struct.pack("<BBH", m["bits"], m.get("sub", 0), m["index"]) + pstr(m.get("name", ""))
        else:
            out += bytes(4) + pstr("")
    return bytes(out)


def build_node(n, first):
    out = bytearray()
    out += bytes.fromhex(n["pre_vendor"])
    for key in ("vendor_id", "check_vendor", "device_type", "check_device_type", "product_code",
                "check_product", "revision", "check_revision", "emergency_cob", "nodeguard_cob",
                "guard_time_ms"):
        out += struct.pack("<I", n[key])
    out += bytes([n["lifetime_factor"]])
    out += struct.pack("<III", n["producer_ms"], n["consumer_ms"], n["heartbeat"])
    out += pstr(n["name"]) + pstr(n["eds_name"])
    out += bytes([n["flag_a"], n["flag_b"]])
    sdo = n["auto_sdo"]
    if len(sdo) > N_SDO:
        raise CopError("wezel %d: za duzo wpisow Auto SDO (max %d)" % (n["id"], N_SDO))
    out += bytes([len(sdo)])
    allsdo = sdo + n.get("stale_sdo", [])
    if len(allsdo) > N_SDO:
        raise CopError("wezel %d: za duzo wpisow Auto SDO z stale_sdo (max %d)" % (n["id"], N_SDO))
    for i in range(N_SDO):
        if i < len(allsdo):
            e = allsdo[i]
            out += struct.pack("<HHIIII", e["index"], e.get("sub", 0), e["len"], e.get("r1", 0), e["data"], e.get("r2", 0))
        else:
            out += bytes(SDO_SIZE)
    out += bytes.fromhex(n["pre_pdo"])
    slots = n["slots"]
    if len(slots) != N_PDO_SLOTS:
        raise CopError("wezel %d: musi byc %d slotow PDO" % (n["id"], N_PDO_SLOTS))
    ntx = sum(1 for s in range(0, N_PDO_SLOTS, 2) if slots[s]["map"])
    nrx = sum(1 for s in range(1, N_PDO_SLOTS, 2) if slots[s]["map"])
    out += bytes([ntx, nrx])
    for s, sl in enumerate(slots):
        out += build_slot(sl, s % 2 == 0)
    return bytes(out)


def fix_trail(n):
    """Koncowka rekordu: przesuniecia (z modelu), liczba bajtow Tx i Rx (wyliczane), stala reszta."""
    tx = sum(slot_bits(n["slots"][s]) for s in range(0, N_PDO_SLOTS, 2)) // 8
    rx = sum(slot_bits(n["slots"][s]) for s in range(1, N_PDO_SLOTS, 2)) // 8
    return struct.pack("<IIII", n["in_offset"], n["out_offset"], tx, rx) + bytes.fromhex(n["trail"])


def build(model):
    global UNI
    m = model["master"]
    UNI = bool(m.get("unicode", False))
    out = bytearray(pstr(m["title"]) + bytes.fromhex(m["hdr1"]))
    for t in m["hdr_strs"]:
        out += pstr(t)
    out += bytes.fromhex(m["hdr2"])
    out += struct.pack("<I", m["heartbeat_ms"]) + pstr(m["name"])
    out += bytes([m["flag"], m["baud_code"]]) + struct.pack("<II", m["sync_cob"], m["cycle_ms"])
    out += bytes([m["work_mode"]]) + pstr(m["ident"])
    nodes = model["nodes"]
    if len(nodes) != N_NODES:
        raise CopError("musi byc %d wezlow" % N_NODES)
    for k, n in enumerate(nodes):
        out += build_node(n, k == 0)
        out += fix_trail(n)
    return bytes(out)


# ---------------------------------------------------------------- wezel domyslny (pusty)

def default_slot(tx, nr, index=0xFFFF):
    s = {"cob": 0, "index": index, "type": 255, "map": [], "nr": nr, "dir": "Tx" if tx else "Rx"}
    if tx:
        s["event_timer"] = 0
        s["inhibit_timer"] = 0
    return s


def default_node(k):
    return {
        "id": k, "pre_vendor": DEF_PRE_VENDOR,
        "vendor_id": 0x1DD, "check_vendor": 1, "device_type": 0x192, "check_device_type": 1,
        "product_code": 0x16, "check_product": 1, "revision": 1, "check_revision": 1,
        "emergency_cob": 0x80 + k, "nodeguard_cob": 0x700 + k, "guard_time_ms": 0,
        "lifetime_factor": 0, "producer_ms": 0, "consumer_ms": 0, "heartbeat": 1,
        "name": "Unknow Device", "eds_name": "99999", "flag_a": 0, "flag_b": 0,
        "auto_sdo": [], "pre_pdo": "00" * 13,
        "slots": [default_slot(s % 2 == 0, s // 2 + 1) for s in range(N_PDO_SLOTS)],
        "in_offset": 0, "out_offset": 0, "trail": DEF_TRAIL[32:],
    }


def same_node(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def is_default_node(n):
    """Pusty wezel (poza bajtem flag_b, ktory w pliku zalezy od historii edycji)."""
    d = default_node(n["id"])
    d["flag_b"] = n["flag_b"]
    return same_node(n, d)


def slot_is_blank(sl, tx, nr):
    """Pusty slot PDO (nieskonfigurowany); jego indeks to 0 albo FFFF (zalezy od wezla)."""
    return (sl["index"] in (0, 0xFFFF)) and same_node(sl, default_slot(tx, nr, sl["index"]))


def blank_index(n):
    idx = [s["index"] for i, s in enumerate(n["slots"]) if slot_is_blank(s, i % 2 == 0, i // 2 + 1)]
    return 0 if idx and idx.count(0) > idx.count(0xFFFF) else 0xFFFF


# ---------------------------------------------------------------- JSON (kompaktowy)

def to_json(model):
    """Wezly identyczne z pustym wezlem domyslnym sa pomijane; w wezlach pomijane sa puste sloty PDO."""
    out = {"master": model["master"], "flag_b_by_node": [n["flag_b"] for n in model["nodes"]], "nodes": []}
    for k, n in enumerate(model["nodes"]):
        if is_default_node(n):
            continue
        c = dict(n)
        del c["flag_b"]
        bi = blank_index(n)
        c["blank_slot_index"] = bi   # indeks wpisany w pustych slotach PDO (pomijanych ponizej)
        c["slots"] = [s for i, s in enumerate(n["slots"])
                      if not (slot_is_blank(s, i % 2 == 0, i // 2 + 1) and s["index"] == bi)]
        out["nodes"].append(c)
    return out


def from_json(js):
    nodes = [default_node(k) for k in range(N_NODES)]
    fb = js.get("flag_b_by_node")
    if fb:
        for k in range(N_NODES):
            nodes[k]["flag_b"] = fb[k]
    for n in js["nodes"]:
        k = n["id"]
        if not 0 <= k < N_NODES:
            raise CopError("zly numer wezla: %r" % k)
        full = dict(n)
        full["flag_b"] = nodes[k]["flag_b"]
        bi = full.pop("blank_slot_index", 0xFFFF)
        slots = [default_slot(i % 2 == 0, i // 2 + 1, bi) for i in range(N_PDO_SLOTS)]
        for s in n["slots"]:
            i = (s["nr"] - 1) * 2 + (0 if s["dir"] == "Tx" else 1)
            if not 0 <= i < N_PDO_SLOTS:
                raise CopError("zly slot PDO: %r %r" % (s.get("dir"), s.get("nr")))
            slots[i] = s
        full["slots"] = slots
        nodes[k] = full
    return {"master": js["master"], "nodes": nodes}


# ---------------------------------------------------------------- opis tekstowy

BAUD = {6: "1 Mbps"}
TXTYPE = {254: "asynchroniczny (producent)", 255: "asynchroniczny (profil)", 0: "synchroniczny acykliczny"}


def txtype(t):
    if t in TXTYPE:
        return "%d (%s)" % (t, TXTYPE[t])
    if 1 <= t <= 240:
        return "%d (synchroniczny cykliczny)" % t
    return str(t)


def dreg(base, off):
    return "" if base is None else " = D%d" % (base + off // 2)


def dump_text(model, base_out=None, base_in=None):
    L = []
    m = model["master"]
    L.append("MASTER: %s  baud %s (kod %d)  SYNC COB-ID %d  okres %d x1000us  heartbeat %d ms  tryb %d"
             % (m["name"], BAUD.get(m["baud_code"], "kod %d" % m["baud_code"]), m["baud_code"],
                m["sync_cob"], m["cycle_ms"], m["heartbeat_ms"], m["work_mode"]))
    L.append("  ident: %s" % m["ident"])
    for k, n in enumerate(model["nodes"]):
        if is_default_node(n) or (n["name"] == "Unknow Device" and not n["auto_sdo"] and all(
                slot_is_blank(sl, i % 2 == 0, i // 2 + 1) for i, sl in enumerate(n["slots"]))):
            continue
        L.append("")
        L.append("WEZEL %d: %s (EDS %s)" % (n["id"], n["name"], n["eds_name"]))
        L.append("  Vendor %08X  DeviceType %08X  Product %08X  Revision %08X  (zaznaczone: %d%d%d%d)"
                 % (n["vendor_id"], n["device_type"], n["product_code"], n["revision"], n["check_vendor"],
                    n["check_device_type"], n["check_product"], n["check_revision"]))
        L.append("  Emergency COB %X  NodeGuard COB %X  heartbeat=%d  producer %d ms  consumer %d ms"
                 "  guard %d ms  lifetime %d"
                 % (n["emergency_cob"], n["nodeguard_cob"], n["heartbeat"], n["producer_ms"], n["consumer_ms"],
                    n["guard_time_ms"], n["lifetime_factor"]))
        L.append("  Mapowanie na rejestry: odczyt (Tx) +%d B%s, zapis (Rx) +%d B%s"
                 % (n["in_offset"], dreg(base_in, n["in_offset"]), n["out_offset"], dreg(base_out, n["out_offset"])))
        if n["auto_sdo"]:
            L.append("  Auto SDO (%d):" % len(n["auto_sdo"]))
            for e in n["auto_sdo"]:
                L.append("    %04X:%02X  dlugosc %d  dane %04X (%d)" % (e["index"], e["sub"], e["len"], e["data"], e["data"]))
        for i, s in enumerate(n["slots"]):
            if slot_is_blank(s, i % 2 == 0, i // 2 + 1):
                continue
            tx = (s["dir"] == "Tx")
            extra = ("  event %d ms  inhibit %d" % (s["event_timer"], s["inhibit_timer"])) if tx else ""
            L.append("  %sPDO%d  COB %X  indeks %04X  transmisja %s%s  (%d bitow)"
                     % (s["dir"], s["nr"], s["cob"], s["index"], txtype(s["type"]), extra, slot_bits(s)))
            for e in s["map"]:
                L.append("      %04X:%02X  %2d bity  %s" % (e["index"], e["sub"], e["bits"], e["name"]))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- polecenia

def load_cop(path):
    with open(path, "rb") as f:
        return f.read()


def roundtrip(data):
    model = parse(data)
    if build(model) != data:
        return False, "skladanie z modelu daje inny plik"
    back = from_json(json.loads(json.dumps(to_json(model))))
    if build(back) != data:
        return False, "skladanie z JSON daje inny plik"
    return True, ""


def main(argv):
    if len(argv) < 3 or argv[1] not in ("dump", "decode", "encode", "check"):
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "encode":
            if len(argv) < 4:
                print("uzycie: encode plik.json plik.cop")
                return 1
            with open(argv[2], "r", encoding="utf-8") as f:
                model = from_json(json.load(f))
            data = build(model)
            if os.path.exists(argv[3]):
                print("BLAD: plik %s juz istnieje (nie nadpisuje)" % argv[3])
                return 1
            with open(argv[3], "wb") as f:
                f.write(data)
            print("zapisano %s (%d bajtow)" % (argv[3], len(data)))
            return 0
        data = load_cop(argv[2])
        if cmd == "check":
            ok, why = roundtrip(data)
            print("OK: rozklad i skladanie daja identyczny plik (%d bajtow)" % len(data) if ok else "BLAD: " + why)
            return 0 if ok else 2
        model = parse(data)
        if cmd == "dump":
            bo = int(argv[3]) if len(argv) > 3 else None
            bi = int(argv[4]) if len(argv) > 4 else None
            sys.stdout.write(dump_text(model, bo, bi))
            return 0
        out = argv[3] if len(argv) > 3 else argv[2] + ".json"
        if os.path.exists(out):
            print("BLAD: plik %s juz istnieje (nie nadpisuje)" % out)
            return 1
        ok, why = roundtrip(data)
        if not ok:
            print("BLAD: " + why)
            return 2
        with open(out, "w", encoding="utf-8", newline="\r\n") as f:
            json.dump(to_json(model), f, ensure_ascii=False, indent=1)
        print("zapisano %s (test bezstratnosci OK)" % out)
        return 0
    except CopError as e:
        print("BLAD: %s" % e)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
