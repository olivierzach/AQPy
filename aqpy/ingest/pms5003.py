import struct
import time


class PMS5003:
    def __init__(self, serial_conn, startup_delay):
        self.serial = serial_conn
        self.startup_delay = startup_delay
        self.cmd_delay = 0.5
        self.timeout = 5

        self.wake()
        self.set_active()

    def sleep(self):
        self.serial.write([0x42, 0x4D, 0xE4, 0x00, 0x00, 0x01, 0x73])
        self.status = "ASLEEP"
        time.sleep(self.cmd_delay)
        self.drain_buffer()

    def wake(self):
        self.serial.write([0x42, 0x4D, 0xE4, 0x00, 0x01, 0x01, 0x74])
        self.status = "AWAKE"
        time.sleep(self.startup_delay)
        self.drain_buffer()

    def set_active(self):
        self.serial.write([0x42, 0x4D, 0xE1, 0x00, 0x01, 0x01, 0x71])
        self.mode = "ACTIVE"
        time.sleep(self.cmd_delay)

    def read(self):
        deadline = time.time() + self.timeout
        found_first = False
        while time.time() < deadline:
            b = self.serial.read(1)
            if len(b) == 0:
                continue

            byte = b[0]
            if not found_first:
                if byte == 0x42:
                    found_first = True
                continue

            if byte == 0x42:
                # Keep searching while treating this as a new potential first byte.
                found_first = True
                continue

            if byte != 0x4D:
                found_first = False
                continue

            payload = self.serial.read(30)
            if len(payload) != 30:
                found_first = False
                continue

            parsed = struct.unpack(">15H", payload)
            checksum = sum(payload[:-2]) + 0x42 + 0x4D
            if checksum != parsed[-1]:
                found_first = False
                continue

            return {
                "pm_st": list(parsed[1:4]),
                "pm_en": list(parsed[4:7]),
                "hist": list(parsed[7:13]),
            }

        raise RuntimeError("valid PMS5003 frame not found before timeout")

    def averaged_read(self, avg_time=10):
        prev_status = self.status
        if self.status == "ASLEEP":
            self.wake()

        start = time.time()
        count = 0
        data = None
        while time.time() - start < avg_time:
            try:
                sample = self.read()
            except RuntimeError:
                continue

            if data is None:
                data = sample
            else:
                for key, values in data.items():
                    for idx in range(len(values)):
                        data[key][idx] += sample[key][idx]
            count += 1

        if count == 0:
            raise RuntimeError("no valid PMS5003 frames collected during averaging window")

        for key, values in data.items():
            for idx in range(len(values)):
                data[key][idx] = int(round(float(values[idx]) / count))

        if prev_status == "ASLEEP":
            self.sleep()
        return data

    def drain_buffer(self):
        while self.serial.in_waiting > 0:
            self.serial.read()

    def close(self):
        self.serial.close()
