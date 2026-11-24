# Flashing a Pixoo 64 with ESPHome

This replaces the Pixoo 64's stock firmware with ESPHome, without soldering, using a 3.3 V USB-to-serial adapter (an FT232RL board, for example). Opening the case and flashing are at your own risk. Back up the stock firmware first: Divoom doesn't publish it, so your own backup is the only way back.

## What's inside

- The mainboard has a classic ESP32 (ESP32-WROVER-IE, 8 MB flash, 8 MB PSRAM). It drives a separate LED board over a ribbon: SPI clock on GPIO25, data on GPIO33, chip select on GPIO26.
- The USB-C port is power only. Flashing goes through the `GND`, `TX` and `RX` pads, and `IO0` held to ground at power-up puts the ESP32 into download mode.
- ESPHome has a `pixoo` display and light platform from 2026.8.0.
- The pin map comes from [simplyRoba's pixoo-firmware](https://github.com/simplyRoba/pixoo-firmware) hardware notes, measured on a REV1.1 board. It has also worked on a REV1.2 board.

## Wiring

Set the adapter's jumper to **3.3V**. Leave the adapter's `VCC` unconnected: the Pixoo runs on its own USB-C power.

| Adapter pin | Pixoo pad |
| --- | --- |
| GND | GND |
| TX | RX |
| RX | TX |
| VCC, CTS, DTR | nothing |

Male jumper pins pushed into the pads, or test hooks, are enough. A bit of tape or Blu Tack holds them.

## Download mode

Ground has to stay connected the whole time, so use a second ground wire for `IO0`:

1. Unplug the Pixoo's USB-C. Wire GND to GND, TX to RX and RX to TX.
2. Put a second wire in one of the adapter's spare GND holes.
3. Optional: open the port in a terminal (`screen /dev/cu.usbserial-XXXX 115200` on macOS) to watch the boot messages.
4. Hold the second wire on `IO0` and plug in the USB-C. After a second, take it away.
5. The terminal shows `boot:0x3 (DOWNLOAD_BOOT…) waiting for download`. The ESP32 stays in download mode until it loses power.

If it shows `SPI_FAST_FLASH_BOOT`, IO0 wasn't low at power-up. Nothing at all means TX and RX are swapped or not touching. Garbage means ground is missing or the baud rate is wrong.

## Backing up the stock firmware

With [esptool](https://docs.espressif.com/projects/esptool/) installed:

```bash
esptool --port /dev/cu.usbserial-XXXX flash-id
esptool --port /dev/cu.usbserial-XXXX get-security-info
esptool --port /dev/cu.usbserial-XXXX --baud 460800 read-flash 0 0x800000 pixoo64-stock.bin
```

- `flash-id` should say 8MB. If it says something else, change `0x800000` to match.
- Stop if `get-security-info` shows flash encryption or Secure Boot enabled.
- If `read-flash` fails partway, run it again without `--baud 460800`.
- Keep the backup private: it holds your Wi-Fi password and Divoom account tokens.
- To go back to stock later: `esptool --port … write-flash 0 pixoo64-stock.bin`.

## Building the firmware

In Home Assistant, open the ESPHome Device Builder, add a new device for an ESP32, and skip installing. Edit it: keep the `api`, `ota` and `wifi` blocks it generated, and use the package from this repository for the rest. The [README](../README.md#the-display) shows the whole configuration.

**Install → Manual download → Factory format** downloads a `.factory.bin` file.

## Flashing

1. Put the Pixoo in download mode again.
2. In Chrome or Edge, open <https://web.esphome.io>, **Connect**, pick the adapter's port, **Install**, and choose the `.factory.bin`.
3. When it finishes, unplug the USB-C, remove every wire (IO0 must not touch GND), and plug the USB-C back in.

The Pixoo joins your Wi-Fi and Home Assistant offers it under Settings → Devices & services → Discovered. Later updates go over Wi-Fi from the Device Builder, so the wires aren't needed again. If it can't join Wi-Fi, it opens its own access point with a page to enter Wi-Fi details.

## Troubleshooting

- The flasher can't connect: TX and RX swapped, the jumper on 5V, a loose pad, or not in download mode.
- Flashed, but the panel stays dark: check that the light is on in Home Assistant, and look for `pixoo` errors in the device log.
