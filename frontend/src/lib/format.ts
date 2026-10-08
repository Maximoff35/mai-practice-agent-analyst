function formatOperands(operands: unknown, separator: string): string {
  if (Array.isArray(operands)) {
    return operands.map((operand) => formatExpression(operand)).join(separator);
  }
  return formatExpression(operands);
}

export function formatExpression(expression: unknown): string {
  if (typeof expression === "string") {
    return expression;
  }
  if (
    typeof expression === "number" ||
    typeof expression === "boolean"
  ) {
    return String(expression);
  }
  if (Array.isArray(expression)) {
    return expression.map(formatExpression).join(", ");
  }
  if (expression !== null && typeof expression === "object") {
    const entry = expression as Record<string, unknown>;
    const [key, operands] = Object.entries(entry)[0];
    switch (key) {
      case "var":
        return String(operands);
      case "eq": {
        const [lhs, rhs] = operands as [unknown, unknown];
        return `${formatExpression(lhs)} = ${formatExpression(rhs)}`;
      }
      case "in": {
        const [lhs, rhs] = operands as [unknown, unknown];
        return `${formatExpression(lhs)} ∈ {${formatExpression(rhs)}}`;
      }
      case "and":
        return `(${formatOperands(operands, " AND ")})`;
      case "or":
        return `(${formatOperands(operands, " OR ")})`;
      case "not":
        return `not (${formatExpression(operands)})`;
      default:
        return `${key}(${formatOperands(operands, ", ")})`;
    }
  }
  return String(expression);
}