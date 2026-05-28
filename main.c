#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"

#define UART_ID         uart0
#define UART_TX_PIN     0
#define UART_RX_PIN     1
#define BAUD_RATE       115200

#define RELAY1_PIN      2
#define RELAY2_PIN      3
#define LED_PIN         25  // Built-in LED on Pico

// Thresholds in milliwatts to avoid float comparisons
#define THRESHOLD_STEP_UP_MW    3500  // Step relay up one level when export exceeds this
#define THRESHOLD_STEP_DOWN_MW   300  // Step relay to OFF immediately when export falls below this

#define STEP_INTERVAL_MS    10000u  // Minimum ms between step changes (matches HAN update rate)

#define NO_DATA_TIMEOUT_MS  300000u  // 5 minutes
#define WATCHDOG_MS           8000u  // Max for RP2350 is ~8388ms

#define BLINK_IDLE_MS  2000u  // 1 blink/4sec = idle, no patrons active
#define BLINK_SLOW_MS   500u  // 1 blink/sec  = one patron active
#define BLINK_FAST_MS   125u  // 4 blinks/sec = both patrons active

#define LINE_BUF_SIZE   128

typedef enum { STATE_OFF, STATE_ONE, STATE_BOTH } relay_state_t;

static relay_state_t relay_state = STATE_OFF;
static char line_buf[LINE_BUF_SIZE];
static int  line_pos = 0;

static void usb_printf(const char *fmt, ...) {
    if (!stdio_usb_connected()) return;
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

static const char *state_name(relay_state_t s) {
    static const char *names[] = {
        [STATE_OFF]  = "OFF",
        [STATE_ONE]  = "ONE",
        [STATE_BOTH] = "BOTH",
    };
    return names[s];
}

static void set_relays_and_state(relay_state_t new_state) {
    if (new_state == relay_state) return;

    static const struct { int r1; int r2; } relay_map[] = {
        [STATE_OFF]  = { 0, 0 },
        [STATE_ONE]  = { 1, 0 },
        [STATE_BOTH] = { 1, 1 },
    };
    gpio_put(RELAY1_PIN, relay_map[new_state].r1);
    gpio_put(RELAY2_PIN, relay_map[new_state].r2);
    
    usb_printf("Relay: %s -> %s\n", state_name(relay_state), state_name(new_state));
    
    relay_state = new_state;
}

// Parses a line looking for: 1-0:2.7.0(X.XXX*kW)
static bool parse_export_power(const char *line, int *mw_out) {
    const char *p = strstr(line, "1-0:2.7.0(");
    if (!p) return false;
    p += 10;
    char *end;
    float kw = strtof(p, &end);
    if (end == p) return false;
    *mw_out = (int)(kw * 1000.0f + 0.5f);
    return true;
}

static void process_power(int export_mw, uint32_t now_ms) {
    static uint32_t last_state_update_ms = 0;

    relay_state_t nextState = 
        export_mw < THRESHOLD_STEP_DOWN_MW && relay_state > STATE_OFF ?  (relay_state_t)(relay_state - 1) : 
        export_mw >= THRESHOLD_STEP_UP_MW && relay_state < STATE_BOTH ?  (relay_state_t)(relay_state + 1) : 
        relay_state;

    if (nextState == relay_state) return;
    if (nextState > relay_state && (now_ms - last_state_update_ms < STEP_INTERVAL_MS)) return;

    set_relays_and_state(nextState);
    last_state_update_ms = now_ms;
}

static void update_led(uint32_t now_ms, uint32_t *led_toggle_ms, bool *led_on) {
    static const uint32_t blink_ms[] = {
        [STATE_OFF]  = BLINK_IDLE_MS,
        [STATE_ONE]  = BLINK_SLOW_MS,
        [STATE_BOTH] = BLINK_FAST_MS,
    };

    uint32_t interval = blink_ms[relay_state];
    if (now_ms - *led_toggle_ms >= interval) {
        *led_on = !*led_on;
        gpio_put(LED_PIN, *led_on);
        *led_toggle_ms = now_ms;
    }
}

static void boot_sequence() {
    stdio_init_all();

    // Relays: write value before setting direction to avoid output glitch on startup
    gpio_init(RELAY1_PIN);
    gpio_put(RELAY1_PIN, 0);
    gpio_set_dir(RELAY1_PIN, GPIO_OUT);

    gpio_init(RELAY2_PIN);
    gpio_put(RELAY2_PIN, 0);
    gpio_set_dir(RELAY2_PIN, GPIO_OUT);

    // LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 0);

    // UART0 on GP0 (TX) / GP1 (RX), 115200 8N1, no flow control
    uart_init(UART_ID, BAUD_RATE);
    gpio_set_function(UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(UART_RX_PIN, GPIO_FUNC_UART);
    uart_set_hw_flow(UART_ID, false, false);
    uart_set_format(UART_ID, 8, 1, UART_PARITY_NONE);

    // -- 10 seconds idle at boot to setup uart and HAN-connector when using USB --
    for (int i = 0; i < 10; i++) {
        gpio_put(LED_PIN, 1);
        sleep_ms(500);
        gpio_put(LED_PIN, 0);
        sleep_ms(500);
    }

    watchdog_enable(WATCHDOG_MS, true);
}

int main(void) {
    bool watchdog_rebooted = watchdog_caused_reboot();

    boot_sequence();

    if (watchdog_rebooted) usb_printf("*** WATCHDOG REBOOT ***\n");
    usb_printf("Solvakt started. step_up=%.1f kW step_down=%.1f kW interval=%u s\n", THRESHOLD_STEP_UP_MW / 1000.0f, THRESHOLD_STEP_DOWN_MW / 1000.0f, STEP_INTERVAL_MS / 1000u);

    uint32_t last_data_ms  = to_ms_since_boot(get_absolute_time());
    uint32_t led_toggle_ms = 0;
    bool     led_on        = false;

    while (true) {
        watchdog_update();

        uint32_t now_ms = to_ms_since_boot(get_absolute_time());

        // --- LED ---
        update_led(now_ms, &led_toggle_ms, &led_on);

        // --- No-data timeout: turn everything off if meter goes silent ---
        if (now_ms - last_data_ms >= NO_DATA_TIMEOUT_MS) {
            usb_printf("No data for %u s, turning off\n", NO_DATA_TIMEOUT_MS / 1000);
            set_relays_and_state(STATE_OFF);
            last_data_ms = now_ms;
        }

        // --- Drain UART FIFO ---
        while (uart_is_readable(UART_ID)) {
            char c = uart_getc(UART_ID);
            if (c == '\r' || c == '\n') {
                if (line_pos > 0) {
                    line_buf[line_pos] = '\0';
                    int export_mw;
                    if (parse_export_power(line_buf, &export_mw)) {
                        last_data_ms = now_ms;
                        usb_printf("Export: %d.%03d kW\n", export_mw / 1000, export_mw % 1000);
                        process_power(export_mw, now_ms);
                    }
                    line_pos = 0;
                }
                continue;
            }
            if (line_pos < LINE_BUF_SIZE - 1) {
                line_buf[line_pos++] = c;
                continue;
            }
            line_pos = 0;  // Line too long, discard and resync
        }

        sleep_ms(1);
    }
}
