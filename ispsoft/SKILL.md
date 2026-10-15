---
name: ispsoft
description: Odczyt i edycja projektów Delta ISPSoft (.isp) bez GUI – rozkładanie projektu na pliki tekstowe (kod ST/LD, zmienne CSV), spis programów i bloków z plikami, dodawanie programów, bloków funkcyjnych i zmiennych, wyszukiwanie zmiennych, kopiowanie bloków funkcyjnych z zależnościami między projektami i z własnych bibliotek ([lib]). Używaj zawsze, gdy rozmowa dotyczy projektu ISPSoft, pliku .isp, sterownika Delta serii AS albo kodu PLC w ST/LD tworzonego w ISPSoft.
---

# Projekty ISPSoft (.isp)

Narzędzie `isp_codec.py` leży w katalogu tego skilla (podanym przy jego wczytaniu jako katalog bazowy).
Wymaga tylko Pythona 3 – uruchamiaj je jako `python "<katalog skilla>/isp_codec.py" ...`
(jeśli polecenie `python` nie działa, spróbuj `py -3`).

## Pliki skilla – czytaj tylko ten, którego potrzebujesz
| Sytuacja | Plik |
|---|---|
| piszesz lub zmieniasz kod ST (`.st`) | `JEZYK_ST.md` |
| czytasz lub zmieniasz kod LD (`.ld`) | `JEZYK_LD.md` |
| potrzebujesz opcji polecenia, bibliotek `[lib]`, układu `_autogen` | `README.md` (albo `POLECENIE -h`) |
| inne pliki `_autogen` (tabele, typy, zadania, drzewo) albo błąd narzędzia | `FORMAT_ISP.md` |

## Zasady pracy
0. **Na początku: `info PROJEKT.isp --jezyk ST`** (albo `LD` – język, w którym będziesz pracować; bez opcji obie
   części). Pokazuje model sterownika, zadania, zakresy pamięci i zapisaną wiedzę o ograniczeniach sterownika
   (folder `PLC`) – stosuj się do niej. Gdy kompilacja zgłosi błąd wynikający z ograniczenia sterownika albo
   użytkownik poda nowe ograniczenie, zaproponuj dopisanie go do właściwego pliku w `PLC` (`AS.md` – seria,
   `<MODEL>.md` – model; sekcje o jednym języku mają w nagłówku `ST` albo `LD`) i dopisz po zgodzie.
1. **Projekt musi być zamknięty w ISPSoft**, zanim zapiszesz `.isp` (`encode` lub opcja `--encode`).
   Zapytaj użytkownika, jeśli nie wiesz. Jeśli użytkownik chce, pracuj na kopii projektu.
2. **Gdzie co jest: `list PROJEKT.isp [WZORZEC] [--typ PRG,FB,DUT,GVL]`** – jedna linia na element: nazwa,
   rodzaj, język/typ, rozmiar, zadanie i plik w `_autogen`. Wzorzec to fragment nazwy albo `Komunikacja*`.
   Nie przeglądaj folderów `_autogen` ręcznie. Gdzie użyta jest zmienna: `find-var`.
3. Otwieraj tylko potrzebne pliki: kod `.st`/`.ld`, zmienne lokalne `.csv` obok niego. Duży plik czytaj
   fragmentami (wyszukaj miejsce, potem przeczytaj zakres linii).
4. Edytuj kod bezpośrednio w plikach `.st`/`.ld`. Nowe programy, bloki funkcyjne i zmienne dodawaj poleceniami
   `add-prg`, `add-fb`, `add-var`. Nie edytuj `_szkielet.txt`, `_naglowek.bin`, `_zrodlo.txt` ani `_kompilacja/`
   i nie zapisuj własnych plików w `_autogen`. Nowy typ (DUT): `FORMAT_ISP.md`.
5. Po zmianach `encode PROJEKT.isp`, a potem poproś użytkownika o otwarcie projektu w ISPSoft i **kompilację** –
   tylko ona potwierdza poprawność. Zgłoszone błędy kompilacji poprawiaj w plikach `_autogen`.
6. Jeśli narzędzie odmawia (np. `.isp` zapisano w ISPSoft, a `_autogen` ma niezapisane zmiany, albo w `_autogen`
   są obce pliki), nie używaj `--force` bez zgody użytkownika – wyjaśnij, co zostałoby utracone.

## Styl kodu
Każdy pisze inaczej – nie narzucaj własnego stylu. Przed napisaniem nowego kodu przeczytaj 1–2 istniejące POU
z projektu i naśladuj ich konwencje (nazewnictwo, komentarze, sposób wywoływania bloków, struktury dla HMI).

## Biblioteki bloków funkcyjnych
W poleceniach zamiast ścieżki można podać `[lib]/NAZWA.isp` (folder bibliotek użytkownika). Kopiowanie bloku
z biblioteki lub do niej: `list-lib [WZORZEC]`, potem `copy-fb ... --dry-run`, pokaż plan użytkownikowi i dopiero
wtedy kopiuj. Szczegóły (także co zrobić, gdy biblioteki nie ma): `README.md`, sekcja „Biblioteki”.

## Ograniczenia
Sprawdzone na ISPSoft 3.19–3.24 i sterownikach AS228/AS218. Dla innej serii lub wersji najpierw: `decode` →
`encode` bez zmian → kompilacja w ISPSoft. Obsługiwane języki: ST i LD (SFC, FBD nie).
Jeśli folder `PLC` nie istnieje, zaproponuj skopiowanie do niego plików z `PLC_start` w katalogu skilla.
