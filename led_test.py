import time
from rpi_ws281x import PixelStrip, Color

LED_COUNT=50
LED_PIN = 18
LED_REQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin

def set_led(index, r, g, b):
    strip.setPixelColor(index, Color(r,g,b))
    pixels.show()

set_led(0, (255, 0, 0))
set_led(1, (0, 255, 0))
set_led(2, (0, 0, 255))

