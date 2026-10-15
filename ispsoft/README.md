# isp_codec – edycja projektów ISPSoft bez GUI

Jeden plik `isp_codec.py`, wymaga tylko Pythona 3 (bez dodatkowych bibliotek).
Sprawdzone na ISPSoft 3.24 i sterowniku AS228P. Opis formatu pliku `.isp`: [FORMAT_ISP.md](FORMAT_ISP.md), zapis kodu: [JEZYK_ST.md](JEZYK_ST.md), [JEZYK_LD.md](JEZYK_LD.md).

## Zasada pracy
1. Zamknij projekt w ISPSoft.
2. `decode` rozkłada `PROJEKT.isp` na pliki tekstowe w folderze `_autogen` obok projektu.
3. Edytujesz pliki w `_autogen` (dowolnym edytorem) albo używasz poleceń `add-*`.
4. `encode` składa `_autogen` z powrotem do `PROJEKT.isp` (poprzednia wersja → `PROJEKT.isp.przed_encode`).
5. Otwierasz projekt w ISPSoft i **kompilujesz** – to jest ostateczna kontrola poprawności.

Narzędzie pilnuje, żeby nie zgubić pracy:
- `add-*` i `encode` odmówią, jeśli `PROJEKT.isp` zapisano w ISPSoft po ostatnim `decode` – wtedy najpierw `decode`;
- `decode` odmówi, jeśli w `_autogen` są zmiany jeszcze niezapisane do `.isp` albo pliki, których narzędzie nie
  utworzyło (`--force` je usuwa) – własnych plików nie trzymaj w `_autogen`.

## Polecenia
```
python isp_codec.py decode  PROJEKT.isp
python isp_codec.py encode  PROJEKT.isp

python isp_codec.py add-prg PROJEKT.isp NAZWA [--lang ST|LD] [--folder Folder/Podfolder] [--task 0|brak]
                                              [--komentarz "..."] [--kod plik.st] [--encode]
python isp_codec.py add-fb  PROJEKT.isp NAZWA [--lang ST|LD] [--folder Folder] [--komentarz "..."] [--kod plik.st] [--encode]
python isp_codec.py add-var PROJEKT.isp MIEJSCE NAZWA TYP [--adres D100] [--init 5] [--komentarz "..."]
                                              [--klasa VAR|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT] [--nowa-tabela] [--encode]
python isp_codec.py list     PROJEKT.isp [WZORZEC ...] [--typ PRG,FB,DUT,GVL]
python isp_codec.py find-var PROJEKT.isp NAZWA
python isp_codec.py list-lib [WZORZEC ...]
python isp_codec.py info PROJEKT.isp|MODEL [--jezyk ST|LD]
python isp_codec.py copy-fb ZRODLO.isp CEL.isp FB1 [FB2 ...] [--folder Folder] [--globalne [--z-adresami]]
                                              [--nadpisz] [--dry-run] [--encode]
```
- `add-prg` dodaje program do drzewa projektu (brakujące foldery są tworzone) i do zadania cyklicznego
  (`--task` = numer T_ID zadania, `brak` – bez przypisania). Program ST dostaje kod z `--kod` albo pusty,
  program LD – jeden pusty network.
- `add-fb` dodaje blok funkcyjny; jego wejścia/wyjścia dodaje się potem przez `add-var ... --klasa VAR_INPUT`.
- `add-var`: `MIEJSCE` to nazwa tabeli zmiennych globalnych (np. `"Global Variables"` – domyślna tabela,
  w ISPSoft widoczna jako „Main Table”) albo nazwa programu/FB. `--nowa-tabela` tworzy brakującą tabelę globalną.
  `\n` w komentarzu = nowa linia.
- `list` wypisuje elementy projektu, po jednej linii: nazwa, rodzaj (`PRG`, `FB`, `DUT` – typ, `GVL` – tabela
  zmiennych globalnych), język albo rodzaj typu, rozmiar (linie ST, networki LD, liczba zmiennych), zadanie
  programu (`T0`, `-` = nieprzypisany) i plik w `_autogen`. `WZORZEC` to fragment nazwy albo wzorzec z `*`
  i `?` (np. `Komunikacja*`), bez rozróżniania wielkości liter; kilka wzorców = suma. `--typ FB,DUT` zawęża rodzaje.
  Przykład: `list Projekt/Projekt.isp Komunikacja* --typ PRG`.
- `find-var` pokazuje, gdzie zmienna jest zadeklarowana (tabele globalne, zmienne lokalne POU), gdzie zmienia się
  jej wartość (przypisania, wyjścia FB `=>`, cewki LD, wyjścia instrukcji), gdzie jest użyta w warunkach (IF/ELSIF/
  WHILE/CASE/UNTIL, styki i porównania LD) i gdzie jeszcze jest odczytywana. Nazwa może zawierać człon struktury
  (np. `Dane.Silnik1`, `Zawor1.Otwarty`). Wynik zawiera plik i numer linii.
- `copy-fb` kopiuje bloki funkcyjne między projektami **razem z zależnościami**: typy użyte w deklaracjach zmiennych
  i w kodzie (np. stała wyliczeniowa `TypKomendy.Start`), typy zagnieżdżone w strukturach oraz bloki FB użyte jako instancje
  (np. blok timera użyty wewnątrz innego bloku). Zmienne globalne używane w kodzie FB są wypisywane; `--globalne` dodaje
  brakujące do tabeli o tej samej nazwie (domyślnie bez adresów – `--z-adresami` je zachowuje). Element, który
  w projekcie docelowym już jest i jest identyczny, jest pomijany; różniący się zatrzymuje kopiowanie (`--nadpisz`
  go zastępuje). `--dry-run` pokazuje plan bez zmian. Typy spoza projektu (np. typy z bibliotek ISPSoft) są
  tylko wypisywane.
- **Folder bibliotek `[lib]`**: w każdym poleceniu zamiast ścieżki do `.isp` można podać `[lib]/NAZWA.isp`.
  Folder bibliotek to `%ISPSOFT_LIB%`, a gdy zmienna nie jest ustawiona – `%USERPROFILE%\.claude\ispsoft\biblioteki`.
  Projekt może leżeć bezpośrednio w nim (`NAZWA.isp`) albo we własnym podfolderze (`NAZWA\NAZWA.isp`).
  Biblioteka to zwykły projekt ISPSoft z co najmniej jednym programem (bez programu się nie skompiluje).
  `list-lib [WZORZEC]` wypisuje biblioteki i ich bloki funkcyjne (z wzorcem – tylko pasujące). Przykłady:
  `copy-fb [lib]/EXAMPLES.isp Projekt/Projekt.isp Zawor --globalne`,
  `copy-fb Projekt/Projekt.isp [lib]/EXAMPLES.isp NowyFB --folder Urzadzenia`.
- **`info`** wypisuje dane projektu (sterownik, zadania, programy, bloki, typy, tabele, zakresy pamięci i retain)
  oraz pełną treść plików z wiedzą o sterowniku z folderu `%USERPROFILE%\.claude\ispsoft\PLC` (inny folder:
  `%ISPSOFT_PLC%`). Pasują pliki, których nazwa jest początkiem nazwy modelu – dla AS228P: `AS.md` (cała seria),
  `AS228.md`, `AS228P.md` (model) – wypisywane od ogólnych do szczegółowych. Zamiast projektu można podać sam model.
  `--jezyk ST` pomija w plikach sterownika sekcje o LD (nagłówki `##`/`###` zawierające słowo `LD`) – i odwrotnie.
  Lista programów i bloków nie jest wypisywana (tylko liczby) – do tego służy `list`.
- Folder `%USERPROFILE%\.claude\ispsoft` (inny: `%ISPSOFT_HOME%`) zawiera `biblioteki\` i `PLC\`.
- Narzędzie nie narzuca stylu kodu: tworzy tylko puste POU i deklaracje, a treść kodu pochodzi od użytkownika.

Przykład:
```
python isp_codec.py add-fb  Projekt/Projekt.isp FB_Licznik --folder Narzedzia --kod licznik.st
python isp_codec.py add-var Projekt/Projekt.isp FB_Licznik CU BOOL --klasa VAR_INPUT
python isp_codec.py add-var Projekt/Projekt.isp FB_Licznik CV INT --klasa VAR_OUTPUT
python isp_codec.py add-prg Projekt/Projekt.isp Liczenie --folder Funkcje
python isp_codec.py add-var Projekt/Projekt.isp Liczenie licznik1 FB_Licznik
python isp_codec.py add-var Projekt/Projekt.isp "Global Variables" Wynik INT --adres D100 --init 0 --encode
```

## Biblioteki – zalecany przebieg (dla Claude i ludzi)
- „Skopiuj blok X z biblioteki”: `list-lib X`; jeśli blok jest w kilku bibliotekach, wybierz (zapytaj), z której.
  Potem `copy-fb [lib]/NAZWA.isp PROJEKT.isp X --folder ... --dry-run`, sprawdź plan (także zmienne globalne,
  których blok potrzebuje) i dopiero wtedy kopiuj (`--globalne` dodaje je bez adresów).
- „Dodaj blok X do biblioteki”: `copy-fb PROJEKT.isp [lib]/NAZWA.isp X --folder ...` (też najpierw `--dry-run`).
- Brak folderu albo biblioteki: utwórz w ISPSoft projekt z co najmniej jednym (choćby pustym) programem i zapisz
  go w folderze bibliotek – bez programu ISPSoft go nie skompiluje. Skill nie zawiera żadnej biblioteki.

## Układ `_autogen`
| Plik | Zawartość |
|---|---|
| `programy/<foldery>/<nazwa>.st` (`.ld`) | sam kod POU – można go skopiować w całości do edytora ISPSoft |
| `programy/<foldery>/<nazwa>.csv` | zmienne lokalne w formacie eksportu/importu ISPSoft (można je zaimportować) |
| `programy/<foldery>/<nazwa>.info` | pozostałe informacje o POU (nagłówek, komentarz, adresy z kompilacji) |
| `bloki_funkcyjne/...` | to samo dla bloków funkcyjnych |
| `zmienne_globalne/<tabela>.txt` | tabela zmiennych globalnych |
| `typy/<nazwa>.txt` | STRUCT / ENUM |
| `zadania.txt`, `drzewo_projektu.txt` | zadania i przypisane programy, foldery w drzewie projektu |
| `tabele_monitorowania.txt` | tabele monitorowania |
| `_szkielet.txt`, `_naglowek.bin`, `_zrodlo.txt`, `_kompilacja/` | reszta projektu i dane techniczne – nie edytować |

Przeniesienie zmian do projektu otwartego w ISPSoft (bez `encode`): skopiuj całą zawartość pliku `.st` do okna
programu w ISPSoft, a zmienne zaimportuj z pliku `.csv`. Pliki `.csv` są w stronie kodowej projektu (jak eksport
z ISPSoft); adresy przydzielane przez kompilator (`W...`) nie są w nich zapisywane. Import CSV w ISPSoft nie radzi
sobie z komentarzami wielowierszowymi (także z plikami wyeksportowanymi przez sam ISPSoft) – zmienna zostaje dodana,
ale komentarz jest obcinany albo pomijany.

## Ograniczenia
- Sprawdzone tylko ISPSoft 3.24 / AS228P; inna seria lub wersja – najpierw test `decode` → `encode` → kompilacja bez zmian.
- Obsługiwane języki: ST i LD. SFC, FBD, RETAIN/CONSTANT – nie zbadane.
- Duże projekty zapisane ze skompilowanym kodem: po `encode` plik różni się bajtami kompresji (treść ta sama) – ISPSoft je przyjmuje.
