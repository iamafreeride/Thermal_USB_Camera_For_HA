# Changelog

## 2.3.1

* **中斷連線** now really disconnects: it closes the socket, clears the last
  frame (the camera entity becomes unavailable) and records `streaming = false`
  so the polling loop stops reconnecting.  Previously the coordinator
  reconnected on the next tick, so the button appeared to do nothing.
* **重新連線** restores the intent (`streaming = true`), reconnects, waits for a
  frame and republishes the state, so the entities come back without waiting for
  the retry timer.
* `switch.連續擷取` uses the same paths: turning it off stops the stream and
  suppresses automatic reconnects, turning it on reconnects when needed.
* Added three regression tests covering disconnect, reconnect and the streaming
  switch (`tests/test_connection.py`).

## 2.3.0

Fixes **every button, number, select and switch failing to be added**:

```
Error adding entity button.thermal_camera_fps_increase for domain button with platform senxor_thermal
AttributeError: 'SenXorButtonDescription' object has no attribute 'device_class'
```

The description dataclasses were plain `@dataclass` objects instead of subclasses
of Home Assistant's `ButtonEntityDescription` / `NumberEntityDescription` /
`SelectEntityDescription` / `SwitchEntityDescription`.  Home Assistant reads
`entity_description.device_class` and
`entity_description.entity_registry_enabled_default` while registering an entity,
so all 4 buttons, 11 numbers, 4 selects and 5 switches were dropped silently.
Only the sensors and the camera survived because their description already
inherited the HA dataclass.

* The four descriptions now inherit the matching HA description classes and use
  the native fields (`native_min_value`, `native_step`, `options`, …).
* Added a strict test harness that reproduces the HA attribute access, so this
  regression cannot come back unnoticed.
* Added `services.yaml` (removes the "Failed to load services.yaml" warning).

## 2.2.0

* Exactly the four requested buttons: 中斷連線 / 重新連線 / FPS 增加 / FPS 減少
  (`single_frame` removed).
* Every number, select and switch is now a **visible control** instead of a
  `config` entity, so they appear directly on the device page rather than inside
  the collapsed *Configuration* section.
* Entities removed in earlier versions (`frames_received`,
  `frame_rate_level`, `single_frame`) are deleted from the entity registry
  automatically on setup.

## 2.1.0

* Every entity now carries a **Chinese display name**, independent of the Home
  Assistant language setting: 熱影像, 最低溫, 最高溫, 平均溫, 中心溫, 溫度1,
  溫度2, 熱點 X/Y, 晶片溫度, 供應電壓, 影格率, X1/Y1/X2/Y2, 放射率, 溫度補償,
  靈敏度, 影格率除數, 極值裁切, 色階上下限, 調色盤, 影像溫度單位, 濾波, 增益,
  連續擷取, 自動色階, 移除極值, 顯示極值標記/色階條, FPS 增加, FPS 減少,
  中斷連線, 重新連線, 單張擷取.
* Entity ids are pinned to ASCII (`number.thermal_camera_x1`,
  `sensor.thermal_camera_temperature_1`, `button.thermal_camera_fps_increase`, …)
  because `slugify()` drops CJK characters and would otherwise generate empty ids.
* Added `translations/zh-Hant.json` and `translations/zh-Hans.json` for the config
  and options dialogs.

## 2.0.1

* Fixed `Unknown error occurred` when adding or reconfiguring the integration:
  the config-flow probe still referenced the pre-2.0 register constants, so it
  raised `NameError` instead of returning a readable `cannot_connect` error.
* Added regression tests for the probe (fake camera server), the full
  `async_setup_entry` / `async_unload_entry` path and the config-flow import.

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
