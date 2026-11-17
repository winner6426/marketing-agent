import { Languages } from "lucide-react";

import { LANGUAGES, useTranslation } from "../../i18n/index.jsx";

const LABELS = { vi: "VI", en: "EN" };

/** `floating` pins it to the top-right corner, as on the login and register pages. */
export function LanguageSwitch({ floating = false }) {
  const { language, setLanguage, t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t("language.group")}
      className={`no-translate isolate z-20 inline-flex h-[42px] items-center gap-[5px] overflow-hidden rounded-[14px] border border-[#c6e2d5] bg-[linear-gradient(135deg,#ffffffeb,#f1faf5e8)] py-1 pr-[5px] pl-1 shadow-[0_8px_22px_#075e4018,inset_0_1px_#fff] before:absolute before:top-[-27px] before:left-[-20px] before:-z-10 before:size-12 before:rounded-full before:bg-[#55cfe03b] before:blur-[5px] before:content-[''] mobile:h-[38px] dark:border-[#2d493d] dark:bg-none dark:bg-[#14261e] dark:text-[#d8e9df] dark:shadow-[0_4px_16px_#0000002e] ${
        floating ? "fixed top-[22px] right-6" : "relative mobile:ml-auto"
      }`}
    >
      <span
        aria-hidden="true"
        className="relative grid size-8 flex-none place-items-center rounded-[10px] border border-[#ffffff9c] bg-[linear-gradient(145deg,#075e40,#0ba971_65%,#55cfe0)] text-white shadow-[0_5px_13px_#087a5535] mobile:size-7"
      >
        <Languages className="size-[17px] stroke-2 mobile:size-[15px]" />
        <i className="absolute right-[3px] bottom-[3px] size-[5px] rounded-full border border-white bg-[#92ffc2] shadow-[0_0_7px_#79ffb6]" />
      </span>
      <span className="inline-flex items-center gap-0.5 rounded-[9px] border border-[#dcebe3] bg-[#eaf4ee] p-0.5 dark:border-[#315244] dark:bg-[#10251c]">
        {LANGUAGES.map((code) => {
          const on = language === code;
          return (
            <button
              key={code}
              type="button"
              aria-pressed={on}
              title={t(`language.${code}`)}
              onClick={() => setLanguage(code)}
              className={`h-[26px] min-w-8 rounded-[7px] px-[7px] text-[10px] font-[850] tracking-[0.08em] transition-[color,background,box-shadow,transform] duration-[180ms] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#55cfe0] active:scale-95 mobile:h-6 mobile:min-w-[29px] mobile:px-1.5 ${
                on
                  ? "bg-[linear-gradient(135deg,#087a55,#10a574)] text-white shadow-[0_4px_9px_#087a5538] [text-shadow:0_1px_1px_#064b35] dark:bg-[linear-gradient(135deg,#16845e,#19ad7b)] dark:text-white"
                  : "text-[#687c71] hover:bg-[#ffffffa8] hover:text-[#075e40] dark:text-[#9cb6aa] dark:hover:bg-[#294639] dark:hover:text-[#e9fff2]"
              }`}
            >
              {LABELS[code]}
            </button>
          );
        })}
      </span>
    </div>
  );
}
