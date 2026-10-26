# Real product Unit Web validation

This directory contains selected passing records. The historical R3 record set
contains 27 case reports: 25 PASS, Limit FAIL and RGB FAIL. The later R4
lifecycle record set contains RGB PASS and Limit QMP-startup FAIL. Their original
reports and evidence ZIPs remain in internal working evidence; the compact
[attempt summary](attempt-summary.json) binds every original case-report hash
and preserves all failures. These record sets combine split runner invocations;
the original aggregate files contain 24 and 1 entries respectively and were
not rewritten. This collection does not establish one all-PASS 27-case run.


Each selected `<unit>/report.json` binds one independently created visible
CoreS3 Device Service session, firmware SHA, live PID/executable SHA, original
pre-stop evidence ZIP, guest/controller result, and real product browser record.
Sessions request the ZIP before stop and retain history with `purge=0`.
The runtime in these records is the frozen QEMU binary
`1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d`.

`browser/<session>/web-report.json` records real HTTP POST/GET responses, input
gestures, actual DOM output and the corresponding product readback, mounted
component states, and the screenshot taken before evidence download. Inputs
use real form controls, browser touch contacts and a real mouse double-click;
the test does not inject values by evaluating API calls or replacing product
functions. Output-only Units are also checked through the product's polling
and rendered output. `tool-sources/` preserves exact executed test tools;
`artifact_sha256` and `SHA256SUMS` bind the associated files.

Earlier direct-PID receipts with null worker fields independently verify the
PID, executable hash and firmware only. Their original method text overstated
generation confirmation; no generation sample is claimed for those receipts.
Worker generation can instead be read from each immutable ZIP. Later tool
snapshots read and reconfirm the API's nested `worker` object. Historical
receipts and hashed ZIPs are retained without modification.

Controller functionality and shell presentation remain distinct. Existing
button/LED component mappings are checked against runtime readback. Raw fields,
missing component kinds, and unconfirmed axis, switch, LED-location or
count-to-angle bindings remain panel presentation. Fan activity does not
establish RPM or a mechanical model. These are virtual-device results;
physical hardware, RF, mechanical, optical, acoustic and electrical equivalence
are not established.

An IR report with `firmware_flavor=custom-guest-ir-callback-root-patch` applies
only to that explicitly modified generated guest wrapper. Its report preserves
original driver, patch and patched-driver hashes. It does not close the
original published wrapper's callback/GC limitation.

The earlier incomplete CardKB browser timing/observer attempts remain in
internal working evidence. Their ZIPs and failures were preserved; passing
results use independently created sessions. No firmware or ROM binaries are
included here.
