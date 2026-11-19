# portfolio.safety_signal_scout: pre-registration and results

Phase 5 step 3a. **Everything above "Results" was committed before the agent's code and
before any disproportionality was computed** (`git log --follow` on this file).

**What was seen before, said now:** to find the query terms I ran count queries by hand
(below): the generic and brand names, the totals, and the drug's top four reaction terms
by count (nausea 593, vomiting 439, constipation 202, off label use 195). No PRR, ROR or
chi-squared was computed, and no other term was looked at, before this file was committed.

## What it says and does not say

It reports **signals of disproportionate reporting** in FDA's adverse event reporting
system (FAERS), through openFDA, for the drug studied in MRD-201: xanomeline, marketed in
the US with trospium chloride (COBENFY). A signal says a reaction term is reported with
the drug more often, relative to all its reports, than with all other drugs. It is never
an incidence, a rate or a causal claim; every finding carries FAERS's own caveats as
evidence. The medical monitor decides each one.

## Data and queries (openFDA drug adverse event endpoint)

- **Product:** `patient.drug.openfda.generic_name.exact:"XANOMELINE AND TROSPIUM CHLORIDE"`.
  Found by count queries on 20 Nov 2026 (data date `meta.last_updated` 2026-10-28):
  `patient.drug.openfda.generic_name:xanomeline` counted by `generic_name.exact` gives one
  xanomeline term, `XANOMELINE AND TROSPIUM CHLORIDE`, in 2,767 reports; the same reports
  by `brand_name.exact` are `COBENFY`. Left out: reports that name the product only in the
  free-text `medicinalproduct` field (`TROSPIUM CHLORIDE\XANOMELINE TARTRATE` 75,
  `TROSPIUM CHLORIDE\XANOMELINE` 27; some may also carry the harmonised name). Any role of
  the drug in the report (suspect, concomitant, interacting) counts, as openFDA counts it.
- **Report totals** come from `count=fulfillexpeditecriteria`, summed: the one field found
  on every report (2,767 of 2,767 for the drug; 21,054,158 in all of FAERS, against
  21,044,294 for `serious` and 17,860,952 for `reporttype`, which some reports lack).
- **Queries, count queries only, no API key:**
  1. the drug's reaction terms: `search=<product>&count=patient.reaction.reactionmeddrapt.exact&limit=999`
     (999 is the largest limit openFDA accepts without a key; the drug has 659 terms);
  2. the drug's reports: `search=<product>&count=fulfillexpeditecriteria`;
  3. all reports: `count=fulfillexpeditecriteria`;
  4. for each term with at least 3 reports with the drug, all its reports:
     `search=patient.reaction.reactionmeddrapt.exact:"<term>"&count=fulfillexpeditecriteria`.
  About 250 term queries plus 3; openFDA's limits without a key are 240 requests a minute
  and 1,000 a day per IP address; the agent waits 0.3 s between requests and stops at 900.
- **The label:** `drug/label.json?search=openfda.generic_name.exact:"XANOMELINE AND
  TROSPIUM CHLORIDE"&limit=1` (a search query on the label endpoint).

## Method (pre-registered)

For each reaction term R with the drug D, the 2 x 2 table of reports:
a = D and R (query 1), b = D without R (query 2 minus a), c = R without D (query 4 minus
a), d = neither (query 3 minus a, b and c).

- **PRR** = [a / (a + b)] / [c / (c + d)]; 95% CI exp(ln PRR +- 1.96 SE), SE =
  sqrt(1/a - 1/(a+b) + 1/c - 1/(c+d)).
- **ROR** = (a d) / (b c); 95% CI exp(ln ROR +- 1.96 SE), SE = sqrt(1/a + 1/b + 1/c + 1/d).
- **Chi-squared**, 1 degree of freedom, with Yates's continuity correction:
  N (|a d - b c| - N/2)^2 / ((a+b)(c+d)(a+c)(b+d)).
- **Signal of disproportionate reporting:** a >= 3 **and** PRR >= 2 **and** chi-squared
  >= 4. Source: Evans SJ, Waller PC, Davis S. Use of proportional reporting ratios (PRRs)
  for signal generation from spontaneous adverse drug reaction reports. Pharmacoepidemiol
  Drug Saf 2001;10(6):483-6, doi:10.1002/pds.677, whose abstract states "as minimum
  criteria for a signal, 3 or more cases, PRR at least 2, chi-squared of at least 4". The
  abstract does not say which chi-squared; Yates's correction is chosen here (it is the
  smaller value, so the stricter rule). The ROR and the CIs are reported, not used in the
  rule; van Puijenbroek EP et al., Pharmacoepidemiol Drug Saf 2002;11(1):3-10,
  doi:10.1002/pds.668, compares these measures ("ROR - 1.96 SE", "PRR - 1.96 SE").
- Every term is reported as openFDA codes it (MedDRA preferred terms), including terms
  about use rather than harm (for example OFF LABEL USE): no term is excluded.
- One finding per signal, check `reporting_signal:<term>`, severity low, visible to the
  medical monitor and the portfolio lead, decided by the medical monitor. A newer scan
  supersedes the same term's finding of an older one; a term no longer a signal is
  retired.

## The label comparison (an evaluation not written by us)

The US label (COBENFY, from the label endpoint) was written by the sponsor and FDA, not by
this project. For each signal, the term is looked for in the label's adverse reactions,
warnings and precautions and boxed warning text: **listed** when the term, lower-cased,
appears as a phrase in that text (lower-cased, punctuation as spaces); else **not found**.
No synonyms and no MedDRA hierarchy: "GASTROOESOPHAGEAL REFLUX DISEASE" is not found in a
label that says "gastrointestinal reflux disease". Reported both ways: the share of
signals listed, and the label's most common adverse reactions (section 6, "incidence >= 5%
and at least twice placebo") with whether each is a signal. As they are; no target.

## FAERS caveats (quoted from open.fda.gov/apis/drug/event, as evidence on every finding)

- "There is no certainty that the reported event (adverse event or medication error) was
  actually due to the product."
- "FDA does not require that a causal relationship between a product and event be proven"
- "FDA does not receive reports for every adverse event or medication error that occurs
  with a product."
- "Many factors can influence whether or not an event will be reported"
- "The information in these reports has not been scientifically or otherwise verified as
  to a cause and effect relationship and cannot be used to estimate the incidence of these
  events."

## Reproducibility

Live data changes. Each run records, on its ActorWoke, every query with the sha256 of its
response body and openFDA's `meta.last_updated`; the responses are kept as the run's
inputs (`var/signals/<trigger seq>/signal/openfda_responses.parquet`), and a rerun on them
(`meridian signals replay`) must give identical drafts.

## Results
