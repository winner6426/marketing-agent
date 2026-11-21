import { ArrowRight, BarChart3, Car, Clock3, Megaphone, ShieldCheck, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState, Spinner, StatusBadge } from "../components/common/Common.jsx";
import { useCampaigns } from "../context/CampaignContext.jsx";
import { useTranslation } from "../i18n/index.jsx";
import { presentCampaign } from "../lib/campaign-presenters.js";
import { campaignPath, ROUTES } from "../lib/navigation.js";
import { campaignProgress, sortByCreationNewestFirst } from "../lib/status.js";

const RECENT_COUNT = 3;
// The three deterministic validation tiers every piece of content passes through.
const VALIDATION_TIER_COUNT = 3;

// Dashboard cards share one dark surface.
const DARK_CARD =
  "dark:border-[#29463a] dark:bg-[linear-gradient(145deg,#172920,#111e18)] dark:text-[#edf8f1] dark:shadow-[0_14px_34px_#0000002e]";

// The accent stripe on top of each recent-campaign card, by position.
const CARD_ACCENTS = [
  "before:bg-[linear-gradient(90deg,#2c7650,#9bd3ac)]",
  "before:bg-[linear-gradient(90deg,#47b8cf,#79ddcb)]",
  // The third card is hidden on tablets, where the grid has two columns.
  "before:bg-[linear-gradient(90deg,#d5a94d,#f0d28b)] max-[1050px]:hidden mobile:block",
];

// Stat tile background and corner blob, by position.
const STAT_TONES = [
  "bg-[linear-gradient(145deg,#fff,#e9f7ee)] after:bg-[#2eb875]",
  "bg-[linear-gradient(145deg,#fff,#fff6e6)] after:bg-[#e4ad42]",
  "bg-[linear-gradient(145deg,#fff,#e9f7f9)] after:bg-[#39b9cb]",
  "bg-[linear-gradient(145deg,#fff,#f0ecfa)] after:bg-[#8269c8]",
];

function CampaignCard({ campaign, index, onOpen }) {
  const { t } = useTranslation();
  const view = presentCampaign(campaign);
  return (
    <article
      onClick={onOpen}
      className={`relative overflow-hidden rounded-2xl border border-[#dfebe2] bg-[linear-gradient(160deg,#fff_65%,#f4f9f5)] p-[19px] shadow-[0_10px_28px_#173c2510] transition-all duration-200 before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:opacity-80 before:content-[''] hover:-translate-y-[5px] hover:border-[#b9cbbb] hover:shadow-[0_20px_40px_#153b2522] ${DARK_CARD} ${CARD_ACCENTS[index]}`}
    >
      <div className="flex justify-between">
        <div className="grid size-[42px] place-items-center rounded-xl bg-[linear-gradient(145deg,#e8f4eb,#f7f2e7)] text-[#31563e] dark:bg-[linear-gradient(145deg,#1c392c,#182921)] dark:text-[#83deb1]">
          <Car />
        </div>
        <StatusBadge status={campaign.status} />
      </div>
      <h3
        title={view.displayName}
        className="mt-[17px] mb-1.5 line-clamp-2 min-h-[38px] text-[17px] leading-[1.4]"
      >
        {view.displayName}
      </h3>
      <p className="mt-[7px] min-h-[30px] text-[14px] leading-[1.65] font-bold text-[#425e4d] mobile:text-[13px] dark:text-[#93aa9d]">
        {view.purpose || view.context || t("dashboard.goalMissing")}
      </p>
      <div className="mt-2 flex min-h-[34px] flex-wrap content-start gap-x-[11px] gap-y-[5px] text-[#758078] dark:text-[#96a69b]">
        {view.purpose && view.context && <Fact>{view.context}</Fact>}
        {view.dateRange && (
          <Fact>
            <Clock3 size={12} />
            {view.dateRange}
          </Fact>
        )}
      </div>
      <div className="my-2.5 flex items-center gap-[5px]">
        <small className="min-w-0 truncate text-[12px] leading-normal text-[#879089] dark:text-[#96a69b]">
          {t("campaignCard.createdBy", {
            who: campaign.created_by || t("campaignCard.currentAccount"),
          })}
        </small>
        <b className="ml-auto text-[10px] whitespace-nowrap text-[#788079]">
          {t("campaignCard.openToView")}
        </b>
      </div>
      <div className="h-1 rounded-[5px] bg-[#edf0ec] dark:bg-[#253a30]">
        <i
          className="block h-full rounded-[5px] bg-[#4c765b] dark:bg-[#48ca92]"
          style={{ width: `${campaignProgress(campaign.status)}%` }}
        />
      </div>
      <footer className="mt-[17px] flex items-center justify-between border-t border-[#eef0ed] pt-[13px]">
        <span className="flex items-center gap-[5px] text-[11px] leading-normal text-[#879089]">
          DB #{campaign.campaign_id}
        </span>
        <button
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
          className="flex items-center gap-[5px] text-[13px] leading-[1.45] font-bold text-[#355e43] mobile:text-[12px]"
        >
          {t("campaignCard.viewDetail")} <ArrowRight size={15} />
        </button>
      </footer>
    </article>
  );
}

function Fact({ children }) {
  return <span className="flex items-center gap-1 text-[9px] leading-[1.35]">{children}</span>;
}

function Stat({ n, label, icon: Icon, index }) {
  return (
    <div
      className={`relative flex justify-between overflow-hidden rounded-[15px] p-5 shadow-[0_12px_30px_#16392312] after:absolute after:right-[-28px] after:bottom-[-40px] after:size-20 after:rounded-full after:opacity-[0.18] after:content-[''] mobile:p-3.5 ${STAT_TONES[index]} ${DARK_CARD}`}
    >
      <div>
        <span className="block text-[12px] text-[#768078] dark:text-[#93aa9d]">{label}</span>
        <strong className="mt-[7px] block text-[27px] mobile:text-[22px]">{n}</strong>
      </div>
      <div className="grid size-[38px] place-items-center rounded-[10px] bg-[#ffffffb5] text-[#4d7059] shadow-[0_5px_14px_#183b2612] mobile:hidden dark:bg-[#1e3a2e] dark:text-[#73dfad]">
        <Icon />
      </div>
    </div>
  );
}

const HERO_BUTTON =
  "flex h-11 items-center gap-2 rounded-[11px] px-4 text-[13px] leading-[1.45] font-extrabold mobile:text-[12px]";

export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { campaigns, loadingList } = useCampaigns();
  const recent = useMemo(
    () => sortByCreationNewestFirst(campaigns).slice(0, RECENT_COUNT),
    [campaigns],
  );
  const waiting = campaigns.filter((campaign) => campaign.status === "waiting_approval").length;
  const published = campaigns.filter((campaign) => campaign.status === "published").length;
  const openAiContent = () => navigate(ROUTES.aiContent);
  const openCampaigns = () => navigate(ROUTES.campaigns);
  const stats = [
    [campaigns.length, t("dashboard.statTotal"), Megaphone],
    [waiting, t("queue.title"), Clock3],
    [published, t("dashboard.statPublished"), ShieldCheck],
    [VALIDATION_TIER_COUNT, t("dashboard.statTiers"), BarChart3],
  ];

  return (
    <>
      <section className="relative mb-[22px] min-h-[410px] overflow-hidden rounded-[23px] bg-[linear-gradient(90deg,#04352afa_0%,#04352ae6_34%,#04352a2e_67%,#04352a0d_100%),url(/images/vinfast-electric-hero.png)] bg-cover bg-center px-[50px] py-12 text-white shadow-[0_20px_50px_#163c2926] mobile:min-h-[470px] mobile:bg-[62%_center] mobile:px-6 mobile:py-[33px] mobile:after:absolute mobile:after:inset-x-0 mobile:after:top-[45%] mobile:after:bottom-0 mobile:after:bg-[linear-gradient(#0000,#073a2caa)] mobile:after:content-[''] dark:shadow-[0_20px_50px_#0007]">
        <div className="relative z-[2] max-w-[520px]">
          <span className="flex items-center gap-1.5 text-[11px] leading-[1.4] font-extrabold tracking-[1.3px] text-[#a8dfb8] dark:text-[#63dda8]">
            <Sparkles size={14} /> {t("dashboard.heroEyebrow")}
          </span>
          <h1 className="mt-[17px] mb-3.5 text-[36px] leading-[1.08] tracking-[-2.3px] mobile:text-[30px]">
            {t("dashboard.heroLine1")}
            <br />
            <em className="text-[#9fe1b4] not-italic">{t("dashboard.heroLine2")}</em>
          </h1>
          <p className="max-w-[480px] text-[14px] leading-[1.65] text-[#d1e1d5] mobile:text-[13px] dark:text-[#96a69b]">
            {t("dashboard.heroLead")}
          </p>
          <div className="mt-[25px] flex gap-[9px] mobile:flex-col mobile:items-start">
            <button className={`${HERO_BUTTON} bg-[#f3fff6] text-[#17492d]`} onClick={openAiContent}>
              <Sparkles />
              {t("dashboard.ctaAi")}
            </button>
            <button
              className={`${HERO_BUTTON} border border-[#ffffff42] bg-[#ffffff0d] text-white backdrop-blur-[7px] mobile:bg-[#164d38cc]`}
              onClick={openAiContent}
            >
              {t("dashboard.ctaStudio")} <ArrowRight />
            </button>
          </div>
          <footer className="mt-[33px] flex gap-[18px] mobile:flex-wrap">
            <HeroFact>
              <Car className="w-[13px]" />
              {t("dashboard.car")}
            </HeroFact>
            <HeroFact>{t("dashboard.motorbike")}</HeroFact>
            <HeroFact>
              <ShieldCheck className="w-[13px]" />
              {t("dashboard.verified")}
            </HeroFact>
          </footer>
        </div>
        <div className="absolute right-[30px] bottom-[27px] flex items-center gap-[9px] rounded-[14px] bg-[#ffffffed] px-4 py-3 text-[#173b29] shadow-[0_10px_25px_#0e2c1b33] mobile:right-[18px] mobile:bottom-[18px]">
          <b className="text-[23px]">{String(campaigns.length).padStart(2, "0")}</b>
          <span className="text-[8px] leading-[1.45]">
            {t("dashboard.badgeLine1")}
            <br />
            {t("dashboard.badgeLine2")}
          </span>
        </div>
      </section>
      <section className="flex items-center gap-[13px] rounded-[15px] border border-[#c5dfce] bg-[linear-gradient(100deg,#edf9f1,#f5fbf7)] px-5 py-[17px] shadow-[0_8px_20px_#17472a0c] mobile:items-start dark:border-[#29463a] dark:bg-[linear-gradient(145deg,#172920,#111e18)] dark:text-[#edf8f1] dark:shadow-[0_14px_34px_#0000002e]">
        <div className="grid size-[39px] place-items-center rounded-[11px] bg-[#d5e6d8] text-[#315c40]">
          <ShieldCheck />
        </div>
        <div>
          <b className="text-[13px]">{t("dashboard.checkedNote")}</b>
          <p className="mt-1 text-[14px] leading-[1.65] text-[#758078] mobile:text-[13px] dark:text-[#9fb4a8]">
            {t("queue.trackNote")}
          </p>
        </div>
      </section>
      <div className="mt-[22px] mb-9 grid grid-cols-4 gap-4 max-[1050px]:grid-cols-2 mobile:gap-[9px]">
        {stats.map(([n, label, icon], index) => (
          <Stat key={label} n={n} label={label} icon={icon} index={index} />
        ))}
      </div>
      <section className="mb-4 flex items-end justify-between mobile:items-start">
        <div>
          <h2 className="mb-[5px] text-[23px] mobile:text-[21px] dark:text-[#edf8f1]">
            {t("dashboard.recent")}
          </h2>
          <p className="text-[14px] leading-[1.65] text-[#768078] mobile:text-[13px] dark:text-[#93aa9d]">
            {t("dashboard.recentNote")}
          </p>
        </div>
        <button
          onClick={openCampaigns}
          className="rounded-[10px] border border-[#dce1dc] bg-white px-[17px] py-[11px] text-[13px] leading-[1.45] mobile:text-[12px] dark:border-[#344238] dark:bg-[#202b22] dark:text-[#dce7df] dark:hover:border-[#3a6854] dark:hover:bg-[#20382d] dark:hover:text-[#edf8f1]"
        >
          {t("dashboard.viewAll")}
        </button>
      </section>
      {loadingList && !campaigns.length ? (
        <Spinner inContent>{t("campaigns.loading")}</Spinner>
      ) : recent.length ? (
        <div className="grid grid-cols-3 gap-[15px] max-[1050px]:grid-cols-2 mobile:grid-cols-1">
          {recent.map((campaign, index) => (
            <CampaignCard
              key={campaign.campaign_id}
              campaign={campaign}
              index={index}
              onOpen={() => navigate(campaignPath(campaign.campaign_id))}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t("dashboard.empty")}
          action={t("dashboard.emptyCta")}
          onAction={openAiContent}
        >
          {t("dashboard.emptyBody")}
        </EmptyState>
      )}
    </>
  );
}

function HeroFact({ children }) {
  return (
    <span className="flex items-center gap-[5px] text-[8px] text-[#c0d7c7]">{children}</span>
  );
}
