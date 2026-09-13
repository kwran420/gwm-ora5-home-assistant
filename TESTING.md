# Trying the ORA 5 integration

This is experimental and currently checked on one Australian ORA 5. The next
useful milestone is five independent installations, including a New Zealand account.

1. Install using the README's HACS link or custom-repository instructions.
   Select the experimental prerelease in HACS's download/version options if needed.
2. Use your own dedicated GWM account with your car shared from the owner account.
   Compare battery, range, odometer, cable and lock state with the car. Sleeping
   vehicles can report older telemetry.
3. Start with sensors. If you choose to test a control, keep the car parked,
   observe it directly and try one action at a time. Record actual behaviour and
   whether HA feedback agreed. Testing the alarm, boot or windows is unnecessary.
4. Check that phone-app use and HA polling coexist on separate accounts. Report
   session interruptions, delayed results and recovery after vehicle sleep.
5. Submit a compatibility report with region, model year/trim, app version,
   integration version and HA version. State which features you did not test.

Use the [compatibility form](https://github.com/kwran420/gwm-ora5-home-assistant/issues/new?template=compatibility.yml)
for results and the [bug form](https://github.com/kwran420/gwm-ora5-home-assistant/issues/new?template=bug.yml)
for reproducible problems. Never upload account details, verification codes, PINs,
tokens, VINs, registration plates, location, network captures or HA configuration
files. Review diagnostics before sharing them.

The optional Raw status signals entity exposes unmapped numeric fields. Describe
a field ID and an observed transition with identifying information removed. An
unknown number is not automatically a fault or an available control.

The household solar/reserve controller is separate and is not included here.
