# V0.2.0

- Add extended telemetry, opt-in vehicle controls, a native lock and optional location tracking.
- Correct ANZ climate Stop and ORA seat payloads using supervised verification.
- Require vehicle-state feedback after command completion; refresh and retry once only after an explicit authentication rejection.
- Label the horn as a loud alarm and disable its entities by default.

# Changelog

## V0.1.1 ? 2026-09-12

- Fix charging-button setup by avoiding Home Assistant's read-only `enabled` property.
- Add runtime coverage for constructing and pressing both charging buttons.
- Validate all 11 tests against the Home Assistant runtime.

## V0.1.0 ? 2026-09-12

- Initial experimental ORA 5 ANZ account setup, telemetry and direct charging controls.
