# Benchmarks

The v0.1 reference is C-MAPSS FD001 using the official last-observation
protocol. See the [independent verification of cb1136e](verification-cb1136e.md)
for measured results and reproduction commands, and the
[dataset/protocol note](../docs/cmapss-fd001.md) for source, hashes, and licensing.

Synthetic fixtures exercise the pipeline and audit; their scores are not
real-equipment benchmarks. The tiny synthetic panel is deliberately degenerate.

SCANIA Component X and other censored fleet benchmarks are deferred beyond v0.1.

The [NASA physical-battery integration check](nasa-battery-smoke.md) exercises
the generic input path with actual sensor measurements and an explicit EOL
rule. It is a small manual smoke check, not an official performance benchmark.

The [NASA physical-milling integration check](nasa-milling-smoke.md) uses
recorded current, vibration, and acoustic-emission traces with a declared
observed-wear event. Its 15 completed cases and two-case held-out splits test a
different equipment shape, but remain too small for a performance claim.
