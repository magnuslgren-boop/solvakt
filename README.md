# Solvakt

Firmware för Raspberry Pi Pico (RP2040) som styr två reläer baserat på aktuell solelsexport.
Data läses från en elmätare via UART (P1-port, 115200 baud).

## Hårdvara

| Pin | Funktion |
|-----|----------|
| GP0 | UART TX |
| GP1 | UART RX (data från elmätare) |
| GP2 | Relä 1 |
| GP3 | Relä 2 |
| GP25 | Inbyggd LED (statusindikator) |

## Logik

| Exporteffekt | Reläer | LED |
|---|---|---|
| > 6,5 kW | Båda på | Blinkar snabbt (4 Hz) |
| 3,5 – 6,5 kW | Relä 1 på | Blinkar långsamt (1 Hz) |
| < 0,5 kW | Båda av | Släckt |
| 0,5 – 3,5 kW | Hystereszonen, behåller nuvarande läge | — |

Ingen data på 5 minuter stänger av båda reläerna. Watchdog-reset indikeras med fast lysande LED.

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
