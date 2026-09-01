/**
 * Node color now comes from something meaningful (architecture category)
 * instead of an arbitrary hash of the file path. A hash-based rainbow reads
 * as noise once a graph has more than a handful of nodes - category color
 * means every "Service" node looks like every other "Service" node, so the
 * graph reads as a map of regions instead of confetti.
 *
 * Cycle membership and risk level are layered on TOP of category color
 * (an outline/badge) rather than overriding it, so you don't lose "what
 * kind of file is this" just because it's also flagged for something.
 */

const CATEGORY_COLORS = {
  Component: "#6C8EF5", // periwinkle blue
  Service: "#4FBFA8",   // teal
  Controller: "#E0925C", // clay
  Model: "#E0C15C",     // gold
  Middleware: "#B98CE0", // violet
  Route: "#5CC8C2",     // turquoise
  Hook: "#C97FB0",      // orchid
  Page: "#7CA8E0",      // sky
  Config: "#8C93A8",    // slate grey
  Util: "#7CC6A0",      // sage
  Test: "#9FD35F",      // lime
  Unknown: "#5B6272",   // neutral
};

export const RISK_COLORS = {
  Low: "#7CC6A0",
  Medium: "#E0C15C",
  High: "#E0925C",
  Critical: "#D1615C",
};

export const CYCLE_COLOR = "#D1615C";

export function colorForCategory(architectureType) {
  return CATEGORY_COLORS[architectureType] ?? CATEGORY_COLORS.Unknown;
}

export function colorForRisk(riskLevel) {
  return RISK_COLORS[riskLevel] ?? null;
}

export const CATEGORY_LEGEND = Object.entries(CATEGORY_COLORS).filter(
  ([name]) => name !== "Unknown"
);
