# preclinical.translational_bridge: pre-registration and results

Phase 5 step 3a. **Everything above "Results" was committed before any code of the agent
existed** (`git log --follow` on this file): the mapping
(config/translational_monitoring.toml), the rules below and the stress set with its ideals.

## What it does and does not say

The phase 3 design planned this agent on the local model. It is deterministic instead:
mapping a target organ to standard clinical monitoring is a rule with sources, not a
judgement a small model should make. It proposes how MRD-101's first-in-human study
should monitor the organs the toxicology NOAEL rests on, and shows the safety margins. It
never decides: the medical monitor accepts, escalates or dismisses the recommendation. It
never adds a rule its mapping does not cite; an organ with no mapping entry is reported
as unmapped, not guessed.

## Trigger and inputs

- **Trigger:** for each SEND study, the latest of: a NoaelDecision, or a HumanDecision that
  accepts a dose proposal (a finding of preclinical.dose_translation). One run on that
  event; an earlier event already followed by a later one is never run alone.
- **Inputs**, written by the host (agents never read the ledger) next to the NOAEL extract
  in /stage/noael, and the SEND study (its design):
  - `noael_decisions`: the study's NOAEL decisions up to the trigger (as for
    dose_translation);
  - `bridge_findings`: every finding cited by a current decision: id, check, title, and
    the decisions that cite it;
  - `bridge_proposal`: the current dose proposal (the newest of the study), if any: id,
    seq, status (open, accepted, escalated, dismissed), who decided it, starting dose,
    MRSD, body weight, the decision it rests on.

## Rules (pre-registered)

1. **Current decisions** as dose_translation reads them (nothing supersedes them). None:
   no finding.
2. **Basis** (for the margins): the combined current decision if recorded, else the most
   sensitive sex's ("not established" first, then the lower NOAEL; equal: males), as
   dose_translation.
3. **Adverse findings:** the union of the findings cited by every current decision (both
   sexes and combined), each once.
4. **Target organ:** each finding's check (for example
   `dose_related_incidence:mi:HEART:INFLAMMATION:M:main`) is matched against each mapping
   entry's prefixes, both as written and without its first part (the rule name); the first
   entry in the mapping's order that matches is the organ. No match: **unmapped**,
   reported with its id and title.
5. **One item per mapped organ**, in the mapping's order: what to measure, the frequency,
   what prompts review, what prompts stopping (each as written in the mapping), the
   sources with section and quote, and the findings it rests on.
6. **Safety margins** (FDA 2005, the same conversion factor and citation as
   dose_translation, read from `[agents.dose_translation]`): for the basis decision, the
   NOAEL and the LOAEL (when given) as human equivalent doses in mg/kg (dose / divisor)
   and in mg for the proposal's body weight (60 kg), and each one's ratio to the planned
   starting dose (the current proposal's). No current proposal with a starting dose: the
   HEDs are given, the ratios are not ("no starting dose").
7. **The proposal's status** is stated: accepted (and by whom), or open, escalated or
   dismissed. A recommendation is made in every case; it says when the starting dose it
   uses is not accepted.
8. **Output:** one MonitoringRecommendation finding for MRD-101's first-in-human study,
   check `monitoring:<basis decision>:<proposal id or none>`, severity medium. Visible to the
   medical monitor, the toxicologist, the portfolio lead and the QA auditor; decided by the
   medical monitor only. The newest recommendation of a study supersedes the older ones
   (as dose proposals).

## Expected on MRD-101 (stated before the agent exists)

Current decisions seq 19941 to 19943 (M, F, combined; NOAEL 2, LOAEL 20 mg/kg/day); basis
the combined one. Cited findings: PRE-0155 and PRE-0196 (heart inflammation), PRE-0198
(liver necrosis), PRE-0165 (AST), PRE-0210 and PRE-0214 (liver vacuolization at recovery).
So two items: **liver** (PRE-0165, PRE-0198, PRE-0210, PRE-0214) and **heart** (PRE-0155,
PRE-0196); nothing unmapped. Margins against 1.94 mg (PRE-0232, accepted by karan.mehta,
seq 19966): NOAEL HED 0.323 mg/kg, 19.4 mg, **10 x**; LOAEL HED 3.23 mg/kg, 194 mg,
**100 x**.

## Stress set (hand-written, committed with this file)

`tests/fixtures/bridge_stress/*.json`: 10 cases, each the staged inputs (decisions,
findings, proposal) and the ideal under `ideal["1.0.0"]`: whether a finding is raised, the
organs with their finding ids, the unmapped ids, and the two ratios (null when there is no
starting dose or no LOAEL). Run once, at the end (`scripts/bridge_stress.py`). It tests the
specification above, by the same author as the agent: agreement shows the code does what
the rules say, not that the monitoring is what a clinical pharmacologist would choose.

| Case | Inputs | Ideal |
|---|---|---|
| liver_only | combined NOAEL 2, LOAEL 20; liver necrosis, AST | liver; 10 x, 100 x |
| heart_only | combined; heart inflammation M and F | heart |
| no_adverse_finding | NOAEL 200, no LOAEL, nothing cited | no organ; NOAEL 10 x, no LOAEL margin |
| unmapped_organ | adrenal vacuolization and liver necrosis | liver; adrenal unmapped |
| revised_noael | a liver decision revised to one resting on the heart | heart only |
| not_established | not established, LOAEL 2, ALT; no proposal | liver; no ratios |
| kidney_haem_bw | creatinine, haemoglobin, body weight | kidney, haematology, body weight |
| sexes_differ | M rests on heart, F on liver, no combined | heart and liver; basis F (lower NOAEL) |
| death_unmapped | an unscheduled death and liver necrosis | liver; the death unmapped |
| proposal_open | as liver_only, the proposal open | liver; margins against the proposed dose |

## Sources

Read in full for this step (PDFs not committed; first 16 hex of each sha256). Every quote
in the mapping was checked against the text of its document, whitespace normalised (the
CTCAE table rows against a raw text extraction, the layout one interleaves columns).

| Document | sha256 |
|---|---|
| FDA, Drug-Induced Liver Injury: Premarketing Clinical Evaluation, July 2009 (fda.gov/media/116737) | `81ca15230303336a` |
| ICH E14, FDA guidance, October 2005 (fda.gov/media/71372) | `d42d1ce641e0a03e` |
| FDA, Toxicity Grading Scale for Healthy Adult and Adolescent Volunteers Enrolled in Preventive Vaccine Clinical Trials, September 2007 (fda.gov/media/73679) | `45824ac8f20a2eb8` |
| NCI CTCAE v5.0, November 27, 2017 (dctd.cancer.gov) | `759783e37fdf8d23` |

**Limits of the sources, said now.** The liver entry is the only one whose source gives a
monitoring frequency and stopping rules for drug development. ICH E14 is about QT
prolongation, not myocardial injury; troponin is cited only through CTCAE's grade
definitions. The 2007 grading scale was written for vaccine trials in healthy volunteers.
CTCAE grades adverse events; it does not say when to measure or stop. Where a source
sets no frequency or stopping rule, the entry says so.

## Results

Run on 20 Nov 2026, preclinical.translational_bridge 1.0.0 at commit `43b2816`; the
pre-registration (`e34b1ff`) unchanged.

### Stress set (10 cases, run once): 10 as ideal

`scripts/bridge_stress.py`, each case through the host's extract writer and the agent;
actuals in each fixture under `actual["1.0.0"]`.

| Case | Ideal | 1.0.0 |
|---|---|---|
| liver_only | liver; 10 x, 100 x | as ideal |
| heart_only | heart; 10 x, 100 x | as ideal |
| no_adverse_finding | no organ; 10 x, no LOAEL margin | as ideal |
| unmapped_organ | liver; adrenal unmapped | as ideal |
| revised_noael | heart only | as ideal |
| not_established | liver; no ratios | as ideal |
| kidney_haem_bw | kidney, haematology, body weight | as ideal |
| sexes_differ | liver and heart; basis F | as ideal |
| death_unmapped | liver; the death unmapped | as ideal |
| proposal_open | liver; margins against the proposed dose | as ideal |

**Said plainly:** before the formal run, a unit test ran the pre-registered expectation for
MRD-101 (liver and heart, 10 x and 100 x) through the same code; it matched.

**A rule the pre-registration did not settle, and how it was settled before the formal
run:** *which* proposal is current. A NOAEL decision always comes before the proposal
derived from it, so a proposal read "as of the trigger" can never be the one resting on
that decision, and could be a stale one resting on a revised decision. The host therefore
takes the study's newest proposal whose basis is a current decision, as the ledger stands
when it writes the extract, with its latest status. Found by a unit test
(`test_an_open_proposal_is_said_to_be_not_accepted`), fixed before any stress case ran;
`test_a_proposal_on_a_revised_noael_is_not_used` covers the stale case.
