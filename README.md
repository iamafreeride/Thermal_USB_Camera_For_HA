# Thermal USB Camera for Home Assistant

Home Assistant integration for the **Meridian Innovation SenXor** thermal camera
module (80 × 62 IR array) when it is reachable over TCP — for example through the
network bridge that ships with the EVK, or a serial-to-Ethernet adapter.

This project is a functional port of the vendor's Windows application
`SenXorEvkViewer_2024.06.06.exe`. The viewer's USB/TCP protocol was
reverse-engineered from the shipped binary and from live traffic, and the
viewer's imaging pipeline (palettes, colour scale, filtering, calibration,
readouts) was re-implemented in pure Python inside a HACS-installable
integration.

```
camera.thermal_camera        live thermogram, 80x62 @ ~15 fps
sensor.*                     min / max / average / centre temperature, hot spot, fps
number.*                     emissivity, temperature offset, manual scale limits
select.*                     palette, image unit, spatial filtering
switch.*                     auto range, remove extremes, markers, colour bar
button.*                     single frame, restart stream, frame rate up/down
```

![Rendered thermogram](docs/images/thermogram.jpg)

The image above is produced by this integration from a real frame of the
`192.168.11.153` camera (HEATED_IRON palette, automatic range, colour bar,
min/max markers and centre readout — the same overlays the Windows viewer draws).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=iamafreeride&repository=Thermal_USB_Camera_For_HA&category=integration)

1. HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/iamafreeride/Thermal_USB_Camera_For_HA` with category **Integration**
3. Install **SenXor Thermal Camera**, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → SenXor Thermal Camera**
5. Enter the camera address (default port `3333`) and submit — the flow connects
   to the device and waits for one real thermal frame before creating the entry

### Manual

Copy `custom_components/senxor_thermal` into your Home Assistant `config` folder
and restart.

## Configuration

| Field | Default | Description |
| --- | --- | --- |
| Host | – | IP address or host name of the camera / TCP bridge |
| Port | `3333` | Raw TCP port of the SenXor firmware |
| Name | `Thermal Camera` | Device name |

Options (⚙ on the integration card): update interval (seconds) and JPEG quality.

## Entities

| Entity | Type | Description |
| --- | --- | --- |
| `camera.thermal_camera` | camera | False colour thermogram, updated every coordinator tick |
| `sensor.thermal_camera_minimum_temperature` | °C | Coldest pixel of the current frame |
| `sensor.thermal_camera_maximum_temperature` | °C | Hottest pixel of the current frame |
| `sensor.thermal_camera_average_temperature` | °C | Mean of all 4960 pixels |
| `sensor.thermal_camera_centre_temperature` | °C | Pixel under the crosshair |
| `sensor.thermal_camera_frame_rate` | fps | Measured frame rate |
| `sensor.thermal_camera_frames_received` | – | Frame counter |
| `sensor.thermal_camera_hotspot_x` / `_y` | px | Coordinates of the hottest pixel |
| `number.thermal_camera_emissivity` | 0.10–1.00 | Grey body emissivity used for the radiance correction |
| `number.thermal_camera_temperature_offset` | °C | Added to every pixel (viewer's "Temp Offset") |
| `number.thermal_camera_scale_minimum` / `_maximum` | °C | Manual colour scale limits |
| `select.thermal_camera_palette` | 12 options | `INFERNO`, `HEATED_IRON`, `BLACK_BODY`, `PLASMA`, `COOLWARM`, `IRON_GLOW`, `GRAYSCALE`, `BONE`, `BEZIER`, `OCEAN`, `RAINBOW`, `SUMMER` |
| `select.thermal_camera_image_temperature_unit` | `°C` `°F` `K` `dK` | Unit used for the values drawn on the image |
| `select.thermal_camera_filtering` | `None` `Low` `High` | 3×3 / 5×5 spatial smoothing |
| `switch.thermal_camera_automatic_temperature_range` | on | Auto colour scale |
| `switch.thermal_camera_remove_extreme_values` | off | Trim 0.1 % of the extremes before scaling |
| `switch.thermal_camera_show_min_max_markers` | on | Draw hot/cold markers |
| `switch.thermal_camera_show_colour_bar` | on | Draw the colour bar |
| `button.thermal_camera_single_frame` | – | Trigger one frame (`WREG 0xB101`) |
| `button.thermal_camera_restart_stream` | – | Reconnect and restart streaming (`WREG 0xB103`) |
| `button.thermal_camera_increase_frame_rate` | – | `WREG 0xB403` |
| `button.thermal_camera_decrease_frame_rate` | – | `WREG 0xB404` |

Sensors always report **°C**; Home Assistant converts them to your unit system.
The *image temperature unit* only affects the numbers drawn on the thermogram,
matching the vendor viewer's "Temperature Unit" radio buttons.

### Service `senxor_thermal.snapshot`

Writes the current thermogram to `config/www/senxor_thermal/`.

```yaml
service: senxor_thermal.snapshot
data:
  filename: kitchen
  csv: true
```

Response: `{"image": ".../kitchen.jpg", "csv": ".../kitchen.csv", "min_dk": 2977, "max_dk": 3034}`

## Example dashboard

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: camera.thermal_camera
    camera_view: auto
    show_name: false
  - type: entities
    entities:
      - sensor.thermal_camera_maximum_temperature
      - sensor.thermal_camera_minimum_temperature
      - select.thermal_camera_palette
      - number.thermal_camera_emissivity
      - switch.thermal_camera_automatic_temperature_range
```

Automation example – notify on a hot spot:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.thermal_camera_maximum_temperature
    above: 60
action:
  - service: notify.persistent_notification
    data:
      title: Hot spot detected
      message: >-
        {{ trigger.to_state.state }} °C at
        ({{ state_attr('sensor.thermal_camera_hotspot_x','x') }}, ...)
```

## Feature parity with the vendor viewer

| Viewer feature | Status here |
| --- | --- |
| TCP/IP connection (host:port) | ✅ config flow |
| USB connection | ❌ (same protocol over a serial port; not ported, HA hosts are usually remote) |
| Connect / Disconnect | ✅ integration setup + *Restart stream* button |
| Single frame / continuous stream | ✅ buttons + always-on stream |
| FPS up / down | ✅ buttons (`0xB403` / `0xB404`) |
| 12 colour palettes | ✅ select (tables recreated, not byte-identical) |
| Auto / manual temperature range, remove extremes | ✅ switches + numbers |
| Filtering none / low / high | ✅ select |
| Temperature unit °C/°F/K/dK | ✅ select (image overlay) |
| Emissivity, temperature offset | ✅ numbers (radiance model, documented) |
| Sensitivity / gain controls | ⚠️ not ported – the viewer applies them inside its own radiometric model; no register write was observed on the wire |
| Temperature at pixel (X, Y) | ✅ hotspot/centre sensors + camera attributes |
| Die info (VDD, die temperature) | ⚠️ the viewer itself shows *N/A* in TCP mode – the registers are only read over USB |
| Data recording to text files | ✅ `senxor_thermal.snapshot` (JPEG + CSV) |
| Life detection (TensorFlow model) | ❌ out of scope (ships `DnIRB_v2_2_thermal_sigma25_depth5.pb`, no portable equivalent) |
| Product calibration | ❌ factory tool, not ported |

## Verified against

* Camera `192.168.11.153:3333` (SenXor firmware answer: `#0008WREG01FD` to a
  stream-start write), host `192.168.11.11`
* `SenXorEvkViewer 2024.06.06.0`, file version `2024.06.06.0`, 23 278 592 bytes

## Troubleshooting

* **Only one TCP client at a time.** The firmware accepts a single connection;
  quit the Windows viewer before using Home Assistant (the integration logs
  `connection closed by device` otherwise).
* **No frames.** Run `python tools/probe.py --host <ip>` on a machine in the same
  network. It prints the message flow and writes `frame.jpg`.
* Enable debug logging:

  ```yaml
  logger:
    logs:
      custom_components.senxor_thermal: debug
  ```

## How it works

The protocol is documented in [docs/protocol.md](docs/protocol.md). In short: a
plain TCP socket, ASCII framed messages (`#` + 4 hex length + 4 char command),
one `WREG` register write to start streaming and then 10253 byte `GFRA` frames
containing 4960 little-endian `uint16` deci-Kelvin samples.

## 繁體中文快速說明

1. HACS → 整合 → 右上角 ⋮ → 自訂儲存庫，貼上本專案網址，類別選「Integration」。
2. 安裝 **SenXor Thermal Camera** 後重新啟動 Home Assistant。
3. 設定 → 裝置與服務 → 新增整合 → 搜尋 `SenXor` → 輸入 `192.168.11.153`、連接埠 `3333`。
4. 相機會出現在 `camera.thermal_camera`，並附上最高/最低/平均/中心溫度感測器、色彩盤、
   濾波、放射率與色階控制。
5. 注意：原廠 Windows 檢視器同一時間只能有一個連線，使用前請先關閉。

## License

MIT – see [LICENSE](LICENSE). Not affiliated with Meridian Innovation Limited.
