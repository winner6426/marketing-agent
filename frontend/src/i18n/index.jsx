import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_LANGUAGE,
  LANGUAGES,
  normalizeLanguage,
  readStoredLanguage,
  STORAGE_KEY,
  translate,
} from "./translate.js";

export { LANGUAGES };

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [language, setLanguageState] = useState(readStoredLanguage);

  useEffect(() => {
    document.documentElement.lang = language;
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // The interface still works when the browser blocks storage.
    }
  }, [language]);

  const setLanguage = useCallback((next) => setLanguageState(normalizeLanguage(next)), []);
  const value = useMemo(
    () => ({ language, setLanguage, t: (key, vars) => translate(language, key, vars) }),
    [language, setLanguage],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useTranslation() {
  const context = useContext(I18nContext);
  if (context === null) {
    return {
      language: DEFAULT_LANGUAGE,
      setLanguage: () => {},
      t: (key, vars) => translate(DEFAULT_LANGUAGE, key, vars),
    };
  }
  return context;
}
