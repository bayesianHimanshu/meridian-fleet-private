# Stage-gate evidence pack and pipeline outlook (phase 5 step 3b)

Written before either agent's code. portfolio.pipeline_intelligence and
portfolio.stage_gate_pack are deterministic, read only what the portfolio lead may see,
and never decide: the outlook is information, and the pack states each criterion's
evidence. The portfolio lead records the gate decision.

## The input: facts, built as the portfolio lead

The host builds one table, `portfolio_facts`, through the Fleet API's Repository acting as
the portfolio lead (rahul.iyer's role; meridian.api.visibility), so it holds only what
that role sees. Columns: asset_id, group, key, label, value, status, severity, seq,
finding_id, number, static. Every live fact carries the ledger seq it rests on; static
facts (config/portfolio.toml) carry none and are marked static. No subject id, no
unblinded value and no finding hidden from the portfolio lead can enter: the builder never
reads the ledger itself, only Repository views, and a test plants all three in a ledger and
checks the staged table.

| Group | One row per | status |
|---|---|---|
| noael | current NOAEL decision (sex) | established, not_established |
| starting_dose | the current dose proposal | its decision: open, accepted, dismissed, escalated |
| ind_readiness | asset with an assessed inventory | assessed (number: percent met) |
| ind_gap | current IND readiness finding | its decision |
| monitoring | the current monitoring recommendation | its decision |
| open_finding | current finding the portfolio lead sees, high, medium or low | its decision (closed ones are left out) |
| sae_recon | the latest operational SAE reconciliation | number: mismatches |
| qtl | MRD-201 | not_shown (the portfolio lead may not see RBQM data) |
| signal_scan, priority_signal | the asset's latest scan; each priority signal | scanned; its decision |
| static | each static field of an asset without live data | static |

MRD-201's QTL status is not shown to the portfolio lead (RBQM site metrics and QTL
findings are not visible to that role), so the outlook says so rather than widen what the
role sees.

## The gate criteria (config/gates.toml)

| Criterion | Basis | Met when |
|---|---|---|
| noael_decided | 21 CFR 312.23(a)(8)(ii)(a); FDA 2005 IV | at least one noael row |
| starting_dose_accepted | 21 CFR 312.23(a)(6)(iii)(e) | the starting_dose row is accepted |
| ind_gaps_resolved | 21 CFR 312.23(a)(8); ind_requirements.toml | an ind_readiness row, and no ind_gap open or escalated |
| monitoring_accepted | 21 CFR 312.23(a)(6)(iii)(g) | the monitoring row is accepted |
| no_open_high_preclinical | policy | no open_finding of severity high that is open or escalated |
| safety_signals_reviewed | policy; only with a scan | no priority_signal open (escalated counts as reviewed) |

Not applicable only by its rule (`applies`): a criterion that applies and has no evidence
is not met, never not applicable. Open items: one per thing that stops a criterion (each
open gap, each open high finding, each open signal; one for a missing decision or a
missing row). The pack lists the seqs of every row it used. It has no overall verdict.

The decision: GateDecision, by the portfolio lead only, through the API: go, conditional
go (at least one condition) or no-go, with a rationale of at least 20 characters, naming the
pack it rests on. The QA auditor may raise an observation on it, as on any ledger event.

## Stress set (tests/fixtures/gate_stress, 10 cases)

Written with these ideals before the agent's code and run once. A specification test: the
cases and the agent have the same author.

## The outlook (portfolio.pipeline_intelligence)

Per asset: the facts; the risks; a status; the changes since the previous outlook.

Risks, each with its seqs: no NOAEL decision (high); an open or escalated high finding
(high, one per finding); the dose proposal not accepted (medium); IND readiness gaps open
(medium, one risk naming their count); the monitoring recommendation not accepted
(medium); SAE reconciliation mismatches above 0 (high); open priority safety signals
(medium, one risk naming their count). Top risks: high before medium, then by seq, at
most 5. Status: at_risk with any high risk, attention with any medium, else on_track; an
asset with only static facts is `static` (its static status text is shown as written).

Changes: against the facts of the previous outlook, by (asset, key): new facts, facts
whose value or status changed (old to new), and facts gone. The first outlook says it is
the first.

Trigger: PortfolioReviewRequested, from the portfolio lead through the API, or monthly by
`meridian portfolio review-due`, which records one for the month when none exists yet
(requested_by system.schedule, recorded by the operator who runs it; run from cron by the
operator, not installed by this project).

The cloud narrator's optional summary is not built in this step (see the step summary).
