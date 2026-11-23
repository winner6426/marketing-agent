import { LogOut } from "lucide-react";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Alert, EmptyState, Spinner } from "./components/common/Common.jsx";
import { AppShell } from "./components/layout/AppShell.jsx";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import { CampaignProvider, useCampaigns } from "./context/CampaignContext.jsx";
import { useTranslation } from "./i18n/index.jsx";
import { NAVIGATION_ITEMS, normalizeRole, ROUTES } from "./lib/navigation.js";
import { LoginPage } from "./pages/auth/Login.jsx";
import { RegisterPage } from "./pages/auth/Register.jsx";

const lazyNamed = (load, name) => lazy(() => load().then((module) => ({ default: module[name] })));
const DashboardPage = lazyNamed(() => import("./pages/Dashboard.jsx"), "DashboardPage");
const AIChatPage = lazyNamed(() => import("./pages/AIChat.jsx"), "AIChatPage");
const CampaignsPage = lazyNamed(() => import("./pages/Campaigns.jsx"), "CampaignsPage");
const CampaignDetailPage = lazyNamed(
  () => import("./pages/CampaignDetail.jsx"),
  "CampaignDetailPage",
);

function PublicRoutes() {
  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.register} element={<RegisterPage />} />
      <Route path="*" element={<Navigate to={ROUTES.login} replace />} />
    </Routes>
  );
}

function MarketerWorkspace() {
  const { t } = useTranslation();
  const { error } = useCampaigns();
  return (
    <AppShell>
      {error && <Alert tone="error">{error}</Alert>}
      <Suspense fallback={<Spinner>{t("common.loadingPage")}</Spinner>}>
        <Routes>
          <Route path={ROUTES.dashboard} element={<DashboardPage />} />
          <Route path={ROUTES.aiContent} element={<AIChatPage />} />
          <Route path={ROUTES.campaigns} element={<CampaignsPage />} />
          <Route path={`${ROUTES.campaigns}/:campaignId`} element={<CampaignDetailPage />} />
          {NAVIGATION_ITEMS.filter((item) => !item.migrated).map((item) => (
            <Route
              key={item.path}
              path={item.path}
              element={<NotMigratedPage titleKey={item.labelKey} />}
            />
          ))}
          <Route path="*" element={<Navigate to={ROUTES.dashboard} replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

function NotMigratedPage({ titleKey }) {
  const { t } = useTranslation();
  return (
    <>
      <section className="mb-7 flex items-end justify-between mobile:items-start mobile:gap-[15px]">
        <div>
          <span className="flex items-center gap-1.5 text-[11px] leading-[1.4] font-extrabold tracking-[1.3px] text-[#078457] dark:text-[#63dda8]">
            VF ContentOS
          </span>
          <h1 className="mt-[9px] mb-1.5 text-[36px] leading-[1.2] tracking-[-1.4px] mobile:text-[30px] dark:text-[#e7f5eb]">
            {t(titleKey)}
          </h1>
        </div>
      </section>
      <EmptyState title={t("migration.pageTitle")}>{t("migration.pageBody")}</EmptyState>
    </>
  );
}

/** Manager and admin pages have not been migrated yet. */
function NotMigratedWorkspace() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  return (
    <AppShell>
      <EmptyState
        title={t("migration.roleTitle")}
        action={
          <>
            <LogOut size={15} /> {t("shell.signOut")}
          </>
        }
        onAction={() => signOut().catch(() => {})}
      >
        {t("migration.roleBody")}
      </EmptyState>
    </AppShell>
  );
}

function AuthenticatedApp() {
  const { t } = useTranslation();
  const { session, profile, loading, error, signOut } = useAuth();

  if (loading) return <Spinner>{t("common.checkingSession")}</Spinner>;
  if (!session) return <PublicRoutes />;
  if (!profile) {
    // The session exists but the profile could not be loaded, e.g. the API is unreachable.
    return (
      <EmptyState
        title={error || t("authError.profile")}
        action={t("shell.signOut")}
        onAction={() => signOut().catch(() => {})}
      />
    );
  }
  if (normalizeRole(profile.role) !== "marketer") return <NotMigratedWorkspace />;
  return (
    <CampaignProvider>
      <MarketerWorkspace />
    </CampaignProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}
