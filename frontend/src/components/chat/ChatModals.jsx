import { ArrowRight, Car, Check, Globe2, Mail, Paperclip, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useProductCatalog } from "../../hooks/useProductCatalog.js";
import { useTranslation } from "../../i18n/index.jsx";
import { formatContent, getAngleLabel } from "../../lib/campaign-presenters.js";
import { CONTENT_CHANNELS, CONTENT_CHANNEL_BY_ID, channelOfContentKey } from "../../lib/channels.js";
import { normalizeDateRange, vietnamDate } from "../../lib/dates.js";
import { campaignPath } from "../../lib/navigation.js";
import { api } from "../../services/api.js";

// Placeholder tiles until an image library exists; labels are looked up at render time.
const MOCK_IMAGES = Array.from({ length: 6 }, (_, index) => ({ id: `vf8-${index + 1}`, index: index + 1 }));

// Gradients for the placeholder tiles, by position; shared with the composer's image chip.
export const MOCK_IMAGE_GRADIENTS = [
  "bg-[linear-gradient(145deg,#f59e0b,#422006)]",
  "bg-[linear-gradient(145deg,#38bdf8,#0c4a6e)]",
  "bg-[linear-gradient(145deg,#fb7185,#881337)]",
  "bg-[linear-gradient(145deg,#34d399,#064e3b)]",
  "bg-[linear-gradient(145deg,#a78bfa,#4c1d95)]",
  "bg-[linear-gradient(145deg,#94a3b8,#1e293b)]",
];

const MOCK_CAR_GRADIENTS = [
  "bg-[linear-gradient(135deg,#fde68a,#b45309)]",
  "bg-[linear-gradient(135deg,#94a3b8,#1e293b)]",
];

const ICON_FRAME =
  "grid size-[34px] flex-none place-items-center overflow-hidden rounded-[10px] border [&>svg]:w-[17px]";

/** A channel's logo, or a generic icon for channels without one. `variant` picks the card style. */
export function ChannelIcon({ channel, variant = "card" }) {
  const generic = !channel.asset;
  const frame =
    variant === "option"
      ? `${ICON_FRAME} border-[#dce8e1] dark:border-[#3a5d4d] dark:bg-[#1e392e] ${
          generic && channel.id !== "zalo_sms" ? "bg-[#e7f6ef] text-[#07875a]" : "bg-white"
        }`
      : `${ICON_FRAME} border-[#d7e7de] bg-white text-[#07955f] dark:border-[#3a5d4d] dark:bg-[#203a30]`;
  return (
    <i className={frame}>
      {channel.asset ? (
        <img
          src={channel.asset}
          alt=""
          className={`block size-full object-contain ${
            variant === "card" ? "rounded-lg" : channel.id === "meta_ads" ? "p-[3px]" : ""
          }`}
        />
      ) : channel.id === "email" ? (
        <Mail />
      ) : (
        <Globe2 />
      )}
    </i>
  );
}

const MODAL_BUTTON = "h-[37px] rounded-lg px-[17px] text-[12px] font-extrabold";

export function Modal({
  title,
  children,
  onCancel,
  onApply,
  applyLabel,
  applyDisabled = false,
  wide = false,
  showApply = true,
}) {
  const { t } = useTranslation();
  return (
    <div
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onCancel()}
      className="fixed inset-0 z-[90] grid place-items-center bg-[#10221899] p-5 backdrop-blur-[4px] mobile:p-2 dark:bg-[#020906cc]"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-[90vh] animate-modal-rise flex-col overflow-hidden rounded-2xl border-2 border-[#8fc3a3] bg-[linear-gradient(#fff,#fbfdfb)] shadow-[0_35px_90px_#0b3b294f] mobile:max-h-[96vh] dark:border dark:border-[#325144] dark:bg-none dark:bg-[#12221b] dark:text-[#edf8f1] dark:shadow-[0_30px_90px_#00000094] ${
          wide ? "w-[min(700px,100%)]" : "w-[min(520px,100%)]"
        }`}
      >
        <header className="z-[5] flex items-center justify-between border-b border-[#e6ece7] bg-[linear-gradient(100deg,#edf8f1,#f4fbf8_60%,#edf9f9)] px-[21px] py-[18px] shadow-[0_6px_22px_#153a2410] backdrop-blur-[8px] mobile:h-[62px] mobile:px-[17px] mobile:py-0 dark:border-[#304d40] dark:bg-none dark:bg-[#162920] dark:text-[#edf8f1]">
          <div>
            <span className="text-[9px] font-extrabold tracking-[1px] text-[#087a55] dark:text-[#6fe1ad]">
              {t("chat.modalKicker")}
            </span>
            <h2 className="mt-[5px] text-[20px] leading-[1.3] tracking-[-0.3px] mobile:text-[18px] dark:text-[#f0faf4]">
              {title}
            </h2>
          </div>
          <button
            aria-label={t("common.close")}
            onClick={onCancel}
            className="grid size-8 place-items-center rounded-lg bg-[#f0f4f1] dark:bg-[#213a2f] dark:text-[#d4e7dc]"
          >
            <X className="w-[15px]" />
          </button>
        </header>
        <div className="overflow-auto px-[21px] py-[18px]">{children}</div>
        <footer className="flex justify-end gap-2 border-t border-[#e6ece7] bg-[#f8fbf9] px-[21px] py-3.5 dark:border-[#304d40] dark:bg-transparent">
          <button
            onClick={onCancel}
            className={`${MODAL_BUTTON} border border-[#d7e0da] bg-white dark:border-[#365548] dark:bg-[#182b22] dark:text-[#c9ddd2]`}
          >
            {showApply ? t("common.cancel") : t("common.close")}
          </button>
          {showApply && (
            <button
              disabled={applyDisabled}
              onClick={onApply}
              className={`${MODAL_BUTTON} bg-[linear-gradient(135deg,#075e40,#0e9a65)] text-white shadow-[0_8px_20px_#08724c2e] disabled:opacity-45`}
            >
              {applyLabel ?? t("common.confirm")}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}

export function ModalHint({ children }) {
  return <p className="text-[11px] text-[#777080] dark:text-[#96a69b]">{children}</p>;
}

/** The outline style shared by product, audience and image choices, plus their selected state. */
function choiceClass(selected) {
  return selected
    ? "border-2 border-[#24865e] bg-[#e2f3e8] dark:border-[#48c28a] dark:bg-[#1b432f] dark:text-[#f0fff6]"
    : "border border-[#c2d9ca] bg-white dark:border-[#304c3f] dark:bg-[#172a21] dark:text-[#d5e7dd]";
}

export function ProductModal({ value, onCancel, onApply }) {
  const { t } = useTranslation();
  const { products: catalog, productError, productsLoading } = useProductCatalog();
  const [draft, setDraft] = useState(value);
  const [query, setQuery] = useState("");
  const products = catalog.filter((item) =>
    `${item.name} ${item.model_id}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Modal
      title={t("chat.pickProduct")}
      onCancel={onCancel}
      onApply={() => onApply(draft)}
      applyDisabled={!draft}
    >
      <SearchBox
        autoFocus
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t("chat.searchProduct")}
        className="h-[42px] border-[#dfe6e1]"
      />
      {productsLoading && <ModalHint>{t("chat.loadingProducts")}</ModalHint>}
      {productError && (
        <div role="alert" className="mt-2 text-[12px] text-[#973b3b]">
          {productError}
        </div>
      )}
      {!productsLoading && !productError && !catalog.length && (
        <ModalHint>{t("chat.noProducts")}</ModalHint>
      )}
      <div className="mt-[13px] grid gap-[7px]">
        {products.map((product, index) => {
          const selected = draft === product.model_id;
          return (
            <button
              key={product.product_id}
              onClick={() => setDraft(product.model_id)}
              className={`flex items-center gap-2.5 rounded-[10px] p-[9px] text-left transition-[border-color,background,transform] duration-[180ms] hover:-translate-y-0.5 ${choiceClass(selected)}`}
            >
              <span
                className={`grid h-[38px] w-[55px] place-items-center rounded-lg ${MOCK_CAR_GRADIENTS[index] ?? MOCK_CAR_GRADIENTS[0]}`}
              >
                <Car className="w-[27px] text-white" />
              </span>
              <span className="flex-1">
                <b className="block text-[12px] leading-[1.35]">{product.name}</b>
                <small className="mt-[3px] block text-[10px] text-[#928b98] dark:text-[#96a69b]">
                  {product.variants.join(" · ")}
                </small>
              </span>
              {selected && <Check className="w-4 text-[#087a55]" />}
            </button>
          );
        })}
      </div>
    </Modal>
  );
}

export function SearchBox({ className = "", ...inputProps }) {
  return (
    <div
      className={`flex items-center gap-[7px] rounded-[9px] border bg-white px-2.5 dark:border-[#315044] dark:bg-[#0f1e18] dark:text-[#edf8f1] ${className}`}
    >
      <Search className="w-[15px] text-[#849188] dark:text-[#86a99a]" />
      <input
        className="w-full bg-transparent text-[12px] outline-0 dark:text-[#f5fbf8] dark:placeholder:text-[#80998c]"
        {...inputProps}
      />
    </div>
  );
}

export function ImageModal({ value, onCancel, onApply }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(value);
  const [tab, setTab] = useState("library");
  const toggle = (image) =>
    setDraft((current) =>
      current.some((item) => item.id === image.id)
        ? current.filter((item) => item.id !== image.id)
        : [...current, image],
    );
  const tabClass = (active) =>
    `px-4 py-2.5 text-[12px] ${
      active
        ? "border-b-2 border-[#087a55] font-extrabold text-[#087a55] dark:border-[#4bd69d] dark:text-[#64dda8]"
        : "dark:text-[#9db2a7]"
    }`;
  return (
    <Modal
      title={t("chat.addImages")}
      wide
      onCancel={onCancel}
      onApply={() => onApply(draft)}
      applyLabel={t("chat.addNImages", { count: draft.length })}
    >
      <div className="-mt-[5px] mb-4 flex border-b border-[#dfe7e1] dark:border-[#304d40]">
        <button className={tabClass(tab === "upload")} onClick={() => setTab("upload")}>
          {t("chat.tabUpload")}
        </button>
        <button className={tabClass(tab === "library")} onClick={() => setTab("library")}>
          {t("chat.tabLibrary")}
        </button>
      </div>
      {tab === "upload" ? (
        <div className="flex min-h-60 flex-col items-center justify-center rounded-[13px] border-[1.5px] border-dashed border-[#bfd3c6] bg-[#fbfdfb] text-center text-[#66756b] dark:border-[#416252] dark:bg-transparent dark:text-[#a5baaf]">
          <Paperclip className="text-[#087a55]" />
          <b className="mt-2.5 text-[13px]">{t("chat.uploadLater")}</b>
          <span className="mt-2.5 text-[11px]">{t("chat.uploadHint")}</span>
          <button
            onClick={() => setTab("library")}
            className="mt-3.5 rounded-lg bg-[#e7f4eb] px-3 py-[9px] text-[11px] text-[#08704c] dark:bg-[#1c3b2d] dark:text-[#75dfae]"
          >
            {t("chat.openLibrary")}
          </button>
        </div>
      ) : (
        <>
          <ModalHint>{t("chat.imageLibraryHint", { count: draft.length })}</ModalHint>
          <div className="grid grid-cols-3 gap-[9px] mobile:grid-cols-2">
            {MOCK_IMAGES.map((image, index) => {
              const selected = draft.some((item) => item.id === image.id);
              return (
                <button
                  key={image.id}
                  onClick={() => toggle(image)}
                  className={`relative overflow-hidden rounded-[10px] border-2 p-0 transition-[border-color,background,transform] duration-[180ms] hover:-translate-y-0.5 ${
                    selected
                      ? "border-[#159568] bg-[#f6f4f7] dark:border-[#48c28a] dark:bg-[#1b432f] dark:text-[#f0fff6]"
                      : "border-transparent bg-[#f6f4f7] dark:border-[#304c3f] dark:bg-[#172a21] dark:text-[#d5e7dd]"
                  }`}
                >
                  <span className={`grid h-[105px] place-items-center ${MOCK_IMAGE_GRADIENTS[index]}`}>
                    <Car className="size-[55px] text-[#fffc]" />
                  </span>
                  <i
                    className={`absolute top-[7px] right-[7px] grid size-[18px] place-items-center rounded-[5px] dark:shadow-[0_5px_14px_#0000004d] ${
                      selected
                        ? "bg-[#087a55] text-white"
                        : "bg-white dark:bg-[#18382b] dark:text-[#9ee9c2]"
                    }`}
                  >
                    {selected ? <Check className="w-3" /> : null}
                  </i>
                  <small className="block p-[7px] text-left text-[10px] leading-[1.35] dark:text-[#96a69b]">
                    {t("chat.imageAlt", { index: image.index })}
                  </small>
                </button>
              );
            })}
          </div>
        </>
      )}
    </Modal>
  );
}

function ChoiceButton({ selected, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`flex h-[42px] min-h-[46px] items-center rounded-[9px] px-3 text-left text-[12px] transition-[border-color,background,transform] duration-[180ms] hover:-translate-y-0.5 ${choiceClass(selected)}`}
    >
      <span>{children}</span>
      <i
        className={`ml-auto grid size-[18px] place-items-center rounded-full border ${
          selected ? "border-[#087a55] bg-[#087a55] text-white" : "border-[#d8d2de]"
        }`}
      >
        {selected && <Check className="w-[11px]" />}
      </i>
    </button>
  );
}

export function SingleChoiceModal({ title, options, value, custom = false, onCancel, onApply }) {
  const { t } = useTranslation();
  const isCustom = custom && value && !options.includes(value);
  const [draft, setDraft] = useState(isCustom ? "custom" : value);
  const [customValue, setCustomValue] = useState(isCustom ? value : "");
  const finalValue = draft === "custom" ? customValue.trim() : draft;
  return (
    <Modal
      title={title}
      onCancel={onCancel}
      onApply={() => onApply(finalValue)}
      applyDisabled={!finalValue}
    >
      <div className="grid gap-[7px]">
        {options.map((option) => (
          <ChoiceButton key={option} selected={draft === option} onClick={() => setDraft(option)}>
            {option}
          </ChoiceButton>
        ))}
        {custom && (
          <ChoiceButton selected={draft === "custom"} onClick={() => setDraft("custom")}>
            {t("chat.custom")}
          </ChoiceButton>
        )}
      </div>
      {draft === "custom" && (
        <textarea
          autoFocus
          value={customValue}
          onChange={(event) => setCustomValue(event.target.value)}
          placeholder={t("chat.audiencePlaceholder")}
          className="mt-3 min-h-[85px] w-full resize-y rounded-[9px] border border-[#d7e0da] p-[11px] text-[12px] leading-normal dark:border-[#30483e] dark:bg-[#14251f] dark:text-[#f5fbf8] dark:placeholder:text-[#80998c]"
        />
      )}
    </Modal>
  );
}

export function ChannelModal({ value, onCancel, onApply }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(value);
  const supported = CONTENT_CHANNELS.filter((channel) => channel.backend);
  const all = supported.every((channel) => draft.includes(channel.id));
  const toggle = (id) =>
    setDraft((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  return (
    <Modal
      title={t("chat.pickChannels")}
      onCancel={onCancel}
      onApply={() => onApply(draft)}
      applyLabel={t("chat.apply")}
    >
      <div className="grid grid-cols-2 gap-[9px] mobile:grid-cols-1">
        {CONTENT_CHANNELS.map((channel) => (
          <label
            key={channel.id}
            className={`flex min-h-[58px] items-center gap-[9px] rounded-[9px] border border-[#c2d9ca] px-2.5 py-[9px] text-[12px] transition-[border-color,background,transform] duration-[180ms] hover:-translate-y-px hover:border-[#9fcbb4] has-checked:border-[#54a982] has-checked:bg-[#eef8f3] has-checked:shadow-[inset_3px_0_#07955f] dark:border-[#304c3f] dark:bg-[#172a21] dark:text-[#d5e7dd] ${
              channel.backend ? "cursor-pointer" : "cursor-not-allowed opacity-48"
            }`}
          >
            <input
              type="checkbox"
              disabled={!channel.backend}
              checked={draft.includes(channel.id)}
              onChange={() => toggle(channel.id)}
              className="size-4 accent-[#087a55] disabled:cursor-not-allowed"
            />
            <ChannelIcon channel={channel} variant="option" />
            <span className="min-w-0">
              <b className="block text-[11px] text-[#244537] mobile:text-[12px] dark:text-inherit">
                {channel.label}
              </b>
              <small className="mt-0.5 block truncate text-[8.5px] text-[#7a8981] mobile:text-[9px] dark:text-[#96a69b]">
                {t(channel.backend ? channel.descriptionKey : "channelDesc.unsupported")}
              </small>
            </span>
          </label>
        ))}
      </div>
      <label className="mt-3.5 flex items-center gap-[9px] rounded-[9px] py-2.5 pr-2.5 pl-0.5 text-[12px] font-extrabold">
        <input
          type="checkbox"
          checked={all}
          onChange={() => setDraft(all ? [] : supported.map((channel) => channel.id))}
          className="size-4 accent-[#087a55]"
        />
        <span>{t("chat.selectAllChannels")}</span>
      </label>
    </Modal>
  );
}

export function DateRangeModal({ dateFrom, dateTo, onCancel, onApply }) {
  const { t } = useTranslation();
  const minimum = vietnamDate();
  const initial = normalizeDateRange(dateFrom, dateTo, minimum);
  const [from, setFrom] = useState(initial.dateFrom);
  const [to, setTo] = useState(initial.dateTo);
  const update = (nextFrom, nextTo) => {
    const range = normalizeDateRange(nextFrom, nextTo, minimum);
    setFrom(range.dateFrom);
    setTo(range.dateTo);
  };
  const field = (label, input) => (
    <label className="grid gap-[7px] text-[11px] font-[750]">
      <span>{label}</span>
      {input}
    </label>
  );
  const inputClass =
    "h-[42px] rounded-[9px] border border-[#d7e3dc] bg-white px-[11px] text-[#183d2d] dark:border-[#30483e] dark:bg-[#14251f] dark:text-[#f5fbf8] dark:[color-scheme:dark]";
  return (
    <Modal
      title={t("chat.campaignPeriod")}
      onCancel={onCancel}
      onApply={() => onApply(from, to)}
      applyDisabled={!from || !to || to < from}
    >
      <ModalHint>{t("chat.dateHint")}</ModalHint>
      <div className="grid grid-cols-2 gap-3">
        {field(
          t("chat.dateFrom"),
          <input
            type="date"
            min={minimum}
            value={from}
            onChange={(event) => update(event.target.value, to)}
            className={inputClass}
          />,
        )}
        {field(
          t("chat.dateTo"),
          <input
            type="date"
            min={from}
            value={to}
            onChange={(event) => update(from, event.target.value)}
            className={inputClass}
          />,
        )}
      </div>
    </Modal>
  );
}

// Text fields across the writer's per-channel schemas, in reading order.
const DRAFT_TEXT_FIELDS = ["hook", "scene", "voiceOver", "overlay", "body", "caption", "cta"];

/** Quick read-only view of one channel's variants; editing and submission live on the campaign page. */
export function ContentPreviewModal({ campaignId, channelId, onClose }) {
  const { t } = useTranslation();
  const { session } = useAuth();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const channel = CONTENT_CHANNEL_BY_ID[channelId];

  useEffect(() => {
    let active = true;
    api
      .getCampaign(session?.access_token, campaignId)
      .then((campaign) => {
        if (!active) return;
        setItems(
          campaign.contentItems
            .filter((item) => channelOfContentKey(item.key) === channelId)
            .sort((left, right) => left.key.localeCompare(right.key)),
        );
      })
      .catch((caught) => active && setError(caught.message));
    return () => {
      active = false;
    };
  }, [campaignId, channelId, session?.access_token]);

  return (
    <Modal title={channel?.label ?? channelId} wide showApply={false} onCancel={onClose}>
      {error && (
        <div role="alert" className="mb-3 text-[12px] text-[#973b3b]">
          {error}
        </div>
      )}
      {!items && !error && <ModalHint>{t("chat.loadingContent")}</ModalHint>}
      {items && !items.length && <ModalHint>{t("chat.notGenerated")}</ModalHint>}
      <div className="mb-3 grid gap-3">
        {items?.map((item) => {
          const draft = item.draft ?? {};
          const hashtags = Array.isArray(draft.hashtags) ? draft.hashtags.join(" ") : "";
          return (
            <article
              key={item.key}
              className="rounded-[13px] border border-[#e1e5e0] bg-white px-4 py-3.5 dark:border-[#304d40] dark:bg-[#172820] dark:text-[#dce7df]"
            >
              <header className="mb-2 flex items-center justify-between gap-2">
                <b>{t("chat.variant", { variant: draft.variant ?? item.key.split("/")[1] })}</b>
                {draft.angle && (
                  <span className="rounded-[20px] bg-[#effaf5] px-2.5 py-0.5 text-[11px] font-bold text-[#0a8f5f] dark:bg-[#183d2c] dark:text-[#72ef9d]">
                    {getAngleLabel(draft.angle)}
                  </span>
                )}
              </header>
              {item.writer_error ? (
                <p className="text-[13px] text-[#b42318]">{item.writer_error}</p>
              ) : (
                DRAFT_TEXT_FIELDS.filter((field) => draft[field]).map((field) => (
                  <div key={field} className="mt-2 first:mt-0">
                    <small className="text-[10px] font-bold tracking-[1px] text-[#758078] uppercase">
                      {t(`draftField.${field}`)}
                    </small>
                    <p className="mt-0.5 text-[13px] leading-[1.55] whitespace-pre-line">
                      {formatContent(draft[field])}
                    </p>
                  </div>
                ))
              )}
              {hashtags && (
                <p className="mt-2 text-[13px] font-semibold text-[#176344] dark:text-[#72ef9d]">
                  {hashtags}
                </p>
              )}
            </article>
          );
        })}
      </div>
      <Link
        to={campaignPath(campaignId)}
        onClick={onClose}
        className="inline-flex items-center gap-1.5 text-[12px] font-extrabold text-[#078457] dark:text-[#72ef9d]"
      >
        {t("chat.openStudio")} <ArrowRight className="w-[14px]" />
      </Link>
    </Modal>
  );
}
