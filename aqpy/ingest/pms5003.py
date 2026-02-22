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
        st = time.time()
        found = False
        while time.time() - st < self.timeout:
            first = self.serial.read(1)
            if len(first) == 0:
                continue
            if first[0] == 0x42:
                found = True
                break

        if not found:
            raise RuntimeError("start byte not found")

        second = self.serial.read(1)
        if len(second) == 0 or second[0] != 0x4D:
            raise RuntimeError("second start byte not found")

        payload = self.serial.read(30)
        if len(payload) != 30:
            raise RuntimeError("read wrong length")

        parsed = struct.unpack(">15H", payload)
        checksum = sum(payload[:-2]) + 0x42 + 0x4D
        if checksum != parsed[-1]:
            raise RuntimeError("checksum problem")

        return {
            "pm_st": list(parsed[1:4]),
            "pm_en": list(parsed[4:7]),
            "hist": list(parsed[7:13]),
        }

    def averaged_read(self, avg_time=10):
        prev_status = self.status
        if self.status == "ASLEEP":
            self.wake()

        start = time.time()
        count = 1
        data = self.read()
        while time.time() - start < avg_time:
            sample = self.read()
            count += 1
            for key, values in data.items():
                for idx in range(len(values)):
                    data[key][idx] += sample[key][idx]

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
