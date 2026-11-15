export type EnumVariable = {
  name: string;
  type: "enum";
  values: string[];
};

export type BooleanVariable = {
  name: string;
  type: "boolean";
};

export type IntegerVariable = {
  name: string;
  type: "integer";
  min: number;
  max: number;
};

export type Variable = EnumVariable | BooleanVariable | IntegerVariable;

export type Expression = unknown;

export type SourceReference = {
  id: string;
  fragment: string;
};

export type SetEffect = {
  set: [string, Expression];
};

export type Transition = {
  name: string;
  guard: Expression;
  effects: SetEffect[];
  source_reference?: SourceReference;
};

export type PropertyType = "invariant" | "forbidden_state" | "reachable" | "deadlock_free";

export type Property = {
  name: string;
  type: PropertyType;
  expression?: Expression;
  terminal_states?: Expression;
  source_reference?: SourceReference;
};

export type BehavioralModel = {
  variables: Variable[];
  initial: Record<string, unknown>;
  transitions: Transition[];
  properties: Property[];
  interpretation?: {
    assumptions: string[];
    questions: string[];
    property_rationale: Record<string, string>;
  } | null;
};

export type VerificationStatus =
  | "PROPERTY_HOLDS"
  | "PROPERTY_VIOLATED"
  | "MODEL_INVALID"
  | "TIMEOUT"
  | "STATE_LIMIT_REACHED"
  | "ENGINE_ERROR";

export type TLCStatistics = Partial<{
  generated_states: number | null;
  distinct_states: number | null;
  queued_states: number | null;
  graph_depth: number | null;
}>;

export type TraceValue = string | boolean | number;

export type TraceState = {
  number: number;
  values: Record<string, TraceValue>;
  transition: string | null;
  tlc_label: string | null;
  related_requirements?: SourceReference[];
};

export type VerificationResult = {
  status: VerificationStatus;
  message: string | null;
  violated_property: string | null;
  counterexample: TraceState[];
  witness?: TraceState[];
  deadlock_path?: TraceState[];
  property_results?: PropertyResult[];
  statistics: TLCStatistics;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  related_requirements?: SourceReference[];
};

export type PropertyResult = {
  property_name: string;
  property_type: PropertyType;
  status: VerificationStatus;
  message: string | null;
  counterexample: TraceState[];
  witness: TraceState[];
  deadlock_path?: TraceState[];
  related_requirements: SourceReference[];
  statistics: TLCStatistics;
};

export type AnalysisResult = {
  requirements: string;
  behavioral_model: BehavioralModel;
  verification_result: VerificationResult;
  counterexample: TraceState[] | null;
  related_requirements?: SourceReference[];
  explanation: string;
};

export type CaseAnalysis = {
  case_id: string;
  model_fingerprint: string;
  analysis: AnalysisResult;
  accepted: boolean;
  mode?: "live" | "recorded";
};

export type JavaArtifact = {
  main_class: string;
  files: { path: string; content: string }[];
  instruction?: string | null;
  generator_model?: string | null;
};

export type JavaReview = {
  approved: boolean;
  reviewer_model: string | null;
  message?: string | null;
  findings: { severity: string; message: string; file?: string | null; line?: number | null; rule?: string | null; transition?: string | null }[];
};

export type JavaReport = {
  case_id: string;
  status: string;
  model_fingerprint: string;
  artifact_fingerprint: string | null;
  artifact: JavaArtifact | null;
  review: JavaReview | null;
  compile_and_check: {
    status: string; compilation: string; coverage: string;
    checks_run: number; message?: string | null; failed_check?: string | null;
    stdout: string; stderr: string;
  } | null;
  message: string | null;
};
