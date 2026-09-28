import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DetailsPanel from "./DetailsPanel";

const base = {
  fileCount: 83, edgeCount: 102, cycleCount: 3, cyclesTruncated: false,
  cyclicComponentCount: 1, highRiskCount: 0, avgDependencies: 1.2,
};

describe("DetailsPanel project stats", () => {
  it("shows the exact cycle count when nothing was truncated", () => {
    render(<DetailsPanel node={null} stats={base} />);
    expect(screen.getByText("Circular cycles").parentElement).toHaveTextContent("3");
    expect(screen.getByText("Circular cycles").parentElement).not.toHaveTextContent("3+");
  });

  it("shows 'N+' when the cycle list was capped, so the number isn't misleading", () => {
    render(<DetailsPanel node={null} stats={{ ...base, cycleCount: 200, cyclesTruncated: true }} />);
    expect(screen.getByText("Circular cycles").parentElement).toHaveTextContent("200+");
  });

  it("shows tangled clusters only when there are any", () => {
    const { rerender } = render(<DetailsPanel node={null} stats={base} />);
    expect(screen.getByText("Tangled clusters")).toBeInTheDocument();
    rerender(<DetailsPanel node={null} stats={{ ...base, cycleCount: 0, cyclicComponentCount: 0 }} />);
    expect(screen.queryByText("Tangled clusters")).not.toBeInTheDocument();
  });
});
