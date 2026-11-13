import {
  CalendarDays,
  Database,
  LayoutDashboard,
  Megaphone,
  Send,
  Sparkles,
  TrendingUp,
} from "lucide-react";

export const ROUTES = Object.freeze({
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
  aiContent: "/ai-content",
  campaigns: "/campaigns",
  calendar: "/calendar",
  channels: "/channels",
  sources: "/sources",
  performance: "/performance",
});

/**
 * The marketer menu, same as the old app. Items with `migrated: false` keep their place in the
 * menu but open a "not migrated yet" page until they are ported.
 */
export const NAVIGATION_ITEMS = [
  { path: ROUTES.dashboard, labelKey: "nav.dashboard", icon: LayoutDashboard, migrated: true },
  { path: ROUTES.aiContent, labelKey: "nav.aiContent", icon: Sparkles, migrated: true },
  { path: ROUTES.campaigns, labelKey: "nav.campaigns", icon: Megaphone, migrated: true },
  { path: ROUTES.calendar, labelKey: "nav.calendar", icon: CalendarDays, migrated: false },
  { path: ROUTES.channels, labelKey: "nav.channels", icon: Send, migrated: false },
  { path: ROUTES.sources, labelKey: "nav.sources", icon: Database, migrated: false },
  { path: ROUTES.performance, labelKey: "nav.performance", icon: TrendingUp, migrated: false },
];

/** The content studio of one campaign. */
export function campaignPath(campaignId) {
  return `${ROUTES.campaigns}/${campaignId}`;
}

export function normalizeRole(role) {
  return ["admin", "manager", "marketer"].includes(role) ? role : "marketer";
}

/** Manager and admin pages are not migrated, so only marketers get a menu. */
export function navigationForRole(role) {
  return normalizeRole(role) === "marketer" ? NAVIGATION_ITEMS : [];
}
