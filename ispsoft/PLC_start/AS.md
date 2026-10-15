# Seria Delta AS (AS100/AS200/AS300) – wspólne ograniczenia i wskazówki

Plik czyta Claude przed pisaniem lub zmianą kodu dla sterowników serii AS. Dopisuj tu wszystko, co dotyczy
całej serii (błędy kompilacji, ograniczenia, sprawdzone wzorce). Informacje dla konkretnego modelu – w pliku
`<MODEL>.md` (np. `AS228P.md`). Przy każdym wpisie podawaj, czy jest sprawdzony.

## Projekt ISPSoft
- Projekt musi zawierać co najmniej jeden program – inaczej się nie skompiluje (sprawdzone).
- Kolejność programów w zadaniu cyklicznym = kolejność wykonywania (sprawdzone).

## Pamięć i adresowanie
- `X` wejścia, `Y` wyjścia (adres `Xm.n`, np. `X0.3`), `M` bity, `D` rejestry 16-bit, `T` timery, `C` liczniki,
  `S` kroki, `SM` bity systemowe, `SR` rejestry systemowe.
- Bit słowa: `D300.1`; adres zmiennej strukturalnej/tablicy = adres początkowy, kolejne słowa po kolei.
- `W…` – pamięć wewnętrzna przydzielana przez kompilator zmiennym bez adresu; niewidoczna w ISPSoft,
  nie przydzielaj jej ręcznie (sprawdzone).
- Zakresy pamięci w nowym projekcie (ISPSoft 3.24): M0–M8191, D0–D29999, T0–T511, C0–C511.
- Domyślne obszary retain: M6000–M8191, D20000–D23000.

## Język ST
- Enum: po ostatnim elemencie **nie może być przecinka** – błąd kompilacji (sprawdzone).
- Odwołanie do elementu enuma: `NazwaTypu.Element` (np. `TypKomendy.Start`).
- Wartość szesnastkowa: `16#00FF`; dostęp do bitu zmiennej: `Status.3 := TRUE;`.
- Komentarze: `(* ... *)`, `/* ... */`, `// ...`.
- Wywołanie FB: `Instancja(We1 := x, We2 := y, Wy => z);` – parametry można pomijać; 
  do wejść instancji można też przypisywać przed wywołaniem: `Instancja.We1 := x + y; Instancja();`.
  Wejście do bloku nie może zawierać działań: Niedozwolone: `Instancja(We1 := x + y);` 
- Instrukcje API dostępne w ST jak funkcje, np. `BMOV(źródło, liczba_słów, cel);`.
- Typ `Union32` (pola `uDW`, `uArrW[0..1]`) pochodzi z bibliotek ISPSoft, a nie z projektu.

## Język LD
- Numery instrukcji (`API_NUM` w zapisie projektu): TMR 14, + 50, - 54, MOV 190, TMRM 764.
- Bloki porównań i instrukcji zajmują w siatce 3 kolumny.

## Import/eksport
- Import zmiennych z CSV w ISPSoft nie przenosi poprawnie komentarzy wielowierszowych (błąd ISPSoft).

## inne informacje 
- Nie zawiera bloku funkcyjnego TON. trzeba korzystać z timerów i instrukcji TMR(rozdzielczość 100ms), TMRM(rozdzielczość 10ms), lub TMRH(rozdzielczość 1ms).

## Wnioski z 6 projektów maszyn (ISPSoft 3.19–3.20; AS228P, AS228R, AS218PX, AS218RX)
Wszystko poniżej odczytane z działających (kompilujących się) projektów; „?” = znaczenie niepotwierdzone.

### Projekt
- Kody CPU w pliku projektu: AS228P 3011, AS228R 3012, AS218PX 3014, AS218RX 3015.
- Zakresy pamięci identyczne we wszystkich czterech modelach: M0–M8191, D0–D29999, T0–T511, C0–C511.
- Obszary retain ustawione we wszystkich 6 projektach: M2048–M4095, D2000–D3919, C224–C254, S912–S1023
  (ustawienie projektu – sprawdzaj `info PROJEKT.isp`).
- Wszystkie projekty używają tylko zadania cyklicznego (T_ID=0, 20 ms).

### Deklaracje
- Klasy zmiennych: `VAR`, `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT`, `VAR_RETAIN` (lokalna zmienna podtrzymywana –
  kompilator przydziela jej adres `W`, np. `[@W0@]`).
- Zmienne lokalne instancji FB dostają po kompilacji adresy `U…` (pamięć instancji FB).
- Typy elementarne w użyciu: BOOL, WORD, DWORD, INT, REAL, TIMER (zmienna typu TIMER z adresem `T11`).
- Tablica w deklaracji zmiennej: `ARRAY [N] OF Typ` (N = liczba elementów, indeks od 0); w definicji struktury
  także `ARRAY[0..24] OF Typ`. Tablice struktur: `ARRAY [9] OF Recipe`.
- Typy użytkownika: STRUCT, ENUM (wartości jawne, nazwy mogą zaczynać się od `_`, np. `_1s := 10`) oraz
  UNION: `TYPE X : UNION  a : Typ1;  b : Typ2;  END_UNION END_TYPE`.

### Język ST
- Słowa kluczowe i operatory bez rozróżniania wielkości liter (`if`/`IF`, `and`/`AND`).
- Instrukcje: `IF/ELSIF/ELSE/END_IF`, `CASE x OF ... END_CASE` (etykiety liczbowe i elementy enuma
  `eCycleStep.Init:`), `FOR i := a TO b [BY -1] DO ... END_FOR`, `EXIT`. `WHILE`/`REPEAT` nie występują w
  żadnym projekcie (niesprawdzone).
- Operatory: `AND OR XOR NOT MOD`, `= <> < > <= >=`, `:=`, `=>` (wyjście FB w wywołaniu).
- Funkcje konwersji IEC (`INT_TO_REAL` itp.) nie są używane – konwersje robi się instrukcjami API:
  `FLT(int, real)`, `DFLT(dint, real)`, `INT(real, int)`, `DINT(real, dint)`.
- Instrukcje API w ST mają postać `NAZWA(argumenty..., cel);`, np.:
  `BMOV(źródło, liczba_słów, cel)`, `NMOV(wartość, liczba, cel)` (wypełnienie), `RMOV(src, dst)` (REAL),
  `DECO(src, n, cel)`, `SQR(src, dst)`, `DLIMIT(min, max, we, wy)`, `TMR(T2, nastawa)`, `DPIDE(...)` (PID).
- Rejestr indeksowy `E`: `E0 := przesuniecie;` i adres `D2500@E0` = D(2500 + E0).
- Rejestry systemowe można czytać i zapisywać w ST jak zmienne: `x := SR826;`, `SR172 := wartosc;`.

### Język LD – instrukcje i numery API (`API_NUM`)
- Przedrostek `D` = wersja 32-bitowa (DMOV, DINC, D+, D-, D/, DCNT, DLIMIT), przyrostek `P` = wykonanie
  impulsowe (MOVP, DMOVP, INCP, DECP), przedrostek `F` = liczby zmiennoprzecinkowe (F+, F-, F*, F/).
- Przesyłanie: MOV 190, MOVP 191, DMOV 192, DMOVP 193, BMOV 202, NMOV 204, MOVB 220, MMOV 144.
- Arytmetyka: + 50, D+ 52, - 54, D- 56, * 58, / 62, D/ 64, F+ 66, F- 70, F* 74, F/ 78, MUL16 112, DIV16 116,
  DIV32 118, INT 136.
- Inkrementacja: INC 104, INCP 105, DINC 106, DEC 108, DECP 109.
- Timery/liczniki: TMR 14, DCNT 17, TMRM 764 (TMRH – niesprawdzony numer).
- Logika na słowach: WAND 250, WOR 256; przesuw: WSFR 304; dekoder: DECO 348; ZRST 356 (zerowanie zakresu);
  SORT 354; LIMIT 394, DLIMIT 396; SCLP 170 (skalowanie); CMPT<> 36.
- Porównania-styki (TYPE 10, API -1): `= <> < > <= >=`, 32-bitowe `D= D<> D< D> D>=`, REAL `F< F>`,
  `& ` (iloczyn bitowy), `Z<` i `DZ< DZ> DZ<=` (?).
  
## Bity i rejestry systemowe 
- `SM400` – zawsze ON.
- `SM405` – zegar 100 ms (zbocze narastające używane jako impuls 100 ms).
- `SM407` – zegar 1 s (OFF-500ms, ON-500ms ).
- `SR411` / `SR412` – czas cyklu: część w ms / część w µs (używane do odmierzania czasu w FB timera).
- `SM400` The flag is always ON (normally open) when the CPU runs. 
- `SM401` The flag is always OFF (normally closed) when the CPU runs. 
- `SM402` The flag is ON only at the first scan.
- `SM403` The flag is OFF only at the first scan.
- `SM404` 10-millisecond clock pulse during which the pulse is ON for 5 milliseconds and then OFF for 5 milliseconds.
- `SM405` 100-millisecond clock pulse during which the pulse is ON for 50 milliseconds and then OFF for 50 milliseconds.
- `SM406` 200-millisecond clock pulse during which the pulse is ON for 100 milliseconds and then OFF for 100 milliseconds.
- `SM407` One-second clock pulse during which the pulse is ON for 500 milliseconds and then OFF for 500 milliseconds.
- `SM604`, `SM750` (SET przy starcie), `SM1376`, `SM1377`, `SM1408`, `SM1409` – używane w LD (?).
- `SR826` – odczytywany jako błąd CAN (kolejne bity oznaczają błąd komunikacji kolejnego slave).



