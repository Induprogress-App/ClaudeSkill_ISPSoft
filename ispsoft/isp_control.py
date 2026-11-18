#!/usr/bin/env python3
"""isp_control - sterowanie otwartym oknem Delta ISPSoft bez GUI i bez ruszania myszy.

Polecenia:
  list                          lista okien ISPSoft (pid, tytul)
  open PROJEKT.isp              nowa instancja ISPSoft z projektem (wypisuje pid)
  close --pid N | --title T     zamkniecie okna ISPSoft ([--nie-zapisuj] odpowiada Nie na pytanie o zapis, [--force] konczy proces)
  compile [--pid N | --title T] kompilacja projektu otwartego w oknie i odczyt panelu Compile Message
  read    [--pid N | --title T] odczyt panelu Compile Message bez kompilacji

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
    a = ap.parse_args()
    try:
        return {"list": cmd_list, "open": cmd_open, "close": cmd_close, "compile": cmd_compile, "read": cmd_read}[a.cmd](a)
    except Blad as e:
        print("BLAD: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
