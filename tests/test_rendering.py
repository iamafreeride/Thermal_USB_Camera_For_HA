"""Rendering, palette and calibration tests."""

from __future__ import annotations

import io
import unittest

from common import load, sample_frames

from PIL import Image

protocol = load("protocol")
rendering = load("rendering")
palette = load("palette")
overlay = load("overlay")


def first_frame():
    messages, _ = protocol.parse_messages(sample_frames())
    return protocol.decode_frame(messages[0][1], 0)


class PaletteTest(unittest.TestCase):
    def test_twelve_palettes(self) -> None:
        self.assertEqual(len(palette.PALETTE_NAMES), 12)
        for name in palette.PALETTE_NAMES:
            table = palette.get_palette(name)
            self.assertEqual(len(table), 256)
            for entry in table:
                self.assertEqual(len(entry), 3)
                self.assertTrue(all(0 <= channel <= 255 for channel in entry))

    def test_unknown_palette_falls_back(self) -> None:
        self.assertEqual(palette.get_palette("nope"), palette.get_palette("HEATED_IRON"))


class TemperatureTest(unittest.TestCase):
    def test_deci_kelvin_conversion(self) -> None:
        self.assertAlmostEqual(rendering.dk_to_celsius(2977), 24.55, places=2)
        self.assertAlmostEqual(rendering.dk_to_celsius(2731.5), 0.0, places=2)

    def test_unit_conversion(self) -> None:
        self.assertAlmostEqual(rendering.celsius_to_unit(25.0, "°F"), 77.0)
        self.assertAlmostEqual(rendering.celsius_to_unit(25.0, "K"), 298.15)
        self.assertEqual(rendering.celsius_to_unit(25.0, "dK"), 2982)
        self.assertAlmostEqual(rendering.celsius_to_unit(25.0, "°C"), 25.0)

    def test_format(self) -> None:
        self.assertEqual(rendering.format_temperature(25.0, "°C", 1), "25.0 °C")
        self.assertEqual(rendering.format_temperature(25.0, "dK"), "2982 dK")


class CalibrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = first_frame()

    def test_identity_calibration(self) -> None:
        values = rendering.calibrate(self.frame.pixels, 1.0, 0.0)
        self.assertAlmostEqual(values[0], self.frame.pixels[0] / 10 - 273.15, places=6)

    def test_offset_shifts_every_pixel(self) -> None:
        base = rendering.calibrate(self.frame.pixels, 1.0, 0.0)
        shifted = rendering.calibrate(self.frame.pixels, 1.0, 2.5)
        for index in (0, 100, 1000, 4959):
            self.assertAlmostEqual(shifted[index] - base[index], 2.5, places=6)

    def test_low_emissivity_raises_apparent_temperature(self) -> None:
        base = rendering.calibrate(self.frame.pixels, 1.0, 0.0)
        low_e = rendering.calibrate(self.frame.pixels, 0.5, 0.0)
        self.assertGreater(max(low_e), max(base))


class FilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.values = [float(v) for v in first_frame().pixels]

    def test_none_is_identity(self) -> None:
        self.assertEqual(rendering.apply_filter(self.values, "None"), self.values)

    def test_low_and_high_reduce_variance(self) -> None:
        original = statistics_variance(self.values)
        low = statistics_variance(rendering.apply_filter(self.values, "Low"))
        high = statistics_variance(rendering.apply_filter(self.values, "High"))
        self.assertLess(low, original)
        self.assertLess(high, low)

    def test_filter_preserves_mean(self) -> None:
        filtered = rendering.apply_filter(self.values, "Low")
        self.assertAlmostEqual(sum(filtered) / len(filtered), sum(self.values) / len(self.values), places=1)


class StatsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.values = [float(v) for v in first_frame().pixels]

    def test_stats_positions(self) -> None:
        stats = rendering.compute_stats(self.values)
        self.assertEqual(len(self.values), 80 * 62)
        index = stats.max_position[1] * 80 + stats.max_position[0]
        self.assertAlmostEqual(self.values[index], stats.maximum)
        index = stats.min_position[1] * 80 + stats.min_position[0]
        self.assertAlmostEqual(self.values[index], stats.minimum)

    def test_centre_pixel(self) -> None:
        stats = rendering.compute_stats(self.values)
        self.assertAlmostEqual(stats.center, self.values[31 * 80 + 40])

    def test_percentile_trim(self) -> None:
        low, high = rendering.percentile_limits(self.values, 0.1)
        self.assertGreaterEqual(low, min(self.values))
        self.assertLessEqual(high, max(self.values))


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = first_frame()

    def test_render_jpeg(self) -> None:
        options = rendering.RenderOptions(width=640, height=496, palette="HEATED_IRON")
        result = rendering.render_frame(self.frame, options)
        self.assertTrue(result.jpeg.startswith(b"\xff\xd8"))
        image = Image.open(io.BytesIO(result.jpeg))
        self.assertEqual(image.size, (640, 496))
        self.assertGreater(result.scale_max, result.scale_min)

    def test_every_palette_renders(self) -> None:
        for name in palette.PALETTE_NAMES:
            with self.subTest(palette=name):
                options = rendering.RenderOptions(width=320, height=248, palette=name)
                result = rendering.render_values(
                    rendering.calibrate(self.frame.pixels, 0.97, 1.5), options
                )
                self.assertTrue(result.jpeg.startswith(b"\xff\xd8"))

    def test_manual_range_is_honoured(self) -> None:
        options = rendering.RenderOptions(
            width=160,
            height=124,
            auto_range=False,
            scale_min=25.0,
            scale_max=26.0,
            show_colorbar=False,
        )
        result = rendering.render_values(
            rendering.calibrate(self.frame.pixels, 1.0, 0.0), options
        )
        self.assertEqual(result.scale_min, 25.0)
        self.assertEqual(result.scale_max, 26.0)

    def test_csv_export(self) -> None:
        csv = rendering.frame_to_csv(self.frame, rendering.RenderOptions())
        lines = csv.strip().splitlines()
        self.assertEqual(len(lines), 4 + 62)
        self.assertTrue(lines[0].startswith("# SenXor"))


def statistics_variance(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


if __name__ == "__main__":
    unittest.main()
