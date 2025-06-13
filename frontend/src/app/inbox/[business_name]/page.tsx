// frontend/src/app/inbox/[business_name]/page.tsx
// This implements the full Nudge Inbox experience, including the new "Frictionless Contact" flow.
// ----------------------------------------------------------------------

"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, AlertCircle, MessageCircle, UserPlus, Circle } from "lucide-react";
import clsx from "clsx";
import { parseISO } from 'date-fns';

import { InboxCustomerSummary, RawCustomerSummary, BackendMessage, TimelineEntry, PaginatedInboxSummariesResponse } from "@/types";
import { InboxSkeleton } from "@/components/inbox/InboxSkeleton";
import CustomerListItem from "@/components/inbox/CustomerListItem";
import TimelineItem from "@/components/inbox/TimelineItem";
import MessageBox from "@/components/inbox/MessageBox";
import NewContactPane from "@/components/inbox/NewContactPane";

const processTimelineEntry = (msg: BackendMessage): TimelineEntry | null => {
  if (!msg.type || typeof msg.id === 'undefined') return null;
  let content: string = "[No Content]";
  let is_faq_answer: boolean = false;
  let appended_opt_in_prompt: boolean = false;

  try {
    if (typeof msg.content === 'string') {
      const parsed = JSON.parse(msg.content);
      if (typeof parsed === 'object' && parsed !== null && 'text' in parsed) {
        content = parsed.text || msg.content;
        is_faq_answer = parsed.is_faq_answer || false;
        appended_opt_in_prompt = parsed.appended_opt_in_prompt || false;
      } else {
        content = msg.content;
      }
    } else {
      content = msg.content || "[No Content]";
    }
  } catch (e) {
    // If JSON parsing fails, use content as is.
    content = msg.content || "[No Content]";
  }

  return {
    ...msg,
    content,
    timestamp: msg.sent_time || msg.scheduled_time || null,
    is_faq_answer: is_faq_answer,
    appended_opt_in_prompt: appended_opt_in_prompt,
    contextual_action: msg.contextual_action
  };
};

export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [customerSummaries, setCustomerSummaries] = useState<InboxCustomerSummary[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<TimelineEntry | null>(null);
  const [isNewMessageMode, setIsNewMessageMode] = useState(false);
  const [newlyCreatedCustomerId, setNewlyCreatedCustomerId] = useState<number | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [activeCustomerDetailsForTimeline, setActiveCustomerDetailsForTimeline] = useState<RawCustomerSummary | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [showMobileDrawer, setShowMobileDrawer] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const fetchInboxSummaries = useCallback(async (bId: number, page: number = 1, size: number = 20) => {
    try {
      const res = await apiClient.get<PaginatedInboxSummariesResponse>(`/review/inbox/summaries?business_id=${bId}&page=${page}&size=${size}`);
      setCustomerSummaries(res.data.items || []);
      return res.data.items || [];
    } catch (error) {
      console.error("Failed to fetch inbox summaries:", error);
      setFetchError("Failed to load conversation list.");
      throw error;
    }
  }, []);

  const fetchActiveCustomerHistory = useCallback(async (bId: number, custId: number) => {
    try {
      const res = await apiClient.get<RawCustomerSummary[]>(`/review/full-customer-history?business_id=${bId}`);
      const activeCustSummary = res.data.find(cs => cs.customer_id === custId);
      if (activeCustSummary) {
        setActiveCustomerDetailsForTimeline(activeCustSummary);
        setTimelineEntries(activeCustSummary.messages
          .map(msg => processTimelineEntry(msg))
          .filter((entry): entry is TimelineEntry => entry !== null)
        );
      } else {
        setActiveCustomerDetailsForTimeline(null);
        setTimelineEntries([]);
      }
    } catch (error) {
      console.error(`Failed to fetch history for customer ${custId}:`, error);
      setFetchError("Failed to load conversation history for selected customer.");
      throw error;
    }
  }, []);

  const activeCustomerHeaderDetails = useMemo(() => {
    return customerSummaries.find(cs => cs.customer_id === activeCustomerId);
  }, [customerSummaries, activeCustomerId]);


  useEffect(() => {
    const initialize = async () => {
      setIsLoading(true);
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data?.business_id;
        if (!id) throw new Error("Failed to retrieve business ID.");
        
        setBusinessId(id);
        
        const summaries = await fetchInboxSummaries(id); 

        const urlCustomerIdStr = searchParams.get('activeCustomer');
        const urlNewMessage = searchParams.get('new');
        
        if (urlNewMessage) {
          setIsNewMessageMode(true);
          setActiveCustomerId(null);
        } else if (urlCustomerIdStr) {
          const urlCustomerId = parseInt(urlCustomerIdStr, 10);
          if (summaries.some(cs => cs.customer_id === urlCustomerId)) {
            setActiveCustomerId(urlCustomerId);
            setIsNewMessageMode(false);
            await fetchActiveCustomerHistory(id, urlCustomerId); 
            await apiClient.put(`/customers/${urlCustomerId}/mark-as-read`);
            await fetchInboxSummaries(id); 
          }
        }
      } catch (error: any) {
        setFetchError(error.message || "Failed to load initial data.");
      } finally {
        setIsLoading(false);
      }
    };
    if (business_name) initialize();
  }, [business_name, fetchInboxSummaries, fetchActiveCustomerHistory, searchParams]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries]);
  
  const handleSelectCustomer = async (customerId: number) => {
    setIsNewMessageMode(false);
    setActiveCustomerId(customerId);
    setNewlyCreatedCustomerId(null); 
    setShowMobileDrawer(false);
    setSelectedDraft(null);
    router.push(`/inbox/${business_name}?activeCustomer=${customerId}`, { scroll: false });
    
    if (businessId) {
        await fetchActiveCustomerHistory(businessId, customerId);
        await apiClient.put(`/customers/${customerId}/mark-as-read`);
        await fetchInboxSummaries(businessId); 
    }
  };

  const handleNewMessageClick = () => {
    setIsNewMessageMode(true);
    setActiveCustomerId(null);
    setSelectedDraft(null);
    setNewlyCreatedCustomerId(null); 
    setShowMobileDrawer(false);
    router.push(`/inbox/${business_name}?new=true`, { scroll: false });
    setTimelineEntries([]);
    setActiveCustomerDetailsForTimeline(null);
  };
  
  const handleSendMessage = async (message: string, recipientPhone?: string) => {
    if (!businessId) return;
    
    if (isNewMessageMode) {
      if (!recipientPhone) throw new Error("Recipient phone number is required.");
      try {
        const res = await apiClient.post(`/customers/find-or-create-by-phone`, { phone_number: recipientPhone, business_id: businessId });
        const customerId = res.data.id;
        
        await apiClient.post(`/conversations/customer/${customerId}/send-message`, { message });
        
        setNewlyCreatedCustomerId(customerId); 
        setIsNewMessageMode(false);
        setActiveCustomerId(customerId);
        await fetchInboxSummaries(businessId);
        await fetchActiveCustomerHistory(businessId, customerId);
        router.push(`/inbox/${business_name}?activeCustomer=${customerId}`, { scroll: false });
      } catch (err) {
        console.error("Failed to create contact and send message", err);
        throw err;
      }
    } else {
      if (!activeCustomerId) throw new Error("No active customer selected.");
      const endpoint = selectedDraft?.ai_draft_id
        ? `/engagement-workflow/reply/${selectedDraft.ai_draft_id}/send`
        : `/conversations/customer/${activeCustomerId}/send-message`;
      const payload = selectedDraft?.ai_draft_id ? { updated_content: message } : { message };
      const method = selectedDraft?.ai_draft_id ? 'put' : 'post';

      try {
        await apiClient[method](endpoint, payload);
        await fetchInboxSummaries(businessId);
        await fetchActiveCustomerHistory(businessId, activeCustomerId);
        setSelectedDraft(null);
      } catch (err) {
        console.error("Failed to send message", err);
        await fetchInboxSummaries(businessId);
        await fetchActiveCustomerHistory(businessId, activeCustomerId);
        throw err;
      }
    }
  };

  const handleActionClick = async (nudgeId: number, actionType: string) => {
    if (!businessId) return;

    if (actionType === "REQUEST_REVIEW") {
      if (!window.confirm("Send a review request SMS to this customer?")) return;
      try {
        await apiClient.post(`/ai-nudge-copilot/nudges/${nudgeId}/sentiment-action`, { action_type: "REQUEST_REVIEW" });
        alert("Review request sent!");
        await fetchInboxSummaries(businessId);
        await fetchActiveCustomerHistory(businessId, activeCustomerId!);
      } catch (err: any) {
        alert(`Failed to send review request: ${err.response?.data?.detail || err.message}`);
      }
    } else {
      alert(`Unsupported action: ${actionType}`);
    }
  };

  const handleDeleteDraft = async (draftId: number | undefined) => {
    if (!businessId || typeof draftId === 'undefined' || !window.confirm("Delete this draft?")) return;
    try {
      await apiClient.delete(`/engagement-workflow/${draftId}`);
      await fetchInboxSummaries(businessId);
      await fetchActiveCustomerHistory(businessId, activeCustomerId!);
      setSelectedDraft(null);
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
  
  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
        <h1 className="text-xl font-semibold text-white">Nudge Inbox</h1>
        <button onClick={() => setShowMobileDrawer(true)} className="p-2" aria-label="Open contact list"><MessageSquare className="w-5 h-5 text-white" /></button>
      </div>

      <aside className={clsx("w-full md:w-80 lg:w-96 bg-[#1A1D2D] border-r border-[#2A2F45] md:relative fixed inset-0 z-30 flex flex-col h-full overflow-y-auto transition-transform", showMobileDrawer ? "translate-x-0" : "-translate-x-full md:translate-x-0")}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
          <h2 className="text-xl font-semibold text-white">Nudge Inbox</h2>
          <button onClick={handleNewMessageClick} className="p-2 rounded-md hover:bg-slate-700 transition-colors" title="New Message">
            <UserPlus className="w-5 h-5 text-white" />
          </button>
          {showMobileDrawer && <button onClick={() => setShowMobileDrawer(false)} className="p-2" aria-label="Close contact list">✕</button>}
        </div>
        <div className="flex-1 overflow-y-auto">
          {customerSummaries.length > 0 ? customerSummaries.map((cs) => (
            <CustomerListItem key={cs.customer_id} summary={cs} isActive={cs.customer_id === activeCustomerId && !isNewMessageMode} onClick={handleSelectCustomer} />
          )) : <p className="p-4 text-gray-400 text-center">No conversations yet.</p>}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-[#0F1221] h-full">
        {activeCustomerHeaderDetails ? (
          <>
            <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-white">{activeCustomerHeaderDetails.customer_name}</h3>
                <p className="text-xs text-gray-400">{activeCustomerHeaderDetails.phone} - 
                  <span className={clsx("ml-1", activeCustomerHeaderDetails.opted_in ? "text-green-400" : "text-red-400")}>{activeCustomerHeaderDetails.consent_status.replace(/_/g, ' ')}</span>
                </p>
              </div>
              {newlyCreatedCustomerId === activeCustomerId && newlyCreatedCustomerId !== null && (
                <NewContactPane customerId={newlyCreatedCustomerId} isNewlyCreated={true} />
              )}
            </div>
            
            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {timelineEntries.map((entry) => (
                <TimelineItem key={entry.id} entry={entry} onEditDraft={setSelectedDraft} onDeleteDraft={handleDeleteDraft} onActionClick={handleActionClick} />
              ))}
            </div>

            <MessageBox
              key={activeCustomerId}
              onSendMessage={handleSendMessage}
              selectedDraftId={selectedDraft?.id ?? null}
              onCancelEdit={() => setSelectedDraft(null)}
            />
          </>
        ) : isNewMessageMode ? (
            <>
              <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
                <h3 className="text-lg font-semibold text-white">New Message</h3>
              </div>
              <div className="flex-1 flex flex-col justify-between">
                <div className="p-4 text-center text-gray-400">Enter a phone number to start a new conversation.</div>
                <MessageBox 
                  onSendMessage={handleSendMessage} 
                  selectedDraftId={null}
                  onCancelEdit={() => {}}
                  isNewMessageMode={true}
                />
              </div>
            </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
            <MessageCircle className="w-16 h-16 mb-4 text-gray-500" /><p className="text-lg">Select a conversation</p><p className="text-sm">Choose a customer from the list to start messaging.</p>
          </div>
        )}
      </main>
    </div>
  );
}