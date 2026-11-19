import { LockKeyhole, Mail, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert } from "../../components/common/Common.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { useTranslation } from "../../i18n/index.jsx";
import { ROUTES } from "../../lib/navigation.js";
import { AuthField, AuthLayout, AuthSubmit, AuthSwitch } from "./AuthLayout.jsx";

// Must match the backend's RegisterRequest limits.
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 72;

export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { signUp, busy, error, clearError } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");

  async function submit(event) {
    event.preventDefault();
    setConfirmation("");
    const data = await signUp({ name, email, password }).catch(() => null);
    if (data?.email_confirmation_required) setConfirmation(t("auth.register.confirmEmail"));
  }

  return (
    <AuthLayout
      eyebrow={t("auth.register.eyebrow")}
      headline1={t("auth.register.headline1")}
      headline2={t("auth.register.headline2")}
      blurb={t("auth.register.blurb")}
      badge={t("auth.register.badge")}
      title={t("auth.register.title")}
      subtitle={t("auth.register.subtitle")}
      onSubmit={submit}
    >
      <AuthField
        id="register-name"
        label={t("auth.field.name")}
        icon={UserRound}
        autoComplete="name"
        placeholder={t("auth.placeholder.name")}
        maxLength={200}
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
      />
      <AuthField
        id="register-email"
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
        id="register-password"
        label={t("auth.field.password")}
        icon={LockKeyhole}
        autoComplete="new-password"
        type="password"
        placeholder={t("auth.placeholder.newPassword")}
        minLength={MIN_PASSWORD_LENGTH}
        maxLength={MAX_PASSWORD_LENGTH}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      {confirmation && <Alert tone="progress">{confirmation}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
      <AuthSubmit
        disabled={busy || !name.trim() || !email.trim() || password.length < MIN_PASSWORD_LENGTH}
      >
        {busy ? t("auth.register.submitting") : t("auth.register.submit")}
      </AuthSubmit>
      <AuthSwitch
        text={t("auth.register.hasAccount")}
        action={t("auth.login.link")}
        onClick={() => {
          clearError();
          navigate(ROUTES.login);
        }}
      />
    </AuthLayout>
  );
}
