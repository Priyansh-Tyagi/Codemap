/**
 * Builds a nested {type, name, children} tree from CodeMap's flat node list
 * (each node has a "/"-separated filePath). Kept as a plain function, not a
 * component, so it's testable in isolation from React/rendering.
 */
export function buildFileTree(nodes) {
  const root = { type: "folder", name: "", children: {} };

  for (const node of nodes) {
    const parts = node.filePath.split("/");
    let current = root;

    parts.forEach((part, idx) => {
      const isFile = idx === parts.length - 1;
      if (isFile) {
        current.children[part] = { type: "file", name: part, id: node.id, node };
      } else {
        if (!current.children[part]) {
          current.children[part] = { type: "folder", name: part, children: {} };
        }
        current = current.children[part];
      }
    });
  }

  return root;
}

/** Sorted children of a folder node: folders first, then files, each alphabetical. */
export function sortedEntries(folder) {
  return Object.values(folder.children).sort((a, b) => {
    if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}
