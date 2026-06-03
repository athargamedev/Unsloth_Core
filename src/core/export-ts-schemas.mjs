#!/usr/bin/env node
/**
 * Export TypeScript command schemas from command-builder.ts as JSON.
 *
 * Uses regex-based parsing — no TypeScript compiler needed.
 * Outputs JSON to stdout: { commandId: { fieldKey: { type, default, ... }, ... }, ... }
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve script directory robustly
const scriptDir = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url));

// scripts is a symlink to src/core, so we go up to src/ then into dashboard/
const TS_FILE = process.argv[2] ||
  path.resolve(
    scriptDir,
    "..",
    "dashboard/unity-npc-llm-training-dashboard/src/backend/services/command-builder.ts",
  );

/**
 * Find the matching closing brace at `openPos`, handling strings.
 */
function findMatchingBrace(text, openPos) {
  let depth = 1;
  for (let i = openPos + 1; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"' || ch === "'") {
      // Skip past string content
      const quoteChar = ch;
      i++;
      while (i < text.length) {
        if (text[i] === "\\") { i += 2; continue; }
        if (text[i] === quoteChar) break;
        i++;
      }
      continue;
    }
    if (ch === "{") depth++;
    if (ch === "}") {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * Parse a simple JSON-like property value.
 */
function parsePropValue(raw) {
  const t = raw.trim().replace(/,$/, "");
  if (t.startsWith('"') && t.endsWith('"')) return t.slice(1, -1);
  if (t === "true") return true;
  if (t === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(t)) {
    const n = Number(t);
    if (!Number.isNaN(n)) return n;
  }
  if (t.startsWith("[") && t.endsWith("]") && t.length > 2) {
    return t.slice(1, -1).split(",").map((s) => {
      const st = s.trim();
      if (st.startsWith('"') && st.endsWith('"')) return st.slice(1, -1);
      if (/^-?\d+\.?\d*$/.test(st)) { const nn = Number(st); return Number.isNaN(nn) ? st : nn; }
      return st;
    });
  }
  return t;
}

/**
 * Parse the body inside a field's { } collecting key: value pairs.
 */
function parseFieldBody(body) {
  const props = {};
  // Match pattern: key: value (simple key=word, value is next token)
  const propRe = /(\w+)\s*:\s*("[^"]*"|\[[^\]]*\]|true|false|-?\d+(?:\.\d+)?|[^\s,}]+)/g;
  let m;
  while ((m = propRe.exec(body)) !== null) {
    if (m[2] !== undefined) {
      props[m[1]] = parsePropValue(m[2]);
    }
  }
  return props;
}

/**
 * Extract all command schemas from the TypeScript file.
 *
 * Strategy: find schema: { blocks, extract their contents, then
 * for each command, find its id by looking backward from schema:.
 */
function extractSchemas(filePath) {
  const text = fs.readFileSync(filePath, "utf-8");
  const result = {};

  let searchPos = 0;
  while (true) {
    const schemaIdx = text.indexOf("schema:", searchPos);
    if (schemaIdx === -1) break;

    const bracePos = text.indexOf("{", schemaIdx + 7);
    if (bracePos === -1) { searchPos = schemaIdx + 7; continue; }

    const endPos = findMatchingBrace(text, bracePos);
    if (endPos === -1) { searchPos = bracePos + 1; continue; }

    const body = text.substring(bracePos + 1, endPos);
    searchPos = endPos + 1;

    // Walk backward from schema: to find the command id
    const before = text.substring(0, schemaIdx);
    // Find the LAST `id: "..."` that appears before schema:
    // (must be before schema, not inside it)
    const idRe = /\bid\s*:\s*"([^"]+)"/g;
    let lastId = null;
    let idMatch;
    while ((idMatch = idRe.exec(before)) !== null) {
      lastId = idMatch;
    }
    if (!lastId) continue;
    const cmdId = lastId[1];

    // Parse fields from schema body using a simple state approach
    const fields = {};

    // Walk through body and find fieldName: { ... } pairs.
    // A field is defined by a key, ':', then an object literal.
    // Keys are quoted or unquoted strings, possibly containing dots.
    let i = 0;
    while (i < body.length) {
      // Skip past strings
      if (body[i] === '"' || body[i] === "'") {
        const qc = body[i];
        i++;
        while (i < body.length && !(body[i] === qc && body[i - 1] !== "\\")) i++;
        i++;
        continue;
      }
      // Skip whitespace
      if (body[i] === " " || body[i] === "\n" || body[i] === "\t" || body[i] === "\r") {
        i++;
        continue;
      }
      // Check for field pattern: something: {
      // Try to find "word: {" or `"quoted.key": {`
      // Strategy: look for : { pattern
      if (body[i] === ":" && body[i + 1] !== undefined) {
        // Check if after whitespace we find {
        let j = i + 1;
        while (j < body.length && (body[j] === " " || body[j] === "\n" || body[j] === "\t")) j++;
        if (body[j] === "{") {
          // We found a field! Extract the key by going backward from i
          let k = i - 1;
          while (k >= 0 && (body[k] === " " || body[k] === "\n" || body[k] === "\t")) k--;
          let keyEnd = k;

          // Check if the key is quoted
          let fieldKey;
          if (body[k] === '"' || body[k] === "'") {
            // Quoted key - find the opening quote
            const qc = body[k];
            let ks = k - 1;
            while (ks >= 0 && !(body[ks] === qc && body[ks - 1] !== "\\")) ks--;
            // ks is at the opening quote (or before it)
            if (ks >= 0 && body[ks] === qc) {
              fieldKey = body.substring(ks + 1, k);
            } else {
              // Use whole quoted segment
              fieldKey = body.substring(ks + 1, k);
            }
          } else {
            // Unquoted key - walk backward to the previous comma or brace
            let ks = k;
            while (ks >= 0 && body[ks] !== "," && body[ks] !== "{" && body[ks] !== "}") ks--;
            fieldKey = body.substring(ks + 1, k + 1).trim();
          }

          if (fieldKey) {
            // Find the matching closing brace for this field value
            const valStart = j;
            const valEnd = findMatchingBrace(body, valStart);
            if (valEnd !== -1) {
              const valBody = body.substring(valStart + 1, valEnd);
              fields[fieldKey] = parseFieldBody(valBody);
              i = valEnd + 1;
              continue;
            }
          }
        }
      }
      i++;
    }

    if (Object.keys(fields).length > 0) {
      result[cmdId] = fields;
    }
  }

  return result;
}

const schemas = extractSchemas(TS_FILE);
process.stdout.write(JSON.stringify(schemas, null, 2) + "\n");
