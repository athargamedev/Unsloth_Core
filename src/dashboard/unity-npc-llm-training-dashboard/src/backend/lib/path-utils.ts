import fs from "fs";
import path from "path";

/**
 * Finds the Unsloth_Core repo root by looking for the `ucore` file.
 * Checks environment variable first, then walks parent directories.
 */
export function findRepoRoot(): string {
  const dashboardRoot = process.cwd();

  const candidates = [
    process.env.UNSLOTH_CORE_ROOT,
    path.resolve(dashboardRoot, "../.."),
    path.resolve(dashboardRoot, "../../.."),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(path.join(resolved, "ucore"))) return resolved;
  }

  throw new Error(
    `Unable to locate Unsloth_Core root. Set UNSLOTH_CORE_ROOT or launch from the dashboard directory. Tried: ${candidates.join(", ")}`,
  );
}

/**
 * Sanitizes a user-supplied path token — alphanumeric, underscore, dot, slash, colon, hyphen only.
 */
export function sanitizeToken(value: string, fieldName: string): string {
  if (!value || !/^[a-zA-Z0-9_./:-]+$/.test(value)) {
    throw new Error(`Invalid ${fieldName}.`);
  }
  return value;
}

/**
 * Normalizes a relative path input: sanitizes and strips leading `../` or `./`.
 */
export function normalizeRelativePath(value: string, fieldName: string): string {
  const token = sanitizeToken(value, fieldName);
  return token.replace(/^\.{1,2}\//, "");
}

/**
 * Resolves a path to its real (canonical) form, following symlinks.
 * Throws if the path does not exist.
 */
export function canonicalizeExistingPath(targetPath: string): string {
  return fs.realpathSync(targetPath);
}

/**
 * Walks up from targetPath to find the nearest existing parent, canonicalizes it,
 * then appends remaining segments. This handles paths where the leaf doesn't exist yet.
 */
export function canonicalizePathFromNearestExistingParent(targetPath: string): string {
  if (fs.existsSync(targetPath)) {
    return canonicalizeExistingPath(targetPath);
  }

  const segments: string[] = [];
  let currentPath = path.resolve(targetPath);
  while (!fs.existsSync(currentPath)) {
    const parentPath = path.dirname(currentPath);
    if (parentPath === currentPath) {
      throw new Error("Invalid path: no existing parent for canonicalization.");
    }
    segments.unshift(path.basename(currentPath));
    currentPath = parentPath;
  }

  const canonicalParent = canonicalizeExistingPath(currentPath);
  return path.resolve(canonicalParent, ...segments);
}

/**
 * Checks whether `candidate` is within or equal to `allowedRoot`.
 */
export function isPathWithinOrEqualToRoot(candidate: string, allowedRoot: string): boolean {
  const relative = path.relative(allowedRoot, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/**
 * Security-constrained path resolution.
 *  1. Normalizes/sanitizes inputPath
 *  2. Resolves against repoRoot
 *  3. Checks canonical candidate is within one of the allowedRoots
 *  Returns relative path from repoRoot.
 */
export function resolvePathWithinRoots(
  inputPath: string,
  fieldName: string,
  allowedRoots: string[],
  repoRoot: string,
): string {
  const safeInput = normalizeRelativePath(inputPath, fieldName);
  const absoluteCandidate = path.resolve(repoRoot, safeInput);

  const canonicalAllowedRoots = allowedRoots.map((root) => {
    const absoluteRoot = path.resolve(root);
    if (!fs.existsSync(absoluteRoot)) {
      throw new Error(`Invalid ${fieldName}: allowed root is unavailable.`);
    }
    return canonicalizeExistingPath(absoluteRoot);
  });

  const canonicalCandidate = canonicalizePathFromNearestExistingParent(absoluteCandidate);
  const isAllowed = canonicalAllowedRoots.some((canonicalRoot) =>
    isPathWithinOrEqualToRoot(canonicalCandidate, canonicalRoot),
  );

  if (!isAllowed) {
    throw new Error(`Invalid ${fieldName}: path escapes allowed roots.`);
  }

  const canonicalRepoRoot = canonicalizeExistingPath(repoRoot);
  return path.relative(canonicalRepoRoot, canonicalCandidate);
}

/**
 * Resolves a payload path: handles absolute paths (must exist) and relative paths
 * resolved through resolvePathWithinRoots.
 */
export function resolvePayloadPath(
  payload: Record<string, unknown>,
  key: string,
  allowedRoots: string[],
  repoRoot: string,
): string {
  const raw = optionValue(payload, key);
  if (!raw) throw new Error(`${key} is required.`);
  if (path.isAbsolute(raw)) {
    if (!fs.existsSync(raw)) {
      throw new Error(`Invalid ${key}: path not found.`);
    }
    return canonicalizeExistingPath(raw);
  }
  return resolvePathWithinRoots(raw, key, allowedRoots, repoRoot);
}

/**
 * Safe option value extraction from a command payload.
 */
function optionValue(payload: Record<string, unknown>, key: string): string {
  const raw = (payload as Record<string, unknown>)[key] ?? (payload.options as Record<string, unknown>)?.[key];
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "";
}
