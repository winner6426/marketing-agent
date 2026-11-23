import { CalendarDays, Car, Image, Megaphone, Palette, Send, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ChatbotLogo,
  ChatMessages,
  ChatSidebar,
  CONTEXT_PILL,
  ContextChip,
  LoadingDots,
} from "../components/chat/ChatParts.jsx";
import {
  ChannelModal,
  ContentPreviewModal,
  DateRangeModal,
  ImageModal,
  Modal,
  ProductModal,
  SingleChoiceModal,
} from "../components/chat/ChatModals.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useCampaigns } from "../context/CampaignContext.jsx";
import { useTranslation } from "../i18n/index.jsx";
import {
  createLocalConversation,
  isAutomaticTitle,
  isLocalConversation,
  mergeChatHistory,
  moveToFront,
  provisionalTitle,
  resolveConversationTitle,
} from "../lib/chat-history.js";
import { addDays, normalizeDateRange, vietnamDate } from "../lib/dates.js";
import { buildBrief, buildGenerationResult } from "../lib/generation.js";
import { api, getAgentFailureMessage } from "../services/api.js";

// Composer options. The values are sent to the pipeline as written, so they stay in Vietnamese,
// the language the content is generated in.
const AUDIENCES = ["Sinh viên", "Người trẻ 22–30", "Gia đình trẻ", "Doanh nhân", "Khách hàng thu nhập cao"];
const TONES = ["Trẻ trung", "Sang trọng", "Chuyên nghiệp", "Hài hước", "Cảm xúc", "Bán hàng mạnh", "Tối giản"];
const PROMPT_MAX_LENGTH = 4000;
const DATE_LABEL = "flex min-w-0 items-center gap-[3px] text-[10px] text-[#607369]";
const DATE_INPUT =
  "w-[92px] min-w-0 bg-transparent text-[10px] text-[#254b38] focus:rounded focus:outline focus:outline-[#7ab99a] dark:bg-[#14251f] dark:text-[#dcebe2] dark:[color-scheme:dark]";
const DEFAULT_CAMPAIGN_DAYS = 14;

function messageFromServer(message) {
  return {
    id: String(message.id),
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    ...(message.metadata ?? {}),
  };
}

/** Everything but the fields stored in their own columns goes into the message metadata. */
function metadataOf(message) {
  const { id: _id, role: _role, content: _content, createdAt: _createdAt, ...metadata } = message;
  return metadata;
}

export function AIChatPage() {
  const { t } = useTranslation();
  const { createChatDraft, answerChatDraft, progress } = useCampaigns();
  const { session } = useAuth();
  const token = session?.access_token;
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [messagesByConversation, setMessagesByConversation] = useState({});
  const [historyQuery, setHistoryQuery] = useState("");
  const [product, setProduct] = useState("");
  const [images, setImages] = useState([]);
  const [audience, setAudience] = useState("");
  const [tone, setTone] = useState("");
  const [channels, setChannels] = useState([]);
  const [dateFrom, setDateFrom] = useState(() => vietnamDate());
  const [dateTo, setDateTo] = useState(() => addDays(vietnamDate(), DEFAULT_CAMPAIGN_DAYS));
  const [prompt, setPrompt] = useState("");
  const [modal, setModal] = useState(null);
  const [preview, setPreview] = useState(null);
  const [generating, setGenerating] = useState({});
  const [loadingId, setLoadingId] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const startedLocallyRef = useRef(false);
  const latestLoadRef = useRef(0);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const messages = messagesByConversation[activeId] ?? [];
  const isGenerating = Boolean(generating[activeId]);
  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === activeId),
    [conversations, activeId],
  );
  const minimumDate = vietnamDate();

  const setMessages = (conversationId, update) =>
    setMessagesByConversation((current) => ({
      ...current,
      [conversationId]: update(current[conversationId] ?? []),
    }));

  const updateDateRange = (nextFrom, nextTo) => {
    const range = normalizeDateRange(nextFrom, nextTo, minimumDate);
    setDateFrom(range.dateFrom);
    setDateTo(range.dateTo);
  };

  const resetComposer = () => {
    setProduct("");
    setImages([]);
    setAudience("");
    setTone("");
    setChannels([]);
    setDateFrom(vietnamDate());
    setDateTo(addDays(vietnamDate(), DEFAULT_CAMPAIGN_DAYS));
    setPrompt("");
    setModal(null);
  };

  const loadConversation = async (conversationId, { keepLocalSelection = false } = {}) => {
    if (!tokenRef.current || !conversationId) return;
    const requestId = ++latestLoadRef.current;
    if (!keepLocalSelection || !startedLocallyRef.current) setActiveId(conversationId);
    const cached = Object.prototype.hasOwnProperty.call(messagesByConversation, conversationId);
    setLoadingId(cached ? null : conversationId);
    try {
      const detail = await api.getChatSession(tokenRef.current, conversationId);
      if (requestId !== latestLoadRef.current) return;
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: (detail.messages ?? []).map(messageFromServer),
      }));
    } finally {
      if (requestId === latestLoadRef.current) setLoadingId(null);
    }
  };

  const startLocalConversation = () => {
    const conversation = createLocalConversation();
    setConversations((current) => [conversation, ...current]);
    setMessagesByConversation((current) => ({ ...current, [conversation.id]: [] }));
    setActiveId(conversation.id);
  };

  const signedIn = Boolean(token);
  useEffect(() => {
    if (!signedIn) return undefined;
    let cancelled = false;
    (async () => {
      const rows = await api.listChatSessions(tokenRef.current);
      if (cancelled) return;
      if (rows.length) {
        setConversations((current) => mergeChatHistory(current, rows));
        await loadConversation(rows[0].id, { keepLocalSelection: true });
      } else if (!startedLocallyRef.current) {
        startLocalConversation();
      }
    })().catch(() => {});
    return () => {
      cancelled = true;
    };
    // Load the history once per sign-in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn]);

  const newConversation = () => {
    startedLocallyRef.current = true;
    latestLoadRef.current += 1;
    setLoadingId(null);
    startLocalConversation();
    resetComposer();
  };

  const renameConversation = async (conversation) => {
    const title = window.prompt(t("chat.rename"), conversation.title)?.trim();
    if (!title) return;
    if (!isLocalConversation(conversation.id)) {
      await api.updateChatSession(token, conversation.id, title);
    }
    setConversations((current) =>
      current.map((item) => (item.id === conversation.id ? { ...item, title } : item)),
    );
  };

  const duplicateConversation = async (conversation) => {
    const created = await api.createChatSession(
      token,
      t("chat.copySuffix", { title: conversation.title }),
    );
    for (const message of messagesByConversation[conversation.id] ?? []) {
      await api.createChatMessage(token, created.id, message.role, message.content, metadataOf(message));
    }
    setConversations((current) => [created, ...current]);
    await loadConversation(created.id);
  };

  const confirmDelete = async () => {
    const conversationId = toDelete?.id;
    if (!conversationId) return;
    if (!isLocalConversation(conversationId)) await api.deleteChatSession(token, conversationId);
    const remaining = conversations.filter((item) => item.id !== conversationId);
    setConversations(remaining);
    setMessagesByConversation((current) => {
      const next = { ...current };
      delete next[conversationId];
      return next;
    });
    setToDelete(null);
    if (!remaining.length) startLocalConversation();
    else if (activeId === conversationId) await loadConversation(remaining[0].id);
  };

  /** Save a server-side conversation for a local one, the first time the user sends a message. */
  const persistConversation = async (conversationId, title) => {
    if (!isLocalConversation(conversationId)) return conversationId;
    const created = await api.createChatSession(token, title);
    setConversations((current) => [
      { ...created, title },
      ...current.filter((item) => item.id !== conversationId && item.id !== created.id),
    ]);
    setMessagesByConversation((current) => {
      const next = { ...current, [created.id]: current[conversationId] ?? [] };
      delete next[conversationId];
      return next;
    });
    setActiveId((current) => (current === conversationId ? created.id : current));
    return created.id;
  };

  const setConversationTitle = (conversationId, title) =>
    setConversations((current) =>
      moveToFront(
        current.map((item) =>
          item.id === conversationId
            ? { ...item, title, updated_at: new Date().toISOString() }
            : item,
        ),
        conversationId,
      ),
    );

  /** Add an assistant message locally, then store it so it survives a reload. */
  const addAssistantMessage = async (conversationId, message) => {
    const localId = `ai-${Date.now()}`;
    setMessages(conversationId, (list) => [...list, { ...message, id: localId, role: "assistant" }]);
    try {
      const saved = await api.createChatMessage(
        token,
        conversationId,
        "assistant",
        message.content,
        metadataOf(message),
      );
      setMessages(conversationId, (list) =>
        list.map((item) => (item.id === localId ? { ...item, id: String(saved.id) } : item)),
      );
    } catch {
      // The message stays visible for this visit even if it could not be stored.
    }
  };

  const assistantReply = (campaign, requestedChannels) => {
    if (campaign.status === "failed" || campaign.status === "generation_failed") {
      throw Object.assign(new Error(campaign.error || t("agent.failure")), { status: 500 });
    }
    if (campaign.humanWait?.type === "clarification") {
      const questions = (campaign.humanWait.questions ?? [])
        .map((question, index) => `${index + 1}. ${question}`)
        .join(" ");
      return {
        type: "clarification",
        draftId: campaign.draft_id,
        content: `${t("chat.clarificationPrefix")} ${questions}`,
      };
    }
    const result = buildGenerationResult({
      requestedChannels,
      contentItems: campaign.contentItems ?? [],
    });
    if (!result.generatedChannels.length) {
      return { draftId: campaign.draft_id, content: t("chat.stoppedNoContent") };
    }
    return {
      type: "generation",
      draftId: campaign.draft_id,
      content: result.message,
      channels: result.channels,
      generatedChannels: result.generatedChannels,
    };
  };

  const sendMessage = async () => {
    const content = prompt.trim();
    if (!content || isGenerating) return;
    let conversationId = activeId;
    const requestedChannels = [...channels];
    // A reply to an open clarification answers that draft instead of starting a new one.
    const lastAssistant = [...messages]
      .reverse()
      .find((message) => message.type === "clarification" || message.type === "generation");
    const pendingDraftId =
      lastAssistant?.type === "clarification" ? lastAssistant.draftId : null;
    const firstPrompt = messages.find((message) => message.role === "user")?.content ?? content;
    const optimisticId = `user-local-${Date.now()}`;
    const startedId = conversationId;
    setGenerating((current) => ({ ...current, [startedId]: true }));
    setPrompt("");
    setMessages(conversationId, (list) => [
      ...list,
      { id: optimisticId, role: "user", content, createdAt: new Date() },
    ]);

    try {
      const brief = buildBrief({
        prompt: content,
        product,
        audience,
        tone,
        channels,
        dateFrom,
        dateTo,
      });
      const oldTitle = activeConversation?.title;
      const title = isAutomaticTitle(oldTitle, firstPrompt) ? provisionalTitle(firstPrompt) : oldTitle;
      const wasLocal = isLocalConversation(conversationId);
      conversationId = await persistConversation(conversationId, title);
      setGenerating((current) => ({ ...current, [conversationId]: true }));

      const savedUser = await api.createChatMessage(token, conversationId, "user", content, {
        product,
        images,
        audience,
        tone,
        channels,
        dateFrom,
        dateTo,
      });
      setMessages(conversationId, (list) =>
        list.map((message) =>
          message.id === optimisticId ? { ...message, id: String(savedUser.id) } : message,
        ),
      );
      if (!wasLocal && title !== oldTitle) await api.updateChatSession(token, conversationId, title);
      setConversationTitle(conversationId, title);

      const campaign = pendingDraftId
        ? await answerChatDraft(brief, pendingDraftId)
        : await createChatDraft(brief, savedUser.id, conversationId);

      const resolvedTitle = resolveConversationTitle(title, campaign, firstPrompt);
      if (resolvedTitle && resolvedTitle !== title) {
        api.updateChatSession(token, conversationId, resolvedTitle).catch(() => {});
        setConversationTitle(conversationId, resolvedTitle);
      }
      await addAssistantMessage(conversationId, assistantReply(campaign, requestedChannels));
    } catch (error) {
      await addAssistantMessage(conversationId, { content: getAgentFailureMessage(error) });
    } finally {
      setGenerating((current) => {
        const next = { ...current };
        delete next[startedId];
        delete next[conversationId];
        return next;
      });
    }
  };

  const closeModal = () => setModal(null);
  const applyAndClose = (setter) => (value) => {
    setter(value);
    closeModal();
  };

  return (
    <div className="chat-page relative grid h-[calc(100vh-68px)] min-h-[580px] grid-cols-[292px_minmax(0,1fr)] overflow-hidden rounded-[15px] border-2 border-[#dce9e1] bg-white text-[#17241d] max-[1350px]:grid-cols-[285px_1fr] max-[1200px]:grid-cols-[265px_minmax(0,1fr)] max-[1150px]:grid-cols-[250px_1fr] max-[1050px]:grid-cols-[235px_1fr] mobile:h-auto mobile:min-h-[calc(100vh-58px)] mobile:grid-cols-1 mobile:overflow-visible mobile:rounded-[14px] dark:border-[#2f5946] dark:bg-[#0d1914] dark:text-[#edf8f1] dark:shadow-[0_20px_55px_#00000057]">
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        query={historyQuery}
        onQuery={setHistoryQuery}
        onSelect={(id) => loadConversation(id)}
        onNew={newConversation}
        onRename={renameConversation}
        onDuplicate={(conversation) => duplicateConversation(conversation).catch(() => {})}
        onDelete={setToDelete}
      />
      <section className="relative grid min-h-0 min-w-0 grid-rows-[auto_1fr_auto] overflow-hidden bg-[#f8fcfa] before:pointer-events-none before:absolute before:top-[45px] before:right-[-150px] before:size-[340px] before:rounded-full before:bg-[radial-gradient(circle,#bcebd033,#0000_68%)] before:content-[''] mobile:min-h-[calc(100vh-110px)] dark:bg-[#0d1813] dark:text-[#edf8f1]">
        <div className="relative z-[3] flex h-12 items-center justify-between border-b border-[#d9e8df] bg-[#ffffffed] px-[18px] py-1.5 shadow-[0_5px_20px_#174d350c] backdrop-blur-[12px] mobile:h-[52px] mobile:rounded-t-[13px] mobile:px-4 mobile:py-[13px] dark:border-[#2b493b] dark:bg-[linear-gradient(100deg,#142b21f7,#12251ef7)]">
          <div className="flex items-center gap-[9px]">
            <ChatbotLogo compact />
            <div className="flex items-center">
              <h2 className="m-0 text-[15px] leading-[1.3] tracking-[-0.25px] dark:text-[#f0faf4]">
                {activeConversation?.title ?? t("chat.newConversation")}
              </h2>
            </div>
          </div>
        </div>
        <div className="relative min-h-0 overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth bg-[radial-gradient(circle_at_90%_5%,#dff7f5_0,#0000_32%),linear-gradient(135deg,#fff_0%,#f7fcf9_55%,#edf8f2_100%)] px-5 pt-[18px] pb-[238px] [scrollbar-gutter:stable] [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border-2 [&::-webkit-scrollbar-thumb]:border-transparent [&::-webkit-scrollbar-thumb]:bg-[#c6d8cc] [&::-webkit-scrollbar-thumb]:bg-clip-padding [&::-webkit-scrollbar-thumb:hover]:bg-[#91b6a0] [&::-webkit-scrollbar-track]:bg-transparent after:pointer-events-none after:absolute after:inset-0 after:bg-[linear-gradient(90deg,#087a5509_1px,#0000_1px),linear-gradient(#087a5507_1px,#0000_1px)] after:bg-size-[36px_36px] after:[mask-image:linear-gradient(#0000,#000_30%,#000_75%,#0000)] after:content-[''] max-[1050px]:p-[22px] max-[1050px]:px-[9px] mobile:min-h-[360px] mobile:bg-[radial-gradient(circle_at_85%_8%,#55cfe021,#0000_24%),linear-gradient(160deg,#fff,#f1f9f4)] mobile:px-1.5 mobile:pt-3 mobile:pb-[245px] dark:bg-[radial-gradient(circle_at_82%_16%,#21735521,#0000_28%),linear-gradient(145deg,#0b1511,#0f1d17)] dark:mobile:bg-[radial-gradient(circle_at_80%_12%,#55cfe012,#0000_22%),linear-gradient(160deg,#101712,#142019)]">
          <ChatMessages
            messages={messages}
            loading={loadingId === activeId}
            loadingTitle={t("chat.loadingConversation")}
            loadingHint={t("chat.loadingHint")}
            onPreview={(campaignId, channelId) => setPreview({ campaignId, channelId })}
          />
          {isGenerating && (
            <LoadingDots title={t("chat.analysing")} hint={progress || t("chat.starting")} />
          )}
        </div>
        <div className="absolute right-5 bottom-4 left-5 z-[4] m-0 overflow-hidden rounded-[14px] border-[1.5px] border-[#48b98b] bg-white shadow-[0_12px_28px_#075e4016] backdrop-blur-[12px] transition-[box-shadow,transform] duration-200 max-[1050px]:mx-[15px] mobile:sticky mobile:right-[7px] mobile:bottom-[7px] mobile:left-[7px] mobile:mx-[5px] mobile:mb-[5px] mobile:shadow-[0_10px_30px_#075e4028] dark:border-[#3e9c73] dark:bg-[#12231b] dark:text-[#edf8f1] dark:shadow-[0_16px_38px_#00000061]">
          <div className="grid min-h-[45px] grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(250px,1.5fr)] items-center justify-start gap-2 overflow-visible border-b border-[#dbe8e0] bg-[#f5faf7] px-2 py-1.5 max-[900px]:flex max-[900px]:overflow-x-auto mobile:min-h-[42px] dark:border-[#2e4d3e] dark:bg-[#152a21]">
            {product ? (
              <ContextChip
                icon={Car}
                text={product}
                onEdit={() => setModal("product")}
                onClear={() => setProduct("")}
              />
            ) : (
              <button className={CONTEXT_PILL} onClick={() => setModal("product")}>
                <Car />
                {t("chat.pickProduct")}
              </button>
            )}
            {images.length ? (
              <ContextChip
                icon={Image}
                text={t("chat.nImages", { count: images.length })}
                thumbnails={images}
                onEdit={() => setModal("images")}
                onClear={() => setImages([])}
              />
            ) : (
              <button className={CONTEXT_PILL} onClick={() => setModal("images")}>
                <Image />
                {t("chat.addImages")}
              </button>
            )}
            {audience ? (
              <ContextChip
                icon={Users}
                text={audience}
                onEdit={() => setModal("audience")}
                onClear={() => setAudience("")}
              />
            ) : (
              <button className={CONTEXT_PILL} onClick={() => setModal("audience")}>
                <Users />
                <span className="min-w-0 truncate">{t("chat.audience")}</span>
              </button>
            )}
            {tone ? (
              <ContextChip
                icon={Palette}
                text={tone}
                onEdit={() => setModal("tone")}
                onClear={() => setTone("")}
              />
            ) : (
              <button className={CONTEXT_PILL} onClick={() => setModal("tone")}>
                <Palette />
                {t("chat.toneTitle")}
              </button>
            )}
            {channels.length ? (
              <ContextChip
                icon={Megaphone}
                text={t("chat.nChannels", { count: channels.length })}
                onEdit={() => setModal("channels")}
                onClear={() => setChannels([])}
              />
            ) : (
              <button className={CONTEXT_PILL} onClick={() => setModal("channels")}>
                <Megaphone />
                {t("chat.channelsButton")}
              </button>
            )}
            <div className="flex h-9 items-center gap-[5px] rounded-[9px] border border-[#cbded3] bg-white px-1.5 py-0.5 whitespace-nowrap max-[900px]:min-w-[250px] dark:border-[#365548] dark:bg-[#1d3026]">
              <button
                aria-label={t("chat.editPeriod")}
                onClick={() => setModal("dates")}
                className="grid size-6 flex-none place-items-center rounded-[7px] bg-[#eaf5ee] text-[#087653]"
              >
                <CalendarDays className="w-3.5" />
              </button>
              <label className={DATE_LABEL}>
                {t("chat.from")}
                <input
                  aria-label={t("chat.dateFrom")}
                  type="date"
                  className={DATE_INPUT}
                  min={minimumDate}
                  value={dateFrom}
                  onChange={(event) => updateDateRange(event.target.value, dateTo)}
                />
              </label>
              <label className={DATE_LABEL}>
                {t("chat.to")}
                <input
                  aria-label={t("chat.dateTo")}
                  type="date"
                  className={DATE_INPUT}
                  min={dateFrom}
                  value={dateTo}
                  onChange={(event) => updateDateRange(dateFrom, event.target.value)}
                />
              </label>
            </div>
          </div>
          <div className="relative flex min-h-[67px] min-w-0 items-center rounded-b-xl bg-white px-2.5 pt-[7px] pb-[15px] mobile:min-h-[62px] mobile:px-1.5 mobile:py-1 dark:bg-[#101f19]">
            <textarea
              className="h-[42px] max-h-[90px] min-h-[47px] w-full min-w-0 flex-1 basis-0 resize-none overflow-y-auto py-1.5 pr-[50px] pl-[7px] text-[12px] leading-[1.45] break-words whitespace-pre-wrap outline-0 [overflow-wrap:anywhere] mobile:h-10 mobile:max-h-[68px] mobile:min-h-[43px] mobile:py-2 mobile:text-[16px] dark:bg-transparent dark:text-[#edf8f1] dark:placeholder:text-[#80998c]"
              maxLength={PROMPT_MAX_LENGTH}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
              placeholder={t("chat.promptPlaceholder")}
            />
            <small className="absolute bottom-[5px] left-[17px] text-[9px] text-[#9aa49e] dark:text-[#80998c]">
              {prompt.length}/{PROMPT_MAX_LENGTH}
            </small>
            <button
              className="absolute right-[11px] bottom-[11px] grid size-[39px] flex-none place-items-center rounded-[11px] bg-[#07955f] text-white shadow-[0_8px_20px_#075e4040] transition-[transform,box-shadow] duration-[180ms] disabled:bg-[#dbe5df] disabled:shadow-none mobile:size-[37px] dark:disabled:bg-[#263a31] dark:disabled:text-[#789087]"
              aria-label={t("chat.send")}
              disabled={!prompt.trim() || isGenerating}
              onClick={sendMessage}
            >
              <Send className="w-4" />
            </button>
          </div>
        </div>
      </section>
      {modal === "product" && (
        <ProductModal value={product} onCancel={closeModal} onApply={applyAndClose(setProduct)} />
      )}
      {modal === "images" && (
        <ImageModal value={images} onCancel={closeModal} onApply={applyAndClose(setImages)} />
      )}
      {modal === "audience" && (
        <SingleChoiceModal
          title={t("chat.audienceTitle")}
          options={AUDIENCES}
          value={audience}
          custom
          onCancel={closeModal}
          onApply={applyAndClose(setAudience)}
        />
      )}
      {modal === "tone" && (
        <SingleChoiceModal
          title={t("chat.toneTitle")}
          options={TONES}
          value={tone}
          onCancel={closeModal}
          onApply={applyAndClose(setTone)}
        />
      )}
      {modal === "channels" && (
        <ChannelModal value={channels} onCancel={closeModal} onApply={applyAndClose(setChannels)} />
      )}
      {modal === "dates" && (
        <DateRangeModal
          dateFrom={dateFrom}
          dateTo={dateTo}
          onCancel={closeModal}
          onApply={(from, to) => {
            updateDateRange(from, to);
            closeModal();
          }}
        />
      )}
      {preview && (
        <ContentPreviewModal
          campaignId={preview.campaignId}
          channelId={preview.channelId}
          onClose={() => setPreview(null)}
        />
      )}
      {toDelete && (
        <Modal
          title={t("chat.deleteTitle")}
          onCancel={() => setToDelete(null)}
          onApply={() => confirmDelete().catch(() => setToDelete(null))}
          applyLabel={t("chat.deleteTitle")}
        >
          <p>{t("chat.deleteBody")}</p>
        </Modal>
      )}
    </div>
  );
}
