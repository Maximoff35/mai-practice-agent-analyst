import type {
  AnalysisResult,
  SourceReference,
  TraceState,
  VerificationResult,
  VerificationStatus,
} from "@/lib/types";

export function makeReference(id: string, fragment: string): SourceReference {
  return { id, fragment };
}

export function makeTrace(): TraceState[] {
  return [
    {
      number: 1,
      values: { status: "created" },
      transition: null,
      tlc_label: null,
    },
    {
      number: 2,
      values: { status: "approved" },
      transition: "approve",
      tlc_label: "<<Approve>>",
    },
    {
      number: 3,
      values: { status: "executed" },
      transition: "execute",
      tlc_label: "<<Execute>>",
    },
  ];
}

export function makeVerification(
  status: VerificationStatus,
  overrides: Partial<VerificationResult> = {},
): VerificationResult {
  return {
    status,
    message: null,
    violated_property: null,
    counterexample: status === "PROPERTY_VIOLATED" ? makeTrace() : [],
    statistics: {},
    stdout: "",
    stderr: "",
    exit_code: null,
    ...overrides,
  };
}

export function makeResult(
  overrides: Partial<AnalysisResult> = {},
): AnalysisResult {
  const trace = makeTrace();
  return {
    requirements: "Заявка и отмена",
    behavioral_model: {
      variables: [
        {
          name: "status",
          type: "enum",
          values: ["created", "approved", "cancelled", "executed"],
        },
      ],
      initial: { status: "created" },
      transitions: [
        {
          name: "approve",
          guard: { eq: [{ var: "status" }, "created"] },
          effects: [{ set: ["status", "approved"] }],
        },
      ],
      properties: [
        {
          name: "NoExecuteAfterCancel",
          type: "invariant",
          expression: { invariant: true },
        },
      ],
    },
    verification_result: makeVerification("PROPERTY_VIOLATED"),
    counterexample: trace,
    explanation: "Найден путь, нарушающий свойство.",
    ...overrides,
  };
}
