# SPDX-FileCopyrightText: 2018 ladyada for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# pylint: disable=line-too-long
"""
`adafruit_sharpmemorydisplay`
====================================================

A display control library for Sharp 'memory' displays

* Author(s): ladyada

Implementation Notes
--------------------

**Hardware:**

* `Adafruit SHARP Memory Display Breakout - 1.3 inch 144x168 Monochrome <https://www.adafruit.com/product/3502>`_

* `Adafruit SHARP Memory Display Breakout - 1.3 inch 96x96 Monochrome <https://www.adafruit.com/product/1393>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

"""
# pylint: enable=line-too-long

from micropython import const
import adafruit_framebuf
from adafruit_bus_device.spi_device import SPIDevice

try:
    import numpy
except ImportError:
    numpy = None

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_SharpMemoryDisplay.git"

_SHARPMEM_BIT_WRITECMD = const(0x80)  # in lsb
_SHARPMEM_BIT_VCOM = const(0x40)  # in lsb
_SHARPMEM_BIT_CLEAR = const(0x20)  # in lsb


def reverse_bit(num):
    """Turn an LSB byte to an MSB byte, and vice versa. Used for SPI as
    it is LSB for the SHARP, but 99% of SPI implementations are MSB only!"""
    result = 0
    for _ in range(8):
        result <<= 1
        result += num & 1
        num >>= 1
    return result


class SharpMemoryDisplay(adafruit_framebuf.FrameBuffer):
    """A driver for sharp memory displays, you can use any size but the
    full display must be buffered in memory!"""

    # pylint: disable=too-many-instance-attributes,abstract-method

    def __init__(self, spi, scs_pin, width, height, *, baudrate=2000000):
        scs_pin.switch_to_output(value=True)
        self.spi_device = SPIDevice(
            spi, scs_pin, cs_active_value=True, baudrate=baudrate
        )
        # prealloc for when we write the display
        self._buf = bytearray(1)

        # even tho technically this display is LSB, we have to flip the bits
        # when writing out SPI so lets just do flipping once, in the buffer
        self.buffer = bytearray((width // 8) * height)
        super().__init__(self.buffer, width, height, buf_format=adafruit_framebuf.MHMSB)

        # Set the vcom bit to a defined state
        self._vcom = True

    def show(self):
        """write out the frame buffer via SPI, we use MSB SPI only so some
        bit-swapping is required.
        """

        with self.spi_device as spi:

            # toggle the VCOM bit
            self._buf[0] = _SHARPMEM_BIT_WRITECMD
            if self._vcom:
                self._buf[0] |= _SHARPMEM_BIT_VCOM
            self._vcom = not self._vcom
            spi.write(self._buf)

            slice_from = 0
            line_len = self.width // 8
            for line in range(self.height):
                self._buf[0] = reverse_bit(line + 1)
                spi.write(self._buf)
                spi.write(memoryview(self.buffer[slice_from : slice_from + line_len]))
                slice_from += line_len
                self._buf[0] = 0
                spi.write(self._buf)
            spi.write(self._buf)  # we send one last 0 byte

    def image(self, img):
        """Set buffer to value of Python Imaging Library image.  The image should
        be in 1 bit mode and a size equal to the display size."""
        # determine our effective width/height, taking rotation into account
        width = self.width
        height = self.height
        if self.rotation in (1, 3):
            width, height = height, width

        if img.mode != "1":
            raise ValueError("Image must be in mode 1.")

        imwidth, imheight = img.size
        if imwidth != width or imheight != height:
            raise ValueError(
                "Image must be same dimensions as display ({0}x{1}).".format(
                    width, height
                )
            )

        if numpy:
            self.buffer = bytearray(
                numpy.packbits(numpy.asarray(img), axis=1).flatten().tolist()
            )
        else:
            # Grab all the pixels from the image, faster than getpixel.
            pixels = img.load()
            # Clear buffer
            for i in range(len(self.buf)):  # pylint: disable=consider-using-enumerate
                self.buf[i] = 0
            # Iterate through the pixels
            for x in range(width):  # yes this double loop is slow,
                for y in range(height):  #  but these displays are small!
                    if img.mode == "RGB":
                        self.pixel(x, y, pixels[(x, y)])
                    elif pixels[(x, y)]:
                        self.pixel(x, y, 1)  # only write if pixel is true
