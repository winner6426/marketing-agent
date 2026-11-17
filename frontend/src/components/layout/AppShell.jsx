import {
  ChevronDown,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useTranslation } from "../../i18n/index.jsx";
import { navigationForRole, normalizeRole, ROUTES } from "../../lib/navigation.js";
import { LanguageSwitch } from "../common/LanguageSwitch.jsx";

const THEME_STORAGE_KEY = "vf-contentos:theme";

function readInitialDarkMode() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark";
  } catch {
    return false;
  }
}

// The collapsed sidebar only exists on desktop; on phones the sidebar is a drawer.
const HIDE_WHEN_COLLAPSED =
  "transition-[opacity,width] duration-[160ms,280ms] desktop:pointer-events-none desktop:w-0 desktop:overflow-hidden desktop:opacity-0";

function navButtonClass(active, collapsed) {
  const base =
    "relative flex items-center gap-3 rounded-[10px] border px-[13px] py-[11px] text-left text-[13px] transition-[background,color,border-color,box-shadow,transform] duration-200 hover:translate-x-0.5 [&>svg]:transition-[color,transform] [&>svg]:duration-200";
  const state = active
    ? "border-[#c5e9d7] bg-[linear-gradient(100deg,#d5f3e1,#e8f8f2_62%,#e1f6f6)] font-bold text-[#075e40] shadow-[inset_3px_0_#0aad72,0_9px_22px_#087a5517] [&>svg]:text-[#06a96e] [&>svg]:drop-shadow-[0_3px_6px_#08a76b28] dark:border-[#36765a] dark:bg-[linear-gradient(100deg,#174c36,#19392e)] dark:text-[#f1fff6] dark:shadow-[inset_3px_0_#43d89c,0_8px_22px_#00000029] dark:[&>svg]:text-[#56e2a7]"
    : "border-transparent text-[#506b60] dark:hover:border-[#315a45] dark:hover:bg-[#183327] dark:hover:text-[#f0fbf4] hover:border-[#d3e9dd] hover:bg-[#ffffffb8] hover:text-[#075f42] hover:shadow-[0_8px_20px_#0b674710] dark:text-[#b5c9be] [&>svg]:text-[#5a756a] hover:[&>svg]:scale-[1.08] hover:[&>svg]:text-[#0aa06c]";
  if (!collapsed) return `${base} ${state}`;
  const collapsedState = active
    ? "desktop:border-[#b8e3cf] desktop:bg-[linear-gradient(145deg,#d7f5e3,#e4f7f4)] desktop:shadow-[inset_3px_0_#08aa70,0_9px_20px_#087a5520] dark:desktop:border-[#3d765d] dark:desktop:bg-[linear-gradient(145deg,#1d4c37,#193b30)]"
    : "desktop:border-[#dcece3] desktop:bg-[#ffffff82] desktop:shadow-[0_6px_16px_#173a250b] dark:desktop:border-[#2e4d3f] dark:desktop:bg-[#172e24e0] dark:desktop:shadow-[0_7px_18px_#00000038]";
  return `${base} ${state} ${collapsedState} desktop:mx-auto desktop:h-11 desktop:w-12 desktop:justify-center desktop:gap-0 desktop:rounded-xl desktop:p-0 desktop:hover:-translate-y-0.5 desktop:hover:translate-x-0 desktop:hover:border-[#a9dbc5] desktop:hover:bg-white dark:desktop:hover:border-[#47745f] dark:desktop:hover:bg-[#203d31]`;
}

const HEADER_BUTTON =
  "grid size-[38px] place-items-center rounded-[10px] border bg-white dark:border-[#2d493d] dark:bg-[#14261e] dark:text-[#d8e9df] dark:shadow-[0_4px_16px_#0000002e] dark:hover:border-[#46725e] dark:hover:bg-[#203a2e] dark:hover:text-white";

export function AppShell({ children }) {
  const { t } = useTranslation();
  const { profile, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(readInitialDarkMode);
  const [account, setAccount] = useState(false);
  const role = normalizeRole(profile?.role);
  const navigation = navigationForRole(role);
  const displayName = profile?.full_name || profile?.email || t("shell.user.fallback");
  const initials = displayName.slice(0, 2).toUpperCase();
  const hide = collapsed ? HIDE_WHEN_COLLAPSED : "transition-[opacity,width] duration-[160ms,280ms]";

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, dark ? "dark" : "light");
    } catch {
      // The theme still applies for this visit.
    }
  }, [dark]);

  return (
    <div
      className={`flex min-h-screen bg-slate-50 text-slate-900 ${
        dark
          ? "dark bg-[radial-gradient(circle_at_76%_-8%,#1b6b4c3d,transparent_31%),linear-gradient(145deg,#09130f,#0d1b15_60%,#0b1713)] text-[#edf8f1] [color-scheme:dark] [&_*]:[scrollbar-color:#3a6653_#0d1914] selection:bg-[#147c56] selection:text-[#f6fff9]"
          : ""
      }`}
    >
      <aside
        className={`fixed inset-y-0 left-0 z-10 flex w-[268px] shrink-0 flex-col overflow-hidden border-r border-r-[#cfe4d8] bg-[radial-gradient(circle_at_12%_10%,#dff8eb_0,#0000_25%),radial-gradient(circle_at_100%_43%,#dff7f8_0,#0000_30%),linear-gradient(#fbfefc_0%,#f2f9f5_55%,#f7fbf8_100%)] px-4 py-[22px] shadow-[12px_0_36px_#123c2714] transition-[width,margin-left,transform] duration-[280ms] ease-[cubic-bezier(0.4,0,0.2,1)] before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:bg-[linear-gradient(90deg,#0000_0_94%,#ffffff70)] before:content-[''] mobile:w-[280px] mobile:shadow-[0_0_40px_#14291b33] mobile:transition-all mobile:duration-[250ms] mobile:ease-[ease] dark:border-r-[#29463a] dark:bg-[radial-gradient(circle_at_0_12%,#19704d42,#0000_29%),linear-gradient(#102119,#0b1712_76%)] dark:text-[#edf8f1] dark:shadow-[14px_0_36px_#00000040] ${
          menu ? "mobile:translate-x-0" : "mobile:-translate-x-full"
        } ${
          collapsed
            ? "group/aside desktop:w-[76px] desktop:overflow-visible desktop:px-2.5 desktop:py-3.5 desktop:bg-[radial-gradient(circle_at_50%_3%,#d9f6e7,#0000_20%),radial-gradient(circle_at_90%_52%,#dff7f8,#0000_31%),linear-gradient(#f9fdfb,#edf7f1_58%,#f6faf7)] dark:desktop:bg-[radial-gradient(circle_at_0_12%,#19704d42,#0000_29%),linear-gradient(#102119,#0b1712_76%)]"
            : ""
        }`}
      >
        <div
          className={`group/brand relative -mx-px -mt-[5px] mb-4 flex items-center gap-[11px] overflow-hidden rounded-[15px] border border-[#ffffff1f] bg-[linear-gradient(145deg,#064831_0%,#086b49_62%,#078d67_135%)] px-3 py-[13px] text-white shadow-[0_14px_30px_#06463032] after:pointer-events-none after:absolute after:top-[-66px] after:right-[-56px] after:size-[120px] after:rounded-full after:bg-[radial-gradient(circle,#63e6bd55,#0000_68%)] after:content-[''] dark:border-[#6de5ae2e] dark:bg-[linear-gradient(135deg,#07583e,#087b55_64%,#116354)] dark:text-[#f4fff8] dark:shadow-[0_14px_32px_#00000052] ${
            collapsed
              ? "desktop:m-0 desktop:h-[58px] desktop:min-h-[58px] desktop:justify-center desktop:overflow-visible desktop:rounded-[17px] desktop:border-0 desktop:bg-[linear-gradient(145deg,#064831,#087856)] desktop:p-2 desktop:shadow-[0_12px_27px_#0646302b]"
              : ""
          }`}
        >
          <div
            className={`relative z-[1] grid size-[38px] place-items-center rounded-xl bg-white p-[3px] text-[#72ef9d] shadow-[0_8px_20px_#002f2238] ${
              collapsed ? "desktop:size-[42px] desktop:flex-none desktop:rounded-[13px] desktop:shadow-[0_7px_18px_#075e4030]" : ""
            }`}
          >
            <img src="/images/voltflow-mark.png" alt="VF" className="size-full object-contain" />
          </div>
          <div className={`relative z-[1] ${hide}`}>
            <b className="block text-[21px] tracking-[-1px]">VF ContentOS</b>
            <small className="mt-0.5 block text-[11px] text-[#a8d7b9] dark:text-[#b3d8c4]">
              AI Marketing Platform
            </small>
          </div>
          <button
            title={t(collapsed ? "shell.sidebar.expand" : "shell.sidebar.collapse")}
            aria-label={t(collapsed ? "shell.sidebar.expand" : "shell.sidebar.collapse")}
            onClick={() => setCollapsed((value) => !value)}
            className={`invisible absolute top-1/2 z-[1] grid -translate-y-1/2 scale-[0.92] place-items-center opacity-0 transition-[opacity,visibility,background,transform] duration-[180ms] focus-visible:visible focus-visible:scale-100 focus-visible:opacity-100 mobile:hidden ${
              collapsed
                ? "-right-2 z-[2] size-7 rounded-full border border-[#a9cfb8] bg-white text-[#176144] shadow-[0_5px_14px_#173a2528] group-hover/aside:visible group-hover/aside:scale-100 group-hover/aside:opacity-100 dark:border-[#438067] dark:bg-[#173c2d] dark:text-[#dff8ea] dark:shadow-[0_7px_18px_#00000057]"
                : "right-[9px] size-8 rounded-[9px] border border-[#ffffff36] bg-[#ffffff16] text-white group-hover/brand:visible group-hover/brand:scale-100 group-hover/brand:opacity-100 hover:bg-[#ffffff28]"
            }`}
          >
            {collapsed ? <PanelLeftOpen className="w-[17px]" /> : <PanelLeftClose className="w-[17px]" />}
          </button>
          <button className="ml-auto hidden mobile:grid" onClick={() => setMenu(false)}>
            <X />
          </button>
        </div>
        <div
          className={`relative flex items-center gap-[9px] overflow-hidden rounded-[14px] border border-[#bfe6d6] bg-[linear-gradient(135deg,#ffffffdc,#eafaf4_55%,#e8f8fb)] p-[11px] shadow-[0_10px_25px_#0b674714] transition-[transform,border-color,box-shadow] duration-200 before:absolute before:top-[-38px] before:right-[-35px] before:size-[76px] before:rounded-full before:bg-[radial-gradient(circle,#55cfe052,#0000_68%)] before:content-[''] hover:-translate-y-0.5 hover:border-[#6bc9a8] hover:shadow-[0_14px_30px_#0b67471f] dark:border-[#2b5b49] dark:bg-[linear-gradient(135deg,#173529,#122a23_60%,#14343a)] dark:text-[#edf8f1] dark:shadow-[0_10px_27px_#0005] dark:hover:border-[#3f9271] dark:hover:shadow-[0_14px_32px_#0007] ${
            collapsed ? "desktop:hidden" : ""
          }`}
        >
          <div className="grid size-[35px] flex-none place-items-center rounded-[9px] border border-[#ffffffba] bg-[linear-gradient(145deg,#087a55,#27b88a_62%,#55cfe0)] text-[12px] font-bold text-white shadow-[0_7px_17px_#087a5533]">
            VX
          </div>
          <div className="relative min-w-0">
            <span className="mb-[3px] flex items-center gap-[5px] text-[7px] font-extrabold tracking-[0.55px] text-[#078457] uppercase dark:text-[#67e3ab]">
              <i className="size-1.5 rounded-full bg-[#16b978] shadow-[0_0_0_3px_#16b9781c]" />
              {t("shell.workspace.active")}
            </span>
            <b className="text-[12px] tracking-[-0.15px] text-[#123d35] dark:text-[#eaf9f0]">
              {t("shell.workspace.name")}
            </b>
            <small className="mt-0.5 block text-[11px] text-[#658079] dark:text-[#9bb2a6]">
              {t("shell.workspace.branch")}
            </small>
          </div>
          <ChevronDown size={16} className="ml-auto" />
        </div>
        <p
          className={`px-3 pt-3.5 pb-1.5 text-[10px] font-bold tracking-[1.5px] text-[#779186] dark:text-[#789486] ${hide}`}
        >
          {t("shell.navLabel")}
        </p>
        <nav
          className={`flex min-h-0 flex-1 flex-col gap-[3px] ${collapsed ? "desktop:mt-[42px] desktop:gap-2" : ""}`}
        >
          {navigation.map(({ path, labelKey, icon: Icon }) => {
            const label = t(labelKey);
            return (
              <button
                key={path}
                title={collapsed ? label : undefined}
                aria-label={label}
                className={navButtonClass(location.pathname === path, collapsed)}
                onClick={() => {
                  navigate(path);
                  setMenu(false);
                }}
              >
                <Icon size={19} className="flex-none" />
                <span className={hide}>{label}</span>
              </button>
            );
          })}
        </nav>
        <div
          className={`mt-auto border-t border-[#d9e9df] pt-2 dark:border-[#213c30] ${collapsed ? "desktop:mx-[7px] desktop:pt-2.5" : ""}`}
        >
          <button
            onClick={() => setAccount(!account)}
            className={`mt-[5px] flex w-full items-center gap-3 rounded-xl px-[13px] py-[11px] text-left text-[13px] text-[#5f6b63] transition-[background,box-shadow] duration-200 hover:bg-[#ffffffc4] hover:shadow-[0_8px_20px_#173a250e] dark:text-[#b5c9be] dark:hover:bg-[#183327] dark:hover:text-[#f0fbf4] ${
              collapsed
                ? "desktop:m-auto desktop:size-[42px] desktop:justify-center desktop:gap-0 desktop:border desktop:border-[#d9e9df] desktop:bg-[#ffffff9c] desktop:p-[3px] desktop:shadow-[0_7px_18px_#173a2510] dark:desktop:border-[#2f4c3f] dark:desktop:bg-[#152a21] dark:desktop:shadow-[0_7px_20px_#00000038]"
                : ""
            }`}
          >
            <div
              className={`grid size-[35px] flex-none place-items-center rounded-full bg-[#345542] text-[12px] font-bold text-white ${collapsed ? "desktop:size-9" : ""}`}
            >
              {initials}
            </div>
            <div className={`min-w-0 ${hide}`}>
              <b className="block text-[12px]">{displayName}</b>
              <small className="mt-0.5 block text-[11px] text-[#758078] dark:text-[#96a69b]">
                {role}
              </small>
            </div>
            <ChevronDown size={15} className={`ml-auto ${collapsed ? "desktop:hidden" : ""}`} />
          </button>
          {account && (
            <div
              className={`absolute z-20 rounded-[11px] border border-[#dde3dd] bg-white p-[5px] shadow-[0_12px_30px_#1833211f] dark:border-[#335143] dark:bg-[#14251e] dark:text-[#edf8f1] dark:shadow-[0_18px_42px_#0000006b] ${
                collapsed
                  ? "right-4 bottom-[75px] left-4 desktop:right-auto desktop:bottom-[18px] desktop:left-[66px] desktop:w-[180px]"
                  : "right-4 bottom-[75px] left-4"
              }`}
            >
              <AccountMenuButton onClick={() => setDark(!dark)}>
                {dark ? <Sun className="w-[15px]" /> : <Moon className="w-[15px]" />}
                {t(dark ? "shell.theme.light" : "shell.theme.dark")}
              </AccountMenuButton>
              <AccountMenuButton onClick={() => signOut().catch(() => {})}>
                <LogOut className="w-[15px]" />
                {t("shell.signOut")}
              </AccountMenuButton>
            </div>
          )}
        </div>
      </aside>
      <main
        className={`ml-[268px] w-[calc(100%-268px)] min-w-0 flex-1 transition-[width,margin-left,transform] duration-[280ms] ease-[cubic-bezier(0.4,0,0.2,1)] mobile:ml-0 mobile:w-full ${
          collapsed ? "desktop:ml-[76px] desktop:w-[calc(100%-76px)]" : ""
        }`}
      >
        <header className="sticky top-0 z-[5] flex h-12 items-center justify-between border-b border-[#dfe9e2] bg-[#ffffffc9] px-[38px] shadow-[0_6px_22px_#153a2410] backdrop-blur-[8px] mobile:h-[46px] mobile:px-[17px] dark:border-[#29463a] dark:bg-[#0c1a14eb] dark:text-[#edf8f1] dark:shadow-[0_8px_28px_#00000038]">
          <button className={`${HEADER_BUTTON} hidden border-[#e4e8e3] mobile:grid`} onClick={() => setMenu(true)}>
            <Menu />
          </button>
          <div className="flex items-center gap-2 text-[9px] text-[#647067] opacity-[0.78]">
            <span className="rounded-[20px] border border-[#cfe6d7] bg-[linear-gradient(100deg,#f2fbf5,#e7f7ed)] px-2.5 py-[7px] mobile:hidden dark:border-[#2e4a3d] dark:bg-none dark:bg-[#13281f] dark:text-[#b9d3c5]">
              <i className="mr-[5px] inline-block size-1.5 rounded-full bg-[#4c9663] dark:bg-[#45d99c] dark:shadow-[0_0_0_4px_#45d99c1f]" />
              <b>{t("shell.runtime.ready")}</b>
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <LanguageSwitch />
            <button
              type="button"
              aria-pressed={dark}
              title={t(dark ? "shell.theme.toLight" : "shell.theme.toDark")}
              aria-label={t(dark ? "shell.theme.toLight" : "shell.theme.toDark")}
              onClick={() => setDark(!dark)}
              className={`${HEADER_BUTTON} border-[#e0e5e0]`}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            {role === "marketer" && (
              <button
                aria-label={t("nav.campaigns")}
                onClick={() => navigate(ROUTES.campaigns)}
                className={`${HEADER_BUTTON} border-[#e4e8e3] mobile:hidden`}
              >
                <Search size={19} />
              </button>
            )}
            <button
              onClick={() => setAccount(!account)}
              className="grid size-[35px] place-items-center rounded-full bg-[#345542] text-[12px] font-bold text-white"
            >
              {initials}
            </button>
          </div>
        </header>
        {/* The chat page (marked `chat-page`) fills the whole width with a thin frame. */}
        <div className="mx-auto w-full max-w-[1500px] p-10 mobile:px-4 mobile:py-6 has-[.chat-page]:max-w-none has-[.chat-page]:px-2 has-[.chat-page]:py-[7px] mobile:has-[.chat-page]:p-[5px]">
          {children}
        </div>
      </main>
    </div>
  );
}

function AccountMenuButton({ onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-[9px] rounded-[7px] p-2.5 text-left text-[10px] dark:hover:bg-[#20392e]"
    >
      {children}
    </button>
  );
}
