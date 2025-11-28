# Bee-Tek Shoe Reader - Installation Guide

## Purpose

A Graphical Application to read cards from Bee-Tek Card-Dealing Shoe and send it on an HTTP POST address to any relevant live dealing game servers (Ex. Poker, Teenpatti, Baccarat).

## System Requirements

- **Operating System**: Ubuntu 20.04 or later, x86_64 (64-bit)
- **Hardware**: 
    - Bee-Tek USPC card shoe
    - STAR Power Cable / PoE Adapter
    - RS-232 to USB Serial Adapter (Model: DTECH)

## Shoe Setup
1. Plug the adapter’s RS-232 side into the RS-232 port on the shoe.

2. Connect the STAR Power Cable to the power port underneath the shoe and switch on the power.

3. Turn on the main power switch located underneath the shoe (near the ports).

### Shoe Mode Setup - Card Drawing Mode
1. Turn the key switch to set the shoe to Diagnostic Mode.

2. Keep pressing the `Mode` button on the shoe until the “Manual Burn Cards” option appears on the shoe display.

3. Press the `Enter` button on the shoe to confirm.

4. Open the Bee-Tek Shoe Monitor app on your computer and press Start.

5. Begin drawing cards, the app will now start reading the cards.

### Shoe Connection to Computer
1. Plug the adapter's USB side into your computer’s USB port.
2. In the app, click `Start`, it will automatically detect the shoe connection.
    -  On most systems, the port appears as /dev/ttyUSB0.
3. Once connected, the app will show “Connected” with a green indicator.

## App Installation Steps

### Step 1: Grant Serial Port Permissions (One-Time)

For the app to communicate with the Bee-Tek shoe, add your user to the `dialout` group (for serial port access):

```bash
sudo usermod -aG dialout $USER
```

**Important:** Log out and log back in (or restart) for this change to take effect.

### Step 2: Download the Application

Download `BeetekShoeMonitor-x86_64.AppImage` to your Downloads folder.

### Step 3: Install Application to the System App Menu

Open terminal and run this single command to install the app icon in your applications menu:

```bash
cd ~/Downloads && chmod +x BeetekShoeMonitor-x86_64.AppImage && mkdir -p ~/.local/bin ~/.local/share/icons ~/.local/share/applications && cp BeetekShoeMonitor-x86_64.AppImage ~/.local/bin/ && ~/.local/bin/BeetekShoeMonitor-x86_64.AppImage --appimage-extract && cp squashfs-root/bee.png ~/.local/share/ && cp squashfs-root/wildace.png ~/.local/share/icons/ && cp squashfs-root/BeetekShoeMonitor.desktop ~/.local/share/applications/ && sed -i "s|Exec=.*|Exec=$HOME/.local/bin/BeetekShoeMonitor-x86_64.AppImage|" ~/.local/share/applications/BeetekShoeMonitor.desktop && sed -i "s|Icon=.*|Icon=$HOME/.local/share/icons/wildace.png|" ~/.local/share/applications/BeetekShoeMonitor.desktop && rm -rf squashfs-root && update-desktop-database ~/.local/share/applications/ && echo "Installed! Search 'Bee-Tek' in app menu"
```

After a successful installation, you’ll see “Installed! Search ‘Bee-Tek’ in app menu"

### Step 4: Run the Application

Search for "Bee-Tek Shoe Reader" in your applications menu and click to launch.

## Configuration

On first run, the app creates a `shoe.json` configuration file with default settings:

- **IP**: 192.168.1.140
- **Port**: 9000
- **URL**: sendCard

Edit these values in the application and click "Save" to update the configuration.



## Troubleshooting

### "Permission denied" Error
You forgot to add yourself to the dialout group. Run:
```bash
sudo usermod -aG dialout $USER
```
Then log out and log back in (or restart).

### "No serial ports detected"
- Ensure the Bee-Tek shoe is powered on
- Check USB cable is properly connected
- Try unplugging and replugging the USB cable
- Verify the device appears: `ls /dev/ttyUSB*`

### "HTTP failed" Messages
- Verify the relevant game server is running
- Check IP address and port in configuration
- Test connection: `ping <server-ip>`

### App Won't Start
- Ensure you ran `chmod +x` on the AppImage
- Verify you're on a 64-bit Linux system: `uname -m` (should show x86_64)

## Uninstallation

To remove the application:

```bash
rm ~/.local/bin/BeetekShoeMonitor-x86_64.AppImage
rm ~/.local/share/applications/BeetekShoeMonitor.desktop
rm ~/.local/share/icons/wildace.png
update-desktop-database ~/.local/share/applications/
```
