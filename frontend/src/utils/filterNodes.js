/**
 * Pure filtering logic for the graph/file-tree, kept separate from any
 * component so it's directly testable (same pattern as buildFileTree.js
 * and nodeColor.js) rather than only verifiable by clicking around.
 *
 * Filters combine with AND: a node must satisfy every active filter to be
 * visible. An empty/null filter value means "no restriction on this axis".
 */

const RISK_ORDER = { Low: 0, Medium: 1, High: 2, Critical: 3 };

export function emptyFilters() {
  return { categories: new Set(), minRisk: null, folder: null };
}

export function hasActiveFilters(filters) {
  return filters.categories.size > 0 || Boolean(filters.minRisk) || Boolean(filters.folder);
}

/** Directory containing a file, e.g. "src/services/userService.js" -> "src/services". */
export function dirnameOf(filePath) {
  const idx = filePath.lastIndexOf("/");
  return idx === -1 ? "(root)" : filePath.slice(0, idx);
}

/** Every distinct architectureType present in the node list, sorted. */
export function availableCategories(nodes) {
  return [...new Set(nodes.map((n) => n.architectureType))].sort();
}

/** Every distinct directory present in the node list, sorted. */
export function availableFolders(nodes) {
  return [...new Set(nodes.map((n) => dirnameOf(n.filePath)))].sort();
}

function matchesFolder(nodeDir, filterFolder) {
  // exact match (files directly in that folder) OR the node is somewhere
  // in a subtree under it - so picking "src" includes "src/services" etc.
  return nodeDir === filterFolder || nodeDir.startsWith(filterFolder + "/");
}

/** Returns the Set of node ids that pass every active filter. */
export function computeVisibleNodeIds(nodes, filters) {
  const { categories, minRisk, folder } = filters;
  const visible = new Set();

  for (const node of nodes) {
    if (categories.size > 0 && !categories.has(node.architectureType)) continue;

    if (minRisk) {
      const level = node.riskLevel;
      if (level == null || RISK_ORDER[level] < RISK_ORDER[minRisk]) continue;
    }

    if (folder && !matchesFolder(dirnameOf(node.filePath), folder)) continue;

    visible.add(node.id);
  }

  return visible;
}
