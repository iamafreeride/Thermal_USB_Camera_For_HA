# Changelog

## 2.0.0

Ported the entity set of the companion integration
[`iamafreeride/home-assistant-senxor`](https://github.com/iamafreeride/home-assistant-senxor)
into this code base, at the register level.

* `WREG` is now modelled correctly as *one byte register + one byte value*; the
  previous "16 bit address" interpretation produced the same bytes but could not
  express value changes.
* New `sensor.vdd` and `sensor.die_temperature`, decoded from the GFRA header
  (`payload[160:320]`): VDD `3.3185 V`, die `36.4 °C` on the test device.
* New register-backed controls: `number.emissivity` (`0xCA`, percent),
  `number.temperature_offset` (`0xCB`, 0.1 K), `number.sensitivity` (`0xC2`),
  `select.gain` (`0xB9`), `number.frame_rate_divider` (`0xB4`, 0–127).
* New `switch.continuous_capture` (`0xB1` = 3/0) and `button.disconnect` /
  `button.reconnect`.
* Frame rate buttons now step the divider (`0` = maximum FPS) instead of the
  earlier four-level model; the `frame_rate_level` select was removed.
* Emissivity and offset are applied by the firmware, so the renderer no longer
  applies them a second time.
* `number.percentile` exposes the extreme-clipping fraction used when
  *remove extreme* is enabled.

## 1.2.0

* Two free probes: `number.probe_1_x/_1_y` and `number.probe_2_x/_2_y` select a
  pixel, `sensor.probe_1_temperature` / `_2_temperature` report its temperature,
  and both probes are drawn on the thermogram.
* Every button entity is now always pressable: a press reconnects first when the
  stream is down and raises a readable error instead of being greyed out.
* Removed the `frames_received` sensor (its counter only grew, the frame rate
  sensor covers the same need).
* Camera attributes now include `probe_1_temperature` / `probe_2_temperature`.

## 1.1.0

* Frame rate control corrected: the firmware uses an absolute level register
  (`0xB400 + level`, 1 = fastest) instead of relative up/down commands, matching
  the packets captured from the vendor viewer (`#000CWREGB40102DF` to speed up,
  `#000CWREGB40202E0` to slow down).
* New `select.frame_rate_level` entity (levels 1-4) plus level-aware
  *increase / decrease frame rate* buttons.
* The selected level is stored in the config entry and re-applied after a
  reconnect.
* Camera attributes now expose `frame_rate_level` alongside the measured rate.

## 1.0.1

* Detect a camera that accepts the TCP connection but never streams (another
  client, typically the Windows viewer, still holds the stream) and report a
  clear error instead of retrying silently.
* Reconnect automatically when frames go stale, with a 15 s cool-down between
  attempts.
* The config-flow probe now stops the stream before closing the socket, so the
  camera is released cleanly for the integration itself.
* Restart the stream with a stop / single-frame / start cycle when a session was
  orphaned.

## 1.0.0

* Initial release: camera entity, temperature sensors, palette/filter/unit
  selects, emissivity and offset calibration, scale controls, stream buttons
  and the `senxor_thermal.snapshot` service.
