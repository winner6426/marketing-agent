import { LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert } from "../../components/common/Common.jsx";
import { DEV_LOGIN_ENABLED, useAuth } from "../../context/AuthContext.jsx";
import { useTranslation } from "../../i18n/index.jsx";
import { ROUTES } from "../../lib/navigation.js";
import { AuthField, AuthLayout, AuthSubmit, AuthSwitch } from "./AuthLayout.jsx";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { signIn, signInAsDev, busy, error, clearError } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!busy) await signIn(email, password).catch(() => {});
  }

  return (
    <AuthLayout
      eyebrow={t("auth.brandEyebrow")}
      headline1={t("auth.login.headline1")}
      headline2={t("auth.login.headline2")}
      blurb={t("auth.login.blurb")}
      badge={t("auth.login.welcome")}
      title={t("auth.login.title")}
      subtitle={t("auth.login.subtitle")}
      onSubmit={submit}
    >
      <AuthField
        id="login-email"
        label={t("auth.field.email")}
        icon={Mail}
        autoComplete="email"
        type="email"
        placeholder={t("auth.placeholder.email")}
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />
      <AuthField
        id="login-password"
        label={t("auth.field.password")}
        icon={LockKeyhole}
        autoComplete="current-password"
        type={showPassword ? "text" : "password"}
        placeholder={t("auth.placeholder.password")}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
        trailing={
          <button
            type="button"
            className="text-[8px] text-[#3c6b49]"
            onClick={() => setShowPassword(!showPassword)}
          >
            {t(showPassword ? "auth.password.hide" : "auth.password.show")}
          </button>
        }
      />
      {error && <Alert tone="error">{error}</Alert>}
      <AuthSubmit disabled={busy || !email.trim() || !password}>
        {busy ? t("auth.login.submitting") : t("auth.login.submit")}
      </AuthSubmit>
      <AuthSwitch
        text={t("auth.login.noAccount")}
        action={t("auth.register.link")}
        onClick={() => {
          clearError();
          navigate(ROUTES.register);
        }}
      />
      {DEV_LOGIN_ENABLED && (
        <AuthSwitch
          action={t("auth.login.devMarketer")}
          disabled={busy}
          onClick={() => signInAsDev("marketer").catch(() => {})}
        />
      )}
    </AuthLayout>
  );
}
