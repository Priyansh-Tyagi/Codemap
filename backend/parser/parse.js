#!/usr/bin/env node
/**
 * CodeMap parser bridge.
 *
 * Not a server. One-shot CLI process invoked by the Python backend.
 *
 * Input (stdin):  JSON  { "files": ["/abs/path/to/file.ts", ...] }
 * Output (stdout): JSON [
 *   {
 *     "filePath": "/abs/path/to/file.ts",
 *     "linesOfCode": 42,
 *     "imports": [
 *       { "specifier": "./auth", "type": "import", "symbols": ["useAuth"] },
 *       { "specifier": "react", "type": "import", "symbols": ["default"] },
 *       { "specifier": "./utils", "type": "re-export", "symbols": ["helper"] },
 *       { "specifier": "./db", "type": "require", "symbols": ["query"] }
 *     ],
 *     "error": null
 *   },
 *   ...
 * ]
 *
 * "symbols" is the list of names actually pulled in from that import - the
 * thing a person means when they ask "what exactly does this file use from
 * that other file", as opposed to just "does it depend on it at all".
 * "default" is used for `import X from "y"` (there's no name in the source
 * to report - X is just whatever the importing file chose to call it), and
 * "*" for `export * from "y"` / `import * as X from "y"` (everything,
 * name unknown until you look at the source module).
 *
 * Only the AST is parsed here. Classifying local-vs-external and resolving
 * paths to real files happens in Python (analyzer/classifier.py, resolver.py) -
 * this script's only job is: file content -> raw import specifiers (+ symbols).
 */

const fs = require("fs");
const path = require("path");
const { parse } = require("@babel/parser");
const traverseModule = require("@babel/traverse");
const traverse = traverseModule.default || traverseModule;

const BABEL_PLUGINS = ["jsx", "typescript", "classProperties", "decorators-legacy"];

/** Extracts symbol names from an import/export specifier list (shared by import + re-export handling). */
function symbolsFromSpecifiers(specifiers) {
  const symbols = [];
  for (const spec of specifiers || []) {
    if (spec.type === "ImportDefaultSpecifier" || spec.type === "ExportDefaultSpecifier") {
      symbols.push("default");
    } else if (spec.type === "ImportNamespaceSpecifier" || spec.type === "ExportNamespaceSpecifier") {
      symbols.push("*");
    } else if (spec.type === "ImportSpecifier") {
      // `imported` is the name in the SOURCE module; `local` is what this
      // file calls it after a possible `as` rename. The source-side name
      // is more useful here - it's what the other file actually exports.
      symbols.push(spec.imported.name || spec.imported.value);
    } else if (spec.type === "ExportSpecifier") {
      // For a re-export (`export { x } from "./y"`), `local` refers to the
      // name in the SOURCE module y (confusingly, Babel's naming is
      // relative to the export statement, not the target file).
      symbols.push(spec.local.name);
    }
  }
  return symbols;
}

/** Best-effort symbol extraction for require(): looks at what the result was bound to. */
function symbolsFromRequireBinding(nodePath) {
  const parent = nodePath.parentPath;
  if (!parent || !parent.isVariableDeclarator()) return [];

  const id = parent.node.id;
  if (id.type === "Identifier") {
    return [id.name]; // const db = require("./database") -> whole module bound as "db"
  }
  if (id.type === "ObjectPattern") {
    // const { x, y } = require("./z") -> destructured named symbols
    return id.properties
      .filter((p) => p.type === "ObjectProperty" && p.key)
      .map((p) => p.key.name || p.key.value)
      .filter(Boolean);
  }
  return [];
}

function parseFile(absolutePath) {
  const result = {
    filePath: absolutePath,
    linesOfCode: 0,
    imports: [],
    error: null,
  };

  let source;
  try {
    source = fs.readFileSync(absolutePath, "utf-8");
  } catch (err) {
    result.error = `read failed: ${err.message}`;
    return result;
  }

  result.linesOfCode = source.split("\n").length;

  let ast;
  try {
    ast = parse(source, {
      sourceType: "unambiguous",
      plugins: BABEL_PLUGINS,
      errorRecovery: true,
    });
  } catch (err) {
    result.error = `parse failed: ${err.message}`;
    return result;
  }

  try {
    traverse(ast, {
      ImportDeclaration(nodePath) {
        const source = nodePath.node.source && nodePath.node.source.value;
        if (source) {
          result.imports.push({
            specifier: source,
            type: "import",
            symbols: symbolsFromSpecifiers(nodePath.node.specifiers),
          });
        }
      },
      ExportNamedDeclaration(nodePath) {
        const source = nodePath.node.source && nodePath.node.source.value;
        if (source) {
          result.imports.push({
            specifier: source,
            type: "re-export",
            symbols: symbolsFromSpecifiers(nodePath.node.specifiers),
          });
        }
      },
      ExportAllDeclaration(nodePath) {
        const source = nodePath.node.source && nodePath.node.source.value;
        if (source) {
          result.imports.push({ specifier: source, type: "re-export", symbols: ["*"] });
        }
      },
      CallExpression(nodePath) {
        const callee = nodePath.node.callee;
        const isRequire = callee && callee.type === "Identifier" && callee.name === "require";
        const isDynamicImport = callee && callee.type === "Import";
        if (isRequire || isDynamicImport) {
          const arg = nodePath.node.arguments[0];
          if (arg && arg.type === "StringLiteral") {
            result.imports.push({
              specifier: arg.value,
              type: isRequire ? "require" : "import",
              symbols: isRequire ? symbolsFromRequireBinding(nodePath) : [],
            });
          }
        }
      },
    });
  } catch (err) {
    // AST walked partially; keep whatever imports we already found and note the error.
    result.error = `traverse failed: ${err.message}`;
  }

  return result;
}

function main() {
  let input = "";
  process.stdin.setEncoding("utf-8");
  process.stdin.on("data", (chunk) => (input += chunk));
  process.stdin.on("end", () => {
    let payload;
    try {
      payload = JSON.parse(input);
    } catch (err) {
      process.stderr.write(`invalid stdin JSON: ${err.message}\n`);
      process.exit(1);
    }

    const files = Array.isArray(payload.files) ? payload.files : [];
    const results = files.map((f) => parseFile(path.resolve(f)));
    process.stdout.write(JSON.stringify(results));
  });
}

main();
