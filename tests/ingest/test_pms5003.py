import struct
import unittest

from aqpy.ingest.pms5003 import PMS5003


class FakeSerial:
    def __init__(self, stream=b""):
        self.stream = bytearray(stream)
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def read(self, n=1):
        if n <= 0 or not self.stream:
            return b""
        count = min(n, len(self.stream))
        chunk = self.stream[:count]
        del self.stream[:count]
        return bytes(chunk)

    @property
    def in_waiting(self):
        return len(self.stream)

    def close(self):
        return None

    def feed(self, data):
        self.stream.extend(data)


def build_frame(values14):
    body = struct.pack(">14H", *values14)
    checksum = sum(body) + 0x42 + 0x4D
    payload = body + struct.pack(">H", checksum)
    return b"\x42\x4D" + payload


class TestPMS5003(unittest.TestCase):
    def test_read_recovers_from_bad_second_start_byte(self):
        values14 = [28, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
        frame = build_frame(values14)
        serial = FakeSerial()
        pms = PMS5003(serial, startup_delay=0)
        serial.feed(b"\x42\x00" + frame)
        pms.timeout = 0.1

        data = pms.read()

        self.assertEqual(data["pm_st"], [1, 2, 3])
        self.assertEqual(data["pm_en"], [4, 5, 6])
        self.assertEqual(data["hist"], [7, 8, 9, 10, 11, 12])

    def test_read_raises_on_timeout_when_no_valid_frame(self):
        serial = FakeSerial()
        pms = PMS5003(serial, startup_delay=0)
        serial.feed(b"\x42\x00\x00\x00")
        pms.timeout = 0.01

        with self.assertRaisesRegex(
            RuntimeError, "valid PMS5003 frame not found before timeout"
        ):
            pms.read()


if __name__ == "__main__":
    unittest.main()
