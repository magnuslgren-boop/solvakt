import serial
import RPi.GPIO as GPIO
import time
import re
from datetime import datetime

# Define GPIO pins
GPIO_PIN1 = 17  # First GPIO (Physical pin 11)
GPIO_PIN2 = 27  # Second GPIO (Physical pin 13)
SWITCH_PIN = 22  # Digital pin for rocker switch (change as needed)

# Power thresholds
THRESHOLD_1 = 4.500  # kW threshold for first GPIO (17)
THRESHOLD_2 = 3.000  # kW threshold for second GPIO (27) - only activates after GPIO 17
RESET_THRESHOLD = 0.500  # kW threshold for resetting pins (can be toggled to 1.500)
RESET_TIME = 30  # Time in seconds to stay over reset threshold before setting HIGH
NO_DATA_TIMEOUT = 300  # Time in seconds before resetting pins if no data received

# Serial connection retry parameters
MAX_RETRIES = 5  # Maximum number of initial connection attempts
RETRY_DELAY = 10  # Seconds to wait between retries

# Timer notification points
TIMER_NOTIFICATIONS = [30, 20, 10, 0]  # Only show timer at these points

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_PIN1, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(GPIO_PIN2, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Setup switch pin with pull-down
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO pins initialized: Pin {GPIO_PIN1}, Pin {GPIO_PIN2}, and Switch Pin {SWITCH_PIN}")

# Function to open serial port with retries
def open_serial_port(max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY):
    retries = 0
    while retries <= max_retries:
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to open serial port (attempt {retries+1}/{max_retries+1})")
            serial_port = serial.Serial(
                "/dev/ttyUSB0",
                baudrate=115200,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=None,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            )
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Serial port opened successfully")
            return serial_port
        except Exception as e:
            retries += 1
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to open serial port: {e}")
            if retries <= max_retries:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Maximum retries reached. Continuing without serial connection.")
                return None

# Open the serial port with retries
serial_port = open_serial_port()

# Tracking timers
reset_time_1 = None  # Timer for first GPIO reset
reset_time_2 = None  # Timer for second GPIO reset
last_timer1_notification = None  # Last timer value we notified for GPIO 1
last_timer2_notification = None  # Last timer value we notified for GPIO 2
last_data_time = time.time()  # Time when last data was received
switch_state = False  # Track switch state (False = 0.5kW, True = 1.5kW)
gpio17_low_time = None  # Timer for tracking when GPIO 17 went LOW
GPIO27_DELAY = 20  # Seconds to wait after GPIO 17 goes LOW before monitoring for GPIO 27

# Setup switch callback function
def switch_callback(channel):
    global RESET_THRESHOLD, switch_state
    switch_state = not switch_state
    if switch_state:
        RESET_THRESHOLD = 1.500
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Switch toggled ON: Reset threshold set to {RESET_THRESHOLD}kW")
    else:
        RESET_THRESHOLD = 0.500
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Switch toggled OFF: Reset threshold set to {RESET_THRESHOLD}kW")

# Add event detection for switch
GPIO.add_event_detect(SWITCH_PIN, GPIO.RISING, callback=switch_callback, bouncetime=300)

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting power monitoring with GPIO 17 threshold: {THRESHOLD_1}kW")
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO 27 will trigger at {THRESHOLD_2}kW but only {GPIO27_DELAY}s after GPIO 17 is LOW")
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reset threshold starting at {RESET_THRESHOLD}kW")
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reset time set to {RESET_TIME} seconds")
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No data timeout set to {NO_DATA_TIMEOUT} seconds")

try:
    while True:
        try:
            # Check if we've exceeded the no data timeout
            if time.time() - last_data_time > NO_DATA_TIMEOUT:
                if GPIO.input(GPIO_PIN1) == GPIO.LOW or GPIO.input(GPIO_PIN2) == GPIO.LOW:
                    GPIO.output(GPIO_PIN1, GPIO.HIGH)
                    GPIO.output(GPIO_PIN2, GPIO.HIGH)
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] NO DATA TIMEOUT: Both GPIO pins set to HIGH after {NO_DATA_TIMEOUT}s without data")
                last_data_time = time.time()  # Reset timer to prevent continuous messages
            
            # If serial port is None or closed, try to reopen it
            if serial_port is None or not serial_port.is_open:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No active serial connection. Attempting to reconnect...")
                serial_port = open_serial_port(max_retries=1, retry_delay=5)
                if serial_port is None:
                    # Sleep before next attempt
                    time.sleep(10)
                    continue
            
            # Read data from serial port with a timeout
            if serial_port and serial_port.in_waiting:
                line = serial_port.readline().decode().strip()
                last_data_time = time.time()  # Update last data time
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {line}")
                
                # Extract output power value for triggering LOW state
                out_match = re.search(r"1-0:2\.7\.0\((\d+\.\d+)\*kW\)", line)
                # Extract input power value for triggering HIGH state
                in_match = re.search(r"1-0:1\.7\.0\((\d+\.\d+)\*kW\)", line)
                
                if out_match:
                    power_value = float(out_match.group(1))
                    
                    # Check first threshold (for GPIO_PIN1)
                    if power_value >= THRESHOLD_1:
                        if GPIO.input(GPIO_PIN1) == GPIO.HIGH:
                            GPIO.output(GPIO_PIN1, GPIO.LOW)
                            gpio17_low_time = time.time()  # Start tracking when GPIO 17 went LOW
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO {GPIO_PIN1} STATE CHANGE: HIGH -> LOW (Power {power_value}kW > {THRESHOLD_1}kW)")
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting {GPIO27_DELAY}s delay before monitoring GPIO {GPIO_PIN2} threshold")
                        reset_time_1 = None
                        last_timer1_notification = None
                    
                    # Check second threshold (for GPIO_PIN2) - only if GPIO_PIN1 is LOW and 20s have passed
                    if (GPIO.input(GPIO_PIN1) == GPIO.LOW and 
                        gpio17_low_time is not None and 
                        time.time() - gpio17_low_time >= GPIO27_DELAY and
                        power_value >= THRESHOLD_2):
                        if GPIO.input(GPIO_PIN2) == GPIO.HIGH:
                            GPIO.output(GPIO_PIN2, GPIO.LOW)
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO {GPIO_PIN2} STATE CHANGE: HIGH -> LOW (Power {power_value}kW > {THRESHOLD_2}kW after {GPIO27_DELAY}s delay)")
                        reset_time_2 = None
                        last_timer2_notification = None
                
                if in_match:
                    in_power = float(in_match.group(1))
                    
                    # Check if input power is above reset threshold for resetting pins
                    if in_power >= RESET_THRESHOLD:
                        # Handle GPIO_PIN2 reset
                        if GPIO.input(GPIO_PIN2) == GPIO.LOW:
                            if reset_time_2 is None:
                                reset_time_2 = time.time()  # Start timing
                                last_timer2_notification = TIMER_NOTIFICATIONS[0]
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER START: GPIO {GPIO_PIN2} - {last_timer2_notification}s remaining for reset")
                            else:
                                elapsed_time = time.time() - reset_time_2
                                
                                # Find the closest notification point
                                for notify_point in TIMER_NOTIFICATIONS:
                                    if RESET_TIME - elapsed_time <= notify_point and (last_timer2_notification is None or notify_point < last_timer2_notification):
                                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER UPDATE: GPIO {GPIO_PIN2} - {notify_point}s remaining for reset")
                                        last_timer2_notification = notify_point
                                        break
                                
                                # Check if timer completed
                                if elapsed_time >= RESET_TIME:
                                    GPIO.output(GPIO_PIN2, GPIO.HIGH)
                                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO {GPIO_PIN2} STATE CHANGE: LOW -> HIGH (After {RESET_TIME}s above reset threshold)")
                                    reset_time_2 = None
                                    last_timer2_notification = None
                        
                        # Handle GPIO_PIN1 reset - only start if GPIO_PIN2 is already HIGH
                        if GPIO.input(GPIO_PIN1) == GPIO.LOW and GPIO.input(GPIO_PIN2) == GPIO.HIGH:
                            if reset_time_1 is None:
                                reset_time_1 = time.time()  # Start timing
                                last_timer1_notification = TIMER_NOTIFICATIONS[0]
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER START: GPIO {GPIO_PIN1} - {last_timer1_notification}s remaining for reset")
                            else:
                                elapsed_time = time.time() - reset_time_1
                                
                                # Find the closest notification point
                                for notify_point in TIMER_NOTIFICATIONS:
                                    if RESET_TIME - elapsed_time <= notify_point and (last_timer1_notification is None or notify_point < last_timer1_notification):
                                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER UPDATE: GPIO {GPIO_PIN1} - {notify_point}s remaining for reset")
                                        last_timer1_notification = notify_point
                                        break
                                
                                # Check if timer completed
                                if elapsed_time >= RESET_TIME:
                                    GPIO.output(GPIO_PIN1, GPIO.HIGH)
                                    gpio17_low_time = None  # Reset the GPIO 17 timer
                                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GPIO {GPIO_PIN1} STATE CHANGE: LOW -> HIGH (After {RESET_TIME}s above reset threshold)")
                                    reset_time_1 = None
                                    last_timer1_notification = None
                    else:
                        # Reset timers if power drops below threshold
                        if reset_time_1 is not None:
                            reset_time_1 = None
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER RESET: GPIO {GPIO_PIN1} - Input power dropped below threshold")
                        if reset_time_2 is not None:
                            reset_time_2 = None
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TIMER RESET: GPIO {GPIO_PIN2} - Input power dropped below threshold")
            else:
                # No data available, sleep briefly to prevent CPU hogging
                time.sleep(0.1)
                
        except serial.SerialException as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Serial port error: {e}")
            # Try to reopen the serial port
            try:
                if serial_port and serial_port.is_open:
                    serial_port.close()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to reopen serial port in 5 seconds...")
                time.sleep(5)
                serial_port = open_serial_port(max_retries=1, retry_delay=5)
                if serial_port:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Serial port reopened successfully")
                    last_data_time = time.time()  # Reset the no data timer
            except Exception as e2:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to reopen serial port: {e2}")
                time.sleep(10)
                
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Unexpected error: {e}")
            time.sleep(1)

except KeyboardInterrupt:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Program terminated by user")
    
finally:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Closing serial port and resetting GPIO...")
    try:
        if serial_port and serial_port.is_open:
            serial_port.close()
    except:
        pass
    GPIO.cleanup()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cleanup complete")