import { describe, it, expect } from "vitest";
import {
  emptyFilters,
  hasActiveFilters,
  dirnameOf,
  availableCategories,
  availableFolders,
  computeVisibleNodeIds,
} from "./filterNodes";

const nodes = [
  { id: "a", filePath: "src/services/userService.js", architectureType: "Service", riskLevel: "Medium" },
  { id: "b", filePath: "src/services/orderService.js", architectureType: "Service", riskLevel: "Low" },
  { id: "c", filePath: "src/controllers/userController.js", architectureType: "Controller", riskLevel: "High" },
  { id: "d", filePath: "src/utils/validators.js", architectureType: "Util", riskLevel: "Critical" },
  { id: "e", filePath: "src/app.js", architectureType: "Unknown", riskLevel: "Low" },
];

describe("dirnameOf", () => {
  it("returns the parent directory", () => {
    expect(dirnameOf("src/services/userService.js")).toBe("src/services");
  });

  it("returns (root) for a top-level file", () => {
    expect(dirnameOf("app.js")).toBe("(root)");
  });
});

describe("availableCategories / availableFolders", () => {
  it("lists distinct categories, sorted", () => {
    expect(availableCategories(nodes)).toEqual(["Controller", "Service", "Unknown", "Util"]);
  });

  it("lists distinct folders, sorted", () => {
    expect(availableFolders(nodes)).toEqual([
      "src",
      "src/controllers",
      "src/services",
      "src/utils",
    ]);
  });
});

describe("computeVisibleNodeIds", () => {
  it("with no active filters, everything is visible", () => {
    const visible = computeVisibleNodeIds(nodes, emptyFilters());
    expect(visible).toEqual(new Set(["a", "b", "c", "d", "e"]));
  });

  it("filters by a single category", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(["Service"]),
      minRisk: null,
      folder: null,
    });
    expect(visible).toEqual(new Set(["a", "b"]));
  });

  it("filters by multiple categories (OR within the category axis)", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(["Service", "Util"]),
      minRisk: null,
      folder: null,
    });
    expect(visible).toEqual(new Set(["a", "b", "d"]));
  });

  it("filters by minimum risk level, inclusive", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(),
      minRisk: "High",
      folder: null,
    });
    expect(visible).toEqual(new Set(["c", "d"])); // High and Critical, not Medium/Low
  });

  it("filters by exact folder", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(),
      minRisk: null,
      folder: "src/services",
    });
    expect(visible).toEqual(new Set(["a", "b"]));
  });

  it("folder filter includes the whole subtree, not just exact matches", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(),
      minRisk: null,
      folder: "src",
    });
    expect(visible).toEqual(new Set(["a", "b", "c", "d", "e"]));
  });

  it("does not match a folder that merely shares a string prefix", () => {
    const trickyNodes = [
      { id: "x", filePath: "src/services/a.js", architectureType: "Service", riskLevel: "Low" },
      { id: "y", filePath: "src/services-legacy/b.js", architectureType: "Service", riskLevel: "Low" },
    ];
    const visible = computeVisibleNodeIds(trickyNodes, {
      categories: new Set(),
      minRisk: null,
      folder: "src/services",
    });
    // "src/services-legacy" must NOT match "src/services" just because the
    // string starts the same way - this is what the "+ '/'" in matchesFolder guards against
    expect(visible).toEqual(new Set(["x"]));
  });

  it("combines filters with AND across axes", () => {
    const visible = computeVisibleNodeIds(nodes, {
      categories: new Set(["Service"]),
      minRisk: "Medium",
      folder: null,
    });
    expect(visible).toEqual(new Set(["a"])); // b is a Service but only Low risk
  });

  it("hasActiveFilters reflects whether any axis is set", () => {
    expect(hasActiveFilters(emptyFilters())).toBe(false);
    expect(hasActiveFilters({ categories: new Set(["Service"]), minRisk: null, folder: null })).toBe(true);
    expect(hasActiveFilters({ categories: new Set(), minRisk: "High", folder: null })).toBe(true);
    expect(hasActiveFilters({ categories: new Set(), minRisk: null, folder: "src" })).toBe(true);
  });
});
