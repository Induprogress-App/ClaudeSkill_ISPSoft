# Język LD w plikach `.ld` (ISPSoft)

Czytaj przed odczytem lub edycją pliku `.ld` w `_autogen`. Plik zawiera same networki programu/FB (treść
między `</LOCAL_VAR>` a `</POU>`); zmienne lokalne są w `.csv` obok. Instrukcje i ograniczenia sterownika
(numery `API_NUM` itd.): `info PROJEKT.isp --jezyk LD`. Ustalenia o zapisie LD dopisuj tutaj.

## Budowa networka (`P_Lang=1`)
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
