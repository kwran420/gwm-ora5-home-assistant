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

## Further investigation - 2026-09-13

The following read contracts were recovered from the ANZ app's native API
definitions and checked using the existing dedicated session. No login/reclaim,
firmware write, safety-alarm command or speculative control was used.

| Surface | Evidence and outcome |
|---|---|
| Remote-command history | `POST vehicle/getWeyVrcHistory`, body `vin`, `pageNum`, `pageSize`, VIN header. Returns a paginated list with `remoteType`, `resultCode`, `createdAt`, `modifiedAt` and other private fields. A three-record page returned real command records. V0.3.0 retains only a sanitised latest-record summary. |
| Firmware update metadata | `GET vehicleFota/getFotaDetail`, VIN query/header. Returned `taskStatus=0` and null target version/progress. This establishes a readable metadata endpoint only; it does not establish update availability, current firmware version or a usable remote-update command. |
| Saved comfort presets | `GET vehicle/getCompoundCommandTemplateList` exists in the app; returned HTTP 404 on the tested ANZ app gateway. Not exposed. |
| Battery-preheat plan | `GET vehicleBatPack/queryBatPackPreheatPlan` exists in the app; returned HTTP 404 on that gateway. Heating is also absent from the tested ORA control capability tree. Not exposed. |
| Native climate appointment | `POST appointment/queryAppointmentPlan`, body `vin`, `vehicleId`, `type="AC"`. Returned HTTP 404 on that gateway. Use HA scheduling of the validated climate command instead. |
| Driving statistics | App declares `/driving-statistics/api/v1.0/driving/getSummaryInfo` and `getDetailInfo`, with `dateType`, `localDate`, `vin`. Response models describe distance, trip count, trip time and speeds. Required date enumeration and regional availability remain unverified; no claimed working endpoint or consumption feed. |

HTTP 404 is evidence about the tested regional route, not proof that the vehicle
hardware can never support the feature. No other gateway was guessed or scanned.

The live status still supplied the same 48 numeric signals. Power-state and
fast/slow-charge items occur in the capability tree but usable extra measurements
were not present in this response. No traction-pack current/voltage, state of
health, cell temperatures or 12 V voltage was found.

`vehicleBasicsInfo.config` contains saved climate temperature/runtime, seat levels,
demister runtimes, blower/power settings and cabin-cleaning metadata. Some saved
values remained enabled while live status showed those functions off. These are
preferences, not current cabin temperature, live fan speed or active demisters.

The app's seat command has separate front-side fields and the capability tree
advertises three heating/ventilation levels for both front seats. Individual-side
behaviour on this right-hand-drive car has not been physically checked; both-seat
tests cannot prove the side mapping. V0.3.0 therefore adds per-command level and
runtime to existing both-front-seat controls without releasing an unverified
driver-only button. Window opening, sunroof, battery heating, away-mode control,
GPS changes and warning-alarm suppression remain outside the released controls.

Validation: 32 synthetic client/HA tests passed in HA Python 3.14, including strict
parameter validation, single-entity targeting, unchanged saved options, requested
seat-level feedback and history redaction. No new physical comfort test has been
claimed. A cloud timeout/authentication interruption occurred during the session;
reads later recovered. The private reserve controller's recovery for a completed
Stop with an unchanged sleeping-car timestamp is tested separately.
