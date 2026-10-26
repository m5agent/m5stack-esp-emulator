# Encoder / 8Encoder binding research — 2026-10-26

Status: **OPEN**, proposed tracker **UNIT-HOST-29**. This archive is read-only research. It neither changes production bindings nor establishes virtual-device or hardware PASS.

Concrete blocker: the controller arrays are logical/electrical LED indices, whereas the fixed visual models name physical light locations. Official diagrams prove the electrical chain, and official photos prove the physical CH/aperture layout, but no inspected source connects the two. Encoder `led0/led1` are front-left/front-right, not verified LED1/LED2. 8Encoder `rgb-1..9` are CH1..8/switch positions, not verified U1..U9 chain indices. Applying an identity permutation to asymmetric colors would guess hardware.

Physical rotation also remains open. Encoder product text says 30 pulses/revolution while the bundled UIFlow example draws a full circle using 58 returned counts. 8Encoder source provides signed A/B-edge counting but not the installed part's pulses/revolution, physical direction or zero. Its guest can write/reset counter registers without physically moving a knob, so an unconditional absolute `angle=count*scale` is not proven.

Uniform LED colors are mathematically independent of the unknown permutation: any bijection maps `[c,...,c]` to the same per-location color `c`. This permits a separately scoped uniform/all-off rendering rule in principle. Nonuniform mapping and physical rotation remain unachieved. This block makes no implementation change.

`findings.json` contains known facts, manually inspected image conclusions and explicit closure criteria. `sources.json` freezes fetched official source URL, commit where applicable, byte count and SHA256. Public diagrams/photos are retained by provenance/hash only. Necessary text extracts preserve source paths, line numbers and full-source hashes. The Encoder public firmware tree proves `.hex` plus documents only; no `.hex`, ROM or firmware binary is archived. `local-source-hashes.json` freezes the matching vendor model and existing driver inputs. The bundled UIFlow example is labelled as a local official-doc snapshot rather than a newly fetched upstream file.

Hardware, firmware execution and browser binding validation: **NOT RUN** in this research.
