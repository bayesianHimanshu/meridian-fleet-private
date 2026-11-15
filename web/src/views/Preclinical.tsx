import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type SyntheticEvent } from "react";
import { api, unwrap, type Schemas } from "../api/client";
import { ErrorNote, Loading, SeverityChip, StatusChip, Time, isStatus } from "../components/common";
import { RaiseObservation } from "../components/Observation";
import { FindingLink } from "../components/text";
import { useIdentity } from "../identity";
import { useApi } from "../queries";

type Study = Schemas["PreclinicalStudy"];
type Table = Schemas["EndpointTableView"];
type Group = Schemas["EndpointGroupView"];
type Decision = Schemas["NoaelDecisionView"];
type Sex = "M" | "F";
type Phase = "main" | "recovery";

const AGENT = "preclinical.tox_study_monitor";
const SEX_TEXT: Record<string, string> = { M: "Males", F: "Females", combined: "Both sexes" };
const PHASE_TEXT: Record<Phase, string> = { main: "Main study", recovery: "Recovery groups" };
const GRADE_TEXT: Record<number, string> = { 1: "minimal", 2: "mild", 3: "moderate", 4: "marked", 5: "severe" };
const CHECK_TEXT: Record<string, string> = {
  dose_related_change: "Dose-related change",
  pairwise_change: "Change without a trend",
  dose_related_incidence: "Dose-related incidence",
  pairwise_incidence: "Higher incidence without a trend",
};

function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3);
}

function pctText(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return `${v > 0 ? "+" : ""}${v.toFixed(0)}%`;
}

function pText(p: number | null | undefined): string {
  if (p === null || p === undefined) return "not tested";
  return p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`;
}

function doseText(dose: number, unit: string): string {
  return dose === 0 ? "Control" : `${String(dose)} ${unit}`;
}

export function PreclinicalView() {
  const studies = useApi(["preclinical", "studies"], () => unwrap(api.GET("/api/v1/preclinical/studies")));
  return (
    <section aria-labelledby="preclinical-title" className="stack">
      <div className="view-head">
        <div>
          <h1 id="preclinical-title">Preclinical</h1>
          <p>
            MRD-101's GLP rat study. Every dose group is compared with the concurrent control of the same sex.
            The monitor says what changed with dose; whether a change is adverse, and the NOAEL, are the
            toxicologist's decisions.
          </p>
        </div>
      </div>
      {studies.isPending ? <Loading what="the preclinical studies" /> : null}
      {studies.isError ? (
        isStatus(studies.error, 403) ? (
          <p className="message">
            Your role does not see preclinical studies. They are shown to the toxicologist, the portfolio lead
            and the QA auditor.
          </p>
        ) : (
          <ErrorNote error={studies.error} />
        )
      ) : null}
      {studies.isSuccess && studies.data.length === 0 ? (
        <p className="message">No preclinical study has been loaded.</p>
      ) : null}
      {studies.isSuccess
        ? studies.data.map((s) => (
            <div key={s.study_id} className="stack">
              <Design study={s} />
              <Endpoints study={s} />
              <Findings study={s} />
              <NoaelPanel study={s} />
            </div>
          ))
        : null}
    </section>
  );
}

function Design({ study }: { study: Study }) {
  return (
    <section className="panel" aria-labelledby="design-title">
      <div className="panel-head">
        <h2 id="design-title">Study design</h2>
        <span className="src mono">{study.study_id}</span>
      </div>
      <p>{study.title}</p>
      <p className="muted">
        {study.species.toLowerCase()} ({study.strain.toLowerCase()}), {study.route.toLowerCase()}, dosing{" "}
        {study.duration}
      </p>
      <div className="table-wrap" tabIndex={0} aria-label="Dose groups table">
        <table>
          <caption className="visually-hidden">Dose groups by phase, with the animals of each sex</caption>
          <thead>
            <tr>
              <th scope="col">Phase</th>
              <th scope="col">Group</th>
              <th scope="col">Dose</th>
              <th scope="col" className="num">
                Males
              </th>
              <th scope="col" className="num">
                Females
              </th>
            </tr>
          </thead>
          <tbody>
            {study.groups.map((g) => (
              <tr key={g.setcd}>
                <td>{PHASE_TEXT[g.phase]}</td>
                <th scope="row" className="mono">
                  {g.setcd}
                </th>
                <td>{doseText(g.dose, study.dose_unit)}</td>
                <td className="num">{g.males}</td>
                <td className="num">{g.females}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Cell({ table, group, unit }: { table: Table; group: Group; unit: string }) {
  const label = doseText(group.dose, unit);
  if (table.kind === "incidence") {
    const grades = (group.grades ?? []).map((g) => `${GRADE_TEXT[g.grade] ?? String(g.grade)} ${String(g.animals)}`);
    return (
      <td className={group.flagged ? "num flagged" : "num"} title={`${label}: ${pText(group.p)}`}>
        <span className="fig">
          {group.affected ?? 0}/{group.n}
        </span>
        {grades.length ? <div className="muted">{grades.join(", ")}</div> : null}
        {group.flagged ? <span className="visually-hidden"> (flagged)</span> : null}
      </td>
    );
  }
  return (
    <td className={group.flagged ? "num flagged" : "num"} title={`${label}: n = ${String(group.n)}, ${pText(group.p)}`}>
      <span className="fig">{num(group.mean)}</span>
      {group.rank > 0 ? <div className="muted">{pctText(group.percent_vs_control)}</div> : null}
      {group.flagged ? <span className="visually-hidden"> (flagged)</span> : null}
    </td>
  );
}

function Endpoints({ study }: { study: Study }) {
  const ids = useId();
  const [sex, setSex] = useState<Sex>("M");
  const [phase, setPhase] = useState<Phase>("main");
  const [flaggedOnly, setFlaggedOnly] = useState(true);
  const endpoints = useApi(["preclinical", study.study_id, "endpoints"], () =>
    unwrap(api.GET("/api/v1/preclinical/{study}/endpoints", { params: { path: { study: study.study_id } } })),
  );
  const doses = study.groups.filter((g) => g.phase === phase).map((g) => g.dose);
  return (
    <section className="panel" aria-labelledby="endpoints-title">
      <div className="panel-head">
        <h2 id="endpoints-title">Endpoints by sex and dose</h2>
        <span className="src">against the concurrent control</span>
      </div>
      <div className="toolbar">
        <label className="field" htmlFor={`${ids}-sex`}>
          Sex
          <select
            id={`${ids}-sex`}
            value={sex}
            onChange={(e) => {
              setSex(e.target.value as Sex);
            }}
          >
            <option value="M">Males</option>
            <option value="F">Females</option>
          </select>
        </label>
        <label className="field" htmlFor={`${ids}-phase`}>
          Phase
          <select
            id={`${ids}-phase`}
            value={phase}
            onChange={(e) => {
              setPhase(e.target.value as Phase);
            }}
          >
            <option value="main">Main study</option>
            <option value="recovery">Recovery groups</option>
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={flaggedOnly}
            onChange={(e) => {
              setFlaggedOnly(e.target.checked);
            }}
          />{" "}
          Only endpoints with a flagged group
        </label>
      </div>
      {endpoints.isPending ? <Loading what="the endpoint tables" /> : null}
      {endpoints.isError ? <ErrorNote error={endpoints.error} /> : null}
      {endpoints.isSuccess ? (
        <>
          <div className="table-wrap heat-wrap" tabIndex={0} aria-label="Endpoint table, scrolls sideways">
            <table className="heat">
              <caption className="visually-hidden">
                {SEX_TEXT[sex]}, {PHASE_TEXT[phase].toLowerCase()}: group mean or incidence per dose; flagged
                groups differ from control by the pre-registered rule
              </caption>
              <thead>
                <tr>
                  <th scope="col">Endpoint</th>
                  {doses.map((d) => (
                    <th scope="col" key={d} className="num">
                      {doseText(d, endpoints.data.dose_unit)}
                    </th>
                  ))}
                  <th scope="col">Trend</th>
                  <th scope="col">Finding</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.data.tables
                  .filter((t) => t.sex === sex && t.phase === phase)
                  .filter((t) => !flaggedOnly || t.check !== null || t.groups.some((g) => g.flagged))
                  .map((t) => (
                    <tr key={t.endpoint}>
                      <th scope="row">
                        {t.label}
                        {t.unit ? <span className="muted"> ({t.unit})</span> : null}
                      </th>
                      {doses.map((d) => {
                        const g = t.groups.find((x) => x.dose === d);
                        return g ? (
                          <Cell key={d} table={t} group={g} unit={endpoints.data.dose_unit} />
                        ) : (
                          <td key={d} className="na">
                            -
                          </td>
                        );
                      })}
                      <td>{pText(t.trend_p)}</td>
                      <td>
                        {t.finding_id ? (
                          <>
                            <FindingLink id={t.finding_id} className="mono" />
                            <div className="muted">{CHECK_TEXT[t.check ?? ""] ?? ""}</div>
                          </>
                        ) : (
                          <span className="muted">none</span>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <DoseSupport data={endpoints.data} phase={phase} />
        </>
      ) : null}
    </section>
  );
}

function DoseSupport({ data, phase }: { data: Schemas["PreclinicalEndpoints"]; phase: Phase }) {
  const rows = data.by_dose.filter((d) => d.phase === phase);
  return (
    <div className="stack" aria-label="Findings per dose group">
      <h3>What flags each dose group ({PHASE_TEXT[phase].toLowerCase()})</h3>
      <p className="muted">
        Decision support for the NOAEL: the findings that flag each dose group. It is not a NOAEL.
      </p>
      {rows.length === 0 ? <p className="muted">No dose group is flagged.</p> : null}
      <dl className="kv">
        {rows.map((d) => (
          <div key={d.dose}>
            <dt>{doseText(d.dose, data.dose_unit)}</dt>
            <dd>
              {d.dose_related.length ? (
                <>
                  {String(d.dose_related.length)} dose-related:{" "}
                  {d.dose_related.map((id, i) => (
                    <span key={id}>
                      {i ? ", " : ""}
                      <FindingLink id={id} className="mono" />
                    </span>
                  ))}
                </>
              ) : null}
              {d.without_trend.length ? (
                <span className="muted">
                  {" "}
                  ({String(d.without_trend.length)} without a trend)
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function usePreclinicalFindings(study: Study) {
  return useApi(["preclinical", study.study_id, "findings"], () =>
    unwrap(api.GET("/api/v1/findings", { params: { query: { agent: AGENT, limit: 500 } } })),
  );
}

function Findings({ study }: { study: Study }) {
  const findings = usePreclinicalFindings(study);
  const items = findings.data?.items.filter((f) => f.study_id === study.study_id) ?? [];
  return (
    <section className="panel" aria-labelledby="pre-findings-title">
      <div className="panel-head">
        <h2 id="pre-findings-title">Findings</h2>
        <span className="src">{findings.isSuccess ? `${String(items.length)} from the monitor` : ""}</span>
      </div>
      {findings.isPending ? <Loading what="the findings" /> : null}
      {findings.isError ? <ErrorNote error={findings.error} /> : null}
      <ul className="findings">
        {items.map((f) => (
          <li key={f.finding_id} className="finding">
            <div className="finding-meta">
              <FindingLink id={f.finding_id} className="mono" />
              <SeverityChip severity={f.severity} />
              <StatusChip status={f.status} />
            </div>
            <p className="headline">{f.title}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DecisionText({ d }: { d: Decision }) {
  return (
    <>
      <p>
        <strong>{SEX_TEXT[d.sex]}:</strong>{" "}
        {d.established ? `NOAEL ${String(d.noael_dose)} ${d.dose_unit}` : "NOAEL not established"}
        {d.loael_dose !== null ? `, LOAEL ${String(d.loael_dose)} ${d.dose_unit}` : ""}
      </p>
      <p>{d.rationale}</p>
      <p className="muted">
        Decided by {d.decided_by}, <Time iso={d.recorded_at} />
        {d.supersedes ? (
          <>
            ; revises <span className="mono">{d.supersedes}</span>
          </>
        ) : null}
        {d.finding_ids.length ? (
          <>
            ; rests on{" "}
            {d.finding_ids.map((id, i) => (
              <span key={id}>
                {i ? ", " : ""}
                <FindingLink id={id} className="mono" />
              </span>
            ))}
          </>
        ) : null}
      </p>
    </>
  );
}

function NoaelPanel({ study }: { study: Study }) {
  const noael = useApi(["preclinical", study.study_id, "noael"], () =>
    unwrap(api.GET("/api/v1/preclinical/{study}/noael", { params: { path: { study: study.study_id } } })),
  );
  return (
    <section className="panel" aria-labelledby="noael-title">
      <div className="panel-head">
        <h2 id="noael-title">NOAEL</h2>
        <span className="src">the toxicologist's decision</span>
      </div>
      {noael.isPending ? <Loading what="the NOAEL decisions" /> : null}
      {noael.isError ? <ErrorNote error={noael.error} /> : null}
      {noael.isSuccess ? (
        <>
          {noael.data.current.length === 0 ? (
            <p className="message" data-testid="noael-none">
              Not yet decided.
            </p>
          ) : (
            <ul className="stack" aria-label="Current decisions">
              {noael.data.current.map((d) => (
                <li key={d.decision_id} className="finding" data-testid="noael-current">
                  <DecisionText d={d} />
                  <RaiseObservation refersTo={{ ledger_seq: d.seq }} />
                </li>
              ))}
            </ul>
          )}
          {noael.data.history.some((d) => !d.current) ? (
            <details>
              <summary>Earlier decisions ({String(noael.data.history.filter((d) => !d.current).length)})</summary>
              <ul className="stack">
                {noael.data.history
                  .filter((d) => !d.current)
                  .map((d) => (
                    <li key={d.decision_id} className="finding">
                      <DecisionText d={d} />
                      <p className="muted">
                        Superseded by <span className="mono">{d.superseded_by}</span>
                      </p>
                    </li>
                  ))}
              </ul>
            </details>
          ) : null}
          {noael.data.may_record ? <NoaelForm study={study} history={noael.data} /> : null}
        </>
      ) : null}
    </section>
  );
}

function NoaelForm({ study, history }: { study: Study; history: Schemas["NoaelHistory"] }) {
  const ids = useId();
  const queryClient = useQueryClient();
  const { person } = useIdentity();
  const findings = usePreclinicalFindings(study);
  const treated = history.doses.filter((d) => d > 0);
  const [sex, setSex] = useState<"M" | "F" | "combined">("combined");
  const [established, setEstablished] = useState(true);
  const [noaelDose, setNoaelDose] = useState<string>(treated[0] === undefined ? "" : String(treated[0]));
  const [loaelDose, setLoaelDose] = useState<string>("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [rationale, setRationale] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const current = history.current.find((d) => d.sex === sex);
  const record = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/preclinical/{study}/noael", {
          params: { path: { study: study.study_id } },
          body: {
            sex,
            established,
            noael_dose: established ? Number(noaelDose) : null,
            loael_dose: loaelDose === "" ? null : Number(loaelDose),
            finding_ids: chosen,
            rationale: rationale.trim(),
            supersedes: current?.decision_id ?? null,
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [person.actor] });
    },
  });
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (rationale.trim().length < 20) {
      setLocalError("Give a rationale of at least 20 characters.");
      return;
    }
    if (loaelDose !== "" && chosen.length === 0) {
      setLocalError("A LOAEL rests on at least one finding: choose the findings.");
      return;
    }
    record.mutate();
  };
  const items = findings.data?.items.filter((f) => f.study_id === study.study_id) ?? [];
  return (
    <form className="decision" onSubmit={submit} aria-label="Record a NOAEL decision">
      <fieldset>
        <legend>{current ? "Revise the NOAEL" : "Record the NOAEL"}</legend>
        {current ? (
          <p className="muted">
            This revises <span className="mono">{current.decision_id}</span>; both stay in the ledger.
          </p>
        ) : null}
        <label className="field" htmlFor={`${ids}-sex`}>
          Sex
          <select
            id={`${ids}-sex`}
            value={sex}
            onChange={(e) => {
              setSex(e.target.value as "M" | "F" | "combined");
            }}
          >
            <option value="combined">Both sexes</option>
            <option value="M">Males</option>
            <option value="F">Females</option>
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={!established}
            onChange={(e) => {
              setEstablished(!e.target.checked);
            }}
          />{" "}
          NOAEL not established (adverse effects at every dose)
        </label>
        {established ? (
          <label className="field" htmlFor={`${ids}-noael`}>
            NOAEL
            <select
              id={`${ids}-noael`}
              value={noaelDose}
              onChange={(e) => {
                setNoaelDose(e.target.value);
              }}
            >
              {treated.map((d) => (
                <option key={d} value={String(d)}>
                  {String(d)} {history.dose_unit}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="field" htmlFor={`${ids}-loael`}>
          LOAEL
          <select
            id={`${ids}-loael`}
            value={loaelDose}
            onChange={(e) => {
              setLoaelDose(e.target.value);
            }}
          >
            <option value="">None</option>
            {treated.map((d) => (
              <option key={d} value={String(d)}>
                {String(d)} {history.dose_unit}
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend>The findings it rests on</legend>
          <div className="stack" style={{ maxHeight: "16rem", overflowY: "auto" }}>
            {items.map((f) => (
              <label key={f.finding_id} className="check">
                <input
                  type="checkbox"
                  checked={chosen.includes(f.finding_id)}
                  onChange={(e) => {
                    setChosen(
                      e.target.checked ? [...chosen, f.finding_id] : chosen.filter((x) => x !== f.finding_id),
                    );
                  }}
                />{" "}
                <span className="mono">{f.finding_id}</span> {f.title}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="field" htmlFor={`${ids}-rationale`}>
          Rationale (required)
          <textarea
            id={`${ids}-rationale`}
            className="reason"
            rows={4}
            value={rationale}
            onChange={(e) => {
              setRationale(e.target.value);
            }}
          />
        </label>
        <div aria-live="polite">
          {localError ? (
            <p className="message error" role="alert">
              {localError}
            </p>
          ) : null}
          {record.isError ? <ErrorNote error={record.error} /> : null}
          {record.isSuccess ? (
            <p className="message ok" role="status" data-testid="noael-recorded">
              Recorded as <span className="mono">{record.data.decision_id}</span> (ledger seq{" "}
              <span className="mono">{record.data.seq}</span>).
            </p>
          ) : null}
        </div>
        <button type="submit" className="btn" disabled={record.isPending}>
          Record the decision
        </button>
      </fieldset>
    </form>
  );
}
