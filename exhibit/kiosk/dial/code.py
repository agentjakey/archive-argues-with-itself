# CircuitPython firmware for the exhibit's year dial on a Raspberry Pi Pico or Pico 2 (docs/exhibit/
# hardware.md). The board becomes a USB keyboard: one click of the knob clockwise sends ArrowRight,
# anticlockwise ArrowLeft, and pressing the knob sends Enter. Copy this file to the board's CIRCUITPY
# drive as code.py, with the adafruit_hid library in lib/.
#
# Wiring (Adafruit 377 encoder): A to GP2, B to GP3, the encoder's middle pin to GND; one switch pin
# to GP4, the other to GND.
import board
import digitalio
import rotaryio
import time
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

DEBOUNCE_S = 0.02
MAX_STEPS_PER_READ = 5     # a fast spin still moves the year, but a fault cannot flood the kiosk

keyboard = Keyboard(usb_hid.devices)
encoder = rotaryio.IncrementalEncoder(board.GP2, board.GP3)
button = digitalio.DigitalInOut(board.GP4)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP

last_position = encoder.position
was_pressed = False

while True:
    position = encoder.position
    delta = position - last_position
    if delta != 0:
        key = Keycode.RIGHT_ARROW if delta > 0 else Keycode.LEFT_ARROW
        for _ in range(min(abs(delta), MAX_STEPS_PER_READ)):
            keyboard.send(key)
        last_position = position
    pressed = not button.value
    if pressed and not was_pressed:
        keyboard.send(Keycode.ENTER)
    was_pressed = pressed
    time.sleep(DEBOUNCE_S)
