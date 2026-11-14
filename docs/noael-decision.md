# The NOAEL is a person's decision (phase 5 step 1)

preclinical.tox_study_monitor reports what changed with dose. It never says "adverse" and
never proposes a NOAEL or a LOAEL (docs/preclinical-notes.md says why). The NOAEL is
recorded by the toxicologist as a `NoaelDecision` event, through the Fleet API only.

## The event

`POST /api/v1/preclinical/{study}/noael`, toxicologist only (403 for every other role):

- **study**, and **sex**: `M`, `F` or `combined`; each has its own current decision;
- **established** and the **NOAEL dose**, or "not established" (no dose);
- the **LOAEL dose**, if any, above the NOAEL;
- the **findings it rests on**: finding ids that must exist, be visible to the
  toxicologist, and be findings of that study (404 or 422 otherwise); a LOAEL needs at
  least one;
- a **rationale** of at least 20 characters (required);
- **supersedes**: the decision it revises.

Doses must be the study's own dose levels (from TX), in its unit. Append-only: a revised
NOAEL is a new decision that names the current one in `supersedes`; a new decision for a
sex that already has one, or one naming a decision that is no longer current, is refused
(409). Both decisions stay in the ledger; the page shows the current one and the history.

## Who sees it

The toxicologist, the portfolio lead and the QA auditor (the roles the agent's findings
reach, `[agents.tox_study_monitor] visible_to`). For every other role the ledger shows a
NOAEL decision, a SEND study load and a preclinical run as redacted (type and hash only),
the preclinical pages answer 403, and the portfolio shows MRD-101's NOAEL as "not shown".

## Why the self-decision rule does not block it, and what checks it instead

Elsewhere, a person may not decide a finding they raised or one about their own actions
(meridian.api.visibility.self_decision). Here the toxicologist both decides the findings
(treatment-related or not, adverse or not) and sets the NOAEL that rests on them. That is
how toxicology works: the study director and toxicologist own the interpretation, and the
NOAEL is their judgement on their own assessment of the findings. Splitting the two
between people would not match practice, and the NOAEL is not a finding, so the rule does
not apply to it.

The independent check is the **QA auditor**, who sees every NOAEL decision and may raise a
quality observation on it (`POST /api/v1/quality/observations` with its `ledger_seq`).
That observation:
- names the toxicologist as the actor under review, so the toxicologist may not decide it;
- reaches the preclinical roles only (the toxicologist sees it; no clinical role does);
- is decided by the portfolio lead (qa_auditor never decides).
