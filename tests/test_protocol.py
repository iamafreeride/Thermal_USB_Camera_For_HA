"""Protocol level tests for the SenXor framing and frame decoding."""

from __future__ import annotations

import unittest

from common import load, sample_frames

protocol = load("protocol")

CAPTURED_COMMANDS = {
    "B103": b"#000CWREGB10302DE",
    "B100": b"#000CWREGB10002DB",
    "B101": b"#000CWREGB10102DC",
    "B404": b"#000CWREGB40402E2",
    "B403": b"#000CWREGB40302E1",
}


class BuildCommandTest(unittest.TestCase):
    def test_generated_commands_match_captured_bytes(self) -> None:
        for register, expected in CAPTURED_COMMANDS.items():
            with self.subTest(register=register):
                self.assertEqual(protocol.build_wreg(int(register, 16)), expected)

    def test_checksum_is_sum_of_characters(self) -> None:
        command = protocol.build_wreg(0xB103)
        body, checksum = command[1:-4], int(command[-4:], 16)
        self.assertEqual(checksum, sum(body))
        self.assertEqual(len(command), 17)

    def test_command_names(self) -> None:
        self.assertEqual(protocol.command_name(0xB103), "stream start")
        self.assertEqual(protocol.command_name(0x1234), "register 0x1234")


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


class FrameMetadataTest(unittest.TestCase):
    def test_metadata_block_is_preserved(self) -> None:
        messages, _ = protocol.parse_messages(sample_frames())
        payload = messages[0][1]
        frame = protocol.decode_frame(payload, 0)
        self.assertEqual(len(frame.meta), protocol.META_LEN)
        self.assertEqual(frame.meta, payload[: protocol.META_LEN])


if __name__ == "__main__":
    unittest.main()
