# GWM ORA 5 for Home Assistant

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/gwm_ora5/brand/dark_logo.png">
  <img src="custom_components/gwm_ora5/brand/logo.png" alt="ORA" width="240">
</picture>

Experimental Home Assistant integration for the **GWM ORA 5 in Australia and New Zealand**, using the regional GWM cloud account. Each installation uses its owner's credentials. A phone or USB connection is not needed after setup.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kwran420&repository=gwm-ora5-home-assistant&category=integration)

**Early testers wanted.** Start with [the testing guide](TESTING.md), then share a
[compatibility report](https://github.com/kwran420/gwm-ora5-home-assistant/issues/new?template=compatibility.yml).
Reports from additional Australian vehicles and New Zealand owners will help
establish which features work across accounts and trims. This project is available
as a HACS custom repository; it is not in the default HACS catalogue.

## What works

- GWM account login, email verification and shared-vehicle discovery.
- Battery, range, odometer, charging time, four tyre pressures/temperatures, doors, windows, locks, seats and climate status.
- Optional raw numeric status signals and GPS tracking (disabled by default).
- Opt-in direct Start and Stop charging buttons, with result polling.
- Opt-in climate, front-seat heating/ventilation, demisters, steering-wheel heating, boot and light/alarm controls; a native lock entity supports secure voice-assistant exposure.
- Serialized commands, a persistent journal, result polling and vehicle-state confirmation. Explicit authentication rejection permits one refresh/retry; ambiguous writes are never automatically resent.
- Per-command climate temperature, comfort runtime and front-seat level through `gwm_ora5.start_comfort`, without changing account options or reconnecting.
- Optional remote-command history summary, including provider result codes, with identifiers and command payloads excluded.
- Diagnostics that exclude credentials, PINs, tokens, vehicle identifiers and location.

**Validation status:** Supervised tests on one Australian ORA 5 verified charging, climate, lock/unlock, front-seat heat/ventilation, steering-wheel heat, front/rear demisters, boot open/close and light/alarm commands. State-changing commands were checked against telemetry; the observer confirmed boot closure and that the horn command is a loud alarm. Cabin-air refresh started and stopped in telemetry. Window-closing motion remains unverified. Schedule writes were accepted but not confirmed in readback; no schedule was left enabled. See [the capability investigation](RESEARCH.md). New Zealand and other trims have not been live-tested. Cloud control cannot guarantee an immediate stop during an outage.

## Install

Requires Home Assistant 2026.1 or newer. This is a custom integration, not an official GWM product.

1. In HACS, add this repository as a custom repository of type **Integration**, then download it. Alternatively, copy `custom_components/gwm_ora5` into Home Assistant's `config/custom_components` directory.
2. Restart Home Assistant.
3. Add **GWM ORA 5** under **Settings → Devices & services → Add integration**.
4. Select AU or NZ and enter your own GWM account and password. Enter the email verification code in Home Assistant when requested.
5. For charging controls, first set a six-digit vehicle PIN in the GWM app under **Car settings → PIN**. Enter it in the integration and explicitly enable experimental charging commands.

Use a dedicated GWM account and share your ORA 5 with it from your owner account. GWM can displace another session using the same account. Keep your phone signed into the owner account, and let Home Assistant use the dedicated one. Configure the vehicle PIN on the dedicated account before signing it into Home Assistant to reduce repeated verification.

Account details, PIN and tokens are stored in Home Assistant's private configuration/storage. Protect Home Assistant backups as you would other credentials; this integration does not provide separate encryption of Home Assistant storage. No credentials are included in this repository. Reconfigure the integration to change credentials or charging permission. Use **Configure** for the separate vehicle-controls opt-in, climate temperature, runtime and front-seat level. No new login is needed for these options. Alarm, boot-open, raw-signal and location entities are disabled by default; enable individually if wanted.

## Raw status signals

Enable **Raw status signals** on the device's entity page to inspect fields that
do not yet have a dedicated sensor. Its state is a **count**, such as `47 signals`.
Open the entity's attributes to see each seven-digit field ID and its numeric
value, plus `signal_labels` and `unmapped_codes`. New numeric fields appear
automatically. Unknown meanings remain explicitly unmapped.

Counts can change when the cloud omits a field. Estimated charging time, for
example, was present in a 48-field reading and absent in a later 47-field reading.
An absent or nonnumeric field is not treated as zero. Raw values use different
enumerations; `1` does not universally mean on or a fault. These cloud fields are
not OBD PID numbers. GPS coordinates remain on the separate opt-in tracker.

## Charging semantics

The buttons send direct commands; they do not change or clear charging schedules. The charging binary sensor reflects cloud telemetry, not an optimistic button state. `Command status` remains `awaiting_feedback` until the requested vehicle state is observed. Alarm/light pulses have no persistent state to verify, so their status represents cloud completion only.

A timed-out request may still execute. The integration journals the attempt before sending and does not resend it. Pending results are polled without repeating the command. A new Start is blocked while an earlier result is unresolved; an explicit Stop remains available.

## Solar and home-battery coordination

The general integration exposes vehicle controls and telemetry. Site-specific solar forecasts, battery reserves, household history and electricity tariffs are **not hard-coded** into it. A private forecast-based overnight-reserve controller is maintained separately. This release does not install energy automations or promise zero grid import.

## Comfort settings in automations

Use **GWM ORA 5: Start comfort with settings** in Home Assistant's action editor.
Target exactly one enabled comfort start button. Climate accepts `temperature`
(16–32 °C) and `duration` (5–30 minutes); front-seat heating/ventilation accepts
`level` (1–3) and `duration`; steering heat and demisters accept `duration`.
Omitted values use integration options. The normal Stop buttons remain available.

```yaml
action: gwm_ora5.start_comfort
target:
  entity_id: button.gwm_ora_5_start_climate
data:
  temperature: 24
  duration: 10
```

Entity names can differ between installations. This action does not expose raw
commands, alarm controls or unsupported hardware. Seat commands currently apply
to both front seats; independent-side mapping still needs physical verification.
Feedback confirms climate activation, not a measured cabin temperature or achieved
setpoint. Seat feedback must match the requested level on both seats.

Enable **Last recorded remote command** in the entity registry for optional cloud
history. It polls at most every 15 minutes and shows only the latest timestamp,
instruction, provider result code and total record count. It is supplementary
diagnostic history, not the command journal or proof of physical completion.
**Command status** now includes the last integration action and expected charging
state, allowing consumers to distinguish a confirmed Stop from unrelated commands.

## Dependency and release status

Authentication and protocol transport use [moryoav/ha-gwm-ev](https://github.com/moryoav/ha-gwm-ev), pinned to an exact source commit in the manifest. Its client distribution is development-stage and carries a [protocol-material notice and production release holds](https://github.com/moryoav/ha-gwm-ev/blob/6a910ca71a68807b6f60ac0a664f00a9c6d1fe41/THIRD_PARTY_NOTICES.md). Those conditions are not resolved by this project. This is an experimental adapter, not a production release of that client. The upstream source archive must remain accessible for installation.

This repository does not redistribute APKs, decompiled source, certificates, private keys or OEM signing constants. See [NOTICE.md](NOTICE.md) for provenance and dependency information.

## Development

Install the manifest's pinned `gwm-client` dependency into Python 3.13 or newer, then run:

```sh
python -m unittest discover -s tests -v
python -m compileall -q custom_components tests
```

Report the app version, region, HA version and a sanitized description. Never post passwords, verification codes, PINs, tokens, VINs, raw captures or Home Assistant configuration files.

## Google Home

Expose the native ORA door-lock entity through Home Assistant's Google Assistant integration. Voice unlocking requires its secure-device PIN configuration. This is separate from the GWM PIN stored by this integration. Google Home exposure is not configured automatically. See [Home Assistant instructions](https://www.home-assistant.io/integrations/google_assistant).
