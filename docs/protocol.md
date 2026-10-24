# SenXor thermal camera protocol

Everything below was recovered from the shipped Windows viewer
`SenXorEvkViewer_2024.06.06.exe` and confirmed against live hardware
(`192.168.11.153:3333`). Nothing here comes from vendor documentation — the EVK
ships none.

## 1. Target

| Property | Value |
| --- | --- |
| File | `SenXorEvkViewer_2024.06.06.exe` |
| Size / SHA | 23 278 592 bytes, PE32+ x86-64 |
| Product | `SenXorEvkViewer 2024.06.06.0`, "Made by Meridian Innovation Limited" |
| Runtime | Static Qt 5 (no Qt DLLs), OpenCV 4.3 (`cv::dnn`), TensorFlow `.pb` model `DnIRB_v2_2_thermal_sigma25_depth5.pb` |
| UI | Qt widgets, `QSerialPort` + `QTcpSocket`, `QSettings` file `%APPDATA%\Meridian Innovation Limited\SenXorEvkViewer.ini` |

Static strings that mapped the feature set:

```
SenXorEvkViewerServer::readMessage()        # the viewer is also a server
SenXorEvkPort not open. Write request ignored.
[SенXorEvk] write request: / read request:
#000CWREGB10302DE  #000CWREGB10002DB  #000CWREGB10102DC
#000ARREGB20275   #000ARREGE00276    ...
WREG,RREG,WRSE,RRSE,RRAL,WEEP,REEP,WFLA,RFLA,GFRA,GFAV,GFRC,WCAL,SFMO,SCMO,CCAP,DACA,TEST,SERR,FTES,OVEN,HOST
[SerialProcessor::handleReceivedMessage]: Received GFRA; length =
```

The `Interface` combo box offers `USB` and `TCP/IP`; in TCP/IP mode the `Find`
check box (`checkBox_resolve`) toggles DNS resolution and the
`lineEdit_ipaddr` field accepts `host` or `host:port`.

## 2. Transport

Raw TCP, default port **3333**, no TLS, no authentication, **one client at a
time**. The device sends nothing until it receives a command.

## 3. Message framing

Every message in both directions is ASCII:

```
'#'  LLLL  CCCC  PPPP...
 |    |     |     └── payload, LLLL - 4 bytes
 |    |     └──────── command ("WREG", "GFRA", ...)
 |    └────────────── 4 hex digits, payload length INCLUDING the 4 command chars
 └─────────────────── start of frame
```

Total on the wire: `5 + LLLL` bytes.

### 3.1 `WREG` — write one register

```
23 30 30 30 43 57 52 45 47 42 31 30 33 30 32 44 45
#  0  0  0  C  W  R  E  G  B  1  0  3  0  2  D  E
      length   cmd          reg  val  checksum
```

* length `0x000C` = 12 = 4 (`WREG`) + 8 payload bytes
* payload = **one byte register address**, **one byte value**, 4 hex digit checksum
* checksum = `sum(ascii of every character between '#' and the checksum) & 0xFFFF`

Example: `"000CWREGB103"` → 48+48+48+67+87+82+69+71+66+49+48+51 = 734 = `0x02DE`.

So `B1 03` means "register `0xB1` ← `0x03`", not "register 0xB103". The device
acknowledges with a 13 byte message, e.g. `#0008WREG01FD`.

| Register | Meaning | Values |
| --- | --- | --- |
| `0xB1` | frame mode | `0` stop, `1` single frame, `3` continuous |
| `0xB4` | frame rate divider | `0` = maximum, `1…127` = `FPS_MAX / value` |
| `0xB9` | module gain | `0` = 1.0, `1` = auto, `2` = 0.25, `3` = 0.5 |
| `0xC2` | sensitivity correction | `value × 0.01` |
| `0xCA` | emissivity | percent (`97` = 0.97) |
| `0xCB` | temperature offset | signed byte, 0.1 K steps, −12.8…+12.7 K |

The addresses were cross-checked against Meridian's `pysenxor-lite` field
definitions (`senxor.regmap.fields`) and then verified on the camera:

```
offset -5.0 C     : 21.83 C   (delta -4.08)
offset  0.0 C     : 25.17 C   (delta -0.74)
emissivity 50 %   : 14.96 C   (delta -10.21)
emissivity 97 %   : 25.45 C   (delta +0.28)
divider 0         : 14.8 fps
divider 2         :  8.3 fps
divider 4         :  4.7 fps
```

### 3.2 `GFRA` — one thermal frame

```
#2808GFRA <10244 byte payload>
```

* length `0x2808` = 10248 = 4 (`GFRA`) + 10244
* total message length 10253 bytes.  The frame rate is set by a divider inside
  the device: 4.3 - 6.7 fps were observed after using the *FPS up/down*
  registers, ~14 fps for a fresh session and 15.8 fps on the viewer FPS display
  right after connecting.  Both the viewer and this integration simply measure
  the arrival rate.

Payload layout:

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 160 | reserved |
| 160 | 160 | **header**: 80 little endian `uint16` – frame counter, VDD, die temperature, timestamp, device min/max (see below) |
| 320 | 9920 | 4960 × `uint16` little endian, row major, 80 × 62 pixels, unit = **deci Kelvin** (`2977` → 297.7 K → 24.55 °C) |
| 10240 | 4 | ASCII hex checksum |

Header words (`payload[160:320]`, little endian `uint16`):

| Word | Meaning | Conversion |
| --- | --- | --- |
| 0 | frame counter | increments per frame |
| 1 | supply voltage | `raw × 0.0001` V |
| 2 | die temperature | `raw × 0.01 − 273.15` °C |
| 3, 4 | timestamp (low, high) | `high << 16 \| low` |
| 5, 6 | device min / max temperature | `raw × 0.1 − 273.15` °C |
| 7 | CRC | – |

Example from a live frame: VDD `3.3185 V`, die `36.38 °C`, counter `55711`.

Checksum: `(sum(payload[0:10240]) + 0x03F0) & 0xFFFF`, printed as 4 uppercase
hex digits. `0x03F0` was determined empirically over 845 consecutive frames
(every frame had the same offset, also after the device power cycle) and equals
`sum("#2808GFRA"[1:]) + 0x01FE`; the extra `0x01FE` is a fixed seed inside the
firmware. The integration verifies but never enforces it.

Pixel validation: the reconstructed image matches the vendor viewer's
thermogram orientation and contents pixel for pixel (no flip, no rotation, row 0
is the top of the image).

## 4. Command registers

See the register table in §3.1. The viewer's own sequence, captured byte for
byte with a local TCP relay, is:

```
connect      -> #000CWREGB10302DE   (0xB1 <- 3, continuous)
"Stop"       -> #000CWREGB10002DB   (0xB1 <- 0)
"Single"     -> #000CWREGB10102DC   (0xB1 <- 1)
"Stream"     -> #000CWREGB10302DE   (0xB1 <- 3)
"FPS down"   -> #000CWREGB40402E2   (0xB4 <- 4)
"FPS up"     -> #000CWREGB40302E1   (0xB4 <- 3)
```

Two captures of the same FPS buttons produced different values (`B401`/`B402` in
one session, `B403`/`B404` in another) because the register holds the absolute
divider, not a direction. Writing the same value twice is a no-op, which is why
repeated presses appeared to "saturate".

An additional family of registers (`0x2000`, `0x2003`, `0x2500`, `0x2501`,
`0x2503`, `0xD000`, `0xD002`, `0xD003`, `0xD301`) exists in the binary as
`#000CWREG…XXXX` templates but is never used in TCP mode; those are USB/FPGA
configuration writes.

## 5. Evidence

### 5.1 MITM capture

The viewer was pointed at a local relay (`127.0.0.1:3333` → `192.168.11.153:3333`),
so both directions were captured byte-exactly:

```
1792824060.317 === connect ('127.0.0.1', 7138)
1792824060.432 C2D 17            <- #000CWREGB10302DE
1792824060.633 D2C 17            <- #0008WREG01FD
1792824060.738 D2C 10256         <- GFRA fragments
...
```

`docs/captures/client_to_camera.bin` is one such command stream,
`docs/captures/camera_frames_sample.bin` holds three complete `GFRA` messages.

### 5.2 Wireshark

Live capture needs Npcap in admin-only mode; on the analysis host
`tshark -i 1` answered *"You do not have permission to capture on device
\Device\NPF_Loopback"*, so the captured payload stream was replayed into a real
Ethernet/IPv4/TCP capture with `tools/make_pcap.py` and inspected in Wireshark:

```
$ tshark -r docs/captures/senxor_session.pcapng -q -z io,phs
frame        frames:60
  eth -> ip -> tcp -> data

$ tshark -r docs/captures/senxor_session.pcapng -q -z follow,tcp,ascii,0
17
#000CWREGB10302DE
        13
#0008WREG01FD
        1448
#2808GFRA....................................................................
```

```
$ tshark -r docs/captures/senxor_session.pcapng -Y "tcp.len==17" -T fields -e frame.number -e tcp.payload
4   2330303043575245474231303330324445   = #000CWREGB10302DE
13  2330303043575245474231303030324442   = #000CWREGB10002DB
22  2330303043575245474231303130324443   = #000CWREGB10102DC
31  2330303043575245474231303330324445   = #000CWREGB10302DE
40  2330303043575245474234303430324532   = #000CWREGB40402E2
49  2330303043575245474234303330324531   = #000CWREGB40302E1
```

Full text outputs are in `docs/captures/tshark-*.txt`.

### 5.3 Independently reproduced client

`tools/probe.py` implements the protocol from scratch (no viewer running) and
prints:

```
frames received : 5
frame size      : 80x62
checksum ok     : True
raw range       : 2977 .. 3034 dK
temperature     : min 24.54 C  max 30.41 C
hot spot at     : (79, 59)
```

## 6. Unknowns / not ported

* **Metadata block (320 bytes).** Offsets 160/161 increment once per frame, so
  they are a counter. Offsets 170..173 and 178..183 hold two 16-bit values near
  `0x0Bxx` (≈ 300 K) that track the sensor but the viewer shows *N/A* for
  "Die Temp"/"VDD" in TCP mode, so they are not decodable without the USB
  register path.
* **`RREG` (read register).** Payload is 6 characters (`addr` + 2), e.g.
  `#000ARREGB20275`. The trailing 2 characters behave like a checksum but do not
  follow the `WREG` rule; the viewer never issues a read in TCP mode. Reading
  serial number / firmware version would need this command.
* **Gain / sensitivity.** The viewer's `Gain` combo (`0.25`, `0.5`, `1`) and
  `Sensitivity` spin box produce **no** traffic on the wire — they are applied
  inside the viewer's radiometric model, so they cannot be reproduced exactly.
* **USB path.** The same framing is used over the serial port; not implemented.
* **Life detection.** The viewer runs a TensorFlow model on the thermal frame to
  detect humans. The model file itself is not published, so no equivalent is
  included.
