# Reflash And Login (Headless)

## 1. Reflash SD Card From Mac
1. Insert Pi microSD card into Mac using the uni reader.
2. Open Raspberry Pi Imager.
3. Choose:
   - Device: your Pi model
   - OS: Raspberry Pi OS (64-bit)
   - Storage: the microSD card
4. Open advanced options with `Cmd+Shift+X` and set:
   - Hostname: `aqpi`
   - Enable SSH: `Use password authentication`
   - Username: `pi`
   - Password: set a known password
   - Wi-Fi SSID + password
   - Wi-Fi country: `US`
5. Click `Write`, wait for completion, eject card.

## 2. Boot Pi And SSH In
1. Put card back in Pi and power it on.
2. Wait 1-2 minutes for first boot.
3. From Mac:
   - `nc -vz 192.168.1.20 22`
   - `ssh pi@192.168.1.20`
4. If `.local` works on your network, you can also try:
   - `ssh pi@aqpi.local`

## 3. Enable Interfaces Needed By Sensors
1. Run `sudo raspi-config`
2. Set:
   - `Interface Options -> I2C -> Enable`
   - `Interface Options -> Serial Port`
     - Login shell over serial: `No`
     - Serial hardware: `Yes`
3. Reboot: `sudo reboot`

## 4. Verify Sensor Hardware
After reboot and reconnect SSH:
1. `ls /dev/serial0`
2. `i2cdetect -y 1`

Expected:
- `/dev/serial0` exists
- BME280 appears at `0x76` (or sometimes `0x77`)

## 5. Bring Up AQPy
```bash
cd /home/pi/AQPy
python3 -m pip install -r requirements.txt
cp .env.example .env
nano .env
sudo cp aqi.service /etc/systemd/system/aqi.service
sudo systemctl daemon-reload
sudo systemctl enable --now aqi
systemctl status aqi
journalctl -u aqi -n 100 --no-pager
```

## 6. Quick Troubleshooting
- SSH timeout: Pi not on network or wrong Wi-Fi credentials.
- `Connection refused` on port 22: SSH not enabled in Imager settings.
- `Permission denied`: wrong username/password.
- Service errors: check logs with `journalctl -u aqi -n 100 --no-pager`.
