# Phase 5 summary: preclinical to portfolio

Phase 5 took the fleet from MRD-201's clinical data to MRD-101's toxicology, its first
human dose and the portfolio. It ran from ledger seq 19601 (the SEND study loaded) to
seq 20140. As before, every agent is deterministic and runs sandboxed; people decide,
through the Fleet API, under their own identity.

## What was built

| Step | Built | Ledger |
|---|---|---|
| 1 | SEND ingest of a GLP 13-week rat study (MRD-101-TOX-01, instem's public sample, pinned by sha256) | SendStudyLoaded 19601 |
| 1 | preclinical.tox_study_monitor 1.0.0 (Dunnett, trend tests, pre-registered) | 133 findings |
| 1 | 1.1.0: control-only evaluation base, small-count statistics, deaths and neoplasms as rules | 98 findings, seq 19828 to 19925 |
| 1 | The NOAEL as the toxicologist's decision (NoaelDecision), never the agent's | 17 decisions, 19927 to 19943 |
| 2 | The NOAEL form's rules enforced in the API; preclinical.dose_translation (FDA 2005 MRSD) | PRE-0232, accepted at 19966 |
| 2 | preclinical.ind_readiness against ICH M3(R2), S7A, S7B, S2(R1) | inventory 19956; 4 gaps, PRE-0233 to 0236 |
| 3a | preclinical.translational_bridge: target organs to cited Phase 1 monitoring, margins | PRE-0237, accepted at 20067 |
| 3a | portfolio.safety_signal_scout 1.0.0: openFDA FAERS for xanomeline with trospium | scan 19985, 76 findings |
| 3b | Attribution: operator identities, AttributionCorrection, audit reviewer 1.3.0 | correction 20068; QA-0178 |
| 3b | Signal scout 1.0.1: retry, context, triage | scan 20105, 9 findings |
| 3b | portfolio.pipeline_intelligence 1.0.0: a PortfolioOutlook event per review | review 20137, outlook 20139 |
| 3b | portfolio.stage_gate_pack 1.0.0: an evidence pack per gate request; GateDecision by the portfolio lead | none recorded yet |

New zones: preclinical (SEND, NOAEL extract, inventory; Substrate), portfolio_signal
(egress to two openFDA paths only; OpenShell) and portfolio (facts built as the portfolio
lead; Substrate). Each policy is rendered, proved against its boundary and passed
conformance. The preclinical leak check passed on kind (20 runs, canary in no store).

## Evaluations, misses included

- **tox_study_monitor 1.0.0** missed its null targets: 9.2 effect findings per null cut
  against at most 6. It also missed planted effects: female liver weight found in 10% and
  0% of copies against a 90% target. The cause was the evaluation design, a permuted
  study carrying its own strong effects. 13-case stress set: 11 as ideal.
- **tox_study_monitor 1.1.0** came close on its null targets but missed them: 5.95 per
  cut against 5, and 3 cuts above 10. Holdout misses: male body weight gain 60% (target
  80%), female liver weight 60% (90%), female HGB 70% (80%). On the real study it raised
  98 findings against an expected 50 to 90 (missed). 16-case stress set: 13 as ideal.
- **ind_readiness**: 12 of 12 stress cases as ideal; 40 generated faults, each raising
  exactly its finding.
- **translational_bridge**: 10 of 10 stress cases; the real run gave the pre-registered
  result.
- **safety_signal_scout 1.0.0**: 19 of 76 signals named in the US label; 5 of the label's
  10 most common reactions were signals. 4 terms went untested (throttled).
  **1.0.1**: all 250 terms tested and 78 signals; triage left 9 priority signals, exactly
  the 9 pre-registered. The medical monitor's queue went from 76 to 9.
- **audit_trail_reviewer 1.3.0**: 20 of 20 stress cases (2 new, written after the check's
  code). On the real ledger it flagged seq 19985 and nothing else.
- **stage_gate_pack**: 10 of 10 stress cases.
- **Said plainly**: every stress set is a specification test by the same author as its
  agent. The tox 1.0.0 stress specs were smoke-run once before their formal run, and two
  ind_readiness inputs were already run by unit tests before their formal run.

## Human decisions recorded in phase 5, and by whom

| Person (role) | Decisions |
|---|---|
| Dr. Leela Nair (toxicologist) | 17 NoaelDecisions (19927 to 19943) and 3 dismissals of tox findings (19944 to 19946) |
| Dr. Karan Mehta (medical monitor) | PRE-0232 dose proposal accepted as provisional (19966); PRE-0237 monitoring plan accepted (20067) |

Of the 17 NOAEL decisions, **14 were superseded**: one sex or combined decided, then
revised, as the form's rules were found wanting in step 1 (for example "not established"
recorded without its LOAEL). The 3 current ones (19941 to 19943) are 2 mg/kg/day for males,
females and combined. Step 2 moved those rules into the API, so the form can no longer be
bypassed.

**The attribution correction.** Seq 19985, the first signal scan, records
`requested_by: karan.mehta`. Claude Code had started it from the CLI with `--by
karan.mehta`; Dr. Mehta did not. The event stays as recorded (the ledger is
append-only). AttributionCorrection seq 20068, by operator:himanshu, records what is
true. The CLI now records only operator ids. The audit reviewer's new check raised
QA-0178 on that event, with the correction as evidence.

No gate request or gate decision is recorded: both are the portfolio lead's to make,
through the Command Center.

## Gaps

- No narrator for the outlook: the optional plain-language summary was not built.
- The portfolio lead cannot see RBQM or QTL data, so the outlook shows MRD-201's QTL status
  as "not shown". Widening that role was not ours to decide.
- "Came through the API" is judged from the record: an event type the API writes, with
  the person as the event's actor. The ledger has no channel field, and redacted rows
  are not judged.
- The signal scout's retry was never needed live; it is tested only on a fake. The scout
  queries one product term and leaves out reports naming the drug only in free text.
- The dose translation uses the FDA 2005 default safety factor of 10; no PAD or MABEL.
- MRD-101's first-in-human design (single and multiple ascending doses, 14 days) is an
  assumption; nothing records it.
- The monthly review needs a cron line that the operator installs.
- The outlook and pack repeat every open finding the portfolio lead sees (about 80 tox
  findings for MRD-101). They are complete, but long.

## Lessons

1. **Identity is data.** One `--by` flag put a person's name on an event they never
   touched, and an append-only ledger keeps it for good. Treat identity as a type with
   rules (operator, agent, person), and enforce the rules where events are written.
2. **Pre-register what can be checked, and say when you looked.** Lists chosen after
   seeing the data (the triage terms) are stated as such. The 9 priority signals matched
   because the rule was fixed before the rerun, not because it was blind.
3. **A queue is a product.** 76 FAERS signals became 9 to review once tiers and
   context were added; the other 69 are still on view, each with its reason.
4. **Who sees what decides what an agent may know.** Building the portfolio input as the
   portfolio lead made the outlook's blind spots visible (QTL) instead of leaking around
   them.
5. **Agents report and people decide.** The gate pack lists evidence and open items and
   stops there; the go, conditional go or no-go is the portfolio lead's.
6. **Evaluation design can be the bug.** tox 1.0.0's misses came from planting effects
   on a permuted study that already carried strong ones.
