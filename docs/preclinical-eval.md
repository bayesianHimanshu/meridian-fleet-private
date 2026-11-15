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
at the end (`scripts/tox_stress.py`). It tests the specification above, written by
the same author as the agent: agreement shows the code does what the rules say, not that
the rules are what a toxicologist would decide.

**The real study.** The agent runs once on MRD-101-TOX-01 in a Substrate sandbox on kind;
every finding is listed next to the signals its reviewer's guide says were built in
(docs/preclinical-data.md).

## Results

Run on 15 Nov 2026, preclinical.tox_study_monitor 1.0.0, nothing above changed. Scorecards:
`data/evals/preclinical/{null,dev,holdout}.json` (git-ignored); ground truth:
`data/ground_truth/preclinical/PRE-*.json`. Re-running each set gives the same files byte
for byte.

**A process slip, said plainly.** While writing the agent, I ran the stress specs once as a
smoke test (before the formal run below), which the protocol says not to do. It showed the
same two differences as the formal run. No rule or threshold was changed in response;
the formal run is the one reported.

### Null cuts (20 permutations): targets missed

| | Target | Result |
|---|---:|---:|
| Effect findings per null cut, mean | at most 6 | **9.2** (2 to 15) |
| dose_related_* per null cut, mean | at most 3 | **7.7** |
| Null cuts with more than 12 | none | **5 of 20** (13, 13, 13, 15, 15) |

Of the 184 effect findings over the 20 cuts, **134 are dose_related_incidence** on rare
lesions (MI 84, MA 35, CL 15 across all checks). Cause: two affected animals out of 40
that land, by chance, both in the top dose group give a Cochran-Armitage z of 1.95
(p = 0.026, normal approximation) and meet the 2-animal, 20-point excess; the exact chance
of that arrangement is about 0.058. The asymptotic trend test is anti-conservative for
sparse counts, and there are many rare lesions. Continuous endpoints contribute 2.4 a
cut. Data-quality findings (8 to 12 a cut) are reported apart.

### Planted effects (dev 10 copies, holdout 10 copies, once each)

| Effect (main study) | Target | Dev | Holdout |
|---|---:|---:|---:|
| ALT up, males / females | 90% | 100% / 100% | 90% / 100% |
| AST up, males / females | 90% | 100% / 100% | 100% / 100% |
| ALT and AST with mid and high flagged (M ALT, M AST, F ALT, F AST) | 80% | 50, 60, 100, 70% | 60, 70, 100, 70% |
| Body weight gain down, males / females | 90% | **20% / 10%** | **0% / 10%** |
| Liver weight up, males / females | 90% | 90% / **10%** | 90% / **0%** |
| Hepatocellular hypertrophy, males / females | 90% | 100% / 100% | 100% / 100% |
| Single-animal creatinine outlier raised | 0 copies | **0** | **0** |
| Findings on unplanted endpoints, mean per copy | at most 6 | 7.8 (max 14) | 8.0 (max 22) |

Met: ALT, AST, hypertrophy, male liver weight, the outlier. Missed: body weight gain,
female liver weight, mid and high flagged together, false positives. Why the misses, from
the ground truth's achieved values (`achieved` in each FaultRecord, dev): high-dose gain
changed by -10% to -39% in males and +6% to -56% in females, female liver weight by -6% to
+66%, because a permuted copy of this study carries the study's own strong effects as
noise (in some copies the real high-dose animals land in the control group). In permuted copies the CV of body
weight gain is 20% to 61% and of female liver weight 17% to 43% per group, against 28%
and 14% in the real control groups, so a 25% to 30% change at 10 animals often misses
Dunnett's 5%. The evaluation design (planting on a permutation of a study with large real
effects) is the main cause, not a fault in the planting.

### Stress set (13 cases, run once): 11 as ideal

`scripts/tox_stress.py`, actuals written into each fixture under `1.0.0`.

| Case | Ideal | 1.0.0 |
|---|---|---|
| clean_controls | nothing | as ideal |
| dose_related_both_sexes | ALT dose-related, M and F | as ideal |
| one_sex_only | AST, F only | as ideal |
| mid_dose_only | change without a trend, M and F | as ideal |
| recovery_reverses | ALT main only | **extra:** relative kidney weight, F, recovery (chance, n = 5) |
| recovery_persists | liver weight abs and rel, both phases and sexes | as ideal |
| early_death | nothing | as ideal |
| deaths_rise_with_dose | mortality dose-related, M and F | as ideal |
| missing_control_values | data quality: too few control ALT, M | as ideal |
| unit_change_in_lb | data quality: GLUC unit | **extra:** body weight, M (chance, no trend) |
| single_animal_outlier | nothing | as ideal |
| small_but_significant | nothing | as ideal |
| hypertrophy_incidence | dose-related incidence, M and F | as ideal |

It tests the specification: the cases and the agent have one author.

### The real study, in a Substrate sandbox on kind

One run on MRD-101-TOX-01 (SendStudyLoaded seq 19601), template
`preclinical-39e5e8f82643-m384`, gVisor, 6.3 s, 0 failed; 133 findings (PRE-0001 to
PRE-0133, seq 19602 to 19735), the drafts identical to an in-process run (drafts sha256
`c6c93308...`). By rule: dose_related_change 78 (main 46, recovery 32), dose_related_incidence
35 (26, 9), pairwise_change 11 (5, 6), data quality 9 (too few control values: GGT and
urine protein, which are mostly non-numeric, and two recovery lung findings). 54 of the
effect findings are organ weights, 27 in each phase: at 200 mg/kg body weight is 18% to 19%
lower, so organ weights relative to body weight rise across organs.

Next to the reviewer's guide's built-in signals (docs/preclinical-data.md), main study:

| Reviewer's guide | The agent (main study) |
|---|---|
| Body weight and gain lower in groups 3 and 4 | Group 4 only: body weight -18% M, -19% F; gain -49% M, -58% F, dose-related. Group 3: -2% / +2%, not flagged |
| AST, ALT, ALP higher in group 4 | AST dose-related, M at 200 (+41%), F at 20 and 200 (+30%, +56%); ALP dose-related M, F at 200 (+28%, +52%); ALT dose-related F at 200 (+25%), change without a trend M at 200 (+34%, trend p 0.034) |
| RBC, HGB, HCT lower in group 4 | **Not raised.** Significant trends (HCT and HGB p < 0.03) but -3% to -9%, below the 10% haematology magnitude |
| Liver weights higher in group 4 | Females: absolute +90%, relative +131%, dose-related. Males: absolute -1% (no change in the data); relative +21% flagged at 200 but trend p 0.011 and Dunnett p above 0.01, **not raised** |
| Liver findings in groups 3 and 4 | Hypertrophy at 200: M 6/10, F 9/10; enlarged liver (MA) M 4/10, F 5/10; vacuolization M; necrosis F at 20 and 200 (4/10, 2/10), all dose-related. **Not raised:** necrosis M (0, 0, 4, 1; trend p 0.067), inflammation at 20 (2/10) |
| Liver tumours in group 4 | Hepatocellular adenoma M 2/10, dose-related. **Not raised:** carcinoma M 1/10 |
| Premature deaths (carcinoma) in group 4 | **Not raised:** 1 male at 200 and 1 in control (one death each) |

### What this means for the next version (not applied: 1.0.0 stays as registered)

- **Sparse incidences:** an exact (permutation) Cochran-Armitage test, or at least 3
  affected animals for dose_related_incidence, would cut most null findings; to be
  pre-registered and evaluated on fresh seeds before use.
- **Haematology magnitude:** 10% missed the guide's red-cell decrease (-4% to -9% with
  clear trends); a toxicologist reads such a coherent pattern as treatment-related.
- **Evaluation design:** plant on a permutation with the study's real effects removed (or
  on a synthetic base), so the planted-effect targets measure the agent, not the noise.

### Decisions the specification did not make

- A data-quality finding per kind of problem **and endpoint** (the stress ideals' form),
  not per domain as the text above says.
- An LB test code measured in more than one specimen (PROT in serum and urine) is one
  endpoint per specimen (`lb:PROT:URINE`).
- Incidence denominators for MA and CL are all animals of the group; for MI, the animals
  with any record for that specimen.
