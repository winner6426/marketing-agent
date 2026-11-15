import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useTranslation } from "../i18n/index.jsx";
import { api } from "../services/api.js";

const AuthContext = createContext(null);
const STORAGE_KEY = "vf-contentos:session";
// Refresh this long before the access token expires.
const REFRESH_MARGIN_MS = 60 * 1000;
// Pairs with the backend's AUTH_DEV_BYPASS: a `dev:<role>` token is accepted without Supabase.
// Only available in the Vite dev server, never in a production build.
export const DEV_LOGIN_ENABLED =
  Boolean(import.meta.env?.DEV) && import.meta.env?.VITE_AUTH_DEV_BYPASS === "true";

function readStoredSession() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
    if (stored?.dev) return DEV_LOGIN_ENABLED ? stored : null;
    return stored?.access_token && stored?.refresh_token ? stored : null;
  } catch {
    return null;
  }
}

function storeSession(session) {
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Without storage the session simply ends with the tab.
  }
}

function sessionFrom(payload) {
  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_at: Date.now() + Number(payload.expires_in ?? 3600) * 1000,
  };
}

export function AuthProvider({ children }) {
  const { t } = useTranslation();
  const [session, setSessionState] = useState(readStoredSession);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(() => Boolean(readStoredSession()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const setSession = useCallback((next) => {
    storeSession(next);
    setSessionState(next);
    if (!next) setProfile(null);
  }, []);

  const refresh = useCallback(
    async (refreshToken) => {
      try {
        const payload = await api.refresh(refreshToken);
        const next = sessionFrom(payload);
        setSession(next);
        return next;
      } catch {
        setSession(null);
        return null;
      }
    },
    [setSession],
  );

  // Restore a stored session: refresh it if it has expired, then load the profile.
  useEffect(() => {
    const stored = readStoredSession();
    if (!stored) return undefined;
    let active = true;
    (async () => {
      const usable =
        stored.dev || stored.expires_at - Date.now() > REFRESH_MARGIN_MS
          ? stored
          : await refresh(stored.refresh_token);
      if (!usable) return;
      try {
        const me = await api.getMe(usable.access_token);
        if (active) setProfile(me);
      } catch (caught) {
        if (!active) return;
        if (caught.status === 401) {
          const renewed = await refresh(usable.refresh_token);
          if (renewed && active) setProfile(await api.getMe(renewed.access_token).catch(() => null));
        } else {
          setError(caught.message || t("authError.profile"));
        }
      }
    })().finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // Runs once on mount; later sessions come from signIn/signUp.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the access token fresh while the app is open.
  useEffect(() => {
    if (!session?.refresh_token || session.dev) return undefined;
    const delay = Math.max(0, session.expires_at - Date.now() - REFRESH_MARGIN_MS);
    const timer = window.setTimeout(() => refresh(session.refresh_token), delay);
    return () => window.clearTimeout(timer);
  }, [session, refresh]);

  async function run(action, fallbackKey) {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (caught) {
      setError(caught?.message || t(fallbackKey));
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  const signIn = (email, password) =>
    run(async () => {
      const payload = await api.login(email.trim().toLowerCase(), password);
      setProfile(payload.user);
      setSession(sessionFrom(payload));
      return payload;
    }, "authError.signIn");

  const signInAsDev = (role) =>
    run(async () => {
      const next = { access_token: `dev:${role}`, refresh_token: null, dev: true };
      setProfile(await api.getMe(next.access_token));
      setSession(next);
    }, "authError.signIn");

  const signUp = ({ name, email, password }) =>
    run(async () => {
      const payload = await api.register({
        email: email.trim().toLowerCase(),
        password,
        fullName: name.trim().normalize("NFC"),
      });
      if (!payload.email_confirmation_required && payload.access_token) {
        setProfile(payload.user);
        setSession(sessionFrom(payload));
      }
      return payload;
    }, "authError.signUp");

  const signOut = () =>
    run(async () => {
      const token = session?.access_token;
      setSession(null);
      // Local sign-out must succeed even if the server call fails.
      if (token) await api.logout(token).catch(() => {});
    }, "authError.signOut");

  const value = useMemo(
    () => ({
      session,
      profile,
      loading,
      busy,
      error,
      signIn,
      signInAsDev,
      signUp,
      signOut,
      clearError: () => setError(""),
    }),
    // The action functions only read state through closures recreated on each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session, profile, loading, busy, error],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
