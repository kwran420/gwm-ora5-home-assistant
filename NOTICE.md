# Provenance and scope

This repository contains an independently structured Home Assistant adapter for an existing GWM client dependency. Credit for that client's authentication, signing, transport and regional protocol work belongs to the contributors of `moryoav/ha-gwm-ev`, including Yoav Mor. Its original code is MIT-licensed subject to its third-party/protocol-material notice. It is installed as a dependency, not vendored here.

Direct charging payload and result behavior were studied with an authorized owner's GWM ANZ Android application (`com.gwm.oceania`, version 1.0.6, version code 27) and an authorized shared account and ORA 5. The application itself, extracted code, proprietary assets, reusable signing material and private captures are not included.

Functional observations used here:

- T5 charging instruction `0x01` uses `switchOrder` `1` for Start and `2` for Stop.
- PIN mode uses type `2` and an MD5 representation of the configured vehicle PIN over TLS. This implements the service protocol; it is not a recommended password-storage design.
- Result polling uses the submitted sequence in the query and native vehicle-request signing, even with current Flutter account authentication.
- The returned hardware-command identifier is not the submitted request sequence. The application selects a charging result by its remote type from the sequence-scoped response.

These interoperability observations do not grant rights to GWM assets or imply GWM endorsement. Upstream's production release holds remain its own unresolved conditions. No claim of production readiness is made here.
