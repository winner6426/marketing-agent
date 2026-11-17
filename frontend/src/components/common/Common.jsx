import { ArrowRight, ShieldCheck } from "lucide-react";

import { statusText, statusTone } from "../../lib/status.js";

// Badge colours by status tone; "red" has no colours of its own, as in the original design.
const BADGE_TONES = {
  amber: ["bg-[#fff3da] text-[#906814]", "bg-[#d49a1a]"],
  blue: ["bg-[#e9f1f8] text-[#3c6c91]", "bg-[#4d86ad]"],
  green: ["bg-[#e3f2e6] text-[#376947]", "bg-[#4e8a61]"],
  red: ["", ""],
};

export function StatusBadge({ status, humanWait }) {
  const [badge, dot] = BADGE_TONES[statusTone(status, humanWait)];
  return (
    <span className={`h-[23px] rounded-[20px] px-[9px] py-[5px] text-[11px] leading-[1.35] font-bold ${badge}`}>
      <i className={`mr-[5px] inline-block size-[5px] rounded-full ${dot}`} />
      {statusText(status, humanWait)}
    </span>
  );
}

export function EmptyState({ title, children, action, onAction }) {
  return (
    <div className="border-t border-[#e9ece9] px-5 py-[70px] text-center dark:border-[#294238]">
      <ShieldCheck className="size-[38px] text-[#4f785d]" />
      <h3 className="text-[17px] leading-[1.4]">{title}</h3>
      <p className="text-[14px] leading-[1.65] text-[#7b857e] mobile:text-[13px] dark:text-[#96a69b]">
        {children}
      </p>
      {action && (
        <button
          onClick={onAction}
          className="rounded-lg border border-[#dce1dc] bg-white px-3 py-[9px] text-[13px] leading-[1.45] mobile:text-[12px] dark:border-[#355244] dark:bg-[#1a3026] dark:text-[#c2d5ca]"
        >
          {action} <ArrowRight size={15} />
        </button>
      )}
    </div>
  );
}

const ALERT_TONES = {
  progress:
    "border-[#c9ddce] bg-[#edf5ef] text-[#28563a] dark:border-[#35624d] dark:bg-[#17352a] dark:text-[#bfe4d0]",
  error:
    "border-[#e8bcbc] bg-[#fff0f0] text-[#973b3b] dark:border-[#714043] dark:bg-[#3b2022] dark:text-[#ffb1b1]",
};

/** An inline status line: `progress` shows a pulsing dot, `error` is announced to screen readers. */
export function Alert({ tone = "progress", children }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`mb-3.5 rounded-[10px] border px-[13px] py-[11px] text-[12px] leading-normal ${ALERT_TONES[tone]}`}
    >
      {tone === "progress" && (
        <span className="mr-2 inline-flex">
          <i className="block size-2 rounded-full bg-[#3f8055] shadow-[0_0_0_4px_#3f805522]" />
        </span>
      )}
      {children}
    </div>
  );
}

export function ApiState({ progress, error }) {
  return (
    <>
      {progress && <Alert tone="progress">{progress}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
    </>
  );
}

/** `inContent` uses the page typography; the bare variant is the session check before the app shell. */
export function Spinner({ children, inContent = false }) {
  return (
    <div
      role="status"
      className="flex min-h-[650px] flex-col items-center justify-center p-[50px] text-center mobile:min-h-[520px]"
    >
      <span className="m-5 inline-block size-4 animate-spin-fast rounded-full border-2 border-[#fff5] border-t-white" />
      <p
        className={`max-w-[440px] text-[#78827b] dark:text-[#93aa9d] ${
          inContent ? "text-[14px] leading-[1.65] mobile:text-[13px]" : "text-[11px] leading-[1.7]"
        }`}
      >
        {children}
      </p>
    </div>
  );
}
