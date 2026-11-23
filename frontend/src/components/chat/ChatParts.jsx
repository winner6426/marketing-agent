import {
  BadgeCheck,
  ChevronRight,
  Clock3,
  Copy,
  MessageSquareText,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useTranslation } from "../../i18n/index.jsx";
import { CONTENT_CHANNEL_BY_ID } from "../../lib/channels.js";
import { ChannelIcon, MOCK_IMAGE_GRADIENTS, SearchBox } from "./ChatModals.jsx";

export function ChatbotLogo({ compact = false }) {
  return (
    <span
      aria-hidden="true"
      className={`relative grid flex-none place-items-center overflow-hidden text-white ${compact ? "size-9" : "size-14"}`}
    >
      <img
        src="/images/iconchat.png"
        alt=""
        className={`block size-full object-cover object-[center_51%] mix-blend-multiply dark:mix-blend-screen ${
          compact ? "scale-[1.64]" : "scale-[1.58] rounded-[14px]"
        }`}
      />
    </span>
  );
}

export function ChatSidebar({
  conversations,
  activeId,
  query,
  onQuery,
  onSelect,
  onNew,
  onRename,
  onDuplicate,
  onDelete,
}) {
  const { t } = useTranslation();
  const [openMenuId, setOpenMenuId] = useState(null);
  const filtered = conversations.filter((item) =>
    item.title.toLowerCase().includes(query.toLowerCase()),
  );
  const act = (action, conversation) => {
    action(conversation);
    setOpenMenuId(null);
  };
  return (
    <aside className="relative z-[1] flex min-h-0 flex-col overflow-hidden border-r-2 border-r-[#b9d7c4] bg-white px-3.5 py-4 shadow-[12px_0_35px_#123b2610] after:absolute after:inset-x-[22px] after:top-[127px] after:h-px after:bg-[linear-gradient(90deg,#0000,#cfe3d6,#0000)] after:content-[''] mobile:hidden dark:border-r-[#2a493a] dark:bg-[linear-gradient(#14271f,#0f1c16)] dark:text-[#edf8f1]">
      <div className="-mx-0.5 -mt-1 mb-3 flex flex-none items-center gap-2.5 rounded-[14px] border border-white bg-[#ffffff8f] px-0.5 pt-0.5 pb-4 shadow-[0_8px_24px_#174d3510] dark:border-[#2d503f] dark:bg-[#142d22b8] dark:shadow-[0_9px_24px_#0000002e]">
        <ChatbotLogo />
        <div>
          <b className="block text-[16px] leading-[1.3] tracking-[-0.2px] dark:text-[#edf8f1]">
            AI Content Marketing
          </b>
          <small className="mt-[3px] flex items-center gap-[5px] text-[11px] leading-[1.4] text-[#758078] dark:text-[#92aa9e]">
            <i className="size-[7px] flex-none rounded-full bg-[#11b875] shadow-[0_0_0_3px_#11b87518]" />
            {t("chat.assistantReady")}
          </small>
        </div>
      </div>
      <button
        onClick={onNew}
        className="group/new relative flex h-14 w-full flex-none items-center justify-start gap-[9px] overflow-hidden rounded-[14px] border border-[#a9dfc5] bg-[linear-gradient(115deg,#f8fffb_0%,#e9faf2_48%,#d9f5e7_100%)] px-2 py-1.5 text-[13px] font-extrabold text-[#075e40] shadow-[0_8px_18px_#1482581f,inset_0_1px_#fff] transition-[transform,box-shadow,filter] duration-200 before:absolute before:inset-y-[-70%] before:left-[-35%] before:w-[36%] before:rotate-[18deg] before:bg-[linear-gradient(90deg,#0000,#ffffffe6,#0000)] before:transition-[left] before:duration-[550ms] before:content-[''] hover:-translate-y-0.5 hover:border-[#78cba5] hover:shadow-[0_12px_24px_#1482582e,inset_0_1px_#fff] hover:saturate-[1.04] hover:before:left-[115%] active:translate-y-0 active:scale-[0.99] motion-reduce:transition-none motion-reduce:before:transition-none dark:border-[#32c58d] dark:bg-[linear-gradient(135deg,#0a8056,#12a56f)] dark:text-[#ecfff5] dark:shadow-[0_9px_22px_#0000003d] dark:hover:bg-[linear-gradient(135deg,#0c9362,#19ba7e)]"
      >
        <span className="relative z-[1] grid size-9 flex-none place-items-center rounded-[11px] border border-[#c6e9d6] bg-white text-[#07955f] shadow-[0_4px_10px_#07754f1a,inset_0_1px_#fff] dark:bg-[#ffffff1c] dark:text-[#dffff0]">
          <Plus className="size-[18px] stroke-[2.2px]" />
        </span>
        <span className="relative z-[1] block min-w-0 text-left">
          <b className="block text-[12px] leading-[1.25] tracking-[-0.1px] whitespace-nowrap">
            {t("chat.newConversation")}
          </b>
          <small className="mt-0.5 block text-[8px] leading-[1.2] font-[550] whitespace-nowrap text-[#5e8573] dark:text-[#96a69b]">
            {t("chat.newIdea")}
          </small>
        </span>
        <span className="relative z-[1] ml-auto grid size-[25px] flex-none place-items-center rounded-full bg-[#ccefdc] text-[#07875a] transition-[transform,background,color] duration-[300ms,200ms,200ms] group-hover/new:rotate-12 group-hover/new:scale-[1.08] group-hover/new:bg-[#10a46f] group-hover/new:text-white motion-reduce:transition-none">
          <Sparkles className="size-[13px]" />
        </span>
      </button>
      <h3 className="mx-0.5 mt-[26px] mb-3 flex-none text-[13px] leading-[1.4] text-[#405248] dark:text-[#edf8f1]">
        {t("chat.history")}
      </h3>
      <SearchBox
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        placeholder={t("chat.searchHistory")}
        className="h-11 flex-none rounded-[11px] border-[#bcd4c5] shadow-[inset_0_1px_2px_#173a2508]"
      />
      <div className="mt-2.5 -mr-[5px] grid min-h-0 flex-1 basis-0 content-start gap-[7px] overflow-x-hidden overflow-y-auto pt-0.5 pr-[5px] pb-2 [scrollbar-color:#9acdb6_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-[5px] [&::-webkit-scrollbar-thumb]:rounded-[10px] [&::-webkit-scrollbar-thumb]:bg-[#a8d4c0] [&::-webkit-scrollbar-thumb:hover]:bg-[#69b794]">
        {filtered.map((conversation) => {
          const active = conversation.id === activeId;
          return (
            <div
              key={conversation.id}
              className={`relative flex min-h-12 items-center rounded-xl transition-[background,box-shadow] duration-[180ms] dark:hover:bg-[#193329] ${
                active
                  ? "bg-[linear-gradient(100deg,#cfead9,#e5f5eb)] text-[#043f30] shadow-[inset_3px_0_#0aa66d] dark:bg-[linear-gradient(100deg,#1c4935,#1a392e)] dark:text-[#effcf4] dark:shadow-[inset_3px_0_#49dda1,0_8px_22px_#00000024]"
                  : "dark:text-[#bcd0c5]"
              }`}
            >
              <button
                onClick={() => act(() => onSelect(conversation.id), conversation)}
                className="flex min-h-12 min-w-0 flex-1 basis-0 items-center gap-2 rounded-xl py-2.5 pr-8 pl-[9px] text-left"
              >
                <MessageSquareText className="w-[18px] flex-none text-[#315e4c] dark:text-[#8ccab0]" />
                <span className="min-w-0 flex-1 basis-0">
                  <b className="block truncate text-[12px] leading-[1.35] max-[1050px]:text-[11px]">
                    {conversation.title}
                  </b>
                </span>
              </button>
              <button
                aria-label={t("chat.conversationOptions", { title: conversation.title })}
                aria-expanded={openMenuId === conversation.id}
                onClick={() =>
                  setOpenMenuId((current) => (current === conversation.id ? null : conversation.id))
                }
                className="absolute top-1/2 right-1.5 z-[2] grid size-[27px] -translate-y-1/2 place-items-center rounded-lg p-0 text-[#718078] opacity-55 hover:bg-[#ffffffbf] hover:opacity-100 dark:text-[#a9c0b4] dark:hover:bg-[#28483a] dark:hover:text-[#f3fbf6]"
              >
                <MoreHorizontal className="w-4" />
              </button>
              {openMenuId === conversation.id && (
                <div className="absolute top-[49px] right-[5px] z-[12] w-[136px] rounded-[10px] border border-[#d9e6de] bg-white p-[5px] shadow-[0_12px_28px_#1437282e] dark:border-[#365547] dark:bg-[#172920] dark:text-[#edf8f1] dark:shadow-[0_16px_36px_#0006]">
                  <MenuButton onClick={() => act(onRename, conversation)}>
                    <Pencil className="w-[13px]" />
                    {t("chat.renameAction")}
                  </MenuButton>
                  <MenuButton onClick={() => act(onDuplicate, conversation)}>
                    <Copy className="w-[13px]" />
                    {t("chat.duplicate")}
                  </MenuButton>
                  <MenuButton danger onClick={() => act(onDelete, conversation)}>
                    <Trash2 className="w-[13px]" />
                    {t("chat.delete")}
                  </MenuButton>
                </div>
              )}
            </div>
          );
        })}
        {!filtered.length && <p>{t("chat.noHistory")}</p>}
      </div>
      <div className="mt-2.5 min-h-[82px] flex-none rounded-[13px] border border-[#c8dfcf] bg-[#f1f9f5] p-3.5 dark:border-[#315442] dark:bg-[#172e24] dark:text-[#d8ebdf]">
        <b className="block text-[12px]">{t("chat.withVinfast")}</b>
        <span className="mt-1 block text-[10px] leading-normal text-[#68776d] dark:text-[#96ada1]">
          {t("chat.tagline")}
        </span>
      </div>
    </aside>
  );
}

function MenuButton({ danger = false, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`flex h-8 w-full items-center gap-[7px] rounded-[7px] px-2 text-left text-[9.5px] ${
        danger
          ? "text-[#a74747] hover:bg-[#fff0f0] dark:text-[#ff9f9f] dark:hover:bg-[#442426]"
          : "text-[#375648] hover:bg-[#eef7f2] dark:text-[#cde0d6] dark:hover:bg-[#234033]"
      }`}
    >
      {children}
    </button>
  );
}

// The composer's context buttons and chips share one pill style; the wide grid column on desktop
// becomes a horizontal scroller below 900px.
export const CONTEXT_PILL =
  "flex h-[33px] w-full min-w-0 items-center justify-center gap-1 rounded-[9px] border border-[#cbded3] bg-white px-2 text-[11px] font-semibold whitespace-nowrap text-[#284b38] transition-[border-color,background] duration-[180ms] hover:border-[#79b996] hover:bg-[#e6f5eb] max-[1350px]:min-w-[auto] max-[900px]:w-auto max-[900px]:min-w-[145px] mobile:h-[31px] mobile:text-[10px] dark:border-[#355848] dark:bg-[#1b3027] dark:text-[#d5e7dd] dark:hover:border-[#4a8066] dark:hover:bg-[#234336] dark:hover:text-[#f4fff8] [&_svg]:size-[15px] [&_svg]:flex-none";

export function ContextChip({ icon: Icon, text, thumbnails, onEdit, onClear }) {
  const { t } = useTranslation();
  return (
    <div className={`${CONTEXT_PILL} pr-0.5`}>
      <button
        onClick={onEdit}
        className="flex min-w-0 flex-1 basis-0 items-center justify-center gap-1 truncate p-0 text-[11px] mobile:text-[10px]"
      >
        <Icon />
        {text}
      </button>
      {thumbnails && (
        <span className="ml-0.5 flex gap-0.5">
          {thumbnails.slice(0, 3).map((item, index) => (
            <i
              key={item.id}
              className={`h-4 w-[17px] rounded ${MOCK_IMAGE_GRADIENTS[index] ?? MOCK_IMAGE_GRADIENTS[0]}`}
            />
          ))}
        </span>
      )}
      <button
        aria-label={t("chat.clearChip", { text })}
        onClick={onClear}
        className="flex size-[18px] flex-none items-center justify-center rounded-[5px] p-0 text-[10px] hover:bg-[#e7f1ea] dark:hover:bg-[#315343]"
      >
        <X />
      </button>
    </div>
  );
}

function AssistantIcon() {
  return (
    <span className="grid size-[26px] flex-none place-items-center rounded-full bg-[#e4f3e9] text-[#087a55] mobile:size-6 dark:bg-[#1b3b2d] dark:text-[#6ee0aa]">
      <Sparkles className="w-[13px]" />
    </span>
  );
}

const MESSAGE_TEXT =
  "m-0 max-w-full min-w-0 text-[13px] leading-[1.55] font-medium tracking-[-0.05px] break-words whitespace-pre-wrap [overflow-wrap:anywhere] max-[1050px]:text-[12px] mobile:text-[13px] dark:text-[#e5f1e9]";

const ASSISTANT_ARTICLE =
  "flex w-full min-w-0 animate-message-in items-start gap-2 justify-self-stretch py-1 max-[1050px]:max-w-[82%] mobile:w-full mobile:max-w-none";

function GenerationMessage({ message, onPreview }) {
  const { t } = useTranslation();
  const generated = new Set(message.generatedChannels ?? []);
  const channels = (message.channels ?? []).filter((id) => CONTENT_CHANNEL_BY_ID[id]);
  return (
    <article className={ASSISTANT_ARTICLE}>
      <AssistantIcon />
      <div className="w-full max-w-full min-w-0 pt-1 mobile:px-2.5 mobile:py-2">
        <p className={`${MESSAGE_TEXT} text-[#24362c]`}>{message.content}</p>
        <div className="mt-3 grid grid-cols-[repeat(3,minmax(160px,1fr))] gap-2.5 max-[1150px]:grid-cols-1">
          {channels.map((id) => {
            const channel = CONTENT_CHANNEL_BY_ID[id];
            const ready = generated.has(id);
            return (
              <button
                key={id}
                disabled={!message.draftId || !ready}
                onClick={() => onPreview(message.draftId, id)}
                className="group/card grid grid-cols-[34px_1fr] gap-[9px] rounded-[13px] border border-[#d6e7dd] bg-white p-[13px] text-left shadow-[0_5px_15px_#173a250b] disabled:border-[#e3e9e5] disabled:bg-[#fafcfb] disabled:shadow-none dark:border-[#315244] dark:bg-[#172c23] dark:disabled:border-[#315244] dark:disabled:bg-[#172c23] dark:text-[#dcece3]"
              >
                <ChannelIcon channel={channel} />
                <span>
                  <b className="block text-[12px]">{channel.label}</b>
                  <small className="mt-1 block text-[9px] text-[#74837a] dark:text-[#96a69b]">
                    <em className="inline-block size-1.5 rounded-full bg-[#10af70]" />{" "}
                    {t(ready ? "chat.generatedTwo" : "chat.notGenerated")}
                  </small>
                </span>
                <strong className="col-start-2 flex items-center gap-1 text-[10px] text-[#078457] group-disabled/card:text-[#a15c24]">
                  {ready ? (
                    <>
                      {t("chat.viewContent")} <ChevronRight className="w-[13px]" />
                    </>
                  ) : (
                    t("chat.needRetry")
                  )}
                </strong>
              </button>
            );
          })}
        </div>
      </div>
    </article>
  );
}

// The three benefit pills on the welcome screen, with their own tints.
const BENEFITS = [
  {
    key: "chat.cardCreative",
    icon: Sparkles,
    pill: "border-[#bfe2d1] bg-[linear-gradient(145deg,#fff,#eff9f3)]",
    badge: "bg-[#dff5e9] text-[#078a5b] dark:bg-[#214535] dark:text-[#66dda9]",
  },
  {
    key: "chat.cardTime",
    icon: Clock3,
    pill: "border-[#c4e4e5] bg-[linear-gradient(145deg,#fff,#eef9f8)]",
    badge: "bg-[#dff4f3] text-[#16877d] dark:bg-[#1c3f3d] dark:text-[#74dce0]",
  },
  {
    key: "chat.cardMultichannel",
    icon: BadgeCheck,
    pill: "border-[#e2d9b9] bg-[linear-gradient(145deg,#fff,#faf7e9)]",
    badge: "bg-[#f6efcf] text-[#8f741c] dark:bg-[#42391f] dark:text-[#f1d276]",
  },
];

// The channel logos orbiting the AI badge; each starts at a different point of the loop.
const ORBIT_ICONS = [
  { src: "/images/channel-meta.webp", delay: "[animation-delay:0s]", box: "h-[39px] w-[46px] p-[7px] max-[1200px]:h-[35px] max-[1200px]:w-[41px]", img: "scale-[1.07] rounded-lg object-contain" },
  { src: "/images/channel-facebook.png", delay: "[animation-delay:-4s]", box: "size-[38px] p-1 max-[1200px]:size-[34px]", img: "scale-[1.07] rounded-lg object-contain" },
  { src: "/images/channel-instagram.svg", delay: "[animation-delay:-8s]", box: "size-[38px] p-[3px] max-[1200px]:size-[34px]", img: "scale-[1.07] rounded-lg object-contain" },
  { src: "/images/channel-tiktok-ui.jpg", delay: "[animation-delay:-12s]", box: "size-[38px] overflow-hidden p-0.5 max-[1200px]:size-[34px]", img: "scale-[1.18] rounded-[9px] object-cover object-[center_35%]" },
  { src: "/images/channel-zalo.webp", delay: "[animation-delay:-16s]", box: "size-[38px] overflow-hidden p-0.5 max-[1200px]:size-[34px]", img: "scale-[1.08] rounded-lg object-contain" },
];

function Welcome() {
  const { t } = useTranslation();
  return (
    <div className="relative isolate z-[1] grid min-h-full w-full flex-1 basis-0 grid-cols-[minmax(330px,41%)_minmax(0,59%)] items-center justify-center gap-0 self-stretch overflow-hidden bg-[#eef8f3] pt-6 pr-[22px] pb-32 pl-7 text-left before:absolute before:inset-0 before:-z-20 before:bg-[url(/images/ai-content-welcome-hero-v2.png)] before:bg-contain before:bg-center before:bg-no-repeat before:brightness-[1.015] before:contrast-[0.98] before:saturate-[0.94] before:content-[''] after:pointer-events-none after:absolute after:inset-0 after:-z-10 after:bg-[linear-gradient(90deg,#fbfefcf7_0%,#fbfefceb_27%,#f7fcf9a6_38%,#eff9f41a_52%,#0000_66%),linear-gradient(#0000_68%,#edf8f280_84%,#edf8f2f0_100%)] after:content-[''] max-[1350px]:grid-cols-[47%_53%] max-[1200px]:grid-cols-[minmax(320px,45%)_minmax(0,55%)] max-[1200px]:pr-3.5 max-[1200px]:pl-5 max-[1180px]:grid-cols-[45%_55%] max-[1150px]:grid-cols-1 max-[1150px]:pb-[210px] max-[1050px]:px-5 max-[1050px]:pt-7 max-[1050px]:pb-[160px] mobile:grid-cols-1 mobile:justify-start mobile:bg-[linear-gradient(145deg,#fbfefc,#edf9f4)] mobile:px-[18px] mobile:pt-6 mobile:pb-[116px] mobile:text-center mobile:before:hidden mobile:after:hidden dark:bg-none dark:bg-[#102018] dark:before:brightness-[0.55] dark:before:contrast-[1.08] dark:before:saturate-[0.76] dark:after:bg-[linear-gradient(90deg,#0c1712_0%,#0c1712f7_34%,#0d1c15c2_51%,#0d1d1733_72%),linear-gradient(#0000_58%,#09130ee6)] dark:mobile:bg-[linear-gradient(145deg,#0d1914,#142a20)]">
      <div className="relative z-[2] m-0 max-w-[430px] self-center pt-0 pr-4 pb-2 pl-1 max-[1200px]:mb-6 max-[1150px]:p-5 mobile:mb-0 mobile:max-w-[520px] mobile:p-0">
        <em className="flex items-center gap-2 text-[10px] font-extrabold tracking-[1.25px] text-[#07945f] not-italic dark:text-[#5ee0a5]">
          <Sparkles className="w-[15px]" /> {t("chat.heroEyebrow")}
        </em>
        <h1 className="mt-[17px] mb-3 max-w-[420px] text-[clamp(27px,2.25vw,35px)] leading-[1.2] tracking-[-1px] text-[#10251c] max-[1350px]:text-[36px] max-[1200px]:text-[29px] max-[1180px]:text-[30px] max-[1050px]:text-[25px] max-[900px]:text-[23px] mobile:text-[30px] dark:text-[#f0faf4] dark:[text-shadow:0_2px_18px_#00000052]">
          {t("chat.greeting")}
          <br />
          {t("chat.greetQuestion1")}{" "}
          <strong className="font-extrabold text-[#07955f]">{t("chat.heroSuffix")}</strong>{" "}
          {t("chat.greetQuestion2")}
        </h1>
        <p className="max-w-[390px] text-[12px] leading-[1.6] text-[#64766c] dark:text-[#a9bdb2]">
          {t("chat.welcomeLead1")}
          <br />
          {t("chat.welcomeLead2")}
        </p>
        <div className="mt-[21px] flex flex-wrap gap-[9px] mobile:hidden">
          {BENEFITS.map(({ key, icon: Icon, pill, badge }) => (
            <span
              key={key}
              className={`relative flex min-h-10 items-center gap-[7px] overflow-hidden rounded-[11px] border py-[7px] pr-[11px] pl-[7px] text-[9px] text-[#087a55] shadow-[0_7px_18px_#075e4011] transition-[transform,border-color,box-shadow] duration-200 after:absolute after:inset-y-[-30%] after:left-[-55%] after:w-[42%] after:-skew-x-[18deg] after:bg-[linear-gradient(90deg,#0000,#fff9,#0000)] after:transition-[left] after:duration-500 after:content-[''] hover:-translate-y-[3px] hover:border-[#77c7a1] hover:shadow-[0_11px_24px_#075e401b] hover:after:left-[120%] dark:border-[#315b46] dark:bg-[#142d22e6] dark:text-[#dcece3] dark:shadow-[0_8px_22px_#00000033] ${pill}`}
            >
              <i className={`grid size-[27px] flex-none place-items-center rounded-[9px] ${badge}`}>
                <Icon className="size-3.5" />
              </i>
              <b className="text-[9px] font-bold whitespace-nowrap text-[#244c3b] dark:text-[#e9f8ef]">
                {t(key)}
              </b>
            </span>
          ))}
        </div>
      </div>
      <div
        role="img"
        aria-label={t("chat.cardFuture")}
        className="relative isolate z-[2] m-0 grid h-full min-h-0 place-items-center self-stretch overflow-visible px-1 py-2 max-[1150px]:hidden"
      >
        <strong className="absolute top-[49%] left-[59%] z-[3] -translate-x-1/2 -translate-y-1/2 text-[clamp(31px,3.2vw,48px)] font-black tracking-[1px] text-[#effff5] [text-shadow:0_0_18px_#64ffad,0_4px_18px_#06482f] max-[1200px]:left-[57%] max-[900px]:hidden">
          AI
        </strong>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-[49%] left-[59%] z-[4] h-[clamp(190px,21vw,286px)] w-[clamp(250px,27vw,370px)] -translate-x-1/2 -translate-y-1/2 [perspective:720px] before:pointer-events-none before:absolute before:inset-0 before:z-[2] before:block before:animate-ring-spin before:rounded-full before:border before:border-[#1bb87b38] before:bg-[conic-gradient(from_15deg,transparent_0deg,transparent_9%,#0db774db_14%,#65ebb852_23%,transparent_31%,transparent_55%,#0db774b8_63%,#78edc133_73%,transparent_82%)] before:drop-shadow-[0_0_7px_#0db7747a] before:[mask-image:radial-gradient(farthest-side,#0000_calc(100%-3px),#000_calc(100%-2px))] before:content-[''] after:pointer-events-none after:absolute after:inset-[11%] after:z-[2] after:block after:animate-ring-reverse after:rounded-full after:border after:border-dashed after:border-[#18b2746b] after:shadow-[0_0_22px_#11ae7033,inset_0_0_20px_#11ae7014] after:content-[''] max-[1200px]:left-[57%] max-[1200px]:h-[174px] max-[1200px]:w-[230px] max-[900px]:hidden"
        >
          {ORBIT_ICONS.map(({ src, delay, box, img }) => (
            <i
              key={src}
              className={`absolute top-[4%] left-1/2 z-[4] grid animate-channel-orbit place-items-center rounded-xl border-[3px] border-[#ffffffeb] bg-white shadow-[0_9px_21px_#05482f2e,0_0_0_1px_#158b5e1a] transition-[filter] duration-200 [will-change:left,top,transform,opacity,filter] hover:brightness-[1.08] hover:[animation-play-state:paused] ${delay} ${box}`}
            >
              <img
                src={src}
                alt=""
                className={`relative z-[1] block size-full max-h-[500px] origin-center opacity-90 brightness-[1.06] contrast-[0.94] saturate-[0.76] mix-blend-multiply transition-transform duration-500 [mask-image:linear-gradient(90deg,#0000_0,#000_4%,#000_97%,#0000_100%)] hover:scale-[1.095] dark:opacity-48 dark:brightness-[0.7] dark:saturate-[0.68] dark:mix-blend-screen ${img}`}
              />
            </i>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LoadingDots({ title, hint }) {
  return (
    <div className="m-[15px] flex items-center gap-[11px] p-3 text-[12px] text-[#355248]">
      <div className="flex gap-[5px]">
        {["", "[animation-delay:.15s]", "[animation-delay:.3s]"].map((delay) => (
          <span key={delay} className={`size-1.5 animate-gen-dot rounded-full bg-[#0aa36c] ${delay}`} />
        ))}
      </div>
      <p className="m-0 block">
        <b className="m-0 block">{title}</b>
        <small className="m-0 mt-[3px] block text-[10px] text-[#6c7e75]">{hint}</small>
      </p>
    </div>
  );
}

export function ChatMessages({ messages, loading = false, loadingTitle, loadingHint, onPreview }) {
  const bottomRef = useRef(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  if (loading) return <LoadingDots title={loadingTitle} hint={loadingHint} />;
  if (!messages.length) return <Welcome />;
  return (
    <div className="relative z-[1] m-auto grid w-full gap-2.5 px-[clamp(2px,1vw,14px)] max-[1050px]:px-0.5 mobile:gap-2 mobile:px-0">
      {messages.map((message) =>
        message.type === "generation" ? (
          <GenerationMessage key={message.id} message={message} onPreview={onPreview} />
        ) : message.role === "user" ? (
          <article
            key={message.id}
            className="flex w-fit max-w-[min(66.666%,760px)] min-w-0 animate-message-in gap-2 justify-self-end max-[1050px]:max-w-[82%]"
          >
            <div className="w-fit max-w-full min-w-0 rounded-[15px_15px_4px_15px] border border-[#b7d8c3] bg-[#dcefe3] px-3 py-2 text-left mobile:px-2.5 mobile:py-[7px] dark:border-[#3e795c] dark:bg-[#21402f] dark:text-[#f0fbf4]">
              <p className={`${MESSAGE_TEXT} text-[#123c29]`}>{message.content}</p>
            </div>
          </article>
        ) : (
          <article key={message.id} className={ASSISTANT_ARTICLE}>
            <AssistantIcon />
            <div className="w-full max-w-full min-w-0 pt-1 mobile:px-2.5 mobile:py-2 dark:text-[#e4f0e9]">
              <p className={`${MESSAGE_TEXT} text-[#24362c]`}>{message.content}</p>
            </div>
          </article>
        ),
      )}
      <span ref={bottomRef} aria-hidden="true" className="block h-px" />
    </div>
  );
}
