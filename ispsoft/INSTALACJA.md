# Instalacja skilla „ispsoft” dla Claude Code

Skill pozwala Claude odczytywać i edytować projekty Delta ISPSoft (`.isp`): kod ST/LD, zmienne, programy,
bloki funkcyjne oraz kopiować bloki między projektami i z własnych bibliotek. Szczegóły narzędzia: `README.md` w paczce.

## Wymagania
- Claude Code (aplikacja desktop, terminal albo rozszerzenie IDE).
- Python 3.8 lub nowszy. Sprawdzenie w wierszu poleceń: `python --version` (albo `py -3 --version`).
  Instalator: https://www.python.org/downloads/ – zaznacz „Add python.exe to PATH”.
- ISPSoft 3.24 (do otwierania i kompilowania projektów; narzędzie sprawdzone z AS228P).

## Instalacja
1. Rozpakuj `ispsoft.zip` do folderu skilli użytkownika, tak aby powstał plik
   `%USERPROFILE%\.claude\skills\ispsoft\SKILL.md`. W PowerShellu:
   ```
   Expand-Archive .\ispsoft.zip -DestinationPath "$env:USERPROFILE\.claude\skills" -Force
   ```
2. Zamknij i ponownie uruchom Claude Code (albo otwórz nową sesję).
3. Sprawdź: w nowej sesji wpisz `/ispsoft` albo zapytaj „Jakie masz skille?” – na liście powinien być `ispsoft`.
4. Przy pierwszej instalacji skopiuj pliki startowe z wiedzą o sterownikach (nie nadpisuj, jeśli już je masz):
   ```
   New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\ispsoft\PLC"
   Copy-Item "$env:USERPROFILE\.claude\skills\ispsoft\PLC_start\*.md" "$env:USERPROFILE\.claude\ispsoft\PLC" -Exclude (Get-ChildItem "$env:USERPROFILE\.claude\ispsoft\PLC").Name
   ```

## Używanie
- Otwórz Claude Code w folderze z projektem PLC (albo podaj pełną ścieżkę do pliku `.isp`) i opisz zadanie,
  np. „Dodaj do projektu X.isp program Transport”.
- **Przed zapisem zmian przez Claude zamknij projekt w ISPSoft.** Po zmianach otwórz go i skompiluj.
- Claude zapyta o zgodę przed uruchomieniem poleceń (`python ... isp_codec.py ...`). Możesz wybrać „zawsze zezwalaj”
  dla tego polecenia, żeby nie potwierdzać go za każdym razem.
- Narzędzie tworzy obok projektu folder `_autogen` z plikami tekstowymi projektu. Nie trzymaj w nim własnych plików.
  Kod programu z pliku `.st` można też ręcznie skopiować do edytora ISPSoft, a zmienne zaimportować z pliku `.csv`.

## Dane użytkownika: biblioteki i wiedza o sterownikach
Folder `%USERPROFILE%\.claude\ispsoft` (inny: zmienna `ISPSOFT_HOME`, np. wspólny dysk zespołu):
- `biblioteki\` – projekty-biblioteki z często używanymi blokami funkcyjnymi (inny folder: `ISPSOFT_LIB`).
  Utwórz w ISPSoft projekt dla swojego sterownika z co najmniej jednym (choćby pustym) programem i zapisz go tam,
  np. `...\ispsoft\biblioteki\EXAMPLES\EXAMPLES.isp`. Potem możesz prosić Claude: „dodaj blok X z projektu Y do
  biblioteki EXAMPLES” albo „skopiuj blok X z biblioteki do projektu Z”.
- `PLC\` – ograniczenia i wskazówki dla sterowników (inny folder: `ISPSOFT_PLC`): `AS.md` dla całej serii AS,
  `AS228P.md` itp. dla konkretnego modelu. Claude czyta je przed pisaniem kodu i proponuje uzupełnienia, np. po
  błędzie kompilacji. Zespół może trzymać ten folder na wspólnym dysku, żeby wszyscy korzystali z tej samej wiedzy.

## Aktualizacja
Rozpakuj nową paczkę poleceniem z punktu 1 (zastępuje folder skilla). Biblioteki i pliki `PLC` leżą w osobnym
folderze `.claude\ispsoft`, więc aktualizacja ich nie zmienia. Nowe pliki startowe z `PLC_start` możesz porównać
ze swoimi i przenieść ręcznie.

## Odinstalowanie
Usuń folder `%USERPROFILE%\.claude\skills\ispsoft` (i ewentualnie dane w `%USERPROFILE%\.claude\ispsoft`).
