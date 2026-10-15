---
name: ispsoft
description: Odczyt i edycja projektów Delta ISPSoft (.isp) bez GUI – rozkładanie projektu na pliki tekstowe (kod ST/LD, zmienne CSV), dodawanie programów, bloków funkcyjnych i zmiennych, wyszukiwanie zmiennych, kopiowanie bloków funkcyjnych z zależnościami między projektami i z własnych bibliotek ([lib]). Używaj zawsze, gdy rozmowa dotyczy projektu ISPSoft, pliku .isp, sterownika Delta serii AS albo kodu PLC w ST/LD tworzonego w ISPSoft.
---

# Projekty ISPSoft (.isp)

Narzędzie `isp_codec.py` leży w katalogu tego skilla (podanym przy jego wczytaniu jako katalog bazowy).
Wymaga tylko Pythona 3 – uruchamiaj je jako `python "<katalog skilla>/isp_codec.py" ...`
(jeśli polecenie `python` nie działa, spróbuj `py -3`). Pełny opis poleceń: `README.md`, opis formatu pliku:
`FORMAT_ISP.md` – oba w katalogu skilla; czytaj je tylko wtedy, gdy potrzebujesz szczegółów.

## Zasady pracy
0. **Na początku pracy z projektem uruchom `info PROJEKT.isp`** – pokazuje model sterownika, strukturę projektu,
   zakresy pamięci i całą zapisaną wiedzę o ograniczeniach tego sterownika (folder `PLC`). Stosuj się do niej przy
   każdym pisaniu i zmianie kodu. Gdy kompilacja zgłosi błąd wynikający z ograniczenia sterownika albo użytkownik
   poda nowe ograniczenie, zaproponuj dopisanie go do właściwego pliku w `PLC` (`AS.md` dla całej serii,
   `<MODEL>.md` dla jednego modelu) i dopisz po zgodzie użytkownika.
1. **Projekt musi być zamknięty w ISPSoft**, zanim zapiszesz `.isp` (`encode` lub opcja `--encode`).
   Zapytaj użytkownika, jeśli nie wiesz. Jeśli użytkownik chce, pracuj na kopii projektu.
2. `decode PROJEKT.isp` rozkłada projekt do folderu `_autogen` obok pliku `.isp`. Polecenia `add-*`, `find-var`,
   `copy-fb` robią to same, gdy trzeba.
3. Czytaj tylko potrzebne pliki – to oszczędza kontekst:
   - `programy/<foldery>/<POU>.st` lub `.ld` – sam kod; `.csv` – zmienne lokalne; `.info` – nagłówek POU,
   - `bloki_funkcyjne/...` – to samo dla bloków funkcyjnych,
   - `zmienne_globalne/<tabela>.txt`, `typy/<nazwa>.txt`, `zadania.txt`, `drzewo_projektu.txt`.
   Gdzie użyta jest zmienna: `find-var` zamiast przeglądania wszystkich plików.
4. Edytuj kod bezpośrednio w plikach `.st`. Nowe programy, bloki funkcyjne i zmienne dodawaj poleceniami
   `add-prg`, `add-fb`, `add-var` (pilnują drzewa projektu, zadań i deklaracji). Nie edytuj `_szkielet.txt`
   (wyjątek: dodanie typu, patrz Ograniczenia), `_naglowek.bin`, `_zrodlo.txt` ani `_kompilacja/` i nie zapisuj
   własnych plików w `_autogen`.
5. Po zmianach `encode PROJEKT.isp`, a potem poproś użytkownika o otwarcie projektu w ISPSoft i **kompilację** –
   tylko ona potwierdza poprawność. Zgłoszone błędy kompilacji poprawiaj w plikach `_autogen`.
6. Jeśli narzędzie odmawia (np. `.isp` zapisano w ISPSoft, a `_autogen` ma niezapisane zmiany, albo w `_autogen`
   są obce pliki), nie używaj `--force` bez zgody użytkownika – wyjaśnij, co zostałoby utracone.
7. Użytkownik może przenieść zmiany sam, bez `encode`: kopiując całą zawartość pliku `.st` do okna programu
   w ISPSoft i importując zmienne z pliku `.csv` (import ISPSoft nie przenosi poprawnie komentarzy wielowierszowych).

## Styl kodu
Każdy pisze inaczej – nie narzucaj własnego stylu. Przed napisaniem nowego kodu przeczytaj 1–2 istniejące POU
z projektu i naśladuj ich konwencje (nazewnictwo, komentarze, sposób wywoływania bloków, struktury dla HMI).

## Biblioteki bloków funkcyjnych
Biblioteki to zwykłe projekty ISPSoft w folderze bibliotek: `%ISPSOFT_LIB%` albo domyślnie
`%USERPROFILE%\.claude\ispsoft\biblioteki` (projekt bezpośrednio w nim lub w podfolderze o tej samej nazwie).
W poleceniach zamiast ścieżki podawaj `[lib]/NAZWA.isp`. Skill nie zawiera żadnej biblioteki – każdy
użytkownik tworzy własne.
- „Skopiuj blok X z biblioteki”: najpierw `list-lib`; jeśli blok jest w kilku bibliotekach, zapytaj, z której.
  Potem `copy-fb [lib]/NAZWA.isp PROJEKT.isp X --folder ... --dry-run`, pokaż plan (także zmienne globalne,
  których blok potrzebuje) i dopiero wtedy kopiuj (`--globalne` dodaje je bez adresów).
- „Dodaj blok X do biblioteki”: `copy-fb PROJEKT.isp [lib]/NAZWA.isp X --folder ...` (też najpierw `--dry-run`).
- Brak folderu albo biblioteki: poproś użytkownika o utworzenie w ISPSoft projektu z co najmniej jednym (choćby
  pustym) programem i zapisanie go w folderze bibliotek – bez programu ISPSoft go nie skompiluje.
- `copy-fb` działa między dowolnymi projektami, nie tylko z bibliotekami.

## Wiedza o sterownikach
Pliki `.md` w `%USERPROFILE%\.claude\ispsoft\PLC` (inny folder: `%ISPSOFT_PLC%`); `info` wypisuje wszystkie
pasujące do modelu (np. dla AS228P: `AS.md`, `AS228.md`, `AS228P.md`). Jeśli folder `PLC` nie istnieje, zaproponuj
skopiowanie do niego plików startowych z `PLC_start` w katalogu skilla. Wpisy dopisuj zwięźle, z informacją,
czy są sprawdzone.

## Ograniczenia
Sprawdzone na ISPSoft 3.24 i AS228P. Dla innej serii lub wersji najpierw: `decode` → `encode` bez zmian →
kompilacja w ISPSoft. Obsługiwane języki: ST i LD (SFC, FBD nie). Typy (STRUCT/ENUM) nie mają polecenia `add`
– nowy typ to plik w `typy/` (wzór: istniejący plik) plus znacznik `@@PLIK:typy/<nazwa>.txt@@` w `_szkielet.txt`
wewnątrz `<DUT_INFO>`.
