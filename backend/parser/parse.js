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
 *       { "specifier": "./auth", "type": "import" },
 *       { "specifier": "react", "type": "import" },
 *       { "specifier": "./utils", "type": "re-export" },
 *       { "specifier": "./db", "type": "require" }
 *     ],
 *     "error": null
 *   },
 *   ...
 * ]
 *
 * Only the AST is parsed here. Classifying local-vs-external and resolving
 * paths to real files happens in Python (analyzer/classifier.py, resolver.py) -
 * this script's only job is: file content -> raw import specifiers.
 */

const fs = require("fs");
const path = require("path");
const { parse } = require("@babel/parser");
const traverseModule = require("@babel/traverse");
const traverse = traverseModule.default || traverseModule;

const BABEL_PLUGINS = ["jsx", "typescript", "classProperties", "decorators-legacy"];

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
          result.imports.push({ specifier: source, type: "import" });
        }
      },
      ExportNamedDeclaration(nodePath) {
        const source = nodePath.node.source && nodePath.node.source.value;
        if (source) {
          result.imports.push({ specifier: source, type: "re-export" });
        }
      },
      ExportAllDeclaration(nodePath) {
        const source = nodePath.node.source && nodePath.node.source.value;
        if (source) {
          result.imports.push({ specifier: source, type: "re-export" });
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
