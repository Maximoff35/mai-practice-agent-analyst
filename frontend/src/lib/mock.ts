import type { AnalysisResult, BehavioralModel } from "./types";

const buggyModel: BehavioralModel = {
  variables: [
    {
      name: "status",
      type: "enum",
      values: ["Created", "Approved", "Cancelled", "Executed"],
    },
    { name: "approved", type: "boolean" },
    { name: "cancelled", type: "boolean" },
  ],
  initial: { status: "Created", approved: false, cancelled: false },
  transitions: [
    {
      name: "Approve",
      guard: { eq: [{ var: "status" }, "Created"] },
      effects: [
        { set: ["status", "Approved"] },
        { set: ["approved", true] },
      ],
    },
    {
      name: "Cancel",
      guard: { in: [{ var: "status" }, ["Created", "Approved"]] },
      effects: [
        { set: ["status", "Cancelled"] },
        { set: ["cancelled", true] },
      ],
    },
    {
      name: "Execute",
      guard: { eq: [{ var: "approved" }, true] },
      effects: [{ set: ["status", "Executed"] }],
    },
  ],
  properties: [
    {
      name: "NoExecutedAfterCancel",
      type: "forbidden_state",
      expression: {
        and: [
          { eq: [{ var: "status" }, "Executed"] },
          { eq: [{ var: "cancelled" }, true] },
        ],
      },
    },
  ],
};

export function buildMockAnalysisResult(requirements: string): AnalysisResult {
  return {
    requirements,
    behavioral_model: buggyModel,
    verification_result: {
      status: "PROPERTY_VIOLATED",
      message:
        "Найден достижимый путь, при котором свойство NoExecutedAfterCancel нарушается.",
      violated_property: "NoExecutedAfterCancel",
      counterexample: [
        {
          number: 1,
          values: { status: "Created", approved: false, cancelled: false },
          transition: null,
          tlc_label: null,
        },
        {
          number: 2,
          values: { status: "Approved", approved: true, cancelled: false },
          transition: "Approve",
          tlc_label: "Step_Approve1",
        },
        {
          number: 3,
          values: { status: "Cancelled", approved: true, cancelled: true },
          transition: "Cancel",
          tlc_label: "Step_Cancel2",
        },
        {
          number: 4,
          values: { status: "Executed", approved: true, cancelled: true },
          transition: "Execute",
          tlc_label: "Step_Execute3",
        },
      ],
      statistics: {
        generated_states: 9,
        distinct_states: 6,
        queued_states: 6,
        graph_depth: 4,
      },
      stdout: "",
      stderr: "",
      exit_code: 0,
    },
    counterexample: null,
    explanation:
      "После отмены заявки признак approved=true сохраняется. Переход Execute проверяет только этот признак, поэтому отменённая заявка всё ещё может быть исполнена. Чтобы исправить модель, добавьте в переход Cancel эффект approved = false.",
  };
}