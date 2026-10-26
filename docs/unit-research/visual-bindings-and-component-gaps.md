# Unit visual bindings and component boundaries

Checked 2026-10-26 against the frozen public visual source
`48ab992f5ff63c1a91296051e1afcb5959877903`, the vendored official UIFlow
drivers, and four live M5Stack official MCP `knowledge_search` queries.
The exact queries, responses, readable excerpts and hashes are archived in
[`2026-10-26-visual-binding-research`](../evidence/2026-10-26-visual-binding-research/manifest.json).
Search results for other products are not a basis for a binding.

`platform/web/unit-visual-mappings.js` gives all 27 products a field-level audit.
Its executable report is
[`unit-visual-mapping-report.json`](../evidence/2026-10-26-visual-model-integration/unit-visual-mapping-report.json).
`mapped` means a browser conversion is implemented; it does not grant a guest,
controller or hardware PASS. Fan's `activity-only` state deliberately has a
separate category. The browser model report now inventories actual component
paths, kinds and metadata for every loaded Unit.

| Product / field | Confirmed evidence | Remaining binding |
| --- | --- | --- |
| Joystick v1.1 U024-C / button raw | Official `JoystickUnit.get_button_status()` returns `bool(buffer[2])`. Product protocol returns byte 2 as BTN STATUS, 0/1. The v1.1 schematic labels ADIN0/1/2, not the switch's active state. | Neither reviewed v1.1 product text nor API text explicitly assigns 0/1 to physical pressed/released. A Joystick2 result explicitly says True means pressed, but that is a different SKU/protocol and is excluded. |
| Joystick / X and Y | Driver's raw bytes and centered values are confirmed. The model has `tilt-x`/`tilt-y` joints with viewer-only ±20° ranges. | Raw axis to geometric rotation axis, sign, mechanical range and calibrated angle remain unconfirmed. |
| RGB U003 / LED array | [Official schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/760/U003-UNIT_RGB-SCHE.pdf) gives DI → LED3 → LED2 → LED1. The visual model places `led0/1/2` at X = -6.5/0/6.5 mm. | No reviewed PCB placement/refdes evidence connects those electrical devices to the three visual positions. A numerical array index alone does not close it. |
| Encoder U135 / LED array | The official protocol's index 0 sets both LEDs; index 1/2 sets a single LED. Official schematic search confirms PA0 → LED1 → LED2. The model has `led0/1` at left/right. | LED1/LED2 to the two model locations needs PCB placement/refdes evidence. |
| 8Encoder U153 / nine RGBs | [Official schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/607/SCH_UNIT_8Encoder_V1.01.pdf) confirms PB0 → U1 → … → U9. Official MCP explicitly records physical_mapping as unspecified. Vendor `rgb-1`…`rgb-9` metadata says physical locations are not schematic chain order. | U1…U9 to eight channel light pipes and the switch pipe remains unconfirmed. |
| 8Encoder / slide switch | Official driver returns bool(register 0x60); schematic shows SW_K9 with R11 10K pull-up and SW9 to ground. The model has stable detents 0/1 along X. | Schematic search explicitly records position_truth_table as unspecified. Left/right detent to high/low or logical on/off cannot be inferred from the symbol. |
| Encoder / counters | Real guest signed counter reads, resets and LED writes are validated separately. | Counts per physical revolution, direction and zero offset remain uncalibrated. |

Explicit evidence-bearing bindings can enable these geometric conversions.
No such defaults are installed. Numeric sliders and raw fields remain usable
through the real controller path while these mechanical bindings are open.

## Feedback implemented without guessing physical placement

- Key and CardKB have a single identified RGB component; their packed observed
  colors map directly to that component. CardKB's keyboard matrix has exactly
  50 visual IDs matching the independently transcribed official key tables.
- Unit panel RGB swatches display the observed packed color(s) in **electrical
  array order**, labelled `LED[0]` onward. They cover Key/CardKB, RGB3,
  Encoder2 and 8Encoder9 without claiming unconfirmed physical light locations.
  They never synthesize an input request or a key-to-light rule.
- Fan has an actual continuous `rotor` joint. The adapter animates only the
  qualitative fact that an available, running controller reports positive PWM
  duty. The graphical cadence is fixed independently of PWM duty/frequency;
  it is not stored in the joint's RPM field and does not represent shaft speed.
  Zero duty, invalid/unavailable data, a terminal session, detach or disposal
  stops/releases the animation. The product panel says speed and
  electromechanical response are unmodeled. No motor plant/load/RPM result is
  claimed.

## Components absent from the frozen source

`src/units/shared/CADUnit.js` adds a `sensor` component whose metadata says
`role=visual-anchor` and `scope=no-sensor-behavior`. ENV III, PIR, ultrasonic,
color, ToF, light, NCIR, heart, thermal, TVOC, Relay and other static Units do
not gain an actuator simply because their files import `Button` or `Led`.
The dynamically loaded component inventory is the check, not import names.
Relay has no contact/armature/indicator component. The sensor housings have no
numeric display component. Fan is the explicit exception above.

The adapter now implements a readout rail outside the interactive canvas for
ENV III, PIR, ultrasonic I2C, Color, ToF, Light, Relay, NCIR, Heart, Thermal,
TVOC and Buzzer. Actual `sensor` anchors and matching numbers identify each
Unit. Values require the frozen session definition, a live response and
`guest-qom` Unit source, a running/available state, and valid scalar types and
ranges. Defaults, pending input, mutable inventory and persisted snapshots do
not create live numbers. This browser display does not add a physical LED,
screen or actuator to the public model.

Source labels are audited per field: simulated inputs, firmware GPIO/LEDC
outputs, Thermal's derived fixture readiness, and its shared control register
are distinct. The Thermal control word can be changed by QOM or guest register
writes, so it is not labelled solely as an injected input. Relay shows the
observed drive level; contact motion still needs its own electromechanical
model. Buzzer now has a user-enabled, band-limited PWM audition driven by live
guest-QOM frequency/duty; a separately hashed custom diagnostic firmware has
actual browser evidence. Short polling-window pulses, physical acoustics and
initial GPIO-route/QOM refresh remain explicit boundaries. Geometric binding coverage above is unchanged;
readout coverage and actual guest evidence are separate validation layers.

The scoped CoreS3 direct-HUB layout now separates full-size ENV III/ToF/Color
housings at four viewport widths, using actual mating frames and public cable
poses. The native Button path, focus and optional-layout failure isolation are
also checked. The policy excludes other hosts, DinBase, deep trees, custom poses
and unsupported children; other permutations are not validated. Phone overview
touch comfort remains partial. `UNIT-HOST-15` records the remaining scope;
controller/topology and physical validation are unchanged.
