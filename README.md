# Solvakt

Firmware för Raspberry Pi Pico 2 (RP2350) som styr två reläer baserat på aktuell solelsexport.
Data läses från en elmätare via UART (HAN-port, 115200 baud).

## Hårdvara

| Pin | Funktion |
|-----|----------|
| GP0 | UART TX |
| GP1 | UART RX (data från elmätare) |
| GP2 | Relä 1 (aktiv hög) |
| GP3 | Relä 2 (aktiv hög) |
| GP25 | Inbyggd LED (statusindikator) |

## Relälogik

Reläerna styrs i tre steg: OFF → ONE → BOTH.

| State | Relä 1 | Relä 2 | Villkor |
|-------|--------|--------|---------|
| OFF   | Av     | Av     | Startläge. Uppsteg när export ≥ 3,5 kW |
| ONE   | På     | Av     | Nedsteg när export < 0,3 kW, uppsteg när export ≥ 3,5 kW |
| BOTH  | På     | På     | Nedsteg när export < 0,3 kW |

- **Uppsteg** sker ett steg i taget med minst 10 sekunders mellanrum
- **Nedsteg** sker ett steg i taget direkt utan fördröjning
- Ingen data på 5 minuter stänger av båda reläerna

## LED

| State | Blinkmönster |
|-------|-------------|
| OFF   | Blinkar var 4:e sekund |
| ONE   | Blinkar 1 Hz |
| BOTH  | Blinkar 4 Hz |

## Bygga

### Krav

- [Raspberry Pi Pico VS Code Extension](https://marketplace.visualstudio.com/items?itemName=raspberry-pi.raspberry-pi-pico) (installerar SDK och verktygskedja automatiskt)
- CMake och Ninja (ingår i tillägget)

### Steg

1. Klona repot och öppna i VS Code
2. Kör **CMake: Configure** (`Ctrl+Shift+P` → "CMake: Configure")  
   Detta skapar `build/`-katalogen med alla byggfiler.
3. Bygg med **Ctrl+Shift+B** eller uppgiften "Compile Project"
4. Flasha `build/solvakt.uf2` till Pico (håll BOOTSEL och anslut USB, dra över filen)
