# Changelog

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
