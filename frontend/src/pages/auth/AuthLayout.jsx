import { ArrowRight } from "lucide-react";
import { useLayoutEffect } from "react";

import { LanguageSwitch } from "../../components/common/LanguageSwitch.jsx";
import { useTranslation } from "../../i18n/index.jsx";

/** The brand panel and card shared by the login and register pages; the form fields go in `children`. */
export function AuthLayout({ eyebrow, headline1, headline2, blurb, onSubmit, badge, title, subtitle, children }) {
  const { t } = useTranslation();

  // The auth pages are always light, whatever theme the app uses.
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
  }, []);

  return (
    <>
      <LanguageSwitch floating />
      <div className="grid min-h-screen grid-cols-[1.1fr_0.9fr] bg-[#f7f8f5] mobile:grid-cols-1">
        <section className="relative flex flex-col justify-between overflow-hidden bg-[#193d2a] bg-[linear-gradient(90deg,#093325fa,#093325d1),url(/images/vinfast-electric-hero.png)] bg-cover bg-center px-[8vw] py-[46px] text-white after:absolute after:top-[120px] after:right-[-180px] after:size-[480px] after:rounded-full after:border after:border-[#ffffff12] after:shadow-[0_0_0_80px_#ffffff05,0_0_0_160px_#ffffff03] after:content-[''] mobile:hidden">
          <div className="flex items-center gap-2.5 text-[24px] font-extrabold">
            <span className="grid size-10 place-items-center rounded-xl bg-white p-1 text-[#163923]">
              <img src="/images/voltflow-mark.png" alt="VF" className="size-full object-contain" />
            </span>
            VF ContentOS
          </div>
          <div>
            <Eyebrow className="text-[#9cd5ac]">{eyebrow}</Eyebrow>
            <h1 className="my-[17px] text-[45px] leading-[1.12] tracking-[-2px]">
              {headline1}
              <br />
              <em className="text-[#91d6a6] not-italic">{headline2}</em>
            </h1>
            <p className="max-w-[570px] text-[13px] leading-[1.8] text-[#bdd1c3]">{blurb}</p>
          </div>
          <small className="text-[8px] text-[#8ba596]">{t("auth.copyright")}</small>
        </section>
        <section className="grid place-items-center p-[35px] mobile:p-5">
          <form
            onSubmit={onSubmit}
            className="w-[min(410px,100%)] rounded-[18px] bg-white p-[34px] shadow-[0_30px_80px_#0c372223] mobile:p-[26px]"
          >
            <Eyebrow className="text-[#078457]">{badge}</Eyebrow>
            <h2 className="mt-2.5 mb-1.5 text-[24px]">{title}</h2>
            <p className="mb-[25px] text-[10px] text-[#7b867e]">{subtitle}</p>
            {children}
          </form>
        </section>
      </div>
    </>
  );
}

export function Eyebrow({ className = "", children }) {
  return (
    <span
      className={`flex items-center gap-1.5 text-[10px] font-extrabold tracking-[1.3px] ${className}`}
    >
      {children}
    </span>
  );
}

/** A labelled input with a leading icon and an optional trailing control. */
export function AuthField({ id, label, icon: Icon, trailing, ...inputProps }) {
  return (
    <>
      <label htmlFor={id} className="mt-3.5 mb-[7px] block text-[9px] font-extrabold">
        {label}
      </label>
      <div className="flex h-11 items-center gap-2 rounded-[10px] border border-[#dce2dc] px-3">
        <Icon className="w-4 text-[#78847b]" />
        <input
          id={id}
          className="min-w-0 flex-1 bg-transparent text-[10px] outline-0"
          {...inputProps}
        />
        {trailing}
      </div>
    </>
  );
}

export function AuthSubmit({ disabled, children }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className="flex h-[45px] w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(135deg,#075e40,#0e9a65)] text-[10px] font-extrabold text-white shadow-[0_10px_25px_#08724c35] disabled:opacity-55"
    >
      {children}
      <ArrowRight />
    </button>
  );
}

/** A centered line of small text with an inline link-style button. */
export function AuthSwitch({ text, action, onClick, disabled }) {
  return (
    <div className="mt-[15px] text-center text-[8px] text-[#768078]">
      {text}
      {text && " "}
      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        className="font-extrabold text-[#2d6841]"
      >
        {action}
      </button>
    </div>
  );
}
