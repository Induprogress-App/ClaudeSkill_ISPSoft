#!/usr/bin/env python3
"""isp_control - sterowanie otwartym oknem Delta ISPSoft bez GUI i bez ruszania myszy.

Polecenia:
  list                          lista okien ISPSoft (pid, tytul)
  open PROJEKT.isp              nowa instancja ISPSoft z projektem (wypisuje pid)
  close --pid N | --title T     zamkniecie okna ISPSoft ([--nie-zapisuj] odpowiada Nie na pytanie o zapis, [--force] konczy proces)
  compile [--pid N | --title T] kompilacja projektu otwartego w oknie i odczyt panelu Compile Message
  read    [--pid N | --title T] odczyt panelu Compile Message bez kompilacji
  st-open NAZWA                 otwiera w oknie blok funkcyjny / program ST z drzewa projektu (dwuklik)
  st-get [--blok N] [--od A --do B]            odczyt kodu ST z otwartego edytora (cale albo zakres linii)
  st-replace OD DO [--plik|--tekst|--usun]     zamiana linii OD..DO na nowe (DO = OD-1: wstawienie przed linia OD)

Dziala tylko w Windows, tylko biblioteka standardowa. Okno nie musi byc na wierzchu ani widoczne
(moze byc zminimalizowane): polecenie Compile jest wysylane jako wiadomosci myszy do paska narzedzi,
a lista komunikatow jest czytana z pamieci procesu ISPSoft.
Kod wyjscia: 0 = bez bledow, 1 = sa bledy kompilacji, 2 = blad narzedzia (brak okna, brak reakcji).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
kernel32.VirtualFreeEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
kernel32.IsWow64Process.argtypes = [wt.HANDLE, ctypes.POINTER(wt.BOOL)]
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
LVM_GETITEMCOUNT, LVM_DELETEALLITEMS, LVM_GETITEMTEXTW = 0x1004, 0x1009, 0x1073
PROCESS_ALL = 0x1F0FFF
MEM_COMMIT_RESERVE, MEM_RELEASE, PAGE_RW = 0x3000, 0x8000, 4

# Przycisk Compile na pasku "PLC": punkt w wspolrzednych klienta paska (ustalone w ISPSoft 3.24).
COMPILE_X, COMPILE_Y = 133, 10
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
WM_LBUTTONDBLCLK = 0x0203


class Blad(Exception):
    pass


def tekst_okna(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def klasa_okna(h):
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(h, buf, 128)
    return buf.value


def pid_okna(h):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def dzieci(h):
    """Wszystkie okna potomne (rekurencyjnie)."""
    wynik = []

    def cb(hh, _):
        wynik.append(hh)
        return True

    user32.EnumChildWindows(h, WNDENUMPROC(cb), 0)
    return wynik


def okna_ispsoft():
    """Glowne okna ISPSoft: okna najwyzszego poziomu z paskami narzedzi (TdxBarControl)."""
    kandydaci = []

    def cb(hh, _):
        if "ISPSoft" in tekst_okna(hh):
            kandydaci.append(hh)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    wynik = []
    for h in kandydaci:
        if any(klasa_okna(d) == "TdxBarControl" for d in dzieci(h)):
            wynik.append(h)
    return wynik


def wybierz_okno(pid=None, tytul=None):
    lista = okna_ispsoft()
    if pid is not None:
        lista = [h for h in lista if pid_okna(h) == pid]
    if tytul:
        lista = [h for h in lista if tytul.lower() in tekst_okna(h).lower()]
    if not lista:
        raise Blad("nie znaleziono okna ISPSoft (pid/tytul nie pasuja albo ISPSoft nie jest uruchomiony)")
    if len(lista) > 1:
        opis = "; ".join("pid %d '%s'" % (pid_okna(h), tekst_okna(h)) for h in lista)
        raise Blad("wiele okien ISPSoft, wskaz --pid albo --title: " + opis)
    return lista[0]


def znajdz_kontrolki(glowne, lista_opcjonalna=False):
    """Zwraca (pasek PLC, lista Compile Message). Lista bywa None, gdy panel jeszcze nie powstal
    (swieze okno ISPSoft tworzy go dopiero przy pierwszej kompilacji) i lista_opcjonalna=True."""
    pasek = None
    lista = None
    for d in dzieci(glowne):
        kl = klasa_okna(d)
        if kl == "TdxBarControl" and tekst_okna(d) == "PLC":
            pasek = d
        elif kl == "TListView":
            # najblizszy nazwany rodzic musi byc panelem "Compile Message" (obok bywa lista z "Transferring Report")
            rodzic = user32.GetParent(d)
            while rodzic and rodzic != glowne:
                nazwa = tekst_okna(rodzic)
                if nazwa:
                    if nazwa == "Compile Message":
                        lista = d
                    break
                rodzic = user32.GetParent(rodzic)
    if not pasek:
        raise Blad("nie znaleziono paska narzedzi PLC w oknie ISPSoft")
    if not lista and not lista_opcjonalna:
        raise Blad("nie znaleziono panelu Compile Message w oknie ISPSoft")
    return pasek, lista


class Lista:
    """Odczyt tekstu pozycji ListView z cudzego procesu."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.proc = kernel32.OpenProcess(PROCESS_ALL, False, pid_okna(hwnd))
        if not self.proc:
            raise Blad("brak dostepu do procesu ISPSoft (uruchom z tymi samymi uprawnieniami)")
        wow = wt.BOOL()
        kernel32.IsWow64Process(self.proc, ctypes.byref(wow))
        self.x86 = bool(wow.value)
        self.mem = kernel32.VirtualAllocEx(self.proc, None, 4096, MEM_COMMIT_RESERVE, PAGE_RW)
        if not self.mem:
            raise Blad("nie mozna zarezerwowac pamieci w procesie ISPSoft")

    def zamknij(self):
        if self.mem:
            kernel32.VirtualFreeEx(self.proc, self.mem, 0, MEM_RELEASE)
            self.mem = None
        kernel32.CloseHandle(self.proc)

    def liczba(self):
        return user32.SendMessageW(self.hwnd, LVM_GETITEMCOUNT, 0, None)

    def wyczysc(self):
        user32.SendMessageW(self.hwnd, LVM_DELETEALLITEMS, 0, None)

    def pozycja(self, i, kol=0):
        buf = self.mem + 256
        if self.x86:
            lvitem = struct.pack("<IiiIIIi", 1, i, kol, 0, 0, buf, 500) + b"\0" * 20
        else:
            lvitem = struct.pack("<IiiIIxxxxQi", 1, i, kol, 0, 0, buf, 500) + b"\0" * 28
        kernel32.WriteProcessMemory(self.proc, self.mem, lvitem, len(lvitem), None)
        kernel32.WriteProcessMemory(self.proc, buf, b"\0" * 1000, 1000, None)
        user32.SendMessageW(self.hwnd, LVM_GETITEMTEXTW, i, ctypes.c_void_p(self.mem))
        wyj = ctypes.create_string_buffer(1000)
        kernel32.ReadProcessMemory(self.proc, buf, wyj, 1000, None)
        surowe = wyj.raw
        # kontrolka zwraca tekst w ANSI (cp1250) albo w UTF-16, zaleznie od wersji
        if len(surowe) > 2 and surowe[1:2] == b"\0" and surowe[0:1] != b"\0":
            return surowe.decode("utf-16-le", "replace").split("\0")[0]
        return surowe.split(b"\0")[0].decode("cp1250", "replace")

    def wszystkie(self):
        return [self.pozycja(i) for i in range(self.liczba())]


def kliknij(pasek, x, y):
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(pasek, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.15)
    user32.PostMessageW(pasek, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.1)
    user32.PostMessageW(pasek, WM_LBUTTONUP, 0, lp)


def czekaj_na_wynik(glowne, timeout):
    """Czeka, az lista komunikatow sie pojawi i przestanie zmieniac. Liste szuka za kazdym razem od nowa:
    ISPSoft potrafi utworzyc ja dopiero przy kompilacji albo podmienic na nowa."""
    start = time.time()
    poprzedni = None
    while time.time() - start < timeout:
        time.sleep(1.0)
        hl = znajdz_kontrolki(glowne, lista_opcjonalna=True)[1]
        if not hl:
            continue
        lista = Lista(hl)
        try:
            akt = lista.wszystkie()
        finally:
            lista.zamknij()
        if akt and akt == poprzedni:
            return akt
        poprzedni = akt
    return poprzedni or []


def podsumuj(wiersze):
    bledy = [w for w in wiersze if w.startswith("Error")]
    ostrz = [w for w in wiersze if w.startswith("Warning")]
    return bledy, ostrz


def znajdz_exe(podany=None):
    """Sciezka do NewISPSoft.exe: --exe, zmienna ISPSOFT_DIR, uruchomiony ISPSoft albo najnowszy w Program Files."""
    import glob
    import os
    if podany:
        return podany
    if os.environ.get("ISPSOFT_DIR"):
        return os.path.join(os.environ["ISPSOFT_DIR"], "NewISPSoft.exe")
    for h in okna_ispsoft():
        proc = kernel32.OpenProcess(0x1000, False, pid_okna(h))  # PROCESS_QUERY_LIMITED_INFORMATION
        if proc:
            buf = ctypes.create_unicode_buffer(1024)
            n = wt.DWORD(1024)
            ok = kernel32.QueryFullProcessImageNameW(proc, 0, buf, ctypes.byref(n))
            kernel32.CloseHandle(proc)
            if ok:
                return buf.value
    for baza in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if baza:
            znalezione = sorted(glob.glob(os.path.join(baza, "Delta Industrial Automation", "ISPSoft*", "NewISPSoft.exe")))
            if znalezione:
                return znalezione[-1]
    raise Blad("nie znaleziono NewISPSoft.exe (podaj --exe albo ustaw ISPSOFT_DIR)")


def dialogi_procesu(pid):
    wynik = []

    def cb(hh, _):
        if pid_okna(hh) == pid and user32.IsWindowVisible(hh) and klasa_okna(hh) == "#32770":
            wynik.append(hh)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return wynik


def tekst_dialogu(dlg):
    return " | ".join(t for t in (tekst_okna(c) for c in dzieci(dlg) if klasa_okna(c) in ("Static", "Button")) if t)


def cmd_open(a):
    import os
    import subprocess
    plik = os.path.abspath(a.plik)
    if not os.path.isfile(plik):
        raise Blad("brak pliku projektu: " + plik)
    exe = znajdz_exe(a.exe)
    if not os.path.isfile(exe):
        raise Blad("brak pliku programu: " + exe)
    # projekt jako argument wiersza polecen (pelna sciezka z .isp); subprocess sam poprawnie cytuje spacje
    # start zminimalizowany i bez aktywacji: aktywne okno ignoruje wiadomosci myszy wysylane do paska narzedzi,
    # a przy okazji nowe okno nie zabiera fokusu uzytkownikowi
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    proc = subprocess.Popen([exe, plik], startupinfo=si)
    pid = proc.pid
    nazwa = os.path.splitext(os.path.basename(plik))[0].lower()
    start = time.time()
    glowne = None
    zaladowany = None
    while time.time() - start < a.timeout:
        time.sleep(0.5)
        for d in dialogi_procesu(pid):
            raise Blad("ISPSoft pokazal okno '%s': %s (pid %d zostaje uruchomiony)"
                       % (tekst_okna(d), tekst_dialogu(d), pid))
        if glowne is None:
            try:
                glowne = wybierz_okno(pid=pid)
            except Blad:
                continue
        if zaladowany is None and nazwa in tekst_okna(glowne).lower():
            zaladowany = time.time()
        if zaladowany and time.time() - zaladowany > 2.0:  # chwila na ewentualny dialog po zaladowaniu
            print("otwarto: pid %d  hwnd %d  %s" % (pid, glowne, tekst_okna(glowne)))
            return 0
    raise Blad("projekt nie otworzyl sie w %d s (tytul okna: '%s', pid %d)"
               % (a.timeout, tekst_okna(glowne) if glowne else "-", pid))


def cmd_close(a):
    """Zamyka okno ISPSoft (WM_CLOSE jak krzyzyk). Nie zamyka bez wskazania --pid albo --title."""
    if a.pid is None and not a.title:
        raise Blad("podaj --pid albo --title okna do zamkniecia (zeby nie zamknac okna uzytkownika przez pomylke)")
    glowne = wybierz_okno(a.pid, a.title)
    pid = pid_okna(glowne)
    tytul = tekst_okna(glowne)
    proc = kernel32.OpenProcess(0x100001, False, pid)  # SYNCHRONIZE | PROCESS_TERMINATE
    if not proc:
        raise Blad("brak dostepu do procesu ISPSoft pid %d" % pid)
    try:
        if a.force:
            kernel32.TerminateProcess(proc, 1)
            kernel32.WaitForSingleObject(proc, 5000)
            print("zakonczono przymusowo: pid %d  %s (niezapisane zmiany przepadly)" % (pid, tytul))
            return 0
        user32.PostMessageW(glowne, 0x0010, 0, None)  # WM_CLOSE
        odpowiedziano = False
        start = time.time()
        while time.time() - start < a.timeout:
            if kernel32.WaitForSingleObject(proc, 500) == 0:
                print("zamknieto: pid %d  %s" % (pid, tytul))
                return 0
            for d in dialogi_procesu(pid):
                if a.nie_zapisuj:
                    przycisk = user32.GetDlgItem(d, 7)  # IDNO ("Nie") - zamkniecie bez zapisu
                    if przycisk:
                        user32.SendMessageW(przycisk, 0x00F5, 0, None)  # BM_CLICK
                        odpowiedziano = True
                    if odpowiedziano:  # po odpowiedzi czekamy juz tylko na koniec procesu (mignie puste okno)
                        time.sleep(0.5)
                        continue
                raise Blad("ISPSoft pyta o decyzje przed zamknieciem ('%s': %s) - okno zostaje otwarte; "
                           "zapisz projekt w ISPSoft albo uzyj --force (niezapisane zmiany przepadna)"
                           % (tekst_okna(d), tekst_dialogu(d)))
        raise Blad("okno nie zamknelo sie w %d s (pid %d)" % (a.timeout, pid))
    finally:
        kernel32.CloseHandle(proc)


# ---------------------------------------------------------------------------------------------
# Edycja kodu ST w otwartym oknie (blok funkcyjny / program ST). Edytor to TSynEdit: caly tekst czyta sie
# przez WM_GETTEXT i ustawia przez WM_SETTEXT. Nie trzeba kursora, klawiatury ani schowka. Ustawienie tekstu
# resetuje kursor, przewiniecie i historie cofania edytora; kompilator widzi zmiane od razu.
# Kazda zmiana jest weryfikowana odczytem; przy rozbieznosci wraca oryginal.
# ---------------------------------------------------------------------------------------------

def edytor_st(glowne, blok=None):
    """Zwraca (nazwa bloku, uchwyt TSynEdit) otwartego edytora ST."""
    ramki = [d for d in dzieci(glowne) if klasa_okna(d) == "TChildFrm"]
    if blok:
        ramki = [d for d in ramki if tekst_okna(d).lower() == blok.lower()]
    znalezione = []
    for r in ramki:
        eds = [d for d in dzieci(r) if klasa_okna(d) == "TSynEdit"]
        if not eds:
            continue

        def pole(h):
            rc = wt.RECT()
            user32.GetWindowRect(h, ctypes.byref(rc))
            return (rc.right - rc.left) * (rc.bottom - rc.top)

        znalezione.append((tekst_okna(r), max(eds, key=pole)))
    if not znalezione:
        raise Blad("brak otwartego edytora ST%s (otworz go: st-open NAZWA)" % (" o nazwie '%s'" % blok if blok else ""))
    if len(znalezione) > 1:
        raise Blad("kilka otwartych edytorow ST, wskaz --blok: " + ", ".join(n for n, _ in znalezione))
    return znalezione[0]


def tekst_edytora(ed):
    n = user32.SendMessageW(ed, 0x000E, 0, None)  # WM_GETTEXTLENGTH
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.SendMessageW(ed, 0x000D, n + 1, ctypes.cast(buf, ctypes.c_void_p))  # WM_GETTEXT
    return buf.value


def ustaw_tekst(ed, tekst):
    """Ustawia caly tekst edytora (WM_SETTEXT) i sprawdza odczytem. Zwraca True, gdy tekst zgadza sie z podanym."""
    buf = ctypes.create_unicode_buffer(tekst)
    user32.SendMessageW(ed, 0x000C, 0, ctypes.cast(buf, ctypes.c_void_p))  # WM_SETTEXT
    start = time.time()
    while time.time() - start < 5.0:
        if tekst_edytora(ed) == tekst:
            return True
        time.sleep(0.1)
    return tekst_edytora(ed) == tekst


def zastap_linie(ed, od, do, nowe):
    """Zamienia linie od..do (numeracja od 1) na liste nowych linii. do = od-1 oznacza wstawienie przed linia od.
    Pusta lista nowych linii usuwa zakres. Zwraca (stary, nowy) tekst; przy bledzie przywraca oryginal."""
    oryginal = tekst_edytora(ed)
    linie = oryginal.split("\r\n")
    n = len(linie)
    if not (1 <= od <= n) or not (od - 1 <= do <= n):
        raise Blad("zakres linii %d-%d poza tekstem (linii: %d)" % (od, do, n))
    wynik = "\r\n".join(linie[:od - 1] + list(nowe) + linie[do:])
    if not ustaw_tekst(ed, wynik):
        ustaw_tekst(ed, oryginal)
        raise Blad("edytor nie przyjal nowego tekstu - przywrocono oryginal")
    return oryginal, wynik


def drzewo_projektu(glowne):
    """Zwraca uchwyt drzewa projektu (TTreeView z korzeniem 'Project [...]')."""
    for d in dzieci(glowne):
        if klasa_okna(d) == "TTreeView" and user32.IsWindowVisible(d):
            drz = Drzewo(d)
            try:
                korzen = drz.nastepny(0, 0)  # TVGN_ROOT
                if korzen and drz.tekst(korzen).lower().startswith("project ["):
                    return d
            finally:
                drz.zamknij()
    raise Blad("nie znaleziono drzewa projektu")


class Drzewo:
    """Odczyt elementow TreeView z cudzego procesu (proces 32-bitowy)."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.proc = kernel32.OpenProcess(PROCESS_ALL, False, pid_okna(hwnd))
        if not self.proc:
            raise Blad("brak dostepu do procesu ISPSoft")
        wow = wt.BOOL()
        kernel32.IsWow64Process(self.proc, ctypes.byref(wow))
        if not wow.value:
            raise Blad("odczyt drzewa zaimplementowano tylko dla 32-bitowego ISPSoft")
        self.mem = kernel32.VirtualAllocEx(self.proc, None, 4096, MEM_COMMIT_RESERVE, PAGE_RW)

    def zamknij(self):
        kernel32.VirtualFreeEx(self.proc, self.mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(self.proc)

    def nastepny(self, h, kod):
        return user32.SendMessageW(self.hwnd, 0x110A, kod, ctypes.c_void_p(h)) & 0xFFFFFFFF  # TVM_GETNEXTITEM

    def tekst(self, h):
        buf = self.mem + 256
        tv = struct.pack("<IIIIIIIIII", 1, h, 0, 0, buf, 500, 0, 0, 0, 0)  # TVIF_TEXT
        kernel32.WriteProcessMemory(self.proc, self.mem, tv, len(tv), None)
        kernel32.WriteProcessMemory(self.proc, buf, b"\0" * 1000, 1000, None)
        user32.SendMessageW(self.hwnd, 0x113E, 0, ctypes.c_void_p(self.mem))  # TVM_GETITEMW
        wyj = ctypes.create_string_buffer(1000)
        kernel32.ReadProcessMemory(self.proc, buf, wyj, 1000, None)
        r = wyj.raw
        if r[1:2] == b"\0" and r[0:1] != b"\0":
            return r.decode("utf-16-le", "replace").split("\0")[0]
        return r.split(b"\0")[0].decode("cp1250", "replace")

    def szukaj(self, nazwa):
        """Pierwszy element o tekscie 'nazwa' albo 'nazwa [typ,jezyk]'. Pomija galaz API (setki pozycji)."""
        nazwa = nazwa.lower()

        def idz(h):
            while h:
                t = self.tekst(h)
                tl = t.lower()
                if tl == nazwa or tl.startswith(nazwa + " ["):
                    return h, t
                if tl != "apis":
                    c = self.nastepny(h, 4)  # TVGN_CHILD
                    if c:
                        wyn = idz(c)
                        if wyn:
                            return wyn
                h = self.nastepny(h, 1)  # TVGN_NEXT
            return None

        return idz(self.nastepny(0, 0))

    def prostokat(self, h):
        user32.SendMessageW(self.hwnd, 0x1114, 0, ctypes.c_void_p(h))  # TVM_ENSUREVISIBLE
        time.sleep(0.3)
        kernel32.WriteProcessMemory(self.proc, self.mem, struct.pack("<I", h) + b"\0" * 12, 16, None)
        if not user32.SendMessageW(self.hwnd, 0x1104, 1, ctypes.c_void_p(self.mem)):  # TVM_GETITEMRECT
            raise Blad("nie mozna pobrac polozenia elementu drzewa")
        wyj = ctypes.create_string_buffer(16)
        kernel32.ReadProcessMemory(self.proc, self.mem, wyj, 16, None)
        return struct.unpack("<iiii", wyj.raw)


def cmd_st_open(a):
    glowne = wybierz_okno(a.pid, a.title)
    drz = Drzewo(drzewo_projektu(glowne))
    try:
        znaleziony = drz.szukaj(a.nazwa)
        if not znaleziony:
            raise Blad("w drzewie projektu nie ma elementu '%s'" % a.nazwa)
        h, tekst = znaleziony
        if "ld" in tekst.lower().split("[")[-1]:
            raise Blad("'%s' to program LD - edytor LD nie jest tekstowy, st-open obsluguje tylko ST" % tekst)
        l, t, r, b = drz.prostokat(h)
    finally:
        drz.zamknij()
    x, y = (l + r) // 2, (t + b) // 2
    lp = (y << 16) | (x & 0xFFFF)
    for kom, wp in ((WM_MOUSEMOVE, 0), (WM_LBUTTONDOWN, 1), (WM_LBUTTONUP, 0), (WM_LBUTTONDBLCLK, 1), (WM_LBUTTONUP, 0)):
        user32.PostMessageW(drzewo_projektu(glowne), kom, wp, lp)
        time.sleep(0.1)
    czysta = tekst.split(" [")[0]
    start = time.time()
    while time.time() - start < 15:
        time.sleep(0.5)
        try:
            nazwa, _ed = edytor_st(glowne, czysta)
            print("otwarto edytor: %s" % nazwa)
            return 0
        except Blad:
            pass
        for d in dialogi_procesu(pid_okna(glowne)):
            raise Blad("ISPSoft pokazal okno '%s': %s" % (tekst_okna(d), tekst_dialogu(d)))
    raise Blad("edytor '%s' nie otworzyl sie w 15 s" % czysta)


def _zakres(a, n):
    od = a.od or 1
    do = a.do or n
    if not (1 <= od <= do <= n):
        raise Blad("zly zakres linii %d-%d (tekst ma %d linii)" % (od, do, n))
    return od, do


def cmd_st_get(a):
    glowne = wybierz_okno(a.pid, a.title)
    nazwa, ed = edytor_st(glowne, a.blok)
    linie = tekst_edytora(ed).split("\r\n")
    od, do = _zakres(a, len(linie))
    wyj = ["%4d: %s" % (i, linie[i - 1]) for i in range(od, do + 1)]
    print("[%s, linii: %d]" % (nazwa, len(linie)))
    for w in wyj:
        print(w)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(linie[od - 1:do]) + "\r\n")
    return 0


def _nowe_linie(a):
    if a.plik:
        with open(a.plik, encoding="utf-8") as f:
            tresc = f.read().replace("\r\n", "\n")
        if tresc.endswith("\n"):
            tresc = tresc[:-1]
        return tresc.split("\n")
    if a.tekst is not None:
        return a.tekst.replace("\\n", "\n").split("\n")
    if a.usun:
        return []
    raise Blad("podaj nowe linie: --plik, --tekst albo --usun (usuniecie zakresu)")


def cmd_st_replace(a):
    nowe = _nowe_linie(a)
    glowne = wybierz_okno(a.pid, a.title)
    nazwa, ed = edytor_st(glowne, a.blok)
    stary, nowy = zastap_linie(ed, a.od, a.do, nowe)
    sl, nl = stary.count("\r\n") + 1, nowy.count("\r\n") + 1
    print("[%s] zamieniono linie %d-%d (%d nowych); linii w bloku: %d -> %d" % (nazwa, a.od, a.do, len(nowe), sl, nl))
    return 0


def cmd_list(_a):
    for h in okna_ispsoft():
        print("pid %d  hwnd %d  %s" % (pid_okna(h), h, tekst_okna(h)))
    return 0


def cmd_read(a):
    glowne = wybierz_okno(a.pid, a.title)
    _, hl = znajdz_kontrolki(glowne)
    lista = Lista(hl)
    try:
        wiersze = lista.wszystkie()
    finally:
        lista.zamknij()
    return wypisz(wiersze, a.out)


def cmd_compile(a):
    glowne = wybierz_okno(a.pid, a.title)
    pasek, hl = znajdz_kontrolki(glowne, lista_opcjonalna=True)
    if hl:  # wyczysc stary wynik, zeby odroznic nowa kompilacje od poprzedniej
        lista = Lista(hl)
        try:
            lista.wyczysc()
        finally:
            lista.zamknij()
    kliknij(pasek, a.x, a.y)
    wiersze = czekaj_na_wynik(glowne, a.timeout)
    if not wiersze:
        dlg = [tekst_okna(d) + ": " + tekst_dialogu(d) for d in dialogi_procesu(pid_okna(glowne))]
        raise Blad("brak wyniku kompilacji po %d s (okno zablokowane dialogiem albo przycisk Compile w innym miejscu - "
                   "sprawdz --x/--y)%s" % (a.timeout, "; dialogi: " + " / ".join(dlg) if dlg else ""))
    return wypisz(wiersze, a.out)


def wypisz(wiersze, plik):
    for w in wiersze:
        print(w)
    if plik:
        with open(plik, "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(wiersze) + "\r\n")
    bledy, _ = podsumuj(wiersze)
    return 1 if bledy else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    po = sub.add_parser("open")
    po.add_argument("plik", help="projekt .isp do otwarcia w nowej instancji ISPSoft")
    po.add_argument("--exe", help="sciezka do NewISPSoft.exe (domyslnie: ISPSOFT_DIR, uruchomiony ISPSoft, Program Files)")
    po.add_argument("--timeout", type=int, default=60)
    pc = sub.add_parser("close")
    pc.add_argument("--pid", type=int)
    pc.add_argument("--title")
    pc.add_argument("--timeout", type=int, default=15)
    pc.add_argument("--nie-zapisuj", dest="nie_zapisuj", action="store_true",
                    help="na pytanie o zapis projektu odpowiedz Nie (zmiany w projekcie przepadna, plik .isp bez zmian)")
    pc.add_argument("--force", action="store_true", help="zakoncz proces bez pytania (niezapisane zmiany przepadna)")
    for nazwa in ("compile", "read"):
        p = sub.add_parser(nazwa)
        p.add_argument("--pid", type=int)
        p.add_argument("--title")
        p.add_argument("--out", help="plik tekstowy na pelny wynik")
        if nazwa == "compile":
            p.add_argument("--timeout", type=int, default=60)
            p.add_argument("--x", type=int, default=COMPILE_X)
            p.add_argument("--y", type=int, default=COMPILE_Y)
    for nazwa in ("st-open", "st-get", "st-replace"):
        p = sub.add_parser(nazwa)
        p.add_argument("--pid", type=int)
        p.add_argument("--title")
        if nazwa == "st-open":
            p.add_argument("nazwa", help="nazwa bloku funkcyjnego / programu ST z drzewa projektu, np. CAN_SDO")
        else:
            p.add_argument("--blok", help="nazwa otwartego edytora (potrzebna, gdy otwartych jest kilka)")
        if nazwa == "st-get":
            p.add_argument("--od", type=int, help="pierwsza linia (domyslnie 1)")
            p.add_argument("--do", type=int, help="ostatnia linia (domyslnie ostatnia)")
            p.add_argument("--out", help="zapisz odczytane linie do pliku UTF-8")
        if nazwa == "st-replace":
            p.add_argument("od", type=int, help="pierwsza zamieniana linia (od 1)")
            p.add_argument("do", type=int, help="ostatnia zamieniana linia; do = od-1 oznacza wstawienie przed linia od")
            p.add_argument("--plik", help="plik UTF-8 z nowymi liniami")
            p.add_argument("--tekst", help="nowe linie w parametrze, rozdzielone \\n")
            p.add_argument("--usun", action="store_true", help="usun zakres (bez nowych linii)")
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    a = ap.parse_args()
    try:
        return {"list": cmd_list, "open": cmd_open, "close": cmd_close, "compile": cmd_compile, "read": cmd_read,
                "st-open": cmd_st_open, "st-get": cmd_st_get, "st-replace": cmd_st_replace}[a.cmd](a)
    except Blad as e:
        print("BLAD: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
