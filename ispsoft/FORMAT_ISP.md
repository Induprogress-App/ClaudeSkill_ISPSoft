# Format projektu ISPSoft 3.24 (AS228P) – ustalenia

Narzędzie: `isp_codec.py` (instrukcja: README.md).

## Praca z projektem przez `_autogen`
```
python isp_codec.py decode Projekt/Projekt.isp      # rozkłada projekt do Projekt/_autogen
python isp_codec.py encode Projekt/Projekt.isp      # składa _autogen z powrotem (kopia: .isp.przed_encode)
```
```
_autogen/
  _naglowek.bin               nagłówek binarny .isp
  _szkielet.txt               reszta projektu + znaczniki @@PLIK:ścieżka@@
  zadania.txt                 <TASK>
  drzewo_projektu.txt         <GroupPOUFolder>
  zmienne_globalne/<tabela>.txt
  typy/<nazwa>.txt            DutContent rozpisany na zwykłe linie
  programy/<foldery>/<POU>.info|.csv|.st|.ld
  bloki_funkcyjne/<foldery>/<POU>.info|.csv|.st|.ld
```
- POU jest rozdzielony na: `.info` (sekcja POU, w której `<LOCAL_VAR>…</LOCAL_VAR>` zastępuje znacznik `@@ZMIENNE@@`,
  a kod – `@@KOD@@`; na końcu po `@@ADRESY_Z_KOMPILACJI@@` adresy `W*` zmiennych lokalnych), `.csv` (zmienne lokalne)
  i `.st`/`.ld` (treść `<IL_ST_CODE>` albo networki). POU, którego nie da się tak rozdzielić bezstratnie, zostaje jako `.txt`.
- CSV zmiennych (format eksportu/importu ISPSoft, zgodny bajt w bajt z eksportem z ISPSoft):
  `Class,Identifiers,Address,Type,Initial Value,Comment`, strona kodowa projektu, nowa linia w komentarzu zapisana jako
  `CR CR LF`, adresy `W*` pomijane (eksport ISPSoft też ich nie zawiera). Pole z przecinkiem/cudzysłowem narzędzie
  ujmuje w cudzysłów (nie sprawdzono, jak robi to ISPSoft).
- Import CSV w ISPSoft (sprawdzone 2026-10-14): zmienne dodaje poprawnie, ale komentarza wielowierszowego nie importuje
  poprawnie – także z pliku wyeksportowanego przez ISPSoft (błąd po stronie ISPSoft).
- Pliki w UTF-8; przy `encode` końce linii są zamieniane na CRLF, a tekst na stronę kodową projektu.
- `decode` sprawdza, że rozkład i złożenie dają plik identyczny 1:1, i odmawia nadpisania `_autogen`, jeśli zawiera niezakodowane zmiany (`--force` pomija tę kontrolę).
- Nowy program/FB/zmienną dodają polecenia `add-prg`, `add-fb`, `add-var` (opis w README.md). Nowy typ (DUT) wymaga
  ręcznego pliku w `typy/` i znacznika w `_szkielet.txt` wewnątrz `<DUT_INFO>`.
- `_zrodlo.txt` przechowuje CRC treści `.isp`, z której powstał `_autogen`. `add-*` i `encode` odmawiają pracy, jeśli
  `.isp` zmieniono później (np. zapis w ISPSoft), a `decode` – jeśli `_autogen` ma niezapisane zmiany.
- `decode-txt` / `encode-txt` – cały projekt jako jeden plik tekstowy.

## Kontener `.isp`
- Nagłówek 0xA4 bajtów, potem blok: `u16 0x0008`, `u32 CRC32(tekst)`, strumień raw deflate (poziom 9).
- Pola nagłówka: 0x7C = rozmiar tekstu, 0x94 = długość bloku, 0x98 = offset bloku (0xA4).
- u16 pod 0x92 nie jest sprawdzane (ISPSoft przyjmuje dowolną wartość).
- **Duże/skompilowane projekty**: offset bloku pod 0x98 nie jest równy 0xA4. Między 0xA0 a blokiem
  danych jest dodatkowy obszar (długość pod 0x9C), zakodowany XOR 0x5D – najpewniej skompilowany kod. Pola 0x88 i 0x90
  mają wtedy niezerowe wartości (znaczenie nieznane). `isp_codec` przenosi cały ten obszar bez zmian w `_naglowek.bin`.
- ISPSoft nie zawsze kompresuje identycznie jak zlib (w dużym projekcie żaden poziom zlib nie daje tych samych bajtów),
  więc po `encode` taki plik różni się bajtami deflate, ale nie treścią.
- Tekst: CRLF, strona kodowa 1250.
- `.bak` = kopia `.isp`; `*_data.~bak` = automatyczne kopie zapasowe.

## Pliki pomocnicze
| Plik | Zawartość | Potrzebny do generowania? |
|---|---|---|
| `.ini` | ustawienia komunikacji + otwarte okna edytora | wystarczy kopia |
| `.pnt` | tabela pozycjonowania osi (ten sam kontener, nagłówek 0x100) | wystarczy kopia |
| `.ipc` | ZIP **szyfrowany** z `CompiledObject.txt` (wynik kompilacji) | nie, powstaje przy kompilacji |
| `.eiptag`, `.inivals`, `.SRbitExistedInProg` | dane z kompilacji / EtherNet/IP | nie |
| `*.diatag` | ręczny eksport tabeli zmiennych (XML) dla DIAScreen/HMI | nie |

## Zmienne globalne – `<GLOBAL_VAR>`
Każda tabela zaczyna się linią `TableName=...`, a jej zmienne idą zaraz za nią.
Domyślna tabela („Main Table” w GUI) ma w pliku nazwę `Global Variables`.
```
<GLOBAL_VAR>
TableName=Global Variables
{
VAR
globalVar1
D100;WORD;
(*
komentarz
*)
}
TableName=HMI
{
VAR
Input_1
X0.0;BOOL;
(*

*)
}
</GLOBAL_VAR>
```
Linia 3 bloku to `ADRES;TYP;WARTOŚĆ_POCZ` (np. `D100;WORD;123`).
Zmienna bez adresu (przed kompilacją): pusty adres, np. `;DWORD;` albo `;STRING(10);`.
Po kompilacji dostaje adres wewnętrzny `W...` (niewidoczny w GUI), który zostaje zapisany w tej linii. Przykłady adresów: `D100`, `W5000`, `X0.0`, `D300.1` (bit słowa), `M0`, `T0` (typ TIMER).
Tablice: `ARRAY [10] OF WORD`.
Jeszcze nie wiadomo: RETAIN, CONSTANT (czy zmieniają linię `VAR`).

## Zadania – `<TASK>`
Każde zadanie to blok `[TASK_S]`…`[TASK_E]`. Programy przypisane do zadania to kolejne linie `T_PName=`, w kolejności wykonywania:
```
[TASK_S]
T_ID=0
T_ACT=TRUE
T_CONFIG_TYPE=3
T_CycTime=20
...
T_PName=TEST
T_PName=Prog0
T_PName=Prog1
[TASK_E]
```
- `T_ID`: 0 = zadanie cykliczne, 32 = ExternalInputInterrupt(000). Pozostałe zadania przerwań mają pewnie inne ID (do sprawdzenia).
- Zadanie przerwania ma te same pola co cykliczne (`T_CONFIG_TYPE=3`, `T_CycTime=20`…), ale ich znaczenie jest tu niejasne.
- Kolejność linii `T_PName` = kolejność wykonywania (potwierdzone zmianą kolejności w GUI).

## Drzewo projektu – `<GroupPOUFolder>`
`<ProgramFolder>` (programy) i `<FBFolder>` (bloki funkcyjne) zawierają wpisy `<FolderContent>`:
- `ContentType`: -1 = folder, 0 = program, 1 = FB.
- `ContentPath`: ścieżka folderu z `/` na końcu (np. `FolderProgramow/`), pusta dla korzenia.
- Folder: `ContentName=FolderProgramow`, `ContentPath=FolderProgramow/`. Elementy w nim mają ten sam `ContentPath`.
- Zagnieżdżenie: pełna ścieżka, np. folder `ContentName=FolderLVL2`, `ContentPath=FolderProgramow/FolderLVL2/`.
- Kolejność wpisów = przejście drzewa w głąb: folder, jego podfoldery i ich zawartość, potem pozostałe elementy folderu, na końcu elementy z korzenia.
  Sekcje `<POU>` są zapisywane w tej samej kolejności.

## POU – `<POU>`
Sekcje `<POU>` są zaraz po `</GroupPOUFolder>`, w kolejności z drzewa projektu: najpierw programy (z folderami na początku), potem FB.
- `P_type`: 0 = program, 1 = blok funkcyjny.
- Klasy zmiennych w `{...}`: `{VAR}`, `{VAR_INPUT}`, `{VAR_OUTPUT}`, `{VAR_IN_OUT}`.
- Instancja FB to zwykła zmienna lokalna z typem = nazwa FB: `testFB : FB_testowyBlokFunkcyjny :=  [@@] {VAR}`.
- Komentarze w kodzie ST: `(* ... *)` i `// ...` są zapisywane bez zmian, polskie znaki w CP1250.

## Zmienne lokalne – `<POU>` → `<LOCAL_VAR>` → `<VAR>`
Jeden blok `{ }` na jedną zmienną (kilka zmiennych w jednym bloku: ISPSoft czyta tylko pierwszą):
```
{
nazwa : TYP := WARTOŚĆ_POCZ [@ADRES@] {VAR}
(*
wiersz1
wiersz2
*)
}
```
- Wartość początkowa: `licznik : INT := 5 [@@] {VAR}` (zapis wygenerowany narzędziem, projekt się kompiluje).
- `[@@]` = brak adresu. Po kompilacji ISPSoft sam przydziela adresy (np. `[@W5010.0@]`) i zapisuje je w pliku.

## Kod ST – `<IL_ST_CODE>`
Zwykły tekst programu. `P_Lang=4` = ST.

## Kod LD (`P_Lang=1`)
Zamiast `<IL_ST_CODE>` po `</LOCAL_VAR>` są kolejne networki:
```
<NETWORK_START>
<PROPERTIES_START>
NET_ID=1
NET_LABEL=
NET_ACTIVE=TRUE
NET_BOOKMARK=FALSE
NET_MODIFY=TRUE
NET_FOLD=FALSE
(*
komentarz networka
*)
<PROPERTIES_END>
<ROOTLINK_START>   ← część warunkowa (styki, porównania)
[LD_NODE] ... [END_LD_NODE]
<ROOTLINK_END>
<OUTLINK_START>    ← część wyjściowa (cewki, instrukcje API)
[LD_NODE] ... [END_LD_NODE]
<OUTLINK_END>
<NETWORK_END>
```
Pusty network: puste sekcje `<ROOTLINK_START>`/`<OUTLINK_START>`. Cewka RESET (`16`) działa też na timerze i słowie (`T511`, `Time_last`).

Typy węzłów `[LD_NODE]` (ustalone na podstawie zrzutów ekranu edytora LD):
| TYPE | Znaczenie | Pola |
|---|---|---|
| 1 | styk NO | `DEV_NAME=` |
| 2 | styk NC | `DEV_NAME=` |
| 3 | styk zbocza narastającego `↑` | `DEV_NAME=` |
| 4 | styk zbocza opadającego `↓` | `DEV_NAME=` |
| 5 | pusta kratka (linia pozioma) w części warunkowej | `DEV_NAME=` (puste) |
| 6 | zamknięcie gałęzi równoległych w części warunkowej | `LNK_C=` liczba gałęzi, `LNK_L=` szerokość gałęzi w kolumnach |
| 7 | koniec bloku instrukcji/FB | – |
| 8 | wywołanie bloku funkcyjnego | `SYMB=`typ FB, `DEV_NAME=`instancja, `API_NUM=-1` |
| 9 | instrukcja API | `SYMB=TMR`/`+`…, `DEV_NAME=`, `API_NUM=` (TMR = 14, + = 50, - = 54, MOV = 190, TMRM = 764) |
| 10 | instrukcja porównania (działa jak styk) | `SYMB==`, `API_NUM=-1` |
| 11 | operandy wejściowe bloku | `<VAR_NODE_S>`, `VAR_NAME=` ×N, `<VAR_NODE_E>` |
| 12 | operandy wyjściowe bloku (może być pusty) | jw. |
| 13 | cewka `( )` | `DEV_NAME=` |
| 15 | cewka SET `(S)` | `DEV_NAME=` |
| 16 | cewka RESET `(R)` | `DEV_NAME=` |
| 20 | pusta kratka w części wyjściowej | `DEV_NAME=` (puste) |
| 24 | impuls zbocza narastającego na linii wyjść (`↑` przed cewką) | `DEV_NAME=???` |
| 25 | impuls zbocza opadającego na linii wyjść (`↓` przed cewką) | `DEV_NAME=???` |
| 29 | zamknięcie gałęzi równoległych w części wyjściowej | `LNK_C=`, `LNK_L=` jak w 6 |

### Zasada zapisu (notacja postfiksowa na siatce)
- Elementy szeregowe = kolejne węzły; każdy zajmuje 1 kolumnę.
- Gałęzie równoległe: kolejno zawartość każdej gałęzi, potem węzeł `6` (lub `29` po stronie wyjść).
  **Wszystkie gałęzie muszą mieć tę samą szerokość `LNK_L`**, krótsze są dopełniane węzłami `5`/`20`.
- Zagnieżdżona grupa równoległa liczy się jako 1 kolumna (sprawdzone dla grupy o szerokości 1).
- Instrukcja API po stronie wyjść (`11,9,12,7`, np. TMRM/MOV/-) również zajmuje **3 kolumny** (blok + `20` w gałęzi o `LNK_L=4`).
- Blok porównania (`11,10,12,7`) zajmuje **3 kolumny** (network 3: 2 porównania w gałęzi → `LNK_L=6`).
- Odczyt: węzeł `6`/`29` zabiera ze stosu `LNK_C` ostatnich gałęzi, każda o szerokości `LNK_L`, licząc od końca.
  Dzięki temu gałąź może zaczynać się w środku networka: network 6 = `M30, M31, M32, 6(C=2,L=1)` → `M30·(M31+M32)`.
- `NET_FOLD=TRUE` = network zwinięty w edytorze (tylko widok).
- Sprawdzone w ISPSoft (wygenerowane networki kompilują się i wyglądają zgodnie z zamierzeniem):
  grupa równoległa w środku gałęzi, styk zboczowy za grupą, równoległe wyjścia z RESET,
  porównanie poprzedzone stykiem, gałęzie różnej długości dopełnione węzłami `5`.
- Blok (instrukcja/FB): `11` (wejścia w kolejności pinów) → `8`/`9`/`10` → `12` (wyjścia) → `7`.
  FB i porównania są w `ROOTLINK`, instrukcje typu TMR/+ w `OUTLINK`. Wyjście `Eno` FB łączy się z `En` następnej instrukcji.
- Wstawienie FB w LD automatycznie dodaje zmienną lokalną instancji (`FB_testowyBlokFunkcyjny0 : FB_testowyBlokFunkcyjny`).

Przykład network 2: `Input_1, M5 | adressedBool_M, /M6 | 6(C=2,L=2) | M7` → `(Input_1·M5 + adressedBool_M·/M6)·M7`.

Przykład network 4 (3 gałęzie po 4 kolumny):
```
gałąź 1: M10, M12, 5, 5
gałąź 2: [↓M11 | ↑M13 | 6(C=2,L=1)], M14, 5, 5     ← zagnieżdżone OR = 1 kolumna
gałąź 3: M15, M16, M17, M18
6(C=3,L=4)
wyjścia: [M19( ), 20] | [D603.0, M20(S)] | 29(C=2,L=2)
```
Przykład network 6 (wyjścia): `[M33( ), 20] | [24, M34( )] | [25, M35( )] | 29(C=3,L=2)`.

## Tablice po kompilacji – `<ARY_VAR>`
Rozwinięcie elementów tablic na adresy, np. `{GLOBAL->GLOBALVAR2[0]}<W5000>(WORD)`. Tworzy je kompilator; w kolejnym zapisie bez kompilacji sekcja zniknęła, więc przy generowaniu ją pomijamy.

## Typy użytkownika – `<DUT_INFO>` → `<DUT_NODE>`
```
DutName=Struct_test
DutType=0            (0 = STRUCT, 1 = ENUM, 2 = UNION)
DutContent=TYPE ... END_TYPE
```
`DutContent` to tekst ST w jednej linii; każdy znak nowej linii jest zastąpiony ciągiem
`PLCnnnnnnnewLineAndSubstitudeeeeeeePLC`.

## Zgodność wersji
- Sprawdzone `decode` → `encode` bez zmian treści: projekty ISPSoft 3.19, 3.20 i 3.24, sterowniki AS228P, AS228R,
  AS218PX, AS218RX (kody CPU 3011, 3012, 3014, 3015). Wszystkie POU dały się rozdzielić na `.info/.csv/.st|.ld`.
- Klasa `{VAR_RETAIN}` w zmiennych lokalnych; zmienne lokalne instancji FB dostają po kompilacji adresy `U…`.
- UNION w `DutContent`: `TYPE X : UNION ... END_UNION END_TYPE` (`DutType=2`).
