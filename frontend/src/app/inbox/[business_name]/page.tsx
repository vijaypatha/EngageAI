// FILE: frontend/src/app/inbox/[business_name]/page.tsx

"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, AlertCircle, MessageCircle } from "lucide-react";
import clsx from "clsx";
import { parseISO } from 'date-fns';

import { InboxCustomerSummary, RawCustomerSummary, BackendMessage, TimelineEntry } from "@/types";
import { InboxSkeleton } from "@/components/inbox/InboxSkeleton";
import CustomerListItem from "@/components/inbox/CustomerListItem";
import TimelineItem from "@/components/inbox/TimelineItem";
import MessageBox from "@/components/inbox/MessageBox";

// --- Helper Functions for Data Transformation ---

const processTimelineEntry = (msg: BackendMessage, customerId: number): TimelineEntry | null => {
  if (!msg.type || typeof msg.id === 'undefined') return null;

  let content: string = "[No Content]";
  let is_faq_answer = false;
  let appended_opt_in_prompt = false;

  switch (msg.type) {
    case 'outbound':
    case 'outbound_ai_reply':
      if (typeof msg.content === 'string') {
        try {
          const parsed = JSON.parse(msg.content);
          content = parsed.text || msg.content;
          is_faq_answer = !!parsed.is_faq_answer;
          appended_opt_in_prompt = !!parsed.appended_opt_in_prompt;
        } catch (e) {
          content = msg.content;
        }
      } else if (msg.content) {
        content = String(msg.content);
      }
      break;

    case 'ai_draft':
      content = msg.ai_response || "[No Content]";
      break;

    default: // Handles 'inbound', 'scheduled', 'failed_to_send', etc.
      content = msg.content || msg.response || "[No Content]";
      break;
  }

  return {
    id: msg.type === 'ai_draft' ? `eng-ai-${msg.id}` : msg.id,
    type: msg.type,
    content,
    timestamp: msg.sent_time || msg.scheduled_time || null,
    customer_id: customerId,
    status: msg.status,
    is_faq_answer,
    appended_opt_in_prompt,
  };
};

const processCustomerSummary = (cs: RawCustomerSummary, lastSeenMap: Record<number, string>): InboxCustomerSummary => {
  const validMessages = (Array.isArray(cs.messages) ? cs.messages : [])
    .filter(m => ['inbound', 'outbound', 'outbound_ai_reply', 'scheduled', 'scheduled_pending', 'failed_to_send'].includes(m.type) && !m.is_hidden)
    .sort((a, b) => new Date(b.sent_time || b.scheduled_time || 0).getTime() - new Date(a.sent_time || a.scheduled_time || 0).getTime());
  
  const lastMsg = validMessages[0] || null;
  
  let previewContent = "[No recent messages]";
  if (lastMsg?.content) {
    try {
      if (typeof lastMsg.content === 'string') {
        const parsed = JSON.parse(lastMsg.content);
        previewContent = parsed.text || lastMsg.content;
      } else {
        previewContent = (lastMsg.content as any).text || JSON.stringify(lastMsg.content);
      }
    } catch { previewContent = lastMsg.content; }
  } else if (lastMsg?.response) {
    previewContent = lastMsg.response;
  }
  
  const last_message_timestamp = lastMsg?.sent_time || lastMsg?.scheduled_time || cs.consent_updated || "1970-01-01T00:00:00.000Z";
  const lastSeenDate = lastSeenMap[cs.customer_id] ? parseISO(lastSeenMap[cs.customer_id]) : null;
  const is_unread = lastSeenDate ? parseISO(last_message_timestamp).getTime() > lastSeenDate.getTime() : true;

  return {
    ...cs,
    last_message_preview: previewContent.slice(0, 40) + (previewContent.length > 40 ? "..." : ""),
    last_message_timestamp,
    is_unread
  };
};

export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [rawSummaries, setRawSummaries] = useState<RawCustomerSummary[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<TimelineEntry | null>(null);
  
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [lastSeenMap, setLastSeenMap] = useState<Record<number, string>>({});
  const [showMobileDrawer, setShowMobileDrawer] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);

  // --- Data Fetching and Processing ---

  const fetchFullHistory = useCallback(async (bId: number) => {
    try {
      // Assuming your API is now updated to return 'inbound'/'outbound' types
      const res = await apiClient.get<RawCustomerSummary[]>(`/review/full-customer-history?business_id=${bId}`);
      setRawSummaries(res.data || []);
      return res.data || [];
    } catch (error) {
      console.error("Failed to fetch customer summaries:", error);
      setFetchError("Failed to load conversation history.");
      throw error;
    }
  }, []);

  const customerSummaries = useMemo<InboxCustomerSummary[]>(() => {
    const processed = rawSummaries.map(cs => processCustomerSummary(cs, lastSeenMap));
    processed.sort((a, b) => new Date(b.last_message_timestamp).getTime() - new Date(a.last_message_timestamp).getTime());
    return processed;
  }, [rawSummaries, lastSeenMap]);

  const timelineEntries = useMemo<TimelineEntry[]>(() => {
    const currentCustomer = rawSummaries.find(cs => cs.customer_id === activeCustomerId);
    if (!currentCustomer || !currentCustomer.messages) return [];
    
    const entries = currentCustomer.messages
      .map(msg => processTimelineEntry(msg, currentCustomer.customer_id))
      .filter((entry): entry is TimelineEntry => entry !== null)
      .sort((a, b) => new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime());
    return entries;
  }, [rawSummaries, activeCustomerId]);

  // --- Effects ---

  useEffect(() => {
    const initialize = async () => {
      if (!business_name) {
        setFetchError("Business identifier is missing.");
        setIsLoading(false);
        return;
      }
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data?.business_id;
        if (!id) {
          setFetchError("Failed to retrieve business ID.");
          setIsLoading(false);
          return;
        }
        setBusinessId(id);
        const summaries = await fetchFullHistory(id);
        const urlCustomerIdStr = searchParams.get('activeCustomer');
        if (urlCustomerIdStr) {
          const urlCustomerId = parseInt(urlCustomerIdStr, 10);
          if (summaries.some(cs => cs.customer_id === urlCustomerId)) {
            setActiveCustomerId(urlCustomerId);
          }
        }
      } catch (error: any) {
        setFetchError(error.message || "Failed to load initial data.");
      } finally {
        setIsLoading(false);
      }
    };
    initialize();
  }, [business_name, fetchFullHistory, searchParams]);

  useEffect(() => {
    if (!businessId) return;
    const intervalId = setInterval(() => {
      if (document.visibilityState === 'visible') fetchFullHistory(businessId);
    }, 30000);
    return () => clearInterval(intervalId);
  }, [businessId, fetchFullHistory]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries]);

  // --- Handlers ---
  
  const handleSelectCustomer = (customerId: number) => {
    setActiveCustomerId(customerId);
    setShowMobileDrawer(false);
    setSelectedDraft(null);
    setLastSeenMap(prev => ({ ...prev, [customerId]: new Date().toISOString() }));
    router.push(`/inbox/${business_name}?activeCustomer=${customerId}`, { scroll: false });
  };
  
  const handleSendMessage = async (message: string) => {
    if (!activeCustomerId) throw new Error("No active customer selected.");

    const endpoint = selectedDraft
      ? `/engagement-workflow/reply/${selectedDraft.id.toString().replace('eng-ai-','')}/send`
      : `/conversations/customer/${activeCustomerId}/send-message`;
    
    const payload = selectedDraft ? { updated_content: message } : { message };
    const method = selectedDraft ? 'put' : 'post';

    try {
      await apiClient[method](endpoint, payload);
      if (businessId) await fetchFullHistory(businessId);
      setSelectedDraft(null);
    } catch (err: any) {
      console.error("Failed to send message", err);
      if (businessId) await fetchFullHistory(businessId);
      throw err;
    }
  };

  const handleDeleteDraft = async (draftId: string | number) => {
    const numericId = parseInt(String(draftId).replace('eng-ai-', ''), 10);
    if (isNaN(numericId) || !window.confirm("Delete this draft?")) return;
    
    try {
      await apiClient.delete(`/engagement-workflow/${numericId}`);
      if (businessId) await fetchFullHistory(businessId);
      if (selectedDraft?.id === draftId) setSelectedDraft(null);
    } catch (err: any) {
      alert(`Failed to delete draft: ${err.response?.data?.detail || err.message}`);
    }
  };

  if (isLoading) return <InboxSkeleton />;

  if (fetchError) return (
    <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
      <AlertCircle className="w-12 h-12 mb-3 text-red-500" />
      <p className="text-xl font-semibold">Oops! Something went wrong.</p>
      <p className="text-sm mt-1">{fetchError}</p>
    </div>
  );
  
  const activeCustomerDetails = customerSummaries.find(cs => cs.customer_id === activeCustomerId);

  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
        <h1 className="text-xl font-semibold text-white">Inbox</h1>
        <button onClick={() => setShowMobileDrawer(true)} className="p-2" aria-label="Open contact list"><MessageSquare className="w-5 h-5 text-white" /></button>
      </div>

      <aside className={clsx("w-full md:w-80 bg-[#1A1D2D] border-r border-[#2A2F45] md:relative fixed inset-0 z-30 flex flex-col h-full overflow-y-auto transition-transform", showMobileDrawer ? "translate-x-0" : "-translate-x-full md:translate-x-0")}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
          <h2 className="text-xl font-semibold text-white">Inbox</h2>
          {showMobileDrawer && <button onClick={() => setShowMobileDrawer(false)} className="p-2" aria-label="Close contact list">✕</button>}
        </div>
        <div className="flex-1 overflow-y-auto">
          {customerSummaries.length > 0 ? customerSummaries.map((cs) => (
            <CustomerListItem key={cs.customer_id} summary={cs} isActive={cs.customer_id === activeCustomerId} onClick={handleSelectCustomer} />
          )) : <p className="p-4 text-gray-400 text-center">No conversations yet.</p>}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-[#0F1221] h-full">
        {activeCustomerDetails ? (
          <>
            <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
              <h3 className="text-lg font-semibold text-white">{activeCustomerDetails.customer_name}</h3>
              <p className="text-xs text-gray-400">{activeCustomerDetails.phone} - 
                <span className={clsx("ml-1", activeCustomerDetails.opted_in ? "text-green-400" : "text-red-400")}>{activeCustomerDetails.consent_status.replace(/_/g, ' ')}</span>
              </p>
            </div>
            
            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {timelineEntries.map((entry) => (
                <TimelineItem key={entry.id} entry={entry} onEditDraft={setSelectedDraft} onDeleteDraft={handleDeleteDraft} />
              ))}
            </div>

            <MessageBox
              key={activeCustomerId}
              customer={activeCustomerDetails}
              selectedDraftId={selectedDraft?.id || null}
              onSendMessage={handleSendMessage}
              onCancelEdit={() => setSelectedDraft(null)}
              initialMessage={selectedDraft?.content}
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
            <MessageCircle className="w-16 h-16 mb-4 text-gray-500" /><p className="text-lg">Select a conversation</p><p className="text-sm">Choose a customer to view messages.</p>
          </div>
        )}
      </main>
    </div>
  );
}