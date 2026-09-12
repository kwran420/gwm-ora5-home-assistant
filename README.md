# GWM ORA 5 for Home Assistant

Experimental Home Assistant integration for the **GWM ORA 5 in Australia and New Zealand**, using the regional GWM cloud account. Each installation uses its owner's credentials. A phone or USB connection is not needed after setup.

## What works

- GWM account login, email verification and shared-vehicle discovery.
- Battery percentage, range, cable connection and charging status.
- Opt-in direct Start and Stop charging buttons, with result polling.
- Serialized commands, a persistent command journal, and no automatic write retries.
- Diagnostics that exclude credentials, PINs, tokens, vehicle identifiers and location.

**Validation status:** Login, telemetry and a bounded Start ? Stop cycle were verified on one Australian ORA 5. Both commands returned completion; cloud telemetry changed to charging after Start and non-charging after Stop, with an accompanying household power increase during charging. This is a single-vehicle test, not broad reliability validation. New Zealand has not been live-tested. Unattended solar control is not included or validated. Cloud control cannot guarantee an immediate stop during an outage.

## Install

Requires Home Assistant 2026.1 or newer. This is a custom integration, not an official GWM product.

1. In HACS, add this repository as a custom repository of type **Integration**, then download it. Alternatively, copy `custom_components/gwm_ora5` into Home Assistant's `config/custom_components` directory.
2. Restart Home Assistant.
3. Add **GWM ORA 5** under **Settings → Devices & services → Add integration**.
4. Select AU or NZ and enter your own GWM account and password. Enter the email verification code in Home Assistant when requested.
5. For charging controls, first set a six-digit vehicle PIN in the GWM app under **Car settings → PIN**. Enter it in the integration and explicitly enable experimental charging commands.

Use a dedicated GWM account and share your ORA 5 with it from your owner account. GWM can displace another session using the same account. Keep your phone signed into the owner account, and let Home Assistant use the dedicated one. Configure the vehicle PIN on the dedicated account before signing it into Home Assistant to reduce repeated verification.

Account details, PIN and tokens are stored in Home Assistant's private configuration/storage. Protect Home Assistant backups as you would other credentials; this integration does not provide separate encryption of Home Assistant storage. No credentials are included in this repository. Reconfigure the integration to change credentials or the command opt-in.

## Charging semantics

The buttons send direct commands; they do not change or clear charging schedules. The charging binary sensor reflects cloud telemetry, not an optimistic button state. `Command status` reports cloud command completion separately from charging telemetry.

A timed-out request may still execute. The integration journals the attempt before sending and does not resend it. Pending results are polled without repeating the command. A new Start is blocked while an earlier result is unresolved; an explicit Stop remains available.

## Solar and home-battery coordination

The general integration exposes vehicle controls and telemetry. Site-specific solar forecasts, battery reserves, household history and electricity tariffs are **not hard-coded** into it. A forecast-based overnight-reserve controller is being developed separately. This release does not install energy automations or promise zero grid import.

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
