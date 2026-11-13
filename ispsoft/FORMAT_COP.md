# Format pliku `.cop` (sieć CANopen, CANopen Builder w ISPSoft)

Plik `<projekt>.cop` leży obok `<projekt>.isp` i zawiera całą konfigurację sieci CANopen modułu
(AS-FCOPM / master CANopen serii AS): master, do 128 węzłów (slave), Auto SDO i mapowanie PDO.
W samym `.isp` nie ma o tym śladu (jest tylko `AS_FCOPM_STATION` i `AS_FCOPM_RATE` w `<projekt>.ini`).
Narzędzie: `cop_codec.py` (`dump`, `decode`, `encode`, `check`). Format ustalono z jednego projektu i zrzutów okien
CANopen Builder; `check` (rozkład → złożenie = ten sam plik) przechodzi na tym projekcie. Inny projekt może mieć
układ, którego tu nie opisano – wtedy `check` zgłosi błąd; nie edytuj takiego pliku.

## Zapis ogólny
Strumień binarny w stylu MFC: liczby little-endian. Napis ma dwa warianty zapisu, a cały plik używa jednego z nich:
- ANSI (starszy zapis): 1 bajt długości + znaki (strona kodowa 1250); plik zaczyna się od bajtu `0F`,
- Unicode (zapis nowszego ISPSoft): `FF FE FF` + 1 bajt długości (liczba znaków) + znaki UTF-16LE; plik zaczyna się
  od `FF FE FF 0F`. Pusty napis to `FF FE FF 00`, więc plik jest ok. 1,5 raza większy.
Narzędzie rozpoznaje wariant po początku pliku i przy składaniu zachowuje go (`master.unicode`).
Plik ma stałą liczbę rekordów (128 węzłów, numer węzła = numer rekordu 0..127) i stałe pojemności tablic
(nieużywane miejsce jest wypełnione zerami), więc rozmiar pliku zmienia się tylko o długość napisów.

## Nagłówek i master
| Pole | Zapis |
|---|---|
| napis `CANopen Builder` (`title`) | napis |
| `hdr1` | 6 bajtów `25 03 20 20 07 02` |
| `hdr_strs` | 6 pustych napisów |
| `hdr2` | 27 bajtów, zachowywane bez zmian |
| czas heartbeat mastera (ms) | u32 |
| nazwa mastera | napis |
| flaga | u8 (1) |
| kod prędkości | u8; 6 = 1 Mbps (zgodny z `AS_FCOPM_RATE`), pozostałych kodów nie sprawdzono |
| COB-ID SYNC | u32 (128) |
| okres SYNC | u32, w jednostkach 1000 µs |
| tryb pracy | u8 (0 = Master Mode) |
| identyfikator | napis 32 znaków (4 liczby hex: vendor, 0, 0x49, 0x00010002 – znaczenie niepewne) |

Numer węzła mastera (okno „Master Configuration”) nie został odnaleziony w nagłówku.

## Rekord węzła
Kolejno (rekord 0 ma na początku 9 bajtów `pre_vendor`, pozostałe 24; oba zachowywane bez zmian):

| Pole | Zapis |
|---|---|
| `pre_vendor` | surowe bajty (stałe: `0a000000 88130000 0a000000 0a000000 05000000 000100 xx`; ostatni bajt `xx` zależy od węzła) |
| Vendor Id, Device Type, Product Code, Revision | cztery pary: wartość u32 + u32 „zaznaczone” (pola z okna Node Configuration) |
| COB-ID Emergency | u32 (0x80 + numer węzła) |
| COB-ID Node Guard | u32 (0x700 + numer węzła) |
| Guard Time (ms) | u32 |
| Life Time Factor | u8 |
| Node Heartbeat Producer Time (ms) | u32 |
| Master Consumer Timeout (ms) | u32 |
| tryb kontroli błędów | u32; 1 = Heartbeat |
| nazwa węzła | napis |
| nazwa EDS | napis (`99999` dla węzła bez pliku EDS) |
| `flag_a` | u8; 1 dla węzła skonfigurowanego, 0 dla pustego; po przypisaniu węzła do rejestrów jest 1 (w pliku widziano węzeł z 0 przed przypisaniem) |
| `flag_b` | u8; 0 albo 2, zależy od historii edycji węzła – zachowywany, nie interpretowany |
| Auto SDO | licznik u8, potem 20 wpisów po 20 bajtów (pojemność 20) |
| `pre_pdo` | 13 bajtów, zachowywane bez zmian (np. `01 96 00 01 …` w węźle skonfigurowanym, zera w pustym) |
| liczby PDO | 2 bajty: ile slotów Tx i ile Rx ma mapowanie (wyliczane przy składaniu) |
| sloty PDO | 16 slotów w kolejności Tx1, Rx1, Tx2, Rx2, … Tx8, Rx8 |
| `trail` | 76 bajtów (ostatni węzeł: reszta pliku) |

Następny rekord zaczyna się od razu po `trail`, a jego `pre_vendor` i pola identyfikacyjne leżą już w obrębie
tych bajtów – dlatego odczyt jest sekwencyjny, a pola identyfikacyjne zaczynają się 57 bajtów przed nazwą węzła.

### Auto SDO
Dane wysyłane do węzła po nawiązaniu połączenia. Wpis (20 B): `u16 indeks, u16 podindeks, u32 długość (bajty),
u32 0, u32 dane, u32 0`. Dla napędów Delta ASDA indeks `0x2000 + 0x100*grupa + numer` odpowiada parametrowi
P<grupa>-<numer> (np. 0x220A = P2-10).

### Slot PDO
| Pole | Tx (178 B pusty) | Rx (170 B pusty) |
|---|---|---|
| COB-ID | u32 | u32 |
| Event Timer | u32 | – |
| indeks parametru komunikacyjnego | u32 (0x1800+n) | u32 (0x1400+n) |
| Inhibit Timer | u32 | – |
| typ transmisji | u8 (1 = synchroniczny cykliczny, 254/255 = asynchroniczny) | u8 |
| liczba wpisów mapowania | u8 | u8 |
| tablica mapowania | 32 × (`u8 bity, u8 podindeks, u16 indeks, napis nazwa obiektu`) | j.w. |

Puste wpisy mapowania mają 5 bajtów (nazwa pusta). Wpis aktywny zajmuje 5 + długość nazwy. Wpisy za licznikiem
mogą zawierać stare dane (pozostałość po usunięciu obiektu z PDO) – narzędzie zachowuje je w polu `stale_map`.
Pusty slot ma COB-ID 0, typ 255 i indeks 0 albo 0xFFFF (zależnie od węzła).

### Koniec rekordu (`trail`) i mapowanie na rejestry
Pierwsze 16 bajtów: `u32 in_offset, u32 out_offset, u32 bajty_Tx, u32 bajty_Rx`.
- `in_offset` – przesunięcie danych węzła (Tx, odczyt ze slave) w bajtach od początku obszaru wejść,
- `out_offset` – przesunięcie danych węzła (Rx, zapis do slave) w bajtach od początku obszaru wyjść,
- `bajty_Tx`, `bajty_Rx` – suma bitów mapowań slotów Tx / Rx podzielona przez 8 (narzędzie przelicza przy składaniu).

Adres rejestru D węzła = początek obszaru + przesunięcie / 2. Sprawdzone na projekcie z początkami obszarów
D25032 (zapis) i D24032 (odczyt): węzeł z przesunięciem 0 → D25032 / D24032, przesunięcie 16 → D25040 / D24040,
36 → D25050 / D24050, 56 → D25060 / D24060, 1736 → D25900 / D24900; wejścia i wyjścia mają osobne przesunięcia
(68 B → D25066, 72 B → D24068). Same początki obszarów (D25032, D24032) nie są zapisane w `.cop` – narzędzie
pokazuje adresy D, gdy poda się je w `dump plik.cop 25032 24032`. Bloki węzłów układają się co 20 bajtów
(10 słów) lub inaczej, jeśli przypisano je ręcznie.

Dalej 60 bajtów stałych: u32 `0x168`, bajty `01 01 14 00 00 00`, u32 10, trzy razy u32 10000, zera, u32 1,
u32 0x80 oraz liczby zmiennoprzecinkowe 10000.0 / 1.0 / 1.0 / 10000.0 (granice parametrów, znaczenie nie zbadane).
W JSON są jako `trail` (bez pierwszych 16 bajtów); ostatni węzeł ma w pliku krótszą końcówkę.

## Czego nie ma w `.cop`
Początków obszarów rejestrów (np. D25032 / D24032 z okna „Node List Setting”) w pliku nie znaleziono; zapisane
są tylko przesunięcia węzłów (patrz wyżej).

## Do zbadania
- dokładne znaczenie `flag_b`, `pre_pdo` i ostatniego bajtu `pre_vendor`; początki obszarów rejestrów,
- numer węzła i pozostałe pola nagłówka mastera, inne kody prędkości,
- węzeł w trybie Node Guarding (zamiast Heartbeat), tryb Slave mastera,
- zależności: nowy węzeł dodany w GUI vs. wpis tylko w pliku (czy ISPSoft przyjmie ręcznie złożony `.cop`).
