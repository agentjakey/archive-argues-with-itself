# Exhibit hardware

These are proposals for a library kiosk. Nothing has been bought or tested on this hardware yet.
Prices were found by web search on 2026-11-01 and are in the currency shown. Many are not Canadian
prices, so check a Canadian supplier before buying.

## What the kiosk needs

The kiosk needs a 1080p touchscreen from 24 to 55 inches, a small computer that runs a browser for
a full day without a network, a physical year dial, and optionally a receipt printer for evidence
cards. The exhibit itself is a static page served from the computer by a small Python server
(`exhibit/kiosk/serve.py`). Any screen and computer that run current Edge or Chrome will do.

For people watching from two or three metres away, prefer a 55-inch screen or larger with a matte
or anti-glare surface, and mount it so the touch area and the dial sit between 380 mm and 1220 mm
above the floor (the Smithsonian's reach range for a forward approach in a wheelchair). The reasons
are in [DESIGN_RESEARCH.md](DESIGN_RESEARCH.md). The type scales with the screen, so a 3840x2160
panel shows the same layout at twice the pixels.

## Recommended parts

### Year dial: a USB keyboard knob

Build the dial from a Raspberry Pi Pico 2, a rotary encoder with a push switch, and a large knob.
The Pico runs a short CircuitPython program (`exhibit/kiosk/dial/code.py`) that makes it a USB
keyboard. It sends ArrowRight or ArrowLeft for each click of the knob and Enter when the knob is
pressed. No driver is needed, and the exhibit treats those keys exactly like the on-screen arrows.

| Part | Example | Price found | Source |
|---|---|---|---|
| Raspberry Pi Pico 2 | SC1631 | about USD 5 list price at launch; GBP 4.55 best UK price | [guru3d](https://www.guru3d.com/story/raspberry-pi-pico-2-release-specifications-and-pricing-just), [PriceSpy](https://pricespy.co.uk/product.php?p=13786175) |
| Rotary encoder with push switch | Adafruit 377 (24 detents) | AUD 8.55 incl. GST; EUR 5.95 | [Core Electronics](https://core-electronics.com.au/rotary-encoder-extras.html.plain.md), [Elektronica voor Jou](https://elektronicavoorjou.nl/en/product/rotary-encoder-push-button) |
| Large knob | Adafruit scrubber knob, 34.7 mm | AUD 2.10 incl. GST | [Core Electronics](https://core-electronics.com.au/scrubber-knob-for-rotary-encoder-35mm.html.md) |
| Enclosure, USB cable | any small box that can be screwed down | not priced | |

That comes to well under CAD 50 in parts, plus an hour of soldering. A sturdier choice for a public
floor is a panel-mount industrial encoder with a metal knob in a bolted-down box. It needs the same
firmware, but I have not priced one.

I would avoid two other kinds of dial. Off-the-shelf "volume knobs" usually send media keys, which
the operating system takes over to change the volume. The Surface Dial is a Bluetooth radial
controller, not a keyboard. A programmable USB knob that can be set to send arrow keys would also
work. I did not find one with a price I could cite.

### Computer: a fanless mini PC

An Intel N100-class fanless mini PC with 8 to 16 GB of memory runs the exhibit comfortably. The
exhibit's JavaScript is about 60 kB compressed, and the deck is a few megabytes. Being fanless
helps in a quiet library.

| Example | Price found | Source |
|---|---|---|
| MINIX Z150 fanless, 16 GB, 512 GB (sold out when checked) | AUD 589 | evotech.au listing (removed since it was checked) |
| Generic fanless N100 | USD 165 (eBay.de listing) | [eBay](https://www.ebay.de/itm/356790862873) |

Run Windows 11 Pro with Assigned Access, or the kiosk account set to sign in automatically and run
`exhibit/kiosk/start-kiosk.ps1`. That script starts the local server and then opens Edge full screen
in kiosk mode with InPrivate browsing. If the browser closes, the script opens it again.

### Receipt printer: an 80 mm thermal printer over USB

| Example | Price found | Source |
|---|---|---|
| Epson TM-m30III, USB and Ethernet, with cutter | CAD 344.99 sale, MSRP CAD 730.19 (out of stock when checked) | [fleetnetwork.ca](https://fleetnetwork.ca/products/c31ck50011/) |
| Same model | USD 304.68 | [Spartan POS](https://spartanpos.com/collections/epson) |

Paper is 80 mm thermal rolls.

## The most reliable printing path

My recommendation is a USB cable, Epson's Windows driver with the printer set as the default
printer, and the browser's own silent printing. In practice:

1. Install the vendor's Windows driver and print a test page from Windows.
2. Set the receipt printer as the default printer.
3. Start Edge with `--kiosk-printing`, which `start-kiosk.ps1` already does. The browser's print
   dialog is then skipped, and `window.print()` goes straight to the default printer.
4. The evidence card's print stylesheet sets an 80 mm page with 4 mm margins.
5. Start the kiosk server with `--printer`. The print button only appears when that flag is set,
   so a kiosk without a printer never offers one.

There are two other paths:

- **Raw ESC/POS from the local server.** This skips the Windows driver, but means writing and
  maintaining a printer protocol.
- **Network printing.** This adds a network the kiosk does not otherwise need.

Both have more ways to fail than one USB cable and the browser's own print path.

If the printer is out of paper or unplugged, the browser's silent print fails quietly. The visitor
still sees the card's QR code and the archive.org address on screen, so nothing is lost. Staff
should check the paper roll at opening.

Still to test on real hardware:

- one full day of printing;
- what Edge does when the printer is offline;
- whether the QR code scans from thermal paper at 34 mm.
