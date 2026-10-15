"""Dekoder/koder plikow projektu ISPSoft (.isp, .bak, .pnt).

Struktura pliku .isp (ustalona na podstawie porownania wersji):
  0x00..0xA3  naglowek binarny (little-endian)
      0x0C  u32  wersja zapisu (1020 = VERSION_FORSAVE)
      0x10  u32  CPU (3011 = AS228P, to samo co CPU= w .ini)
      0x78  u32  strona kodowa (1250)
      0x7C  u32  rozmiar danych po dekompresji
      0x92  u16  nieznane (nie jest to CRC16/suma - prawdopodobnie smieci)
      0x94  u32  dlugosc bloku danych (od offsetu danych do konca pliku)
      0x98  u32  offset bloku danych (0xA4)
  blok danych:
      u16  0x0008  (metoda?)
      u32  CRC32 danych po dekompresji
      ...  surowy strumien deflate (zlib wbits=-15)
Plik .pnt (magic "PNT1") ma naglowek 0x100 bajtow:
      0xF0  u32  dlugosc binarnego ogona za strumieniem deflate
      0xF4  u32  offset konca bloku danych
      0xF8  u32  dlugosc bloku danych
      0xFC  u32  offset bloku danych (0x100)

Uzycie:
  python isp_codec.py decode PROJEKT.isp [--force]
      Rozdziela projekt na pliki w folderze _autogen obok pliku .isp.
  python isp_codec.py encode PROJEKT.isp [--force]
      Sklada _autogen z powrotem do PROJEKT.isp (poprzednia wersja -> PROJEKT.isp.przed_encode).
      --force zapisuje plik takze wtedy, gdy tresc projektu sie nie zmienila.
  python isp_codec.py add-prg PROJEKT.isp NAZWA [--lang ST|LD] [--folder A/B] [--task 0|brak] [--kod plik.st]
  python isp_codec.py add-fb  PROJEKT.isp NAZWA [--lang ST|LD] [--folder A/B] [--kod plik.st]
  python isp_codec.py add-var PROJEKT.isp TABELA|POU NAZWA TYP [--adres D100] [--init 5]
                              [--komentarz "..."] [--klasa VAR_INPUT] [--nowa-tabela]
      Dodaja elementy w _autogen (--encode zapisuje od razu do .isp). Szczegoly: python isp_codec.py POLECENIE -h
  python isp_codec.py find-var PROJEKT.isp NAZWA
      Deklaracje zmiennej, miejsca zmiany wartosci, uzycie w warunkach i pozostale odczyty (ST i LD).
  python isp_codec.py copy-fb ZRODLO.isp CEL.isp FB [FB ...] [--folder F] [--globalne] [--nadpisz] [--dry-run]
      Kopiuje bloki funkcyjne z zaleznosciami (typy, FB uzyte jako instancje) do innego projektu.
  python isp_codec.py list-lib
      Projekty i bloki funkcyjne w folderze bibliotek. W kazdym poleceniu zamiast sciezki do .isp mozna podac
      [lib]/NAZWA.isp - folder bibliotek to %ISPSOFT_LIB% albo %USERPROFILE%/.claude/ispsoft/biblioteki.
  python isp_codec.py info PROJEKT.isp|MODEL
      Dane projektu i cala wiedza o sterowniku z folderu %USERPROFILE%/.claude/ispsoft/PLC
      (pliki AS.md, AS228.md, AS228P.md... - od ogolnych do szczegolowych).
  python isp_codec.py decode-txt PLIK.isp|.pnt [WYJSCIE.txt]
  python isp_codec.py encode-txt WZORZEC.isp TEKST.txt WYJSCIE.isp
      Caly projekt jako jeden plik tekstowy (do porownan i diagnostyki).

Uklad folderu _autogen:
  _naglowek.bin              naglowek binarny .isp (potrzebny do zakodowania)
  _zrodlo.txt                CRC tresci .isp, z ktorej powstal _autogen (ochrona przed nadpisaniem zmian z ISPSoft)
  _szkielet.txt              reszta projektu; znaczniki @@PLIK:sciezka@@ wskazuja wydzielone pliki
  zadania.txt                sekcja <TASK>
  drzewo_projektu.txt        sekcja <GroupPOUFolder> (foldery programow i FB)
  tabele_monitorowania.txt   sekcja <MONITOR_GROUPS>
  _kompilacja/instancje_FB.txt  sekcja <FBInstVAR> (adresy instancji FB, tworzy kompilator)
  zmienne_globalne/<tabela>.txt
  typy/<nazwa>.txt           STRUCT/ENUM; DutContent rozpisany na zwykle linie
  programy/<foldery>/<nazwa>.info|.csv|.st|.ld
  bloki_funkcyjne/<foldery>/<nazwa>.info|.csv|.st|.ld
      .info - naglowek POU ze znacznikami @@ZMIENNE@@ i @@KOD@@ (+ adresy W* przydzielone przez kompilator)
      .csv  - zmienne lokalne w formacie eksportu/importu ISPSoft (strona kodowa projektu)
      .st   - sam kod ST (do wklejenia w edytor ISPSoft), .ld - networki LD
      POU o nietypowej budowie zostaje w jednym pliku <nazwa>.txt
Pliki tekstowe sa w UTF-8 (oprocz .csv) z koncami linii CRLF; w .isp tekst jest w stronie kodowej projektu.
"""
import os
import re
import shutil
import struct
import sys
import zlib

AUTOGEN = '_autogen'
HEADER_FILE = '_naglowek.bin'
SKELETON_FILE = '_szkielet.txt'
SOURCE_FILE = '_zrodlo.txt'  # CRC32 tresci .isp, z ktorej powstal _autogen
INCLUDE_RE = re.compile(r'^@@PLIK:(.+)@@\r\n', re.M)
DUT_NEWLINE = 'PLCnnnnnnnewLineAndSubstitudeeeeeeePLC'


# --- kontener binarny -------------------------------------------------------

def _is_pnt(data):
    return data[:4] == b'PNT1'


def _data_offset(data):
    return struct.unpack_from('<I', data, 0xFC if _is_pnt(data) else 0x98)[0]


def decode(data):
    off = _data_offset(data)
    magic, crc = struct.unpack_from('<HI', data, off)
    if magic != 8:
        raise ValueError('nieoczekiwany znacznik bloku: %#x' % magic)
    raw = zlib.decompressobj(-15).decompress(data[off + 6:])
    if zlib.crc32(raw) != crc:
        raise ValueError('niezgodne CRC32')
    return raw


def encode(template, raw):
    off = _data_offset(template)
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = comp.compress(raw) + comp.flush()
    block = struct.pack('<HI', 8, zlib.crc32(raw)) + body
    hdr = bytearray(template[:off])
    if _is_pnt(template):
        tail_len = struct.unpack_from('<I', hdr, 0xF0)[0]
        tail = template[len(template) - tail_len:] if tail_len else b''
        struct.pack_into('<II', hdr, 0xF4, off + len(block), len(block))
        return bytes(hdr) + block + tail
    struct.pack_into('<I', hdr, 0x7C, len(raw))
    struct.pack_into('<I', hdr, 0x94, len(block))
    return bytes(hdr) + block


def codepage(raw):
    m = re.search(rb'^Active_CodePage=(\d+)\r$', raw, re.M)
    return 'cp' + m.group(1).decode() if m else 'cp1250'


# --- podzial tekstu na pliki ------------------------------------------------

def _safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')
    return name or '_'


def _sections(text, start, end):
    """Zwraca (poczatek, koniec) kazdej sekcji od linii `start` do linii `end` wlacznie z CRLF."""
    for m in re.finditer(r'^%s\r\n.*?^%s\r\n' % (re.escape(start), re.escape(end)), text, re.M | re.S):
        yield m.start(), m.end()


def _pou_folders(text):
    """Nazwa POU -> (folder glowny, lista podfolderow) na podstawie <GroupPOUFolder>."""
    result = {}
    for kind, root in (('ProgramFolder', 'programy'), ('FBFolder', 'bloki_funkcyjne')):
        m = re.search(r'<%s>\r\n(.*?)</%s>' % (kind, kind), text, re.S)
        if not m:
            continue
        for entry in re.finditer(r'ContentType=(-?\d+)\r\nContentName=(.*?)\r\nContentPath=(.*?)\r\n', m.group(1)):
            if entry.group(1) != '-1':
                result[entry.group(2)] = (root, [p for p in entry.group(3).split('/') if p])
    return result


def _dut_to_file(piece):
    def expand(m):
        return 'DutContent=\r\n' + m.group(1).replace(DUT_NEWLINE, '\r\n') + '\r\n'
    return re.sub(r'^DutContent=(.*)\r\n', expand, piece, count=1, flags=re.M)


def _dut_from_file(piece):
    m = re.search(r'^DutContent=\r\n(.*)\r\n</DUT_NODE>\r\n\Z', piece, re.M | re.S)
    if not m:
        return piece
    return piece[:m.start()] + 'DutContent=' + m.group(1).replace('\r\n', DUT_NEWLINE) + '\r\n</DUT_NODE>\r\n'


# --- POU jako trzy pliki: .info (naglowek), .csv (zmienne lokalne), .st/.ld (kod) ----

CSV_HEADER = 'Class,Identifiers,Address,Type,Initial Value,Comment'
VAR_MARK = '@@ZMIENNE@@\r\n'
CODE_MARK = '@@KOD@@\r\n'
COMPILED_MARK = '@@ADRESY_Z_KOMPILACJI@@\r\n'
_VAR_BLOCK_RE = re.compile(r'\{\r\n([^\r\n]*)\r\n\(\*\r\n(.*?)\r\n\*\)\r\n\}\r\n', re.S)
_DECL_RE = re.compile(r'^(\S+) : (.+?) := (.*) \[@([^@]*)@\] \{(\w+)\}$')


def _parse_local_vars(section):
    """Tresc miedzy <LOCAL_VAR> a </LOCAL_VAR> -> lista zmiennych albo None, gdy format nieznany."""
    if section == '':
        return []
    if not (section.startswith('<VAR>\r\n') and section.endswith('</VAR>\r\n')):
        return None
    body, pos, result = section[7:-8], 0, []
    for m in _VAR_BLOCK_RE.finditer(body):
        if m.start() != pos:
            return None
        d = _DECL_RE.match(m.group(1))
        if not d:
            return None
        name, typ, init, addr, cls = d.groups()
        result.append({'cls': cls, 'name': name, 'addr': addr, 'type': typ, 'init': init, 'comment': m.group(2)})
        pos = m.end()
    return result if pos == len(body) and result else None


def _format_local_vars(variables):
    if not variables:
        return ''
    blocks = ''.join('{\r\n%s : %s := %s [@%s@] {%s}\r\n(*\r\n%s\r\n*)\r\n}\r\n'
                     % (v['name'], v['type'], v['init'], v['addr'], v['cls'], v['comment']) for v in variables)
    return '<VAR>\r\n' + blocks + '</VAR>\r\n'


def _csv_field(value):
    value = value.replace('\r\n', '\r\r\n')  # nowa linia w komentarzu - tak zapisuje ISPSoft
    if ',' in value or '"' in value:
        value = '"' + value.replace('"', '""') + '"'
    return value


def csv_text(variables):
    """Zmienne lokalne w formacie eksportu/importu ISPSoft. Adresy W* (przydzielone przez kompilator) pomijane."""
    rows = [CSV_HEADER]
    for v in variables:
        addr = '' if v['addr'].upper().startswith('W') else v['addr']
        rows.append(','.join(_csv_field(x) for x in (v['cls'], v['name'], addr, v['type'], v['init'], v['comment'])))
    return '\r\n'.join(rows) + '\r\n'


def parse_csv(text):
    """Odczyt CSV zmiennych (format ISPSoft; akceptuje tez cudzyslowy i konce linii LF)."""
    records, fields, field, i, quoted = [], [], [], 0, False
    while i < len(text):
        c = text[i]
        if quoted:
            if c == '"' and text[i + 1:i + 2] == '"':
                field.append('"'); i += 2; continue
            if c == '"':
                quoted = False; i += 1; continue
            if text.startswith('\r\r\n', i) or text.startswith('\r\n', i):
                field.append('\n'); i += 3 if text.startswith('\r\r\n', i) else 2; continue
            field.append(c); i += 1; continue
        if c == '"' and not field:
            quoted = True; i += 1; continue
        if text.startswith('\r\r\n', i):
            field.append('\n'); i += 3; continue
        if c == ',':
            fields.append(''.join(field)); field = []; i += 1; continue
        if text.startswith('\r\n', i) or c == '\n':
            fields.append(''.join(field)); records.append(fields); fields, field = [], []
            i += 2 if c == '\r' else 1; continue
        field.append(c); i += 1
    if field or fields:
        fields.append(''.join(field)); records.append(fields)
    if not records or ','.join(records[0][:6]) != CSV_HEADER:
        raise ProjectError('plik CSV zmiennych musi zaczynac sie naglowkiem: ' + CSV_HEADER)
    result = []
    for n, r in enumerate(records[1:], 2):
        if r == ['']:
            continue
        if len(r) < 6:
            raise ProjectError('CSV zmiennych, rekord %d: oczekiwano 6 kolumn, jest %d' % (n, len(r)))
        cls, name, addr, typ, init, comment = r[:6]
        result.append({'cls': cls.strip().upper() or 'VAR', 'name': name.strip(), 'addr': addr.strip(),
                       'type': typ.strip(), 'init': init.strip(), 'comment': comment.replace('\n', '\r\n')})
    return result


def split_pou(text):
    """POU -> (info, csv, kod, rozszerzenie) albo None, gdy POU ma nieobslugiwana budowe (zostaje jako .txt)."""
    m = re.match(r'(.*?)<LOCAL_VAR>\r\n(.*?)</LOCAL_VAR>\r\n(.*)\Z', text, re.S)
    if not m:
        return None
    head, var_section, rest = m.groups()
    variables = _parse_local_vars(var_section)
    lang = re.search(r'^P_Lang=(\d+)\r\n', head, re.M)
    if variables is None or not lang:
        return None
    if lang.group(1) == LANGS['ST']:
        c = re.match(r'(<BOOKMARK_MAP>\r\n.*?</BOOKMARK_MAP>\r\n<IL_ST_CODE>\r\n)(.*)(</IL_ST_CODE>\r\n</POU>\r\n)\Z', rest, re.S)
        ext = '.st'
    elif lang.group(1) == LANGS['LD']:
        c = re.match(r'(.*?)(<NETWORK_START>\r\n.*<NETWORK_END>\r\n)(</POU>\r\n)\Z', rest, re.S)
        ext = '.ld'
    else:
        return None
    if not c:
        return None
    compiled = ''.join('%s=%s\r\n' % (v['name'], v['addr']) for v in variables if v['addr'].upper().startswith('W'))
    info = head + VAR_MARK + c.group(1) + CODE_MARK + c.group(3) + (COMPILED_MARK + compiled if compiled else '')
    parts = (info, csv_text(variables), c.group(2), ext)
    return parts if join_pou(*parts[:3]) == text else None


def join_pou(info, csv, code):
    compiled = {}
    if COMPILED_MARK in info:
        info, tail = info.split(COMPILED_MARK, 1)
        compiled = dict(line.split('=', 1) for line in tail.split('\r\n') if '=' in line)
    variables = parse_csv(csv)
    for v in variables:
        if not v['addr'] and v['name'] in compiled:
            v['addr'] = compiled[v['name']]
    if info.count(VAR_MARK) != 1 or info.count(CODE_MARK) != 1:
        raise ProjectError('plik .info musi zawierac po jednym znaczniku %s i %s' % (VAR_MARK.strip(), CODE_MARK.strip()))
    return info.replace(VAR_MARK, '<LOCAL_VAR>\r\n' + _format_local_vars(variables) + '</LOCAL_VAR>\r\n') \
               .replace(CODE_MARK, _normalize(code))


def _join_pou_files(base, read_file):
    info = _normalize(read_file(base + '.info'))
    try:
        code = read_file(base + '.st')
    except (KeyError, OSError):
        code = read_file(base + '.ld')
    return join_pou(info, read_file(base + '.csv'), code)


def split(text):
    """Dzieli tekst projektu na {sciezka_wzgledna: tresc} oraz szkielet ze znacznikami."""
    pieces = []  # (start, end, sciezka znacznika, {sciezka: tresc})
    folders = _pou_folders(text)

    for name, tag in (('zadania.txt', 'TASK'), ('drzewo_projektu.txt', 'GroupPOUFolder'),
                      ('tabele_monitorowania.txt', 'MONITOR_GROUPS'),
                      ('_kompilacja/instancje_FB.txt', 'FBInstVAR')):
        for s, e in _sections(text, '<%s>' % tag, '</%s>' % tag):
            pieces.append((s, e, name, {name: text[s:e]}))

    m = re.search(r'^<GLOBAL_VAR>\r\n(.*?)^</GLOBAL_VAR>\r\n', text, re.M | re.S)
    if m:
        body_start = m.start(1)
        starts = [body_start + t.start() for t in re.finditer(r'^TableName=', m.group(1), re.M)]
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else m.end(1)
            table = re.match(r'TableName=(.*)\r\n', text[s:e]).group(1)
            path = 'zmienne_globalne/%s.txt' % _safe_name(table)
            pieces.append((s, e, path, {path: text[s:e]}))

    for s, e in _sections(text, '<DUT_NODE>', '</DUT_NODE>'):
        name = re.search(r'^DutName=(.*)\r\n', text[s:e], re.M).group(1)
        path = 'typy/%s.txt' % _safe_name(name)
        pieces.append((s, e, path, {path: _dut_to_file(text[s:e])}))

    for s, e in _sections(text, '<POU>', '</POU>'):
        name = re.search(r'^P_Name=(.*)\r\n', text[s:e], re.M).group(1)
        is_fb = re.search(r'^P_type=1\r\n', text[s:e], re.M)
        root, sub = folders.get(name, ('bloki_funkcyjne' if is_fb else 'programy', []))
        base = '/'.join([root] + [_safe_name(p) for p in sub] + [_safe_name(name)])
        parts = split_pou(text[s:e])
        if parts:
            info, csv, code, ext = parts
            pieces.append((s, e, base + '.info', {base + '.info': info, base + '.csv': csv, base + ext: code}))
        else:
            pieces.append((s, e, base + '.txt', {base + '.txt': text[s:e]}))

    pieces.sort(key=lambda p: p[0])
    files, skeleton, pos = {}, [], 0
    for s, e, path, contents in pieces:
        if s < pos:
            raise ValueError('nakladajace sie sekcje przy %s' % path)
        for p in contents:
            if p.lower() in (f.lower() for f in files):
                raise ValueError('powtorzona nazwa pliku: %s' % p)
        skeleton.append(text[pos:s])
        skeleton.append('@@PLIK:%s@@\r\n' % path)
        files.update(contents)
        pos = e
    skeleton.append(text[pos:])
    return ''.join(skeleton), files


def _normalize(content):
    content = content.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')
    if content and not content.endswith('\r\n'):
        content += '\r\n'
    return content


def join(skeleton, read_file):
    def include(m):
        path = m.group(1)
        if path.endswith('.info'):
            return _join_pou_files(path[:-5], read_file)
        content = _normalize(read_file(path))
        return _dut_from_file(content) if path.startswith('typy/') else content
    return INCLUDE_RE.sub(include, _normalize(skeleton))


# --- operacje na folderze _autogen ------------------------------------------

def _read_text(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8-sig')


def _write_text(path, text, cp=None):
    """Zapis UTF-8; pliki .csv w stronie kodowej projektu (tak jak eksport zmiennych z ISPSoft)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(text.encode(cp if path.lower().endswith('.csv') and cp else 'utf-8'))


def _read_any(path, cp):
    data = open(path, 'rb').read()
    if path.lower().endswith('.csv'):
        try:
            return data.decode('utf-8-sig')
        except UnicodeDecodeError:
            return data.decode(cp)
    return data.decode('utf-8-sig')


def _skeleton_codepage(skeleton):
    m = re.search(r'^Active_CodePage=(\d+)\r?$', skeleton, re.M)
    return 'cp' + m.group(1) if m else 'cp1250'


def build_from_dir(folder):
    header = open(os.path.join(folder, HEADER_FILE), 'rb').read()
    skeleton = _read_text(os.path.join(folder, SKELETON_FILE))
    cp = _skeleton_codepage(skeleton)
    text = join(skeleton, lambda p: _read_any(os.path.join(folder, *p.split('/')), cp))
    return encode(header, text.encode(cp))


def decode_to_dir(isp_path, force=False):
    data = open(isp_path, 'rb').read()
    raw = decode(data)
    text = raw.decode(codepage(raw))
    skeleton, files = split(text)
    if join(skeleton, files.__getitem__).encode(codepage(raw)) != raw:
        raise ValueError('podzial nie jest odwracalny - przerwano, nic nie zapisano')

    folder = os.path.join(os.path.dirname(os.path.abspath(isp_path)), AUTOGEN)
    if os.path.isdir(folder) and not force and has_unsaved_changes(folder, raw):
        raise SystemExit('%s zawiera zmiany niezapisane do %s. '
                         'Uzyj "encode" albo "decode --force" (zmiany zostana utracone).' % (folder, isp_path))
    os.makedirs(folder, exist_ok=True)
    foreign = _foreign_files(folder)
    if foreign and not force:
        raise SystemExit('%s zawiera pliki, ktorych nie utworzylo narzedzie - przenies je albo uzyj "decode --force" '
                         '(zostana usuniete):\n  %s' % (folder, '\n  '.join(foreign)))
    _clear_dir(folder)
    with open(os.path.join(folder, HEADER_FILE), 'wb') as f:
        f.write(data[:_data_offset(data)])
    _write_text(os.path.join(folder, SKELETON_FILE), skeleton)
    for path, content in files.items():
        _write_text(os.path.join(folder, *path.split('/')), content, codepage(raw))

    _write_source(folder, raw)

    rebuilt = build_from_dir(folder)
    if decode(rebuilt) != raw or rebuilt[:_data_offset(data)] != _patched_header(data, rebuilt):
        raise ValueError('kontrola: zakodowany _autogen nie odtwarza tresci projektu')
    # ISPSoft nie zawsze kompresuje tak samo jak zlib (np. duze projekty) - wtedy roznia sie tylko bajty deflate
    return folder, len(files), rebuilt == data


def _clear_dir(folder):
    """Usuwa zawartosc folderu; foldery zablokowane przez inne programy (eksplorator, edytor) zostaja puste."""
    for entry in os.listdir(folder):
        path = os.path.join(folder, entry)
        if os.path.isdir(path):
            _clear_dir(path)
            try:
                os.rmdir(path)
            except OSError:
                pass
        else:
            os.remove(path)


def _foreign_files(folder):
    """Pliki w _autogen, ktore nie pochodza z narzedzia (nie sa wskazane w szkielecie)."""
    skeleton_path = os.path.join(folder, SKELETON_FILE)
    if not os.path.isfile(skeleton_path):
        return []
    known = {HEADER_FILE, SKELETON_FILE, SOURCE_FILE}
    for rel in INCLUDE_RE.findall(_normalize(_read_text(skeleton_path))):
        known.add(rel)
        if rel.endswith('.info'):
            known.update(rel[:-5] + ext for ext in ('.csv', '.st', '.ld'))
    known = {k.lower() for k in known}
    found = []
    for root, _, names in os.walk(folder):
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), folder).replace(os.sep, '/')
            if rel.lower() not in known:
                found.append(rel)
    return sorted(found)


def _crc(raw):
    return '%08x' % zlib.crc32(raw)


def _read_source(folder):
    try:
        return open(os.path.join(folder, SOURCE_FILE)).read().strip()
    except OSError:
        return None


def _write_source(folder, raw):
    with open(os.path.join(folder, SOURCE_FILE), 'w') as f:
        f.write(_crc(raw) + '\n')


def has_unsaved_changes(folder, isp_raw):
    """Czy _autogen zawiera zmiany, ktorych nie ma w pliku .isp, z ktorego powstal."""
    try:
        built = decode(build_from_dir(folder))
    except (OSError, ValueError, AttributeError):
        return False  # niekompletny _autogen - nie ma czego chronic
    source = _read_source(folder)
    return _crc(built) != source if source else built != isp_raw


def check_source(folder, isp_path):
    """Blad, jesli .isp zmieniono po decode (np. zapis w ISPSoft) - edycja _autogen nadpisalaby te zmiany."""
    if not os.path.exists(isp_path):
        return
    raw = decode(open(isp_path, 'rb').read())
    source = _read_source(folder)
    if source is None:
        if decode(build_from_dir(folder)) == raw:
            _write_source(folder, raw)
            return
        source = ''
    if _crc(raw) != source:
        raise ProjectError('%s zmieniono po ostatnim decode (np. zapis w ISPSoft). '
                           'Uruchom: python isp_codec.py decode "%s"' % (isp_path, isp_path))


def _patched_header(original, rebuilt):
    """Naglowek oryginalu z polami rozmiarow wzietymi z pliku przebudowanego."""
    hdr = bytearray(original[:_data_offset(original)])
    if not _is_pnt(original):
        hdr[0x7C:0x80] = rebuilt[0x7C:0x80]
        hdr[0x94:0x98] = rebuilt[0x94:0x98]
    return bytes(hdr)


def encode_from_dir(isp_path, force=False):
    folder = os.path.join(os.path.dirname(os.path.abspath(isp_path)), AUTOGEN)
    data = build_from_dir(folder)
    raw = decode(data)  # kontrola
    if not force:
        check_source(folder, isp_path)
    if os.path.exists(isp_path):
        old = open(isp_path, 'rb').read()
        if not force and (old == data or (decode(old) == decode(data) and _patched_header(old, data) == data[:_data_offset(data)])):
            return None
        shutil.copyfile(isp_path, isp_path + '.przed_encode')
    with open(isp_path, 'wb') as f:
        f.write(data)
    _write_source(folder, raw)
    return len(data)


# --- dodawanie elementow projektu (add-prg / add-fb / add-var) --------------

IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
LANGS = {'ST': '4', 'LD': '1'}
FB_CLASSES = ('VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT')
TREE_ENTRY = '<FolderContent>\r\nContentType=%s\r\nContentName=%s\r\nContentPath=%s\r\n</FolderContent>\r\n'
TREE_KINDS = (('ProgramFolder', 'programy', '0'), ('FBFolder', 'bloki_funkcyjne', '1'))


class ProjectError(Exception):
    pass


def _comment_block(comment):
    """Komentarz ISPSoft: (* / linie / *) - pusty komentarz to jedna pusta linia."""
    comment = (comment or '').replace('\\n', '\n')
    if '*)' in comment:
        raise ProjectError('komentarz nie moze zawierac "*)"')
    lines = comment.replace('\r\n', '\n').split('\n')
    return '(*\r\n' + '\r\n'.join(lines) + '\r\n*)\r\n'


def _check_field(value, what):
    if value and re.search(r'[;\r\n@\[\]{}]', value):
        raise ProjectError('niedozwolone znaki w polu %s: %r' % (what, value))


class Project:
    """Edycja rozlozonego projektu w folderze _autogen (wymaga wczesniejszego decode)."""

    def __init__(self, isp_path):
        self.isp_path = isp_path
        self.folder = os.path.join(os.path.dirname(os.path.abspath(isp_path)), AUTOGEN)
        if not os.path.isfile(os.path.join(self.folder, SKELETON_FILE)):
            decode_to_dir(isp_path)
        try:
            check_source(self.folder, isp_path)
        except ProjectError:
            # .isp zapisano w ISPSoft po decode - jesli w _autogen nie ma wlasnych zmian, wystarczy go odswiezyc
            if has_unsaved_changes(self.folder, None):
                raise ProjectError('%s zapisano w ISPSoft po ostatnim decode, a _autogen ma niezapisane zmiany - konflikt. '
                                   'Zapisz zmiany z _autogen recznie albo porzuc je: decode --force' % isp_path)
            decode_to_dir(isp_path)
            print('(odswiezono _autogen - %s zapisano w ISPSoft po ostatnim decode)' % isp_path)
        self.cp = _skeleton_codepage(_read_text(os.path.join(self.folder, SKELETON_FILE)))
        self.tree = self._parse_tree()

    # pliki (.csv bez normalizacji koncow linii - ISPSoft zapisuje w nich nowa linie komentarza jako CR CR LF)
    def _path(self, rel):
        return os.path.join(self.folder, *rel.split('/'))

    def read(self, rel):
        text = _read_any(self._path(rel), self.cp)
        return text if rel.lower().endswith('.csv') else _normalize(text)

    def write(self, rel, text):
        _write_text(self._path(rel), text if rel.lower().endswith('.csv') else _normalize(text), self.cp)

    def exists(self, rel):
        return os.path.isfile(self._path(rel))

    # drzewo projektu
    def _parse_tree(self):
        text = self.read('drzewo_projektu.txt')
        tree = {}
        for kind, _, _ in TREE_KINDS:
            m = re.search(r'<%s>\r\n(.*?)</%s>\r\n' % (kind, kind), text, re.S)
            body = m.group(1) if m else ''
            entries = [e.groups() for e in re.finditer(
                r'<FolderContent>\r\nContentType=(-?\d+)\r\nContentName=(.*?)\r\nContentPath=(.*?)\r\n</FolderContent>\r\n', body)]
            if ''.join(TREE_ENTRY % e for e in entries) != body:
                raise ProjectError('nieznany format drzewa projektu (%s)' % kind)
            tree[kind] = [list(e) for e in entries]
        if self._tree_text(tree) != text:
            raise ProjectError('nieznany format pliku drzewo_projektu.txt')
        return tree

    @staticmethod
    def _tree_text(tree):
        parts = ['<GroupPOUFolder>\r\n']
        for kind, _, _ in TREE_KINDS:
            parts.append('<%s>\r\n' % kind + ''.join(TREE_ENTRY % tuple(e) for e in tree[kind]) + '</%s>\r\n' % kind)
        return ''.join(parts) + '</GroupPOUFolder>\r\n'

    def pou_names(self):
        return {e[1]: kind for kind, _, _ in TREE_KINDS for e in self.tree[kind] if e[0] != '-1'}

    def pou_base(self, name):
        """Sciezka POU bez rozszerzenia (pliki: .info/.csv/.st|.ld albo pojedynczy .txt)."""
        for kind, root, _ in TREE_KINDS:
            for typ, ename, path in self.tree[kind]:
                if typ != '-1' and ename == name:
                    sub = [_safe_name(p) for p in path.split('/') if p]
                    return '/'.join([root] + sub + [_safe_name(name)])
        return None

    def pou_file(self, name):
        """Plik wskazywany w szkielecie: .info (POU rozdzielony) albo .txt (POU w jednym pliku)."""
        base = self.pou_base(name)
        if base is None:
            return None
        return base + '.txt' if self.exists(base + '.txt') else base + '.info'

    def pou_source(self, name):
        """(jezyk, zmienne lokalne, kod, plik z kodem, numer linii poczatku kodu w tym pliku)."""
        rel = self.pou_file(name)
        if rel.endswith('.info'):
            base = rel[:-5]
            lang = 'LD' if self.exists(base + '.ld') else 'ST'
            code_rel = base + ('.ld' if lang == 'LD' else '.st')
            return lang, parse_csv(self.read(base + '.csv')), self.read(code_rel), code_rel, 1
        text = self.read(rel)
        lang = 'LD' if re.search(r'^P_Lang=1\r\n', text, re.M) else 'ST'
        variables = []
        for m in _VAR_BLOCK_RE.finditer(text):
            d = _DECL_RE.match(m.group(1))
            if d:
                variables.append(dict(zip(('name', 'type', 'init', 'addr', 'cls'), d.groups()), comment=m.group(2)))
        pattern = r'<IL_ST_CODE>\r\n(.*)</IL_ST_CODE>' if lang == 'ST' else r'(<NETWORK_START>.*<NETWORK_END>\r\n)'
        m = re.search(pattern, text, re.S)
        if not m:
            return lang, variables, '', rel, 1
        return lang, variables, m.group(1), rel, text[:m.start(1)].count('\r\n') + 1

    def _insert_tree(self, kind, typ, name, folder_parts):
        entries = self.tree[kind]
        for i in range(len(folder_parts)):
            path = '/'.join(folder_parts[:i + 1]) + '/'
            if any(e[0] == '-1' and e[2] == path for e in entries):
                continue
            parent = '/'.join(folder_parts[:i]) + '/' if i else ''
            if parent:
                pos = next(j for j, e in enumerate(entries) if e[0] == '-1' and e[2] == parent) + 1
            else:  # foldery glownego poziomu sa przed elementami z korzenia
                pos = next((j for j, e in enumerate(entries) if e[2] == ''), len(entries))
            entries.insert(pos, ['-1', folder_parts[i], path])
        path = '/'.join(folder_parts) + '/' if folder_parts else ''
        idx = [j for j, e in enumerate(entries) if e[2].startswith(path)] if path else list(range(len(entries)))
        entries.insert(idx[-1] + 1 if idx else len(entries), [typ, name, path])
        self.write('drzewo_projektu.txt', self._tree_text(self.tree))

    def _sync_pou_includes(self):
        """Znaczniki POU w szkielecie zaraz za drzewem projektu, w kolejnosci drzewa."""
        skeleton = self.read(SKELETON_FILE)
        skeleton = re.sub(r'^@@PLIK:(programy|bloki_funkcyjne)/.*@@\r\n', '', skeleton, flags=re.M)
        marker = '@@PLIK:drzewo_projektu.txt@@\r\n'
        if marker not in skeleton:
            raise ProjectError('brak znacznika drzewa projektu w szkielecie')
        names = [e[1] for kind, _, _ in TREE_KINDS for e in self.tree[kind] if e[0] != '-1']
        includes = ''.join('@@PLIK:%s@@\r\n' % self.pou_file(n) for n in names)
        self.write(SKELETON_FILE, skeleton.replace(marker, marker + includes, 1))

    # typy i zmienne globalne
    def dut_names(self):
        folder = self._path('typy')
        if not os.path.isdir(folder):
            return []
        return [re.search(r'^DutName=(.*)\r\n', self.read('typy/' + f), re.M).group(1) for f in os.listdir(folder)]

    def global_tables(self):
        """Nazwa tabeli -> sciezka pliku."""
        folder = self._path('zmienne_globalne')
        tables = {}
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                rel = 'zmienne_globalne/' + f
                tables[re.match(r'TableName=(.*)\r\n', self.read(rel)).group(1)] = rel
        return tables

    def global_var_names(self):
        names = {}
        for table, rel in self.global_tables().items():
            for m in re.finditer(r'^\{\r\n\w+\r\n(\w+)\r\n', self.read(rel), re.M):
                names[m.group(1).upper()] = table
        return names

    # polecenia
    def add_pou(self, name, is_fb, lang='ST', folder='', task='0', comment='', code=''):
        if not IDENT_RE.match(name):
            raise ProjectError('niepoprawna nazwa POU: %r' % name)
        lang = lang.upper()
        if lang not in LANGS:
            raise ProjectError('jezyk %s nieobslugiwany (dostepne: %s)' % (lang, ', '.join(LANGS)))
        taken = {n.upper() for n in list(self.pou_names()) + self.dut_names()}
        if name.upper() in taken:
            raise ProjectError('nazwa %s jest juz uzyta w projekcie' % name)
        parts = [p for p in folder.replace('\\', '/').split('/') if p]
        for p in parts:
            _check_field(p, 'folder')

        head = ['<POU>', 'P_Name=' + name, 'P_En_Eno=TRUE', 'P_Last_Chg=', 'P_type=' + ('1' if is_fb else '0'),
                'P_Rtn_Type=', 'P_Lang=' + LANGS[lang], 'P_Step=0', 'P_Version=1.00', 'P_DeltaFB=FALSE',
                'P_Security=', 'P_Active=TRUE', 'P_Priority=9999', 'P_DFBName=']
        text = '\r\n'.join(head) + '\r\n' + _comment_block(comment) + '<LOCAL_VAR>\r\n</LOCAL_VAR>\r\n'
        if lang == 'ST':
            body = _normalize(code) if code.strip() else '\r\n'
            text += '<BOOKMARK_MAP>\r\n</BOOKMARK_MAP>\r\n<IL_ST_CODE>\r\n' + body + '</IL_ST_CODE>\r\n'
        else:
            if code.strip():
                raise ProjectError('kod startowy obslugiwany tylko dla ST (LD dostaje jeden pusty network)')
            text += ('<NETWORK_START>\r\n<PROPERTIES_START>\r\nNET_ID=1\r\nNET_LABEL=\r\nNET_ACTIVE=TRUE\r\n'
                     'NET_BOOKMARK=FALSE\r\nNET_MODIFY=TRUE\r\nNET_FOLD=FALSE\r\n(*\r\n\r\n*)\r\n<PROPERTIES_END>\r\n'
                     '<ROOTLINK_START>\r\n<ROOTLINK_END>\r\n<OUTLINK_START>\r\n<OUTLINK_END>\r\n<NETWORK_END>\r\n')
        text += '</POU>\r\n'

        kind, root, typ = TREE_KINDS[1] if is_fb else TREE_KINDS[0]
        base = '/'.join([root] + [_safe_name(x) for x in parts] + [_safe_name(name)])
        info, csv, code_text, ext = split_pou(text)
        files = {base + '.info': info, base + '.csv': csv, base + ext: code_text}
        for rel in list(files) + [base + '.txt']:
            if self.exists(rel):
                raise ProjectError('plik %s juz istnieje' % rel)
        # najpierw wszystkie kontrole, potem zapisy - blad nie zostawia polowicznych zmian
        task_text = self._task_text_with(name, task) if not is_fb and task not in (None, '', 'brak') else None
        self._insert_tree(kind, typ, name, parts)
        for rel, content in files.items():
            self.write(rel, content)
        rel = base + ext
        if task_text:
            self.write('zadania.txt', task_text)
        self._sync_pou_includes()
        return rel

    def _task_text_with(self, name, task_id):
        text = self.read('zadania.txt')
        blocks = list(re.finditer(r'^\[TASK_S\]\r\n(.*?)^\[TASK_E\]\r\n', text, re.M | re.S))
        ids = [re.search(r'^T_ID=(\d+)\r\n', b.group(1), re.M).group(1) for b in blocks]
        if str(task_id) not in ids:
            raise ProjectError('brak zadania T_ID=%s (dostepne: %s)' % (task_id, ', '.join(ids) or 'brak'))
        b = blocks[ids.index(str(task_id))]
        end = b.end(1)
        return text[:end] + 'T_PName=%s\r\n' % name + text[end:]

    def add_var(self, place, name, typ, address='', init='', comment='', cls='VAR', new_table=False):
        if not IDENT_RE.match(name):
            raise ProjectError('niepoprawna nazwa zmiennej: %r' % name)
        if not typ or re.search(r'[;\r\n@{}]', typ):
            raise ProjectError('niepoprawny typ: %r' % typ)
        _check_field(address, 'adres')
        _check_field(init, 'wartosc poczatkowa')
        cls = cls.upper()
        tables = {t.upper(): (t, rel) for t, rel in self.global_tables().items()}
        pous = {n.upper(): (n, k) for n, k in self.pou_names().items()}
        key = place.upper()
        if key in tables and key in pous:
            raise ProjectError('"%s" to zarowno tabela globalna, jak i POU - niejednoznaczne' % place)

        if key in pous:
            pou, kind = pous[key]
            allowed = FB_CLASSES if kind == 'FBFolder' else ('VAR',)
            if cls not in allowed:
                raise ProjectError('klasa %s niedozwolona w %s (dozwolone: %s)' % (cls, pou, ', '.join(allowed)))
            rel = self.pou_file(pou)
            if rel.endswith('.info'):
                rel = rel[:-5] + '.csv'
                variables = parse_csv(self.read(rel))
                if name.upper() in (v['name'].upper() for v in variables):
                    raise ProjectError('zmienna %s juz istnieje w %s' % (name, pou))
                variables.append({'cls': cls, 'name': name, 'addr': address, 'type': typ, 'init': init,
                                  'comment': _comment_block(comment)[4:-6]})  # tresc miedzy '(*' CRLF a CRLF '*)' CRLF
                self.write(rel, csv_text(variables))
                return '%s (zmienna lokalna %s)' % (rel, cls)
            text = self.read(rel)
            if re.search(r'^%s : ' % re.escape(name), text, re.M | re.I):
                raise ProjectError('zmienna %s juz istnieje w %s' % (name, pou))
            block = '{\r\n%s : %s := %s [@%s@] {%s}\r\n%s}\r\n' % (name, typ, init, address, cls, _comment_block(comment))
            if '</VAR>\r\n</LOCAL_VAR>\r\n' in text:
                text = text.replace('</VAR>\r\n</LOCAL_VAR>\r\n', block + '</VAR>\r\n</LOCAL_VAR>\r\n', 1)
            elif '<LOCAL_VAR>\r\n</LOCAL_VAR>\r\n' in text:
                text = text.replace('<LOCAL_VAR>\r\n</LOCAL_VAR>\r\n',
                                    '<LOCAL_VAR>\r\n<VAR>\r\n' + block + '</VAR>\r\n</LOCAL_VAR>\r\n', 1)
            else:
                raise ProjectError('nie znaleziono sekcji zmiennych lokalnych w %s' % rel)
            self.write(rel, text)
            return '%s (zmienna lokalna %s)' % (rel, cls)

        if cls != 'VAR':
            raise ProjectError('zmienne globalne maja klase VAR')
        existing = self.global_var_names()
        if name.upper() in existing:
            raise ProjectError('zmienna globalna %s juz istnieje (tabela %s)' % (name, existing[name.upper()]))
        block = '{\r\nVAR\r\n%s\r\n%s;%s;%s\r\n%s}\r\n' % (name, address, typ, init, _comment_block(comment))
        if key in tables:
            rel = tables[key][1]
            self.write(rel, self.read(rel) + block)
            return '%s (tabela %s)' % (rel, tables[key][0])
        if not new_table:
            raise ProjectError('nie ma tabeli globalnej ani POU o nazwie "%s" (tabele: %s). '
                               'Nowa tabela: --nowa-tabela' % (place, ', '.join(t for t, _ in tables.values())))
        _check_field(place, 'nazwa tabeli')
        rel = 'zmienne_globalne/%s.txt' % _safe_name(place)
        if self.exists(rel):
            raise ProjectError('plik %s juz istnieje' % rel)
        self.write(rel, 'TableName=%s\r\n' % place + block)
        skeleton = self.read(SKELETON_FILE)
        last = list(re.finditer(r'^@@PLIK:zmienne_globalne/.*@@\r\n', skeleton, re.M))
        pos = last[-1].end() if last else skeleton.index('<GLOBAL_VAR>\r\n') + len('<GLOBAL_VAR>\r\n')
        self.write(SKELETON_FILE, skeleton[:pos] + '@@PLIK:%s@@\r\n' % rel + skeleton[pos:])
        return '%s (nowa tabela %s)' % (rel, place)


# --- wyszukiwanie zmiennej (find-var) ----------------------------------------

LD_CONTACTS = {'1': 'styk NO', '2': 'styk NC', '3': 'styk zbocza narastajacego', '4': 'styk zbocza opadajacego'}
LD_COILS = {'13': 'cewka', '15': 'cewka SET', '16': 'cewka RESET'}


def _blank_st(code):
    """Usuwa komentarze i stale tekstowe (zastepuje spacjami, zachowujac nowe linie i pozycje)."""
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    return re.sub(r"\(\*.*?\*\)|/\*.*?\*/|//[^\n]*|'[^'\n]*'|\"[^\"\n]*\"", blank, code, flags=re.S)


def _name_regex(name):
    return re.compile(r'(?<![\w.#])' + re.escape(name) + r'(?![\w])', re.I)


def find_in_st(code, name):
    """Lista (kategoria, offset) wystapien zmiennej w kodzie ST."""
    clean = _blank_st(code.replace('\r\n', '\n'))
    spans = []
    for pattern in (r'\b(?:ELSIF|IF|WHILE)\b(.*?)\b(?:THEN|DO)\b', r'\bCASE\b(.*?)\bOF\b', r'\bUNTIL\b(.*?);'):
        spans += [(m.start(1), m.end(1)) for m in re.finditer(pattern, clean, re.I | re.S)]
    depth, depths = 0, []
    for ch in clean:
        depths.append(depth)
        depth += (ch == '(') - (ch == ')')
    result = []
    for m in _name_regex(name).finditer(clean):
        o, after = m.start(), clean[m.end():]
        suffix = re.match(r'(?:\.\w+|\[[^\]]*\])*\s*', after).group(0)
        rest = after[len(suffix):]
        if any(s <= o < e for s, e in spans):
            kind = 'warunek'
        elif rest.startswith(':=') or rest.startswith('=>'):
            if depths[o] > 0:
                continue  # nazwa parametru formalnego w wywolaniu FB (np. Czas := Czas)
            kind = 'zapis'
        elif clean[:o].rstrip().endswith('=>'):
            kind = 'zapis'  # wyjscie FB przypisane do zmiennej: Out => zmienna
        elif rest.startswith('(') and not suffix.strip('. \t\n'):
            kind = 'wywolanie'
        else:
            kind = 'odczyt'
        result.append((kind, clean[:o].count('\n')))
    return result


def find_in_ld(code, name):
    """Lista (kategoria, linia, opis) wystapien zmiennej w networkach LD."""
    rx = re.compile(r'^' + re.escape(name) + r'(?:[.\[].*)?$', re.I)
    result, net = [], '?'
    nodes = list(re.finditer(r'\[LD_NODE\]\r\n(.*?)\[END_LD_NODE\]', code, re.S))
    for i, m in enumerate(nodes):
        before = code[:m.start()]
        nets = re.findall(r'^NET_ID=(\d+)', before, re.M)
        net = nets[-1] if nets else '?'
        line = before.count('\r\n')
        body = m.group(1)
        typ = re.search(r'^TYPE=(\d+)', body, re.M).group(1)
        dev = re.search(r'^DEV_NAME=(.*)\r\n', body, re.M)
        dev = dev.group(1) if dev else ''
        operands = re.findall(r'^VAR_NAME=(.*)\r\n', body, re.M)
        where = 'network %s' % net
        if dev and rx.match(dev):
            if typ in LD_CONTACTS:
                result.append(('warunek', line, '%s: %s %s' % (where, LD_CONTACTS[typ], dev)))
            elif typ in LD_COILS:
                result.append(('zapis', line, '%s: %s %s' % (where, LD_COILS[typ], dev)))
            elif typ == '8':
                result.append(('wywolanie', line, '%s: wywolanie FB %s' % (where, dev)))
            else:
                result.append(('odczyt', line, '%s: element TYPE=%s %s' % (where, typ, dev)))
        for op in operands:
            if not rx.match(op):
                continue
            if typ == '12':
                result.append(('zapis', line, '%s: wyjscie instrukcji -> %s' % (where, op)))
                continue
            block = next((re.search(r'^TYPE=(\d+)', n.group(1), re.M).group(1) for n in nodes[i + 1:]
                          if re.search(r'^TYPE=(8|9|10)\r\n', n.group(1), re.M)), '')
            symb = next((re.search(r'^SYMB=(.*)\r\n', n.group(1), re.M) for n in nodes[i + 1:]
                         if re.search(r'^SYMB=', n.group(1), re.M)), None)
            symb = symb.group(1) if symb else '?'
            if block == '10':
                result.append(('warunek', line, '%s: porownanie %s, argument %s' % (where, symb, op)))
            else:
                result.append(('odczyt', line, '%s: wejscie instrukcji %s, argument %s' % (where, symb, op)))
    return result


def _find_var(project, name):
    base = name.split('.')[0].split('[')[0]
    out = {'deklaracje': [], 'zapis': [], 'warunek': [], 'odczyt': [], 'wywolanie': []}
    for table, rel in project.global_tables().items():
        for m in re.finditer(r'^\{\r\n(\w+)\r\n(\w+)\r\n([^;\r\n]*);([^;\r\n]*);([^\r\n]*)\r\n\(\*\r\n(.*?)\r\n\*\)', project.read(rel), re.M | re.S):
            if m.group(2).upper() == base.upper():
                out['deklaracje'].append('[globalna] tabela "%s": %s : %s%s%s%s' % (
                    table, m.group(2), m.group(4), ' @' + m.group(3) if m.group(3) else '',
                    ' := ' + m.group(5) if m.group(5) else '', '  // ' + ' / '.join(m.group(6).split('\r\n')) if m.group(6) else ''))
    for pou in project.pou_names():
        lang, variables, code, code_rel, first_line = project.pou_source(pou)
        local = [v for v in variables if v['name'].upper() == base.upper()]
        for v in local:
            out['deklaracje'].append('[lokalna] %s: %s %s : %s%s%s' % (
                pou, v['cls'], v['name'], v['type'], ' @' + v['addr'] if v['addr'] and not v['addr'].upper().startswith('W') else '',
                ' := ' + v['init'] if v['init'] else ''))
        scope = ' (lokalna)' if local else ''
        if lang == 'ST':
            lines = code.replace('\r\n', '\n').split('\n')
            for kind, idx in find_in_st(code, name):
                out[kind].append('%s:%d%s  %s' % (code_rel, first_line + idx, scope, lines[idx].strip()))
        else:
            for kind, idx, desc in find_in_ld(code, name):
                out[kind].append('%s:%d%s  %s' % (code_rel, first_line + idx, scope, desc))
    return out


def print_find_var(project, name):
    out = _find_var(project, name)
    titles = (('deklaracje', 'Deklaracje'), ('zapis', 'Zmiana wartosci'), ('warunek', 'Uzycie w warunkach'),
              ('odczyt', 'Pozostale odczyty'), ('wywolanie', 'Wywolania (FB)'))
    print('Zmienna: %s' % name)
    for key, title in titles:
        if key == 'wywolanie' and not out[key]:
            continue
        print('\n%s (%d):' % (title, len(out[key])))
        for line in out[key] or ['-']:
            print('  ' + line)
    return out


# --- kopiowanie blokow funkcyjnych z zaleznosciami (copy-fb) ----------------

ELEMENTARY = {
    'BOOL', 'BYTE', 'WORD', 'DWORD', 'LWORD', 'SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT',
    'REAL', 'LREAL', 'TIME', 'DATE', 'TOD', 'DT', 'TIME_OF_DAY', 'DATE_AND_TIME', 'STRING', 'WSTRING', 'TIMER',
    'COUNTER', 'ARRAY', 'OF', 'POINTER', 'TO'}


def _identifiers(text):
    return set(re.findall(r'(?<![\w.#])([A-Za-z_]\w*)', text))


def _dut_body(text):
    """Tresc definicji typu bez komentarzy (do szukania typow zaleznych)."""
    m = re.search(r'^DutContent=\r\n(.*)</DUT_NODE>', text, re.M | re.S)
    body = m.group(1) if m else text
    body = _blank_st(body.replace('\r\n', '\n'))
    m = re.search(r'\bTYPE\s+\w+\s*:(.*)\bEND_TYPE\b', body, re.S | re.I)
    return m.group(1) if m else body


class _Index:
    """Spis typow, FB i zmiennych globalnych projektu (nazwy bez rozrozniania wielkosci liter)."""

    def __init__(self, project):
        self.project = project
        self.duts = {}
        folder = project._path('typy')
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                rel = 'typy/' + f
                text = project.read(rel)
                self.duts[re.search(r'^DutName=(.*)\r\n', text, re.M).group(1).upper()] = (rel, text)
        self.fbs = {n.upper(): n for n, k in project.pou_names().items() if k == 'FBFolder'}
        self.pous = {n.upper(): n for n in project.pou_names()}
        self.globals = {}
        for table, rel in project.global_tables().items():
            for m in re.finditer(r'^\{\r\n(\w+)\r\n(\w+)\r\n([^;\r\n]*);([^;\r\n]*);([^\r\n]*)\r\n\(\*\r\n(.*?)\r\n\*\)',
                                 project.read(rel), re.M | re.S):
                addr = '' if m.group(3).upper().startswith('W') else m.group(3)  # W* przydziela kompilator
                self.globals[m.group(2).upper()] = {'table': table, 'name': m.group(2), 'addr': addr,
                                                    'type': m.group(4), 'init': m.group(5), 'comment': m.group(6)}


def fb_text(project, name):
    """Pelny tekst sekcji POU (bez adresow z kompilacji) - do porownan."""
    rel = project.pou_file(name)
    if rel.endswith('.txt'):
        return project.read(rel)
    base = rel[:-5]
    info = project.read(rel).split(COMPILED_MARK)[0]
    code = project.read(base + '.ld') if project.exists(base + '.ld') else project.read(base + '.st')
    return join_pou(info, project.read(base + '.csv'), code)


def resolve_fb_dependencies(src, names):
    """Zwraca (lista FB w kolejnosci zaleznosci, lista typow w kolejnosci zaleznosci, zmienne globalne, nieznane typy)."""
    idx = _Index(src)
    fbs, duts, globals_used, unknown = [], [], {}, set()
    visiting = set()

    def visit_dut(key):
        if key in visiting or any(d.upper() == key for d in duts):
            return
        visiting.add(key)
        rel, text = idx.duts[key]
        for ident in _identifiers(_dut_body(text)):
            k = ident.upper()
            if k in idx.duts and k != key:
                visit_dut(k)
        duts.append(re.search(r'^DutName=(.*)\r\n', text, re.M).group(1))

    def visit_fb(key):
        if key in visiting or any(f.upper() == key for f in fbs):
            return
        visiting.add(key)
        name = idx.fbs[key]
        lang, variables, code, _, _ = src.pou_source(name)
        local = {v['name'].upper() for v in variables}
        for v in variables:
            for ident in _identifiers(v['type']):
                k = ident.upper()
                if k in idx.duts:
                    visit_dut(k)
                elif k in idx.fbs:
                    visit_fb(k)
                elif k not in ELEMENTARY and not ident.isdigit():
                    unknown.add('%s (zmienna %s w %s)' % (ident, v['name'], name))
        text = _blank_st(code.replace('\r\n', '\n')) if lang == 'ST' else ' '.join(re.findall(r'^(?:DEV_NAME|VAR_NAME|SYMB)=(.*)$', code, re.M))
        for ident in re.findall(r'(?<![\w.#])([A-Za-z_]\w*)', text):
            k = ident.upper()
            if k in idx.duts:
                visit_dut(k)
            elif k in idx.globals and k not in local:
                globals_used.setdefault(k, (idx.globals[k], set()))[1].add(name)
                for t in _identifiers(idx.globals[k]['type']):  # np. globalna instancja innego FB
                    if t.upper() in idx.duts:
                        visit_dut(t.upper())
                    elif t.upper() in idx.fbs:
                        visit_fb(t.upper())
        fbs.append(name)

    for n in names:
        k = n.upper()
        if k not in idx.fbs:
            raise ProjectError('w projekcie zrodlowym nie ma bloku funkcyjnego %s' % n)
        visit_fb(k)
    return fbs, duts, globals_used, sorted(unknown)


def copy_fbs(src, dst, names, folder='', overwrite=False, dry_run=False, copy_globals=False, keep_addresses=False):
    fbs, duts, globals_used, unknown = resolve_fb_dependencies(src, names)
    s_idx, d_idx = _Index(src), _Index(dst)
    plan, problems = [], []

    for name in duts:
        key = name.upper()
        src_text = s_idx.duts[key][1]
        if key in d_idx.duts:
            same = d_idx.duts[key][1] == src_text
            plan.append(('typ', name, 'pominiety (identyczny)' if same else ('nadpisany' if overwrite else 'KONFLIKT')))
            if not same and not overwrite:
                problems.append('typ %s istnieje w projekcie docelowym i rozni sie' % name)
        elif key in d_idx.pous:
            problems.append('w projekcie docelowym POU %s ma te sama nazwe co typ' % name)
        else:
            plan.append(('typ', name, 'dodany'))
    for name in fbs:
        key = name.upper()
        if key in d_idx.fbs:
            same = fb_text(dst, d_idx.fbs[key]) == fb_text(src, name)
            plan.append(('FB', name, 'pominiety (identyczny)' if same else ('nadpisany' if overwrite else 'KONFLIKT')))
            if not same and not overwrite:
                problems.append('blok %s istnieje w projekcie docelowym i rozni sie' % name)
        elif key in d_idx.pous or key in d_idx.duts:
            problems.append('w projekcie docelowym jest juz element o nazwie %s' % name)
        else:
            plan.append(('FB', name, 'dodany'))
    for key, (g, users) in sorted(globals_used.items()):
        if key in d_idx.globals:
            state = 'jest w projekcie docelowym'
        elif copy_globals:
            state = 'dodana do tabeli "%s"%s' % (g['table'], ' z adresem ' + g['addr'] if keep_addresses and g['addr'] else ' bez adresu')
        else:
            state = 'BRAK w projekcie docelowym (uzyj --globalne)'
        plan.append(('globalna', '%s : %s%s (uzywa: %s)' % (g['name'], g['type'], ' @' + g['addr'] if g['addr'] else '',
                                                           ', '.join(sorted(users))), state))

    report = ['%-9s %-60s %s' % row for row in plan]
    report += ['typ spoza projektu (biblioteka ISPSoft?): ' + u for u in unknown]
    if problems:
        raise ProjectError('kopiowanie przerwane:\n  ' + '\n  '.join(report + problems))
    if dry_run:
        return report

    parts = [p for p in folder.replace('\\', '/').split('/') if p]
    for kind, name, state in plan:
        if kind == 'typ' and state in ('dodany', 'nadpisany'):
            _copy_dut(src, dst, s_idx, d_idx, name, state == 'nadpisany')
    for kind, name, state in plan:
        if kind == 'FB' and state in ('dodany', 'nadpisany'):
            _copy_fb(src, dst, name, parts, state == 'nadpisany')
    if copy_globals:
        for key, (g, _) in sorted(globals_used.items()):
            if key not in d_idx.globals:
                exists = g['table'].upper() in (t.upper() for t in dst.global_tables())
                dst.add_var(g['table'], g['name'], g['type'], g['addr'] if keep_addresses else '', g['init'],
                            g['comment'], 'VAR', new_table=not exists)
    return report


def _copy_dut(src, dst, s_idx, d_idx, name, replace):
    rel_src, text = s_idx.duts[name.upper()]
    if replace:
        dst.write(d_idx.duts[name.upper()][0], text)
        return
    rel = 'typy/%s.txt' % _safe_name(name)
    if dst.exists(rel):
        raise ProjectError('plik %s juz istnieje' % rel)
    dst.write(rel, text)
    skeleton = dst.read(SKELETON_FILE)
    if '</DUT_INFO>\r\n' not in skeleton:
        raise ProjectError('brak sekcji <DUT_INFO> w szkielecie projektu docelowego')
    dst.write(SKELETON_FILE, skeleton.replace('</DUT_INFO>\r\n', '@@PLIK:%s@@\r\n</DUT_INFO>\r\n' % rel, 1))


def _copy_fb(src, dst, name, folder_parts, replace):
    rel = src.pou_file(name)
    if rel.endswith('.txt'):
        files = {'.txt': src.read(rel)}
    else:
        base = rel[:-5]
        files = {'.info': src.read(rel).split(COMPILED_MARK)[0], '.csv': src.read(base + '.csv')}
        ext = '.ld' if src.exists(base + '.ld') else '.st'
        files[ext] = src.read(base + ext)
    if replace:
        old = dst.pou_file(name)
        old_base = old[:-5] if old.endswith('.info') else old[:-4]
        for e in ('.txt', '.info', '.csv', '.st', '.ld'):
            if dst.exists(old_base + e):
                os.remove(dst._path(old_base + e))
        target = old_base
    else:
        target = '/'.join(['bloki_funkcyjne'] + [_safe_name(p) for p in folder_parts] + [_safe_name(name)])
        for e in ('.txt', '.info', '.csv', '.st', '.ld'):
            if dst.exists(target + e):
                raise ProjectError('plik %s juz istnieje' % (target + e))
        dst._insert_tree('FBFolder', '1', name, folder_parts)
    for e, content in files.items():
        dst.write(target + e, content)
    dst._sync_pou_includes()


# --- folder ispsoft: biblioteki ([lib]) i wiedza o sterownikach (PLC) -------

LIB_PREFIX = '[lib]'


def home_dir():
    """Folder danych uzytkownika: %ISPSOFT_HOME% albo %USERPROFILE%/.claude/ispsoft."""
    return os.environ.get('ISPSOFT_HOME') or os.path.join(os.path.expanduser('~'), '.claude', 'ispsoft')


def lib_dir():
    """Folder bibliotek: %ISPSOFT_LIB% albo <folder ispsoft>/biblioteki."""
    return os.environ.get('ISPSOFT_LIB') or os.path.join(home_dir(), 'biblioteki')


def plc_dir():
    """Folder wiedzy o sterownikach: %ISPSOFT_PLC% albo <folder ispsoft>/PLC."""
    return os.environ.get('ISPSOFT_PLC') or os.path.join(home_dir(), 'PLC')


def plc_files(model):
    """Pliki .md z folderu PLC, ktorych nazwa jest poczatkiem nazwy modelu (AS.md, AS228.md, AS228P.md...)."""
    folder = plc_dir()
    if not model or not os.path.isdir(folder):
        return []
    found = [f for f in os.listdir(folder)
             if f.lower().endswith('.md') and model.upper().startswith(f[:-3].upper()) and f[:-3]]
    return [os.path.join(folder, f) for f in sorted(found, key=lambda f: (len(f), f.upper()))]


def project_info(isp_path):
    """Najwazniejsze dane projektu odczytane bez tworzenia _autogen."""
    data = open(isp_path, 'rb').read()
    raw = decode(data)
    text = raw.decode(codepage(raw)).replace('\r\n', '\n')

    def field(name):
        m = re.search(r'^%s=(.*)$' % name, text, re.M)
        return m.group(1).strip() if m else ''
    lines = ['Projekt: %s' % isp_path,
             '  nazwa: %s, sterownik: %s (kod CPU %d), ISPSoft: %s, strona kodowa: %s' % (
                 field('Prj_Name'), field('Prj_DT') or '?', struct.unpack_from('<I', data, 0x10)[0],
                 field('Prj_ISPVer'), field('Active_CodePage'))]
    for block in re.findall(r'^\[TASK_S\]\n(.*?)^\[TASK_E\]', text, re.M | re.S):
        tid = re.search(r'^T_ID=(\d+)', block, re.M).group(1)
        cyc = re.search(r'^T_CycTime=(\d+)', block, re.M)
        progs = re.findall(r'^T_PName=(.*)$', block, re.M)
        kind = 'cykliczne, %s ms' % (cyc.group(1) if cyc else '?') if tid == '0' else 'T_ID=%s' % tid
        lines.append('  zadanie %s: %s' % (kind, ', '.join(progs) or '(brak programow)'))
    pous = re.findall(r'^<POU>\nP_Name=(.*)\n(?:.*\n)*?P_type=(\d)\n(?:.*\n)*?P_Lang=(\d+)', text, re.M)
    langs = {v: k for k, v in LANGS.items()}
    for typ, title in (('0', 'programy'), ('1', 'bloki funkcyjne')):
        items = ['%s (%s)' % (n, langs.get(l, 'jezyk %s' % l)) for n, t, l in pous if t == typ]
        lines.append('  %s (%d): %s' % (title, len(items), ', '.join(items) or '-'))
    duts = re.findall(r'^DutName=(.*)$', text, re.M)
    lines.append('  typy (%d): %s' % (len(duts), ', '.join(duts) or '-'))
    tables = re.findall(r'^TableName=(.*)$', text, re.M)
    lines.append('  tabele zmiennych globalnych: %s' % (', '.join(tables) or '-'))
    ranges = [(d, up, lo) for up, lo, d in
              re.findall(r'^\[\w+_RANGE\]\n<UPPER>(\d+)\n<LOWER>(\d+)\n<(\w+)>', text, re.M)]
    if ranges:
        lines.append('  zakresy pamieci: ' + ', '.join('%s%s-%s%s' % (d, lo, d, up) for d, up, lo in ranges))
    retain = re.findall(r'^\[(\w)_DEVICE_START\]\n<BLOCK>\n(?:.*\n)*?RETAIN_S=(\d+)\nRETAIN_E=(\d+)', text, re.M)
    if retain:
        lines.append('  obszary retain: ' + ', '.join('%s%s-%s%s' % (d, s, d, e) for d, s, e in retain))
    return field('Prj_DT'), lines


def print_info(target):
    if target.lower().endswith('.isp') or os.path.isfile(target):
        model, lines = project_info(target)
        print('\n'.join(lines))
    else:
        model = target
    print('\nWiedza o sterowniku %s (folder %s):' % (model or '?', plc_dir()))
    files = plc_files(model)
    if not files:
        print('  brak plikow - dodaj np. %s (seria) albo %s (model)' % (
            os.path.join(plc_dir(), re.match(r'[A-Za-z]*', model or 'AS').group(0) + '.md'),
            os.path.join(plc_dir(), (model or 'MODEL') + '.md')))
    for path in files:
        print('\n===== %s =====' % os.path.basename(path))
        print(open(path, encoding='utf-8-sig').read().rstrip())


def resolve_isp(path):
    """[lib]/NAZWA.isp -> NAZWA.isp w folderze bibliotek (bezposrednio albo w podfolderze NAZWA/)."""
    if not path or not path.lower().startswith(LIB_PREFIX):
        return path
    rest = path[len(LIB_PREFIX):].lstrip('/\\')
    base = lib_dir()
    direct = os.path.join(base, *re.split(r'[/\\]', rest))
    candidates = [direct]
    name = os.path.basename(direct)
    if name.lower().endswith('.isp'):
        candidates.append(os.path.join(os.path.dirname(direct), name[:-4], name))
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise ProjectError('nie znaleziono %s w folderze bibliotek %s (sprawdzono: %s). Utworz w ISPSoft projekt '
                       'z co najmniej jednym programem i zapisz go tam (np. %s).'
                       % (rest, base, ', '.join(candidates), candidates[-1]))


def list_lib():
    base = lib_dir()
    if not os.path.isdir(base):
        print('Folder bibliotek %s nie istnieje. Utworz go i zapisz w nim projekt ISPSoft z co najmniej jednym '
              'programem (np. %s).' % (base, os.path.join(base, 'EXAMPLES', 'EXAMPLES.isp')))
        return
    found = []
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        if entry.lower().endswith('.isp') and os.path.isfile(path):
            found.append(path)
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, entry + '.isp')):
            found.append(os.path.join(path, entry + '.isp'))
    print('Folder bibliotek: %s' % base)
    if not found:
        print('  (brak projektow .isp)')
    for path in found:
        raw = decode(open(path, 'rb').read())
        text = raw.decode(codepage(raw))
        folders = _pou_folders(text)
        fbs = sorted('/'.join(sub + [name]) for name, (root, sub) in folders.items() if root == 'bloki_funkcyjne')
        print('\n[lib]/%s  (%d blokow funkcyjnych)' % (os.path.basename(path), len(fbs)))
        for fb in fbs:
            print('  ' + fb)


# --- linia polecen ----------------------------------------------------------

def _finish(args, message):
    print(message)
    if getattr(args, 'encode', False):
        size = encode_from_dir(args.isp)
        print('bez zmian' if size is None else 'zapisano %s %d bajtow' % (args.isp, size))
    else:
        print('zmiany sa w _autogen - zapisz je do .isp: python isp_codec.py encode "%s"' % args.isp)


def main(argv):
    import argparse
    p = argparse.ArgumentParser(prog='isp_codec.py', description='Projekty ISPSoft (.isp): rozkladanie, skladanie i edycja.',
                                epilog='Szczegoly formatu: FORMAT_ISP.md')
    sub = p.add_subparsers(dest='cmd', metavar='POLECENIE')

    s = sub.add_parser('decode', help='rozloz PROJEKT.isp do folderu _autogen')
    s.add_argument('isp')
    s.add_argument('--force', action='store_true', help='nadpisz _autogen mimo niezapisanych zmian')
    s = sub.add_parser('encode', help='zloz _autogen z powrotem do PROJEKT.isp')
    s.add_argument('isp')
    s.add_argument('--force', action='store_true', help='zapisz takze bez zmian w tresci')
    s = sub.add_parser('decode-txt', help='caly projekt jako jeden plik tekstowy')
    s.add_argument('isp')
    s.add_argument('out', nargs='?')
    s = sub.add_parser('encode-txt', help='zakoduj plik tekstowy z naglowkiem z WZORZEC.isp')
    s.add_argument('template')
    s.add_argument('txt')
    s.add_argument('out')

    for cmd, is_fb in (('add-prg', False), ('add-fb', True)):
        s = sub.add_parser(cmd, help='dodaj nowy %s' % ('blok funkcyjny' if is_fb else 'program'))
        s.add_argument('isp')
        s.add_argument('name', help='nazwa POU')
        s.add_argument('--lang', default='ST', help='ST (domyslnie) albo LD')
        s.add_argument('--folder', default='', help='folder w drzewie projektu, np. Funkcje/Transport (tworzony w razie potrzeby)')
        if not is_fb:
            s.add_argument('--task', default='0', help='T_ID zadania (0 = cykliczne, domyslnie); "brak" = bez przypisania')
        s.add_argument('--komentarz', default='', help='komentarz POU (\\n = nowa linia)')
        s.add_argument('--kod', default='', help='plik z poczatkowym kodem ST')
        s.add_argument('--encode', action='store_true', help='od razu zapisz zmiany do .isp')
        s.set_defaults(is_fb=is_fb)

    s = sub.add_parser('copy-fb', help='skopiuj bloki funkcyjne z zaleznosciami (typy, FB) do innego projektu')
    s.add_argument('src', help='projekt zrodlowy .isp (np. biblioteka EXAMPLES)')
    s.add_argument('isp', help='projekt docelowy .isp')
    s.add_argument('names', nargs='+', help='nazwy blokow funkcyjnych')
    s.add_argument('--folder', default='', help='folder w drzewie projektu docelowego dla nowych FB')
    s.add_argument('--nadpisz', action='store_true', help='nadpisz rozniace sie typy/FB w projekcie docelowym')
    s.add_argument('--globalne', action='store_true', help='dodaj brakujace zmienne globalne uzywane w kodzie FB')
    s.add_argument('--z-adresami', action='store_true', help='z --globalne: zachowaj adresy zmiennych globalnych')
    s.add_argument('--dry-run', action='store_true', help='tylko pokaz, co zostaloby skopiowane')
    s.add_argument('--encode', action='store_true', help='od razu zapisz zmiany do .isp')
    s = sub.add_parser('info', help='dane projektu i wszystkie informacje o jego sterowniku z folderu PLC')
    s.add_argument('target', help='PROJEKT.isp albo nazwa modelu, np. AS228P')
    s = sub.add_parser('list-lib', help='projekty i bloki funkcyjne w folderze bibliotek [lib]')
    s = sub.add_parser('find-var', help='gdzie zmienna jest zadeklarowana, zmieniana i uzywana w warunkach')
    s.add_argument('isp')
    s.add_argument('name', help='nazwa zmiennej, mozna z czlonem struktury, np. Dane.Silnik1 albo Zawor1.Otwarty')
    s = sub.add_parser('add-var', help='dodaj zmienna do tabeli globalnej albo do POU')
    s.add_argument('isp')
    s.add_argument('place', help='nazwa tabeli zmiennych globalnych albo programu/bloku funkcyjnego')
    s.add_argument('name', help='nazwa zmiennej')
    s.add_argument('type', help='typ, np. BOOL, WORD, ARRAY [10] OF INT, nazwa struktury/FB')
    s.add_argument('--adres', default='', help='adres, np. D100, M10, X0.3 (domyslnie bez adresu)')
    s.add_argument('--init', default='', help='wartosc poczatkowa')
    s.add_argument('--komentarz', default='', help='komentarz (\\n = nowa linia)')
    s.add_argument('--klasa', default='VAR', help='VAR (domyslnie), VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT (tylko w FB)')
    s.add_argument('--nowa-tabela', action='store_true', help='utworz tabele globalna, jesli nie istnieje')
    s.add_argument('--encode', action='store_true', help='od razu zapisz zmiany do .isp')

    args = p.parse_args(argv)
    try:  # polskie znaki w wynikach niezaleznie od strony kodowej konsoli
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    try:
        for attr in ('isp', 'src', 'template'):  # [lib]/NAZWA.isp -> folder bibliotek
            if getattr(args, attr, None):
                setattr(args, attr, resolve_isp(getattr(args, attr)))
        if args.cmd == 'decode':
            folder, count, identical = decode_to_dir(args.isp, force=args.force)
            print('zapisano', folder, '-', count, 'plikow, kontrola tresci OK' +
                  ('' if identical else ' (uwaga: inna kompresja niz w ISPSoft - po encode plik nie bedzie identyczny bajt w bajt)'))
        elif args.cmd == 'encode':
            size = encode_from_dir(args.isp, force=args.force)
            print('bez zmian' if size is None else 'zapisano %s %d bajtow' % (args.isp, size))
        elif args.cmd == 'decode-txt':
            raw = decode(open(args.isp, 'rb').read())
            out = args.out or args.isp + '.txt'
            open(out, 'wb').write(raw)
            print('zapisano', out, len(raw), 'bajtow')
        elif args.cmd == 'encode-txt':
            data = encode(open(args.template, 'rb').read(), open(args.txt, 'rb').read())
            decode(data)  # kontrola
            open(args.out, 'wb').write(data)
            print('zapisano', args.out, len(data), 'bajtow')
        elif args.cmd in ('add-prg', 'add-fb'):
            code = _read_text(args.kod) if args.kod else ''
            rel = Project(args.isp).add_pou(args.name, args.is_fb, args.lang, args.folder,
                                            getattr(args, 'task', None), args.komentarz, code)
            _finish(args, 'dodano %s' % rel)
        elif args.cmd == 'copy-fb':
            if os.path.abspath(args.src) == os.path.abspath(args.isp):
                raise ProjectError('projekt zrodlowy i docelowy to ten sam plik')
            report = copy_fbs(Project(args.src), Project(args.isp), args.names, args.folder, args.nadpisz,
                              args.dry_run, args.globalne, args.z_adresami)
            print(chr(10).join(report))
            if not args.dry_run:
                _finish(args, 'skopiowano do %s' % args.isp)
        elif args.cmd == 'info':
            print_info(resolve_isp(args.target))
        elif args.cmd == 'list-lib':
            list_lib()
        elif args.cmd == 'find-var':
            print_find_var(Project(args.isp), args.name)
        elif args.cmd == 'add-var':
            where = Project(args.isp).add_var(args.place, args.name, args.type, args.adres, args.init,
                                              args.komentarz, args.klasa, args.nowa_tabela)
            _finish(args, 'dodano %s -> %s' % (args.name, where))
        else:
            p.print_help()
            return 1
    except (ProjectError, ValueError, OSError) as e:
        print('BLAD:', e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
