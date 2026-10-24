"""Protocol level tests for the SenXor framing, registers and frame decoding."""

from __future__ import annotations

import unittest

from common import load, sample_frames

protocol = load("protocol")

# (register, value, bytes captured on the wire)
CAPTURED_COMMANDS = (
    (0xB1, 0x03, b"#000CWREGB10302DE"),  # start continuous capture
    (0xB1, 0x00, b"#000CWREGB10002DB"),  # stop
    (0xB1, 0x01, b"#000CWREGB10102DC"),  # single frame
    (0xB4, 0x04, b"#000CWREGB40402E2"),  # divider 4
    (0xB4, 0x03, b"#000CWREGB40302E1"),  # divider 3
    (0xB4, 0x02, b"#000CWREGB40202E0"),  # divider 2 (captured by the user)
    (0xB4, 0x01, b"#000CWREGB40102DF"),  # divider 1 (captured by the user)
    (0xB4, 0x00, b"#000CWREGB40002DE"),  # divider 0 = maximum frame rate
)


class BuildCommandTest(unittest.TestCase):
    def test_generated_commands_match_captured_bytes(self) -> None:
        for register, value, expected in CAPTURED_COMMANDS:
            with self.subTest(register=register, value=value):
                self.assertEqual(protocol.build_wreg(register, value), expected)

    def test_checksum_is_sum_of_characters(self) -> None:
        command = protocol.build_wreg(0xB1, 0x03)
        body, checksum = command[1:-4], int(command[-4:], 16)
        self.assertEqual(checksum, sum(body))
        self.assertEqual(len(command), 17)

    def test_command_names(self) -> None:
        self.assertEqual(protocol.command_name(0xB1, 0x03), "start stream")
        self.assertEqual(protocol.command_name(0xB1, 0x00), "stop stream")
        self.assertEqual(protocol.command_name(0xB1, 0x01), "single frame")
        self.assertEqual(protocol.command_name(0xB4, 3), "frame rate divider")
        self.assertEqual(protocol.command_name(0xC2, 95), "sensitivity correction")
        self.assertEqual(protocol.command_name(0xEE, 1), "register 0xEE")


class RegisterLimitsTest(unittest.TestCase):
    def test_divider_range(self) -> None:
        self.assertEqual(protocol.FPS_DIVIDER_MIN, 0)
        self.assertEqual(protocol.FPS_DIVIDER_MAX, 127)

    def test_gain_values(self) -> None:
        self.assertEqual(protocol.GAIN_VALUES, {"1": 0, "Auto": 1, "0.25": 2, "0.5": 3})
        self.assertEqual(protocol.GAIN_DISPLAY[1], "Auto")


class MessageParsingTest(unittest.TestCase):
    def test_parse_complete_stream(self) -> None:
        data = sample_frames()
        messages, remainder = protocol.parse_messages(data)
        self.assertEqual(remainder, b"")
        self.assertEqual(len(messages), data.count(b"#2808GFRA"))
        for command, payload in messages:
            self.assertEqual(command, "GFRA")
            self.assertEqual(len(payload), protocol.GFRA_PAYLOAD_LEN)

    def test_incremental_parsing(self) -> None:
        data = sample_frames()
        buffer = b""
        seen = []
        for index in range(0, len(data), 4096):
            buffer += data[index : index + 4096]
            messages, buffer = protocol.parse_messages(buffer)
            seen.extend(messages)
        self.assertEqual(len(seen), sample_frames().count(b"#2808GFRA"))
        self.assertEqual(buffer, b"")

    def test_garbage_before_header_is_ignored(self) -> None:
        messages, _ = protocol.parse_messages(b"\x00\xff" + sample_frames()[:20000])
        self.assertEqual(len(messages), 1)

    def test_partial_message_is_kept_for_later(self) -> None:
        data = sample_frames()[:5000]
        messages, remainder = protocol.parse_messages(data)
        self.assertEqual(messages, [])
        self.assertEqual(remainder, data)


class FrameDecodingTest(unittest.TestCase):
    def setUp(self) -> None:
        messages, _ = protocol.parse_messages(sample_frames())
        self.payloads = [payload for _, payload in messages]

    def test_frame_geometry_and_checksum(self) -> None:
        frame = protocol.decode_frame(self.payloads[0], 7)
        self.assertEqual(frame.sequence, 7)
        self.assertEqual(len(frame.pixels), protocol.PIXEL_COUNT)
        self.assertEqual(len(frame.pixels), 80 * 62)
        self.assertTrue(frame.checksum_ok)
        self.assertEqual(frame.min_dk, min(frame.pixels))
        self.assertEqual(frame.max_dk, max(frame.pixels))

    def test_temperature_range_is_plausible(self) -> None:
        frame = protocol.decode_frame(self.payloads[-1], 0)
        self.assertGreater(frame.min_dk, 2000)  # > -73 C
        self.assertLess(frame.max_dk, 4000)  # < 127 C

    def test_pixel_accessor(self) -> None:
        frame = protocol.decode_frame(self.payloads[0], 0)
        self.assertEqual(frame.pixel(0, 0), frame.pixels[0])
        self.assertEqual(frame.pixel(79, 61), frame.pixels[-1])

    def test_bad_length_is_rejected(self) -> None:
        with self.assertRaises(protocol.SenXorProtocolError):
            protocol.decode_frame(self.payloads[0][:-10], 0)

    def test_corrupted_checksum_is_flagged(self) -> None:
        payload = bytearray(self.payloads[0])
        payload[400] ^= 0xFF
        frame = protocol.decode_frame(bytes(payload), 0)
        self.assertFalse(frame.checksum_ok)


class HeaderDecodingTest(unittest.TestCase):
    def setUp(self) -> None:
        messages, _ = protocol.parse_messages(sample_frames())
        self.payloads = [payload for _, payload in messages]

    def test_header_fields_are_decoded(self) -> None:
        frame = protocol.decode_frame(self.payloads[0], 0)
        header = frame.header
        self.assertIsNotNone(header)
        assert header is not None
        self.assertGreater(header.vdd, 2.5)
        self.assertLess(header.vdd, 5.5)
        self.assertGreater(header.die_temperature, -40.0)
        self.assertLess(header.die_temperature, 125.0)

    def test_frame_counter_increments(self) -> None:
        counters = [
            protocol.decode_frame(payload, index).header.frame_counter
            for index, payload in enumerate(self.payloads)
        ]
        self.assertEqual(counters, list(range(counters[0], counters[0] + len(counters))))

    def test_decode_header_directly(self) -> None:
        payload = self.payloads[0]
        header = protocol.decode_header(payload[: protocol.META_LEN])
        self.assertIsNotNone(header)
        assert header is not None
        self.assertAlmostEqual(header.vdd, int.from_bytes(payload[162:164], "little") * 0.0001, places=6)
        self.assertAlmostEqual(
            header.die_temperature,
            int.from_bytes(payload[164:166], "little") * 0.01 - 273.15,
            places=6,
        )

    def test_short_metadata_is_tolerated(self) -> None:
        self.assertIsNone(protocol.decode_header(b"\x00" * 100))


if __name__ == "__main__":
    unittest.main()
