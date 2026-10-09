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

export type SetEffect = {
  set: [string, Expression];
};

export type Transition = {
  name: string;
  guard: Expression;
  effects: SetEffect[];
};

export type PropertyType = "invariant" | "forbidden_state";

export type Property = {
  name: string;
  type: PropertyType;
  expression: Expression;
};

export type BehavioralModel = {
  variables: Variable[];
  initial: Record<string, unknown>;
  transitions: Transition[];
  properties: Property[];
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
};

export type VerificationResult = {
  status: VerificationStatus;
  message: string | null;
  violated_property: string | null;
  counterexample: TraceState[];
  statistics: TLCStatistics;
  stdout: string;
  stderr: string;
  exit_code: number | null;
};

export type AnalysisResult = {
  requirements: string;
  behavioral_model: BehavioralModel;
  verification_result: VerificationResult;
  counterexample: TraceState[] | null;
  explanation: string;
};
