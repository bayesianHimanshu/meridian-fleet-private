import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../src/api/client";
import { renderApp } from "./render";
import { BASE, finding, server } from "./server";

const STUDY = "MRD-101-TOX-01";

const study: Schemas["PreclinicalStudy"] = {
  study_id: STUDY,
  asset_id: "MRD-101",
  cut_id: "TOX-FINAL",
  loaded_seq: 19601,
  title: "13-Week Repeat Dose Toxicity Study on MRD-101 in Rats",
  species: "RAT",
  strain: "SPRAGUE-DAWLEY",
  route: "ORAL GAVAGE",
  duration: "P13W",
  dose_unit: "mg/kg",
  groups: [
    { setcd: "1", phase: "main", dose: 0, control: true, males: 10, females: 10 },
    { setcd: "2", phase: "main", dose: 2, control: false, males: 10, females: 10 },
    { setcd: "3", phase: "main", dose: 20, control: false, males: 10, females: 10 },
    { setcd: "4", phase: "main", dose: 200, control: false, males: 10, females: 10 },
  ],
};

function group(rank: number, dose: number, over: Partial<Schemas["EndpointGroupView"]> = {}): Schemas["EndpointGroupView"] {
  return { rank, dose, n: 10, mean: 40, sd: 5, percent_vs_control: rank ? 0 : null, p: rank ? 0.5 : null, affected: null, grades: [], flagged: false, ...over };
}

const endpoints: Schemas["PreclinicalEndpoints"] = {
  study_id: STUDY,
  cut_id: "TOX-FINAL",
  dose_unit: "mg/kg",
  tables: [
    {
      endpoint: "lb:AST", label: "AST", kind: "continuous", unit: "U/L", sex: "M", phase: "main",
      groups: [group(0, 0), group(1, 2), group(2, 20, { mean: 48, percent_vs_control: 20 }),
        group(3, 200, { mean: 56.4, percent_vs_control: 41, p: 0.0001, flagged: true })],
      trend_p: 3.4e-7, check: "dose_related_change", finding_id: "PRE-0007",
    },
    {
      endpoint: "lb:GLUC", label: "GLUC", kind: "continuous", unit: "mg/dL", sex: "M", phase: "main",
      groups: [group(0, 0), group(1, 2), group(2, 20), group(3, 200)],
      trend_p: 0.6, check: null, finding_id: null,
    },
    {
      endpoint: "mi:LIVER:HYPERTROPHY", label: "Liver: hypertrophy (microscopic)", kind: "incidence", unit: "", sex: "F", phase: "main",
      groups: [group(0, 0, { affected: 0, mean: null }), group(1, 2, { affected: 0, mean: null }), group(2, 20, { affected: 0, mean: null }),
        group(3, 200, { affected: 9, mean: null, grades: [{ grade: 2, animals: 9 }], flagged: true, p: 0.0001 })],
      trend_p: 2e-6, check: "dose_related_incidence", finding_id: "PRE-0040",
    },
  ],
  by_dose: [{ phase: "main", dose: 200, dose_related: ["PRE-0007", "PRE-0040"], without_trend: [] }],
};

function decision(over: Partial<Schemas["NoaelDecisionView"]> = {}): Schemas["NoaelDecisionView"] {
  return {
    seq: 19800, recorded_at: "2026-11-15T10:00:00Z", decision_id: "NOAEL-0123456789ab", study_id: STUDY,
    sex: "combined", established: true, noael_dose: 20, loael_dose: 200, dose_unit: "mg/kg",
    finding_ids: ["PRE-0007"], rationale: "Hepatocellular hypertrophy and AST rise at 200 only.",
    decided_by: "leela.nair", supersedes: null, superseded_by: null, current: true, ...over,
  };
}

function history(current: Schemas["NoaelDecisionView"][], may_record: boolean): Schemas["NoaelHistory"] {
  return { study_id: STUDY, dose_unit: "mg/kg", doses: [0, 2, 20, 200], current, history: current, may_record };
}

function preclinical(noael: Schemas["NoaelHistory"]) {
  server.use(
    http.get(`${BASE}/preclinical/studies`, () => HttpResponse.json([study])),
    http.get(`${BASE}/preclinical/${STUDY}/endpoints`, () => HttpResponse.json(endpoints)),
    http.get(`${BASE}/preclinical/${STUDY}/noael`, () => HttpResponse.json(noael)),
    http.get(`${BASE}/findings`, () =>
      HttpResponse.json({
        items: [
          finding("PRE-0007", { study_id: STUDY, agent_id: "preclinical.tox_study_monitor", title: "AST higher with dose in males, main study" }),
          finding("PRE-0040", { study_id: STUDY, agent_id: "preclinical.tox_study_monitor", title: "Liver: hypertrophy more frequent with dose in females" }),
        ],
        total: 2, limit: 500, offset: 0,
      }),
    ),
  );
}

describe("Preclinical page", () => {
  it("is a live menu item and shows the design, the flagged endpoints and what flags each dose", async () => {
    preclinical(history([], true));
    renderApp("/preclinical", "leela.nair");
    expect(await screen.findByRole("heading", { name: "Preclinical" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Preclinical" })).toBeTruthy();
    const design = await screen.findByRole("table", { name: /Dose groups/ });
    expect(within(design).getAllByRole("row")).toHaveLength(5);
    const table = await screen.findByRole("table", { name: /group mean or incidence per dose/ });
    const rows = within(table).getAllByRole("row");
    expect(rows.map((r) => r.textContent).join("|")).toContain("AST");
    expect(rows.some((r) => r.textContent.includes("GLUC"))).toBe(false); // only flagged by default
    expect(within(table).getByText(/\(flagged\)/)).toBeTruthy();
    expect(within(table).getByRole("link", { name: "PRE-0007" })).toBeTruthy();
    const support = screen.getByLabelText("Findings per dose group");
    expect(within(support).getByText("200 mg/kg")).toBeTruthy();
    expect(within(support).getByText(/It is not a NOAEL/)).toBeTruthy();
  });

  it("switches sex and shows incidence with severity grades", async () => {
    preclinical(history([], false));
    const user = userEvent.setup();
    renderApp("/preclinical", "rahul.iyer");
    await screen.findByRole("table", { name: /group mean or incidence per dose/ });
    await user.selectOptions(screen.getByLabelText("Sex"), "F");
    const table = screen.getByRole("table", { name: /group mean or incidence per dose/ });
    expect(within(table).getByText("9/10")).toBeTruthy();
    expect(within(table).getByText("mild 9")).toBeTruthy();
  });

  it("shows 'not yet decided' and no form to a role that may not record", async () => {
    preclinical(history([], false));
    renderApp("/preclinical", "rahul.iyer");
    expect(await screen.findByTestId("noael-none")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Record a NOAEL decision" })).toBeNull();
  });

  it("lets the toxicologist record a NOAEL, sending the doses, findings and rationale", async () => {
    preclinical(history([], true));
    let posted: unknown = null;
    let postedRole: string | null = null;
    server.use(
      http.post(`${BASE}/preclinical/${STUDY}/noael`, async ({ request }) => {
        posted = await request.json();
        postedRole = request.headers.get("X-Meridian-Role");
        return HttpResponse.json(decision(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/preclinical", "leela.nair");
    const form = await screen.findByRole("form", { name: "Record a NOAEL decision" });
    await user.selectOptions(within(form).getByLabelText("NOAEL"), "20");
    await user.selectOptions(within(form).getByLabelText("LOAEL"), "200");
    await user.click(await within(form).findByRole("checkbox", { name: /PRE-0007/ }));
    await user.click(within(form).getByRole("button", { name: "Record the decision" }));
    expect(await within(form).findByRole("alert")).toBeTruthy(); // the rationale is required
    await user.type(within(form).getByLabelText("Rationale (required)"), "AST rise and hypertrophy at 200 only.");
    await user.click(within(form).getByRole("button", { name: "Record the decision" }));
    expect(await screen.findByTestId("noael-recorded")).toBeTruthy();
    expect(posted).toEqual({
      sex: "combined", established: true, noael_dose: 20, loael_dose: 200, finding_ids: ["PRE-0007"],
      rationale: "AST rise and hypertrophy at 200 only.", supersedes: null,
    });
    expect(postedRole).toBe("toxicologist");
  });

  it("revises the current decision by naming it, and shows the QA auditor a way to observe it", async () => {
    preclinical(history([decision()], true));
    renderApp("/preclinical", "leela.nair");
    expect(await screen.findByTestId("noael-current")).toBeTruthy();
    expect(screen.getByText(/NOAEL 20 mg\/kg, LOAEL 200 mg\/kg/)).toBeTruthy();
    expect(screen.getByText(/This revises/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Raise an observation" })).toBeNull();
  });

  it("offers the QA auditor an observation on the current decision", async () => {
    preclinical(history([decision()], false));
    renderApp("/preclinical", "nina.fernandes");
    const current = await screen.findByTestId("noael-current");
    expect(within(current).getByRole("button", { name: "Raise an observation" })).toBeTruthy();
  });

  it("tells a clinical role plainly that it does not see preclinical studies", async () => {
    server.use(
      http.get(`${BASE}/preclinical/studies`, () => HttpResponse.json({ detail: "forbidden" }, { status: 403 })),
    );
    renderApp("/preclinical", "asha.rao");
    expect(await screen.findByText(/Your role does not see preclinical studies/)).toBeTruthy();
  });
});

describe("Portfolio NOAEL field", () => {
  function portfolio(live: Schemas["AssetLive"]): Schemas["Portfolio"] {
    return {
      assets: [{
        asset_id: "MRD-101",
        static: { title: "MRD-101", stage: "preclinical", indication: "Fibrosis", intervention: "Oral ALK5 inhibitor",
          milestone: "IND submission", milestone_due: "Q2 2027", progress_percent: 72, probability_of_success: null,
          status: { level: "warning", text: "Dog study in-life" } },
        live,
      }],
    };
  }

  it("shows the current NOAEL as a live field", async () => {
    server.use(http.get(`${BASE}/portfolio`, () => HttpResponse.json(portfolio({
      open_findings: 3, noael_status: "decided",
      noael: [{ decision_id: "NOAEL-0123456789ab", sex: "combined", established: true, noael_dose: 20, dose_unit: "mg/kg",
        recorded_at: "2026-11-15T10:00:00Z", decided_by: "leela.nair" }],
    }))));
    renderApp("/portfolio", "rahul.iyer");
    const field = await screen.findByTestId("noael-field");
    expect(field.textContent).toContain("NOAEL: 20 mg/kg (both sexes)");
  });

  it("says not yet decided, or not shown to the role", async () => {
    server.use(http.get(`${BASE}/portfolio`, () => HttpResponse.json(portfolio({ open_findings: 0, noael_status: "not_shown", noael: [] }))));
    renderApp("/portfolio", "asha.rao");
    expect((await screen.findByTestId("noael-field")).textContent).toContain("not shown to your role");
  });
});
