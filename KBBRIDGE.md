# Reinstall kbbridge

This fork preserves the Pi Zero 2 W bridge built for a Glove80 and Lightning
Magic Trackpad 2. Its deployment profile reduces trackpad motion to 75 percent
and reverses both scroll axes for macOS Natural Scrolling. The installer steps
below also enable four-finger Spaces shortcuts.

## Install on a fresh card

1. In Raspberry Pi Imager, choose Raspberry Pi OS Lite (64-bit, Debian 13
   Trixie) for the Pi Zero 2 W. Set the hostname to `kbbridge`, set up Wi-Fi
   and your user account, and enable SSH. If the original Pi is still on the
   network, give the test Pi a different hostname.
2. Boot the Pi. With SSH or a local console, run the following commands. They
   expect a fresh system without a checkout at `/opt/bluetooth_2_usb`.

   ```sh
   sudo apt update
   sudo apt install -y --no-install-recommends git libinput10
   sudo git clone --branch kbbridge-v1 https://github.com/garytaylor/bluetooth_2_usb.git /opt/bluetooth_2_usb
   cd /opt/bluetooth_2_usb
   sudo env PYTHONPATH=src python3 -m bluetooth_2_usb install
   sudo install -d -m 755 /etc/systemd/system/bluetooth_2_usb.service.d
   printf '[Service]\nEnvironment=B2U_SPACES_GESTURE=1\n' |
     sudo tee /etc/systemd/system/bluetooth_2_usb.service.d/spaces.conf >/dev/null
   sudo systemctl daemon-reload
   sudo reboot
   ```

3. Pair the Glove80 and Magic Trackpad using the [upstream pairing instructions](README.md#3-pair-your-bluetooth-device).
   Put the keyboard on the intended Bluetooth profile and the trackpad in pairing
   mode. If a Glove80 profile still points at the old Pi, use a spare profile or
   clear that individual pairing before reusing it. The default bridge settings
   use auto relay and input grabbing. Pair only devices you intend to relay.
4. Connect the Pi's data port marked **USB** to the unlocked laptop, with the
   Pi powered separately. Check the bridge with
   `systemctl is-active bluetooth_2_usb` and
   `cat /sys/class/udc/*/state`. Expect `active` and `configured`.
5. On macOS, enable Natural Scrolling and confirm Control–Left/Right Arrow
   switch Spaces. Check Glove80 typing, pointer motion, physical clicks,
   scrolling vertically and horizontally, and a four-finger swipe in each
   direction. For a KVM, test switching away and back on the actual device.

The repo does not store Wi-Fi credentials or Bluetooth pairing keys. A clean
install requires entering Wi-Fi details and pairing the devices again.

## Restart or rebuild

- Restart the bridge with `sudo systemctl restart bluetooth_2_usb`. This does
  not erase pairings. If the Pi stays `not attached`, shut down with
  `sudo poweroff`. Once halted, disconnect USB data and power, reconnect power,
  let the Pi boot, and then reconnect data to the unlocked laptop.
- For a clean reset, follow the fresh-card steps. Keep the original card while
  testing the replacement.
- The install recipe intentionally checks out a tag. The upstream `update`
  command expects a branch, so use the tagged recipe for a reproducible rebuild.

## Version and validation

`kbbridge-v1` is the first recovery snapshot. It uses the same upstream base as
the working appliance. The source-tree build adds optional dependency handling
and enables Spaces through a service override. Direct USB behavior was verified
on the original hardware with the equivalent live patch. A blank-card rebuild
and KVM switching remain to be verified.
