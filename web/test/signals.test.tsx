import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../src/api/client";
import { renderApp } from "./render";
import { BASE, server } from "./server";

function row(term: string, over: Partial<Schemas["SignalRow"]> = {}): Schemas["SignalRow"] {
  return {
    term, reports: 50, drug_reports: 2767, term_reports: 646830, prr: 6.1, prr_low: 5.6, prr_high: 6.6,
    ror: 7.2, ror_low: 6.5, ror_high: 7.9, chi2: 2100.4, signal: true, label_listed: true,
    finding_id: "SIG-0001", status: "open", ...over,
  };
}

const VIEW: Schemas["SafetySignalsView"] = {
  study_id: "MRD-201", drug: "xanomeline (with trospium chloride, COBENFY)", status: "scanned",
  scan_id: "SCAN-20261120T030000Z", scan_seq: 19990, data_date: "2026-10-28",
  product_query: 'patient.drug.openfda.generic_name.exact:"XANOMELINE AND TROSPIUM CHLORIDE"',
  drug_reports: 2767, all_reports: 21054158, terms_with_drug: 659, tested: 250,
  signals: [row("NAUSEA"), row("GASTROOESOPHAGEAL REFLUX DISEASE", { finding_id: "SIG-0002", label_listed: false, reports: 12 })],
  not_signals: [row("HEADACHE", { signal: false, prr: 0.8, finding_id: null, status: null })],
  label_set_id: "8f0e73bf", label_version: "6", label_effective: "20260116", signals_listed: 1,
  label_most_common: [{ reaction: "nausea", signal_terms: ["NAUSEA"] }, { reaction: "dyspepsia", signal_terms: [] }],
  rule: "Evans et al. 2001: at least 3 reports, PRR at least 2, chi-squared (Yates) at least 4",
  caveats: ["There is no certainty that the reported event (adverse event or medication error) was actually due to the product."],
  caveats_source: "open.fda.gov/apis/drug/event (Disclaimer)", requests: 254,
};

describe("Safety signals", () => {
  it("shows the signals with PRR, ROR and counts, the label comparison, the data date and the caveats", async () => {
    server.use(http.get(`${BASE}/safety/signals`, () => HttpResponse.json(VIEW)));
    renderApp("/safety/signals", "karan.mehta");
    expect((await screen.findByTestId("scan-summary")).textContent).toContain("2767 reports of 21054158 in FAERS");
    expect(screen.getByText(/openFDA data date 2026-10-28/)).toBeTruthy();
    const nausea = screen.getByTestId("signal-NAUSEA");
    expect(nausea.textContent).toContain("50 of 2767");
    expect(nausea.textContent).toContain("6.10 (5.60 to 6.60)");
    expect(nausea.textContent).toContain("7.20 (6.50 to 7.90)");
    expect(nausea.textContent).toContain("listed");
    expect(within(nausea).getByRole("link", { name: "SIG-0001" })).toBeTruthy();
    expect(screen.getByTestId("signal-GASTROOESOPHAGEAL REFLUX DISEASE").textContent).toContain("not found");
    expect(screen.getByTestId("label-summary").textContent).toContain("1 of 2 signals are named in the label");
    const common = screen.getByRole("list", { name: "The label's most common adverse reactions" });
    expect(common.textContent).toContain("nausea: a signal (nausea)");
    expect(common.textContent).toContain("dyspepsia: not a signal");
    expect(screen.getByText(/There is no certainty that the reported event/)).toBeTruthy();
    expect(screen.getByText(/never an incidence and never evidence that the drug causes/)).toBeTruthy();
  });

  it("tells other roles plainly who sees it", async () => {
    server.use(http.get(`${BASE}/safety/signals`, () => HttpResponse.json({ detail: "forbidden" }, { status: 403 })));
    renderApp("/safety/signals", "asha.rao");
    expect(await screen.findByText(/shown to the medical monitor and the portfolio lead/)).toBeTruthy();
  });

  it("says when no scan has run", async () => {
    server.use(http.get(`${BASE}/safety/signals`, () => HttpResponse.json({ ...VIEW, status: "not_scanned", signals: [], not_signals: [] })));
    renderApp("/safety/signals", "rahul.iyer");
    expect((await screen.findByTestId("signals-none")).textContent).toContain("No scan of openFDA has run yet");
  });
});
