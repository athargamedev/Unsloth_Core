/**
 * Replaces `{key}` patterns in a string with matching values from context.
 * If a key is not found in context, the `{key}` placeholder is left unchanged.
 */
export function resolveTemplates(str: string, context: Record<string, string>): string {
  return str.replace(/\{(\w+)\}/g, (match, key) => {
    return key in context ? context[key] : match;
  });
}
