# Język ST w plikach `.st` (ISPSoft)

Czytaj przed pisaniem lub edycją pliku `.st` w `_autogen`. Składnia ST jest standardowa (IEC 61131-3) –
tutaj tylko to, co wynika z ISPSoft i z zapisu projektu. Ograniczenia sterownika (instrukcje API, enumy,
wywołania FB, konwersje): `info PROJEKT.isp --jezyk ST`. Ustalenia o zapisie ST dopisuj tutaj.

## Plik `.st`
- Zawiera sam kod POU (treść `<IL_ST_CODE>`), bez deklaracji – można go w całości wkleić do edytora ISPSoft.
- Zmienne lokalne są w pliku `.csv` obok (`Class,Identifiers,Address,Type,Initial Value,Comment`); nowe dodawaj
  poleceniem `add-var`, nie ręcznie, chyba że zmieniasz istniejący wiersz.
- Kodowanie: w `_autogen` UTF-8, w `.isp` strona kodowa projektu (zwykle 1250) – znaki spoza niej się nie zapiszą.
- Komentarze `(* ... *)` i `// ...` są zapisywane bez zmian; nie zostawiaj `*)` wewnątrz komentarza.

## Deklaracje używane w kodzie
- Instancja FB to zmienna lokalna z typem = nazwa FB (np. `Zawor1 : Valve`), dodawana `add-var POU Zawor1 Valve`.
- Wejścia/wyjścia FB: `add-var FB Nazwa Typ --klasa VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT`.
- Zmienne globalne: tabele w `zmienne_globalne/`, adresy np. `D100`, `M10`, `X0.3`; bez adresu kompilator
  przydziela pamięć `W…` – nie wpisuj jej ręcznie.
- Typy użytkownika (STRUCT/ENUM/UNION): pliki `typy/<nazwa>.txt`, odwołanie do elementu enuma `Typ.Element`.

## Przed pisaniem kodu
- Sprawdź `list PROJEKT.isp --typ FB,DUT`, czy potrzebny blok lub typ już istnieje.
- Przeczytaj 1–2 istniejące POU i naśladuj ich styl.
