# Candidate 0032: wakeable host poll

`0032-wasm-wakeable-host-poll.patch` is registered in the 75-patch source lock
as a candidate experiment after independent replay from the 74-patch source.
That registration permits a reproducible candidate build; it does not grant
guest/browser admission or promotion. The source patch uses standard U3
context and preserves native poll branches.

The existing WASM wait re-polls SDK descriptors after a bounded host sleep.
SDK3.1.50 sleeps on a private dummy futex, so a QEMU notifier pipe write cannot
finish that sleep early. The candidate wakes a separate shared host epoch only
after the original `event_notifier_set` write succeeds or reports EAGAIN.
`qemu_poll_ns` snapshots the epoch before real `g_poll`, then compare-waits;
it never converts a notification into a fabricated readiness result.

The fallback remains bounded for JS-only descriptors and epoch ABA/wrap.
Main-runtime waits retain a 1 ms queue-service bound. Cancellation and queued
calls are serviced before waiting, and a finite deadline is recomputed after
queue processing. The option `M5SW_POLL_WAKE=0`, frozen by `pthread_once`,
permits a same-binary legacy-wait control; the candidate defaults to the new
host synchronization behavior. Option initialization happens only in poll;
the low-level notifier always uses atomic increment/wake and performs no
`pthread_once`, getenv lookup or blocking initialization. Its small notification
cost is common to both A/B modes. This option is not a new browser profile.

Source and host contracts do not establish QEMU/firmware performance,
application readiness or browser Worker cleanup. The pinned SDK probe retains
original/candidate cancellation failures independently from passing positive
readiness controls. See the [probe and scope](../../tests/browser-qemu/poll_wake/README.md).
Before publication or promotion, repeat an actual affected browser guest with the same
firmware, clock/controller path, UART/input and QMP quit/Worker cleanup evidence.
