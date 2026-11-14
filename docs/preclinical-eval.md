# preclinical.tox_study_monitor: pre-registration and evaluation

Phase 5 step 1. **Everything above "Results" was committed before any agent code existed
and before the agent ran on any data** (commit of this file; `git log --follow`). The
thresholds are in `config/default.toml` `[agents.tox_study_monitor]`; changing one is a
new agent version. Background: docs/preclinical-notes.md.

## What the agent does and does not say

- It compares each dose group with the **concurrent control** of the same sex and phase,
  never with historical control data (1.0.0).
- It may say a change is **dose-related** (a significant trend and a flagged dose group)
  or a **change without a trend**. It never says "adverse", never proposes a NOAEL or a
  LOAEL: those are the toxicologist's decisions (NoaelDecision, recorded through the API).
- A record it cannot use becomes a **data-quality finding**; the run never fails on data.

## Analysis population

- **Groups** come from TX. A set is **toxicokinetic** if TKDESC is "TK" (excluded from every
  analysis); **recovery** if TX has RECOVDUR, else if its SET name contains the word
  "recovery" not preceded by "non"; the **control** is the set with TCNTRL present and dose
  0 (if a phase has more than one, the one whose TCNTRL contains "vehicle"; if still
  ambiguous, a data-quality finding and no analysis of that phase). Dose groups are ranked
  by TRTDOS within each phase: control 0, then 1, 2, 3.
- **Phases** are analysed separately: **main** (sets that are neither TK nor recovery) and
  **recovery**. Sexes are analysed separately (DM SEX).
- **Deaths:** DS DSDECOD other than TERMINAL SACRIFICE and RECOVERY SACRIFICE is an
  unscheduled death.

## Endpoints

| Endpoint | Value per animal | Class (magnitude) |
|---|---|---|
| Body weight (BW, BWTESTCD BW) | the weight at the phase's final weighing day: the most common last BW day among the phase's animals; animals without a weight that day (early deaths) are left out | body_weight (5%) |
| Body weight gain | that weight minus the animal's first weight (its earliest BWDY) | body_weight_gain (10%) |
| Clinical pathology (LB, each LBTESTCD with LBSTRESN) | the value at the phase's scheduled collection day for that test: the most common LBDY among the phase's animals; other days are unscheduled and left out | LBCAT: HEMATOLOGY 10%, COAGULATION 10%, CLINICAL CHEMISTRY 20%, URINALYSIS 25%, else 20% |
| Organ weight, absolute (OM, OMTESTCD WEIGHT, each OMSPEC) | OMSTRESN | organ_weight (10%) |
| Organ weight relative to body weight | OMSTRESN / terminal body weight (BW TERMBW) x 100 | organ_weight (10%) |
| Microscopic findings (MI, each MISPEC and MISTRESC other than NORMAL, UNREMARKABLE or empty) | affected if any record; examined if the animal has an MI record for that specimen (MISTAT not NOT DONE) | incidence |
| Macroscopic findings (MA, each MASPEC and MASTRESC other than NORMAL, UNREMARKABLE, NO VISIBLE LESIONS or empty) | affected if any record; every animal of the group is examined at necropsy | incidence |
| Clinical observations (CL, each CLCAT and CLSTRESC other than NORMAL or empty) | affected if observed on any day | incidence |
| Mortality | an unscheduled death (above) | incidence |

MI severity (MISEV: MINIMAL 1, MILD 2, MODERATE 3, MARKED 4, SEVERE 5) is reported in the
evidence per group (count per grade and mean grade of the affected animals); 1.0.0 does
not test it.

**Unusable records (data-quality findings, one per kind of problem per domain):** an LB
value whose LBSTRESU differs from the unit most of that test's values have in the study
(no conversion in 1.0.0); a numeric value with an empty unit when the test has a unit;
two values for one animal, test and day; a dose group or sex not in TX or DM; a control
with fewer than `min_per_group` (3) usable values for an endpoint (that endpoint is not
analysed in that sex and phase). NOT DONE records and qualitative results are not used and
are not reported.

## Methods (pre-registered)

**Continuous endpoints**, per endpoint, sex and phase, groups with at least 3 values:
- Group mean, SD, N, and percent difference of each dose group's mean from the control's.
- **Dunnett's test** (many-to-one against control, two-sided; `scipy.stats.dunnett`, its
  numerical integration seeded with `dunnett_seed`).
- **Jonckheere-Terpstra trend test** across control < low < mid < high (two-sided; normal
  approximation with the tie correction; Hollander and Wolfe, Nonparametric Statistical
  Methods, 3rd ed., section 6.2).
- A dose group is **flagged** when Dunnett p < 0.05 **and** |percent difference| is at least
  the class magnitude **and**, with the group's single animal farthest from the control
  mean left out, |percent difference| is still at least the magnitude (so one animal never
  makes a finding).
- **dose_related_change:** at least one flagged group, trend p < 0.01, and every flagged
  group and the trend in the same direction.
- **pairwise_change:** otherwise, a flagged group with Dunnett p < 0.01 (a change without a
  trend, for example only at the mid dose).

**Incidence endpoints**, per endpoint, sex and phase:
- Incidence (affected / examined) per group; MI severity as above.
- **Cochran-Armitage trend test** (one-sided, increase; scores = dose rank 0, 1, 2, 3;
  Agresti, Categorical Data Analysis, 2nd ed., section 5.3.5) and **Fisher's exact test**
  of each dose group against control (one-sided, increase).
- **dose_related_incidence:** trend p < 0.05 and the top dose group exceeds the control by
  at least 2 animals and at least 20 percentage points.
- **pairwise_incidence:** otherwise, a dose group with Fisher p < 0.01 that exceeds the
  control by at least 2 animals and 20 points.
- Decreases in incidence are not raised in 1.0.0.

No adjustment for the number of endpoints: each endpoint is judged on its own, as a study
report does, and the null evaluation below measures what that costs.

**Severity of a finding** (its triage weight, not adversity): dose_related_* medium,
pairwise_* low, data quality low. Each finding carries the group table (N, mean or
incidence, percent difference, p-values) as evidence, with roles and display strings.

## Evaluation (targets stated before running)

All evaluation copies are made from the curated study (MRD-101-TOX-01, TOX-FINAL), run in
process through the same agent code (`meridian preclinical eval`), and never recorded in
the ledger: no evaluation finding can reach a reviewer's queue.

**Null cuts.** 20 copies (seeds 1 to 20), each with the group labels (SETCD, ARMCD) of the
main-phase animals permuted among the main-phase animals of the same sex, and the same
within the recovery phase; TK animals untouched. No true effect remains. Data-quality
findings (which depend on the records, not the groups) are reported apart.
- **Target:** at most 6 effect findings per null cut on average, at most 3 of them
  dose_related_*, and no null cut with more than 12.

**Planted effects.** Copies of a null cut (seeded permutation as above, then liver
hypertrophy records reset to NORMAL), with, in the main phase of both sexes:
- ALT and AST x 1.5 at the mid dose and x 2.5 at the high dose;
- body weight gain at the high dose reduced by 30% (the final-day weight lowered so that
  gain falls by 30%; the lower final weight may also be flagged and is not a false
  positive);
- liver weight x 1.10 at the mid dose and x 1.25 at the high dose (absolute; the relative
  weight follows);
- liver hepatocellular hypertrophy (MI LIVER, HYPERTROPHY, MINIMAL or MILD) in 0, 0, 3 and
  8 animals of 10 per group;
- one high-dose male's creatinine (CREAT) set to 5 times the median of its group: a
  single-animal outlier that **must not** become a finding.

Ground truth per copy in the format of data/ground_truth (GroundTruth, one FaultRecord
per effect and sex). Sets: **dev** 10 copies (seeds 101 to 110), **holdout** 10 copies
(seeds 201 to 210); holdout is run once, after dev, with nothing changed between.
- **Targets:** each planted effect found (the right endpoint, sex, phase and direction, as
  dose_related_* or pairwise_*) in at least 90% of copies of each set, ALT and AST with
  both the mid and high dose flagged in at least 80%; the outlier raised in 0 copies;
  findings on endpoints nothing was planted in at most the null target.

**Stress set.** 13 hand-written cases in tests/fixtures/tox_stress (each a study spec and
its ideal findings), committed with this file, before the agent code: effect in one sex
only, effect only at the mid dose, recovery groups present (effect reversing and
persisting), an animal that died early, deaths rising with dose, missing control values, a
unit change within LB, a single-animal outlier, a small but significant change, liver
hypertrophy incidence, a dose-related change in both sexes, and clean controls. Run once,
at the end (`meridian preclinical stress`). It tests the specification above, written by
the same author as the agent: agreement shows the code does what the rules say, not that
the rules are what a toxicologist would decide.

**The real study.** The agent runs once on MRD-101-TOX-01 in a Substrate sandbox on kind;
every finding is listed next to the signals its reviewer's guide says were built in
(docs/preclinical-data.md).

## Results

(Filled in after the runs; nothing above changes.)
