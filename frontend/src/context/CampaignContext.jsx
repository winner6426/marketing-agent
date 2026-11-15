import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useTranslation } from "../i18n/index.jsx";
import { api, createIdempotencyKey, getAgentStepKey } from "../services/api.js";
import { useAuth } from "./AuthContext.jsx";

const CampaignContext = createContext(null);

function payloadFingerprint(value) {
  const text = JSON.stringify(value, Object.keys(value ?? {}).sort());
  let hash = 0;
  for (let index = 0; index < text.length; index += 1)
    hash = (hash * 31 + text.charCodeAt(index)) | 0;
  return Math.abs(hash).toString(36);
}

export function CampaignProvider({ children }) {
  const { t, language } = useTranslation();
  const { session } = useAuth();
  const token = session?.access_token;
  const [campaigns, setCampaigns] = useState([]);
  const [loadingList, setLoadingList] = useState(false);
  const [error, setError] = useState("");
  // A translation key, not text: the line must follow a language switch made mid-run.
  const [progressKey, setProgress] = useState("");
  const progress = progressKey ? t(progressKey) : "";
  const idemKeys = useRef(new Map());
  // Read through a ref so a token refresh mid-poll does not restart anything.
  const tokenRef = useRef(token);
  tokenRef.current = token;

  // The same request retried by the user must reuse its key, so the backend does not run it twice.
  const stableKey = useCallback((action, scope) => {
    const key = `${action}:${scope}`;
    if (!idemKeys.current.has(key)) idemKeys.current.set(key, createIdempotencyKey(action));
    return idemKeys.current.get(key);
  }, []);

  const refreshCampaigns = useCallback(async () => {
    if (!tokenRef.current) return [];
    setLoadingList(true);
    try {
      const list = await api.listCampaigns(tokenRef.current);
      setCampaigns(list);
      return list;
    } catch (err) {
      setError(err.message || t("campaignError.list"));
      return [];
    } finally {
      setLoadingList(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signedIn = Boolean(token);
  useEffect(() => {
    setCampaigns([]);
    setError("");
    setProgress("");
    if (signedIn) refreshCampaigns();
  }, [signedIn, refreshCampaigns]);

  const onPollUpdate = (campaign) => {
    if (campaign.status === "running" || campaign.currentNode)
      setProgress(getAgentStepKey(campaign.currentNode));
  };

  const waitIfRunning = async (started, draftId) =>
    started.status === "running"
      ? api.waitForResult(draftId, tokenRef.current, { onUpdate: onPollUpdate })
      : api.getCampaign(tokenRef.current, draftId);

  async function createChatDraft(brief, requestId, chatSessionId = null) {
    setError("");
    setProgress("progress.chatDraft");
    try {
      const started = await api.createChatDraft(
        tokenRef.current,
        { brief, chatSessionId },
        stableKey("chat-draft", requestId ?? payloadFingerprint(brief)),
      );
      const result = await waitIfRunning(started, started.draft_id);
      setProgress(
        result.humanWait?.type === "clarification" ? "progress.needBrief" : "progress.draftReady",
      );
      refreshCampaigns();
      return { ...result, draft_id: started.draft_id };
    } catch (err) {
      setError(err.message || t("campaignError.chatDraft"));
      throw err;
    }
  }

  async function answerChatDraft(briefAdditions, draftId) {
    setError("");
    setProgress("progress.analysing");
    try {
      const started = await api.answerChatDraft(
        tokenRef.current,
        draftId,
        briefAdditions,
        stableKey(`chat-answer-${payloadFingerprint(briefAdditions)}`, draftId),
      );
      const result = await waitIfRunning(started, draftId);
      refreshCampaigns();
      return { ...result, draft_id: Number(draftId) };
    } catch (err) {
      setError(err.message || t("campaignError.draftAdditions"));
      throw err;
    }
  }

  const value = useMemo(
    () => ({
      campaigns,
      loadingList,
      error,
      progress,
      refreshCampaigns,
      createChatDraft,
      answerChatDraft,
      clearError: () => setError(""),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [campaigns, loadingList, error, progressKey, language, refreshCampaigns],
  );
  return <CampaignContext.Provider value={value}>{children}</CampaignContext.Provider>;
}

export function useCampaigns() {
  const value = useContext(CampaignContext);
  if (!value) throw new Error("useCampaigns must be used inside CampaignProvider");
  return value;
}
