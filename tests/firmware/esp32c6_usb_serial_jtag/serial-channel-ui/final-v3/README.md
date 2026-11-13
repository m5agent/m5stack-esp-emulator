# Final-v3 NanoC6 serial-channel page validation

The [bounded summary](summary.json) records a **new, independent original
Honeypot session** on native runtime
`80d92a6c6c68137a7813b8b7c519725aac350258078d9b244098eaabf82f63bf`
and Device Service source
`4a5d28e6d4764ec78c0621aed0e0527080597486`.
The original BIN remains
`4184ffc6b56f1742a926845d782f3b65c37246490cc6d3e1bfa067bff7b0c381`.
All 2,178 served tool/page source files matched the pinned Git object and the
previously tested `10c826b8` tool/page bytes. This is a new runtime result;
[the earlier 8df page record](../README.md) remains separate.

## Result

The owner observed the guest for 90.012 seconds of host monotonic time,
without application input, an HMP observer, or a launch wrapper. The actual
native process used the production plain-NanoC6 USB clock policy:
`-accel tcg,thread=single -icount shift=5,align=off,sleep=off`.
The 461-byte console and 614-byte USB logs shared the same ROM/PHY prefix;
USB additionally contained the complete 153-byte, four-CRLF application
suffix with SHA-256
`957653a047aacb4f6c16b22209ba72edc5e5ae941ff7fd744992c3c297d9f3c6`.
Each channel had one ROM banner and no observed fatal marker. Both application
regions remained unchanged.

On the same running guest, Public, Sessions and Observatory each completed
`console → usb-serial-jtag → console`. Eighteen API chunks and thirteen actual
page responses matched their own channel bytes in the final evidence ZIP.
The USB application output stayed out of console, and returning to console
resumed its retained offset. All three pages passed in one browser attempt,
with zero page errors and zero mutating API requests. The browser closed
before the owner exported the ZIP and stopped the guest. An independent
visual review confirmed all nine new screenshots; only their hashes are
published. The guest, Flash, lease, native process and owned service were
released.

## Retained attempts and scope

An earlier attempt to borrow a different final-v3 guest began after its fixed
180-second owner window had ended. The initial GET received a connection
refusal before any browser was started. That attempt remains
`INFRA_FAILED`, with its page result `NOT RUN`; it is not a firmware failure.
The new run used an explicit owner/borrower completion receipt and a bounded
window. It does not overwrite that first attempt or the earlier 8df
Observatory observer failure and page-only follow-up.

The serial API and native-service page scope is **PASS**. The complete
Honeypot application remains **PARTIAL**: configuration output does not prove
AP association, HTTP service, network behavior or physical RF. PHY calibration
mismatch and PLL-calibration diagnostics remain in the logs. Browser WASM,
physical hardware, the combined runtime matrix and resident delivery require
separate evidence. No Burner submission was made.

For reproduction, use the exact source/runtime/firmware identities above and
the [same serial API and page procedure](../README.md#reproduce-the-same-path).
Before attaching the pages, require the complete 153-byte suffix; compare each
channel's chunks with its own log, export evidence before `purge=0` stop, and
verify resource release. Never substitute an old runtime's page results for
this run.
