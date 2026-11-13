/**
 * The pure half of the translation layer, so tests can run it with `node --test`.
 *
 * Fallback order: the selected language, then Vietnamese, then the key itself.
 * A missing translation shows Vietnamese instead of breaking the screen.
 */

import { en } from "./en.js";
import { vi } from "./vi.js";

export const LANGUAGES = Object.freeze(["vi", "en"]);
export const DEFAULT_LANGUAGE = "vi";
export const STORAGE_KEY = "vf-language";

const DICTIONARIES = Object.freeze({ vi, en });
const warned = new Set();

export function normalizeLanguage(value) {
  return LANGUAGES.includes(value) ? value : DEFAULT_LANGUAGE;
}

export function readStoredLanguage() {
  try {
    return normalizeLanguage(globalThis.localStorage?.getItem(STORAGE_KEY));
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

function interpolate(template, vars) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole,
  );
}

export function translate(language, key, vars) {
  const dictionary = DICTIONARIES[normalizeLanguage(language)] ?? vi;
  const value = dictionary[key] ?? vi[key];
  if (value === undefined) {
    if (import.meta.env?.DEV && !warned.has(key)) {
      warned.add(key);
      console.warn(`[i18n] missing key: ${key}`);
    }
    return key;
  }
  return interpolate(value, vars);
}

/** For plain modules that cannot use the hook; callers render inside a component that re-renders on language change. */
export function label(key, vars) {
  return translate(readStoredLanguage(), key, vars);
}
