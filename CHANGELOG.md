# Changelog

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
