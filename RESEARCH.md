# ORA 5 capability investigation

Evidence collected on 2026-09-12 from the ANZ app, its capability response for one shared ORA 5 and supervised tests. These findings do not establish support on every GWM vehicle. No app binaries, credentials, identifiers, coordinates or captures are included.

## Readable on the tested vehicle

| Data | Signal or endpoint | Evidence |
|---|---|---|
| Battery percentage and range | `2013021`, `2011501` | Live values |
| Charging state, cable, estimated remaining minutes | `2041142`, `2042082`, `2013022` | Live values and charging transitions |
| Charging mode | `2013023` | App maps this to `charModel`; enumeration not yet verified |
| Away-mode state | `2012881` | App maps this to `awayMode`; enumeration not yet verified |
| Odometer | `2103010` | Live value |
| Four tyre pressures and temperatures | `2101001`–`2101008` | Live kPa and Celsius values |
| Tyre warning and window-learning codes | Status response | Raw numeric diagnostics; not interpreted as mechanical faults |
| Lock, doors, boot and windows | Status response | Live states; lock and boot transitions verified |
| Climate, demisters, steering-wheel heat and front-seat levels | Status response | Live on/off transitions |
| Position and source timestamps | Status envelope | Present; location entity is opt-in |
| Climate and other saved comfort settings | `vehicle/vehicleBasicsInfo` | Response includes more configuration fields than the upstream parser retains |
| Charging schedule | `vehicleCharge/getChargingInfos` | Returns `chargePlanList`; `planType` is a string and unset times may be null. Upstream parser rejects this shape |
| Charging history | `vehicleCharge/getChargeLogs` | POST read with `vin`, `pageNum`, `pageSize`; paginated start/end timestamps, including null end times |
| Vehicle/account capability tree | `vehicle/findVehicleCapabilityItem` | GET with `vin`, `userRole`; official app derives role as discovery `ownership + 1` |

The current response does not provide battery-pack current/voltage, 12 V voltage, cell temperatures, battery health or instantaneous charging kW. Generic fields in another GWM client are not evidence that this ORA exposes them.

## Controls

| Control | T5 instruction | Test result |
|---|---|---|
| Charging start/stop | `0x01` | Both verified |
| Climate on/off | `0x04` | Both verified; off requires nested `switchOrder="2"`, `operationTime="0"`, not the upstream client's off value `0` |
| Unlock/lock | `0x05` | Both verified; native HA lock entity |
| Flash, alarm, flash+alarm | `0x06` | Cloud completion and observer feedback; horn is a loud alarm. Disabled by default |
| Close windows | `0x08` | App capability and body decoded; motion test pending |
| Boot open/close | `0x09` | Both verified; first close rejected due to session expiry, close-only command succeeded with current session; observer confirmed closure |
| Front seat heat/ventilation | `0x0A` | Both fronts on/off verified at level 1; unsupported rear-seat parameters caused immediate rejection |
| Front/rear demisting | `0x0B` | Both verified; front demisting also activates climate |
| Cabin-air cleaning | `0x11` | Start completed, climate/circulation became active, and both returned off automatically; vehicle unplugged. Observer feedback pending. |
| Steering-wheel heating | `0x19` | Both verified |

Most observed commands completed in approximately six seconds; some took eleven. The tests do not establish a universal timeout. A protocol rejection and an expired session can look like an unreliable control in the app but require different remedies.

Schedule-write test: a future window was accepted but never appeared in readback during a 60-second wait. Clearing was accepted and three subsequent reads showed no active schedule. Schedule editing remains unreleased.

## Hidden/shared app definitions

The shared command factory also contains battery/plugged-in heating (`0x18`), idle charging (`0x12`), away mode (`0x35`), GPS authorization (`0xCF`), warning reset (`0x16`), sunroof/shade and other functions. Presence in the APK does not imply ORA 5 hardware support. Battery heating and window opening were not advertised in the tested car's capability tree. These commands are not exposed as general-purpose buttons and were not sent.

The advertised warning-reset function is labelled as silencing a life-sign/occupancy detection alarm. It must not be confused with clearing diagnostic fault codes. No safety-alarm scenario was induced to test it.

## Feedback and retries

Commands are journaled before transmission. Results are scoped by request sequence and instruction type. For persistent controls, cloud completion is followed by checking the requested telemetry state. If the state does not agree, the journal remains `awaiting_feedback` and blocks another start operation. Explicit stop/lock/close-window operations remain available. Alarm/light pulses lack continuous feedback and therefore report provider completion only.

One refresh/retry is allowed only after an explicit authentication rejection before command acceptance. Network timeout, unknown outcome and pending execution do not trigger blind resends. A real physical observer remains important when validating movement and audible behaviour.
