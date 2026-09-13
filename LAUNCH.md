# Finding the first ORA 5 testers

Start with five to ten ORA 5 owners who already run Home Assistant. Seek a second
Australian car, a New Zealand account and different trims. Ask them to install,
verify telemetry and submit a compatibility report; optional supervised controls
can follow once their account works.

The [Home Assistant GWM/ORA discussion](https://community.home-assistant.io/t/integration-gwm-ora/745945)
and [r/gwmora](https://www.reddit.com/r/gwmora/) are relevant audiences. Check each
community's current rules and existing threads before posting. Local ORA owner
groups may reach more owners, but HA users are the most useful initial testers.

Include a short demonstration of fresh telemetry and one observed charging stop,
with household details and vehicle identifiers removed. Work with the upstream
GWM maintainers on shared protocol findings and credit their client prominently.
Do not advertise bundled solar optimisation or full vehicle control.

After additional-car validation, address the current [HACS inclusion requirements](https://www.hacs.xyz/docs/publish/include/),
including HACS validation, Hassfest and release checks. Custom-repository installs
are available now; default catalogue inclusion is a later review process.

## Community post draft

**ORA 5 owners in Australia/NZ: testers wanted for a Home Assistant integration**

I have been building a Home Assistant integration around my ORA 5 so I can use
its charging state and controls in my home energy automations. It connects to
the regional GWM cloud account, so a phone or USB connection is not needed after setup.

It exposes battery, range, odometer, charging, tyres, doors and comfort telemetry,
with optional charging and vehicle controls. Each owner enters their own details
in Home Assistant. A dedicated shared GWM account helps avoid displacing the phone session.

It has been tested on one Australian ORA 5 and is still experimental. I am looking
for a few other owners, including someone in New Zealand, to try installation and
report which readings work. Controls are optional. The README distinguishes
observed behaviour from features still being investigated; the household solar
controller is separate and not included in this release.

The integration uses the GWM client developed by moryoav/ha-gwm-ev. Credit for its
authentication and transport work belongs to that project's contributors.

Repository, HACS installation and testing guide:
https://github.com/kwran420/gwm-ora5-home-assistant

A report with region, trim and setup result would help, even if you only try
sensors. Please keep credentials, VINs and location out of public reports.
