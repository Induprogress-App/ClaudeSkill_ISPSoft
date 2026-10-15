"""Synchronizuje pliki sterownikow, buduje paczke skilla i instaluje ja lokalnie - jednym poleceniem.

Uzycie:
  python aktualizuj_skill.py [--bez-instalacji] [--ignoruj-slowa]

1. Pliki *.md o wiedzy o sterownikach moga byc poprawiane w dwoch miejscach:
     ispsoft/PLC_start/   (repozytorium - pliki startowe w paczce)
     folder PLC skilla    (%ISPSOFT_PLC% albo %USERPROFILE%/.claude/ispsoft/PLC)
   Dla kazdego pliku nowsza wersja (data modyfikacji) trafia do drugiego miejsca; nadpisywana wersja jest
   zapisywana w _ns_dist/_kopie_PLC/<data-godzina>/<miejsce>/. Usuniecia sie nie przenosza.
2. Buduje _ns_dist/ispsoft.zip (zbuduj_skill.py, z kontrola zakazanych slow).
3. Instaluje paczke w %USERPROFILE%/.claude/skills (pomijane z --bez-instalacji).
"""
import datetime
import filecmp
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ispsoft'))
sys.path.insert(0, HERE)
import isp_codec  # noqa: E402
import zbuduj_skill  # noqa: E402

DIST = os.path.join(HERE, '_ns_dist')


def sync_plc():
    places = {'repozytorium': os.path.join(HERE, 'ispsoft', 'PLC_start'), 'skill': isp_codec.plc_dir()}
    for folder in places.values():
        os.makedirs(folder, exist_ok=True)
    names = sorted({f for folder in places.values() for f in os.listdir(folder) if f.lower().endswith('.md')})
    backup = os.path.join(DIST, '_kopie_PLC', datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
    changed = False
    for name in names:
        versions = [(os.path.getmtime(os.path.join(f, name)), place) for place, f in places.items()
                    if os.path.isfile(os.path.join(f, name))]
        newest_place = max(versions)[1]
        newest = os.path.join(places[newest_place], name)
        for place, folder in places.items():
            target = os.path.join(folder, name)
            if os.path.isfile(target) and filecmp.cmp(newest, target, shallow=False):
                continue
            if os.path.isfile(target):
                os.makedirs(os.path.join(backup, place), exist_ok=True)
                shutil.copy2(target, os.path.join(backup, place, name))
            shutil.copy2(newest, target)
            changed = True
            print('  %-12s -> %-12s %s' % (newest_place, place, name))
    if not changed:
        print('  pliki sterownikow sa zgodne w obu miejscach')
    elif os.path.isdir(backup):
        print('  poprzednie wersje: %s' % backup)


def install():
    skills = os.path.join(os.path.expanduser('~'), '.claude', 'skills')
    target = os.path.join(skills, 'ispsoft')
    if os.path.isdir(target):
        shutil.rmtree(target)  # folder skilla nie zawiera danych uzytkownika (sa w .claude/ispsoft)
    with zipfile.ZipFile(os.path.join(DIST, 'ispsoft.zip')) as z:
        z.extractall(skills)
    print('  zainstalowano w %s (wersja %s)' % (target, open(os.path.join(target, 'WERSJA.txt'), encoding='utf-8').read().strip()))


def main(argv):
    print('1. Pliki sterownikow (folder PLC skilla: %s)' % isp_codec.plc_dir())
    sync_plc()
    print('2. Budowanie paczki')
    if zbuduj_skill.main(['--ignoruj-slowa'] if '--ignoruj-slowa' in argv else []) != 0:
        print('Przerwano - paczka nie zostala zbudowana.')
        return 1
    if '--bez-instalacji' not in argv:
        print('3. Instalacja skilla')
        install()
    print('Gotowe. Paczka dla innych: %s' % os.path.join(DIST, 'ispsoft.zip'))
    print('Pamietaj o commicie zmian w ispsoft/ (git add -A && git commit).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
