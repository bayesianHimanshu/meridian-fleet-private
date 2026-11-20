// Run the 30 committed questions (docs/demo/qa-questions.json) against the built index, once,
// with the page's own search code. Writes docs/demo/qa-results.md and var/demo/qa-results.json.
// The questions were committed before the index existed; nothing here may be tuned on them.
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { DECLINE_BELOW, search } from "./search.mjs";

const ROOT = resolve(import.meta.dirname, "..", "..");
const index = JSON.parse(readFileSync(resolve(ROOT, "var/demo/index.json"), "utf-8"));
const transcript = JSON.parse(readFileSync(resolve(ROOT, "var/demo/transcript.json"), "utf-8"));
const { questions } = JSON.parse(readFileSync(resolve(ROOT, "docs/demo/qa-questions.json"), "utf-8"));

const inGroup = (source, group) => group.includes(source);
const fmt = (t) => `${String(Math.floor(t / 60))}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

const rows = [];
for (const q of questions) {
  const r = search(index, q.question);
  const got = r.results.map((p) => p.source);
  let top1 = null;
  let top3 = null;
  let declinedOk = null;
  if (q.kind === "uncovered") {
    declinedOk = r.declined;
  } else if (q.kind === "answerable") {
    top1 = !r.declined && got.length > 0 && inGroup(got[0], q.expected[0]);
    top3 = !r.declined && got.some((s) => inGroup(s, q.expected[0]));
  } else {
    const [g1, g2] = q.expected;
    top1 = !r.declined && got.length > 0 && (inGroup(got[0], g1) || inGroup(got[0], g2));
    top3 = !r.declined && got.some((s) => inGroup(s, g1)) && got.some((s) => inGroup(s, g2));
  }
  const t = r.results.find((p) => p.start !== null);
  rows.push({
    id: q.id,
    kind: q.kind,
    question: q.question,
    declined: r.declined,
    top1,
    top3,
    declined_ok: declinedOk,
    best_coverage: r.results[0]?.coverage ?? 0,
    retrieved: r.results.map((p) => ({ source: p.source, start: p.start, score: p.score, coverage: p.coverage })),
    first_transcript_time: t ? fmt(t.start) : null,
  });
}

const sum = (kind, key) => rows.filter((x) => x.kind === kind && x[key]).length;
const count = (kind) => rows.filter((x) => x.kind === kind).length;
const summary = {
  answerable: { n: count("answerable"), top1: sum("answerable", "top1"), top3: sum("answerable", "top3") },
  two_source: { n: count("two_source"), top1: sum("two_source", "top1"), top3_both: sum("two_source", "top3") },
  uncovered: { n: count("uncovered"), declined: sum("uncovered", "declined_ok") },
  declined_wrongly: rows.filter((x) => x.kind !== "uncovered" && x.declined).map((x) => x.id),
  threshold: DECLINE_BELOW,
  passages: index.docs.length,
  video_duration: transcript.duration,
};
writeFileSync(resolve(ROOT, "var/demo/qa-results.json"), JSON.stringify({ summary, rows }, null, 2) + "\n");

const yn = (v) => (v === null ? "" : v ? "yes" : "no");
const md = [
  "# Demo Q&A: evaluation results",
  "",
  "The 30 questions in [qa-questions.json](qa-questions.json) were committed before the index",
  "was built. They were run once, on the index the recording built, with the page's own search",
  "(web/demo/search.mjs, BM25, declining when the best passage covers less than",
  `${String(DECLINE_BELOW)} of the question's idf weight). Nothing was tuned on them. This file is`,
  "written by `node web/demo/eval-qa.mjs`.",
  "",
  "| Set | Questions | Top-1 hit | Top-3 hit | Declined |",
  "|---|---:|---:|---:|---:|",
  `| Answerable from one source | ${String(summary.answerable.n)} | ${String(summary.answerable.top1)} | ${String(summary.answerable.top3)} | ${String(rows.filter((x) => x.kind === "answerable" && x.declined).length)} |`,
  `| Needing two sources (top-3: both present) | ${String(summary.two_source.n)} | ${String(summary.two_source.top1)} | ${String(summary.two_source.top3_both)} | ${String(rows.filter((x) => x.kind === "two_source" && x.declined).length)} |`,
  `| Not covered (should be declined) | ${String(summary.uncovered.n)} | | | ${String(summary.uncovered.declined)} correctly declined |`,
  "",
  `The index holds ${String(summary.passages)} passages (transcript segments and document sections).`,
  "",
  "## Every question",
  "",
  "| Id | Question | Declined | Top-1 | Top-3 | Best coverage | First retrieved source |",
  "|---|---|---|---|---|---:|---|",
  ...rows.map(
    (x) =>
      `| ${x.id} | ${x.question} | ${yn(x.declined)} | ${yn(x.top1)} | ${x.kind === "uncovered" ? (x.declined_ok ? "correctly declined" : "NOT declined") : yn(x.top3)} | ${x.best_coverage.toFixed(2)} | ${x.retrieved[0] ? x.retrieved[0].source + (x.retrieved[0].start !== null ? ` (${fmt(x.retrieved[0].start)})` : "") : ""} |`,
  ),
  "",
];
const text = md.join("\n");
if (text.includes(String.fromCodePoint(0x2014))) throw new Error("an em dash in the results");
writeFileSync(resolve(ROOT, "docs/demo/qa-results.md"), text);
process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
