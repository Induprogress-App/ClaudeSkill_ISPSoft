# isp_codec – narzędzie i skill do projektów Delta ISPSoft

Repozytorium narzędzia `isp_codec.py`, które odczytuje i edytuje projekty Delta ISPSoft (`.isp`) bez GUI,
oraz skilla `ispsoft` dla Claude Code, który z niego korzysta. Narzędzie trafia do wielu osób, każda pisze
kod po swojemu.

## Struktura
| Plik / folder | Zawartość |
|---|---|
| `ispsoft/` | **zawartość paczki skilla 1:1** – wszystko, co tu jest, trafia do paczki |
| `ispsoft/SKILL.md`, `ispsoft/INSTALACJA.md` | skill dla Claude i instrukcja instalacji dla ludzi |
| `ispsoft/isp_codec.py` | całe narzędzie: jeden plik, tylko biblioteka standardowa Pythona 3 |
| `ispsoft/README.md` | instrukcja poleceń dla użytkowników |
| `ispsoft/FORMAT_ISP.md` | opis formatu pliku `.isp` – wszystko, co ustalono o zapisie projektu |
| `ispsoft/JEZYK_ST.md`, `ispsoft/JEZYK_LD.md` | zapis kodu ST i LD w `_autogen` – skill czyta tylko plik języka, w którym pracuje |
| `ispsoft/PLC_start/*.md` | pliki startowe wiedzy o sterownikach; `info` czyta pliki, których nazwa jest początkiem nazwy modelu (`AS.md` seria, `AS228.md` rodzina AS228P/AS228R, `AS228P.md` jeden model) |
| `zbuduj_skill.py` | pakuje `ispsoft/` do `_ns_dist/ispsoft.zip` (+ `WERSJA.txt`) |
| `aktualizuj_skill.py` | synchronizuje pliki sterowników, buduje paczkę i instaluje skill lokalnie |
| `CLAUDE.md`, `.gitignore` | ten plik i reguły repozytorium |

Wszystko, co nie ma trafić do repozytorium, leży w plikach lub folderach o nazwie zaczynającej się od `_ns_`
(NoSynch), np. `_ns_dist` (wyniki budowania), `_ns_tests` (projekty testowe), `_ns_analiza`, `_ns_smietnik`
(rzeczy usunięte przy porządkach – zamiast kasowania). Projekty PLC (`.isp`) trzymać wyłącznie w folderach `_ns_`.
Uruchamianie narzędzia z repozytorium: `python ispsoft/isp_codec.py ...`.

Dane użytkownika (poza repozytorium, nie zależą od jego położenia):
- `%USERPROFILE%\.claude\skills\ispsoft\` – zainstalowany skill,
- `%USERPROFILE%\.claude\ispsoft\biblioteki\` – biblioteki bloków funkcyjnych (`[lib]`, np. `EXAMPLES\EXAMPLES.isp`),
- `%USERPROFILE%\.claude\ispsoft\PLC\` – wiedza o sterownikach używana przez skill (`info`).

## Zasady pracy (ustalone z użytkownikiem)
- W folderze repozytorium wolno bez pytania czytać pliki, tworzyć i zmieniać pliki oraz uruchamiać polecenia.
  Poza nim – najpierw zapytać (wyjątek: instalacja skilla przez `aktualizuj_skill.py`, gdy zmiany działają).
- Zmiany w `%USERPROFILE%\.claude\ispsoft\` (biblioteki, pliki PLC) tylko na prośbę użytkownika.
- Projektów `.isp` użytkownika nie zmieniać bez zgody. Do testów tworzyć kopie, każdą w osobnym folderze
  (narzędzie tworzy jeden `_autogen` na folder; do samego odczytu kilku projektów z jednego folderu: `decode-txt`).
- Ostateczny test to otwarcie i kompilacja w ISPSoft – robi to użytkownik. Po zmianie narzędzia: test
  `decode` → `encode` (bez zmian treści) na wszystkich dostępnych projektach, potem pliki do sprawdzenia w ISPSoft.
- Nie używać `--force` na projektach użytkownika bez jego zgody. Nie zapisywać własnych plików w `_autogen`.

## Gałęzie git
- Prace i testy commitować do lokalnej gałęzi `tests` (utworzyć ją z `main`, jeśli nie istnieje).
  Gałęzi `tests` **nie wysyłać na serwer** (żadnego `git push` tej gałęzi).
- Do `main` trafiają tylko zmiany przetestowane i działające (po teście `decode` → `encode` i sprawdzeniu
  w ISPSoft przez użytkownika) – przeniesione z `tests` (merge / cherry-pick) dopiero po potwierdzeniu.
- Wysyłać na serwer (GitHub) wyłącznie `main`, i tylko na prośbę użytkownika.

## Poufność i zakres analizy
- W narzędziu, dokumentacji, przykładach, plikach `ispsoft/PLC_start/` i opisach commitów **nie umieszczać szczegółów
  z rzeczywistych projektów**: nazw projektów, zmiennych, bloków, typów, tabel, adresów ani ogólnej struktury
  programów. Przykłady mają być ogólne (np. `Zawor1`, `Dane.Silnik1`, `TypKomendy.Start`).
- Przy rozwijaniu narzędzia i skilla projekty użytkownika analizować **tylko pod kątem składni i formatu
  zapisu** (budowa pliku, konstrukcje języka, typy, instrukcje, ograniczenia sterownika), bez analizowania,
  czym program steruje i jak działa maszyna – chyba że użytkownik wprost o to poprosi.
- Paczka dla innych osób powstaje wyłącznie z plików repozytorium; przed wydaniem przejrzeć je pod tym kątem.

## Wydanie nowej wersji
1. Commit zmian (numer wersji paczki = numer commitu; niezacommitowane zmiany dają dopisek `-dirty`).
2. `python aktualizuj_skill.py` – nowsza wersja każdego pliku sterownika z dwóch miejsc (`ispsoft/PLC_start/`
   i `%USERPROFILE%\.claude\ispsoft\PLC\`) trafia do drugiego (stare wersje do `_ns_dist/_kopie_PLC/`),
   potem budowanie paczki i instalacja skilla. Usunięcia się nie przenoszą: plik usunięty
   lub przemianowany w jednym miejscu trzeba usunąć także w pozostałych, inaczej wróci przy synchronizacji. Jeśli pliki w `ispsoft/` się zmieniły – commit
   i ponowne uruchomienie, żeby paczka miała czysty numer.
3. Paczka do wysłania: `_ns_dist/ispsoft.zip`. Biblioteki bloków nie są do niej dołączane.

## Konwencje kodu
- `isp_codec.py`: jeden plik, bez zależności, komunikaty i komentarze po polsku bez polskich znaków.
  Dokumentacja (`.md`) z polskimi znakami.
- Teksty projektu: w `.isp` strona kodowa projektu (zwykle 1250) i CRLF; w `_autogen` UTF-8 i CRLF,
  pliki `.csv` w stronie kodowej projektu (jak eksport ISPSoft).
- Każda zmiana formatu musi zachować bezstratność: `decode` sprawdza, że rozkład i złożenie dają tę samą treść.
- Przy edycji kodu skryptami uważać na sekwencje `\r\n` i `\` w napisach – bezpieczniej Edit/Write
  albo surowe napisy w pliku skryptu.
- Nowe ustalenia o formacie dopisywać do `ispsoft/FORMAT_ISP.md` (o zapisie kodu – do `JEZYK_ST.md` / `JEZYK_LD.md`), nowe polecenia do `ispsoft/README.md`
  i `ispsoft/SKILL.md`.

## Otwarte sprawy
- `ispsoft/PLC_start/AS.md`: wpis o domyślnych obszarach retain różni się od wartości odczytanych z projektów
  (M2048–M4095, D2000–D3919, C224–C254, S912–S1023) – ignorowac te zapisy. Bity z „?” w `AS.md`
  (SM604, SM750, SM1376/1377/1408/1409) do potwierdzenia w dokumentacji Delta.
- Kilka projektów w jednym folderze współdzieli `_autogen` – rozważyć `_autogen_<nazwa>` albo ostrzeżenie.
- Niezbadane: SFC, FBD, RETAIN/CONSTANT zmiennych globalnych, ID zadań przerwań poza 32, szerokość
  wywołania FB w gałęzi równoległej LD, polecenie `add-dut`, import CSV z polami w cudzysłowie.
- Import CSV w ISPSoft nie przenosi komentarzy wielowierszowych (błąd ISPSoft – świadomie pominięte).
