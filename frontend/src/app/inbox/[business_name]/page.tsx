// frontend/src/app/inbox/[business_name]/page.tsx
"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Clock, Send, MessageSquare, Check, AlertCircle, Trash2, Edit3, CheckCheck } from "lucide-react";
import clsx from "clsx";

interface CustomerSummary {
  customer_id: number;
  customer_name: string;
  phone: string;
  opted_in: boolean;
  consent_status: string;
  consent_updated?: string | null;
  message_count: number;
  messages: BackendMessage[];
  content?: string;
  sent_time?: string;
}

interface BackendMessage {
  id: string | number;
  type: "sent" | "customer" | "ai_draft" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message"; // Added more types from backend
  content: any; // Allow content to be object or string initially
  status?: string;
  scheduled_time?: string | null;
  sent_time?: string | null;
  source?: string; // Added source from backend
  customer_id: number;
  is_hidden?: boolean;
  response?: string;
}

type TimelineEntry = {
  id: string | number;
  type: "customer" | "sent" | "ai_draft" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message"; // Matched BackendMessage
  content: string;
  timestamp: string | null;
  customer_id: number;
  is_hidden?: boolean;
  status?: string;
  source?: string; // Added source here as well
};

export default function InboxPage() {
  const { business_name } = useParams<{business_name: string}>();
  const [customerSummaries, setCustomerSummaries] = useState<CustomerSummary[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<string | number | null>(null);

  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [lastSeenMap, setLastSeenMap] = useState<Record<number, string>>({});
  const [showMobileDrawer, setShowMobileDrawer] = useState(false);

  const chatContainerRef = useRef<null | HTMLDivElement>(null);
  const inputRef = useRef<null | HTMLInputElement>(null);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries]);

  const fetchAndSetCustomerSummaries = async (bId: number) => {
    const res = await apiClient.get(`/review/full-customer-history?business_id=${bId}`);
    const customerDataArray: CustomerSummary[] = res.data || [];

    const summariesWithPreview = customerDataArray.map(cs => {
        // First, ensure messages exist and are an array
        const validMessages = Array.isArray(cs.messages) ? cs.messages : [];
        const lastMsgArray = validMessages
            .filter(m => m.type === 'sent' || m.type === 'customer')
            .sort((a,b) => new Date(b.sent_time || b.scheduled_time || 0).getTime() - new Date(a.sent_time || a.scheduled_time || 0).getTime());
        const lastMsg = lastMsgArray.length > 0 ? lastMsgArray[0] : null;

        // Content preview logic
        let previewContent = "";
        if (lastMsg?.content) {
            if (typeof lastMsg.content === 'string') {
                try {
                    const parsed = JSON.parse(lastMsg.content);
                    if (parsed && typeof parsed.text === 'string') {
                        previewContent = parsed.text;
                    } else {
                        previewContent = lastMsg.content;
                    }
                } catch (e) {
                    previewContent = lastMsg.content;
                }
            } else if (typeof lastMsg.content === 'object' && lastMsg.content !== null && typeof (lastMsg.content as any).text === 'string') {
                previewContent = (lastMsg.content as any).text;
            }
        }

        return {
          ...cs,
          content: previewContent.slice(0,30) + (previewContent.length > 30 ? "..." : ""),
          sent_time: lastMsg?.sent_time || lastMsg?.scheduled_time || cs.consent_updated || "1970-01-01T00:00:00.000Z"
        }
      });

    summariesWithPreview.sort((a,b) => {
        const timeA = a.sent_time ? new Date(a.sent_time).getTime() : 0;
        const timeB = b.sent_time ? new Date(b.sent_time).getTime() : 0;
        return timeB - timeA;
    });
    setCustomerSummaries(summariesWithPreview);
    return summariesWithPreview;
  };

  useEffect(() => {
    const initialize = async () => {
      if (!business_name) {
        setIsLoading(false);
        setFetchError("Business identifier is missing.");
        return;
      }
      setIsLoading(true);
      setFetchError(null);
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data.business_id;
        setBusinessId(id);

        if (id) {
          const initialSummaries = await fetchAndSetCustomerSummaries(id);
          if (initialSummaries.length > 0 && initialSummaries[0].customer_id){
              setActiveCustomerId(initialSummaries[0].customer_id);
          } else {
            setActiveCustomerId(null);
          }
        } else {
          setFetchError("Failed to retrieve business ID.");
        }
      } catch (error: any) {
        setFetchError(error.message || "Failed to load initial data.");
      } finally {
        setIsLoading(false);
      }
    };
    initialize();
  }, [business_name]);

  useEffect(() => {
    if (!businessId ) return;
    const interval = setInterval(async () => {
      try {
        await fetchAndSetCustomerSummaries(businessId);
      } catch (error) {
        // silent fail for polling
      }
    }, 7000);
    return () => clearInterval(interval);
  }, [businessId]);

  useEffect(() => {
    const currentCustomerData = customerSummaries.find(cs => cs.customer_id === activeCustomerId);
    let newTimelineEntries: TimelineEntry[] = [];

    if (currentCustomerData && Array.isArray(currentCustomerData.messages)) {
      newTimelineEntries = currentCustomerData.messages
        .filter(msg => !msg.is_hidden)
        .map((msg: BackendMessage): TimelineEntry | null => {
          if (!msg.type || typeof msg.id === 'undefined') return null;

          // --- FIX 1: MODIFIED CONTENT PARSING START ---
          let processedContent = "";
          if (typeof msg.content === 'string') {
            try {
              const parsedJson = JSON.parse(msg.content);
              // Check for nested text structure: {"text": {"text": "..."}}
              if (parsedJson && typeof parsedJson === 'object' && parsedJson.text && typeof parsedJson.text === 'object' && typeof parsedJson.text.text === 'string') {
                  processedContent = parsedJson.text.text; // Extract the deeply nested text
              } else if (parsedJson && typeof parsedJson.text === 'string') {
                  // Handle the simpler {"text": "..."} structure
                  processedContent = parsedJson.text;
              } else {
                // It's a string, but not the JSON structure we expect, or no 'text' field. Use as is.
                processedContent = msg.content;
              }
            } catch (e) {
              // Not a valid JSON string, use as is
              processedContent = msg.content;
            }
          } else if (typeof msg.content === 'object' && msg.content !== null) {
            // It's already an object, try to access 'text' property
            // Also check for the nested structure if it's already an object
            if (typeof (msg.content as any).text === 'object' && typeof (msg.content as any).text.text === 'string') {
                 processedContent = (msg.content as any).text.text; // Extract deeply nested text from object
            } else if (typeof (msg.content as any).text === 'string') {
              processedContent = (msg.content as any).text; // Extract simple text from object
            } else {
              // Object doesn't have 'text' (or it's not a string/nested object), or it's not a string. Stringify for display.
              processedContent = JSON.stringify(msg.content);
            }
          } else if (msg.type === "customer" && msg.response) {
            // Fallback for customer messages if content is missing but response exists
             processedContent = msg.response;
          }
          // --- FIX 1: MODIFIED CONTENT PARSING END ---


          return {
            id: String(msg.id),
            type: msg.type as TimelineEntry['type'],
            content: processedContent, // Use the processed content
            timestamp: msg.sent_time || msg.scheduled_time || null,
            customer_id: currentCustomerData.customer_id,
            is_hidden: msg.is_hidden || false,
            status: msg.status,
            source: msg.source // Ensure source is mapped
          };
        }).filter(Boolean) as TimelineEntry[];

      newTimelineEntries.sort((a, b) => {
        const timeA = a.timestamp ? new Date(a.timestamp).getTime() : null;
        const timeB = b.timestamp ? new Date(b.timestamp).getTime() : null;
        const validTimeA = timeA !== null && !isNaN(timeA) ? timeA : null;
        const validTimeB = timeB !== null && !isNaN(timeB) ? timeB : null;
        if (validTimeA === null && validTimeB === null) return String(a.id).localeCompare(String(b.id));
        if (validTimeA === null) return 1;
        if (validTimeB === null) return -1;
        return validTimeA - validTimeB;
      });
    }
    setTimelineEntries(newTimelineEntries);
  }, [customerSummaries, activeCustomerId]);

  const handleSendMessage = async () => {
    const messageToSend = newMessage.trim();
    if (!messageToSend || isSending) return;
    setIsSending(true);
    setSendError(null);
    const isSendingDraft = selectedDraftId != null && activeCustomerId;
    const targetCustomerId = activeCustomerId;
    if (!targetCustomerId) {
        setSendError("No active customer selected.");
        setIsSending(false);
        return;
    }
    try {
      if (isSendingDraft && selectedDraftId) {
        let numericIdToSend: number;
        if (typeof selectedDraftId === 'string') {
          const match = selectedDraftId.match(/\d+$/);
          if (match) {
            numericIdToSend = parseInt(match[0], 10);
          } else {
            console.error("Could not parse numeric ID from selectedDraftId:", selectedDraftId);
            setSendError("Error: Could not identify the draft to send.");
            setIsSending(false);
            return;
          }
        } else {
          numericIdToSend = selectedDraftId;
        }
        await apiClient.put(`/engagement-workflow/reply/${numericIdToSend}/send`, { updated_content: messageToSend });
      } else {
        await apiClient.post(`/conversations/customer/${targetCustomerId}/reply`, { message: messageToSend });
      }
      setNewMessage("");
      setSelectedDraftId(null);
      if (inputRef.current) inputRef.current.focus();
      if (businessId) await fetchAndSetCustomerSummaries(businessId);
      setLastSeenMap(prev => ({ ...prev, [targetCustomerId]: new Date().toISOString() }));
    } catch (err: any) {
      const response = err?.response;
      const status = response?.status;
      const detail = response?.data?.detail || err.message || "An error occurred.";
      setSendError(`Failed to send: ${detail}. Status: ${status || 'N/A'}`);
      if ((status === 409 || status === 404) && businessId) {
        await fetchAndSetCustomerSummaries(businessId);
      }
    } finally {
      setIsSending(false);
    }
  };

  const handleEditDraft = (draft: TimelineEntry) => {
    // Ensure we only allow editing actual drafts
    if (draft.type === 'ai_draft' && draft.source === 'ai_draft_suggestion' && draft.customer_id === activeCustomerId) {
      setSelectedDraftId(draft.id);
      setNewMessage(draft.content); // This will now be the processed string content
      if (inputRef.current) inputRef.current.focus();
    }
  };

  const handleDeleteDraft = async (draftTimelineEntryId: string | number) => {
    let numericDraftId: number;

    if (typeof draftTimelineEntryId === 'string') {
      if (draftTimelineEntryId.startsWith('eng-ai-')) {
        numericDraftId = parseInt(draftTimelineEntryId.replace('eng-ai-', ''), 10);
      } else {
        const match = draftTimelineEntryId.match(/\d+$/);
        numericDraftId = match ? parseInt(match[0], 10) : NaN;
      }
    } else if (typeof draftTimelineEntryId === 'number') {
      numericDraftId = draftTimelineEntryId;
    } else {
      console.error("[InboxPage] Invalid draft ID format for deletion:", draftTimelineEntryId);
      alert("Cannot delete draft: Invalid ID format.");
      return;
    }

    if (isNaN(numericDraftId)) {
        console.error("[InboxPage] Could not parse a valid numeric ID from draft ID:", draftTimelineEntryId);
        alert("Cannot delete draft: ID is not a valid number after parsing.");
        return;
    }

    // Check if the entry is actually a deletable draft before confirming
    const entryToDelete = timelineEntries.find(e => e.id === draftTimelineEntryId);
    if (!(entryToDelete && entryToDelete.type === 'ai_draft' && entryToDelete.source === 'ai_draft_suggestion')) { // Changed to 'ai_draft_suggestion' for consistency if this is the intended source for drafts
        alert("This message is not a draft and cannot be deleted this way.");
        return;
    }

    if (window.confirm("Delete this draft? This action cannot be undone.")) {
      try {
        await apiClient.delete(`/engagement-workflow/${numericDraftId}`);
        setTimelineEntries((prev) => prev.filter((e) => e.id !== draftTimelineEntryId));
        if (selectedDraftId === draftTimelineEntryId) {
          setNewMessage("");
          setSelectedDraftId(null);
        }
        if (businessId) {
            await fetchAndSetCustomerSummaries(businessId);
        }
      } catch (err: any) {
        console.error("[InboxPage] ❌ API call to delete draft failed:", err);
        const errorDetail = err.response?.data?.detail || err.message || "An unknown error occurred.";
        alert(`Failed to delete draft: ${errorDetail}`);
      }
    }
  };

  const currentCustomer = useMemo(() => {
    return customerSummaries.find(cs => cs.customer_id === activeCustomerId);
  }, [customerSummaries, activeCustomerId]);

  if (isLoading && !customerSummaries.length) {
    return <div className="h-screen flex items-center justify-center bg-[#0B0E1C] text-white text-lg">Loading Inbox... <span className="animate-pulse">⏳</span></div>;
  }

  if (fetchError && !customerSummaries.length) {
    return <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
        <AlertCircle className="w-12 h-12 mb-3 text-red-500"/>
        <p className="text-xl font-semibold">Oops! Something went wrong.</p>
        <p className="text-sm mt-1">{fetchError}</p>
        <p className="text-xs mt-3">Please try refreshing the page. If the problem persists, contact support.</p>
    </div>;
  }

  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45]">
        <h1 className="text-xl font-semibold text-white">Inbox</h1>
        <button
          onClick={() => setShowMobileDrawer(!showMobileDrawer)}
          className="p-2 hover:bg-[#242842] rounded-lg transition-colors"
          aria-label="Toggle contact list"
        >
          <MessageSquare className="w-5 h-5 text-white" />
        </button>
      </div>

      <aside className={clsx(
        "w-full md:w-80 bg-[#1A1D2D] border-r border-[#2A2F45]",
        "md:relative fixed inset-0 z-30 md:z-auto",
        "transition-transform duration-300 ease-in-out",
        showMobileDrawer ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        "flex flex-col h-full"
      )}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45]">
          <h2 className="text-xl font-semibold text-white">{showMobileDrawer ? "Contacts" : "Inbox"}</h2>
          {showMobileDrawer && (
            <button
              onClick={() => setShowMobileDrawer(false)}
              className="p-2 hover:bg-[#242842] rounded-lg"
              aria-label="Close contact list"
            >
              ✕
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {customerSummaries.length === 0 && !isLoading && (
            <p className="p-4 text-gray-400 text-center">No conversations yet. Add contacts to begin.</p>
          )}
          {customerSummaries.map((cs) => {
            // The previewText logic in fetchAndSetCustomerSummaries already handles content parsing
            const previewText = cs.content || "No recent messages";
            return (
                <div
                key={cs.customer_id}
                onClick={() => {
                    setActiveCustomerId(cs.customer_id);
                    setSelectedDraftId(null);
                    setNewMessage("");
                    setLastSeenMap(prev => ({ ...prev, [cs.customer_id]: new Date().toISOString() }));
                    if (showMobileDrawer) setShowMobileDrawer(false);
                }}
                className={clsx(
                    "p-4 cursor-pointer border-b border-[#2A2F45] last:border-b-0",
                    "hover:bg-[#242842] transition-colors",
                    cs.customer_id === activeCustomerId && "bg-[#242842]"
                )}
                >
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 flex items-center justify-center text-white font-medium">
                    {cs.customer_name?.[0]?.toUpperCase() || '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                        <span className="font-medium text-white truncate">
                        {cs.customer_name || 'Unknown Customer'}
                        </span>
                    </div>
                    <p className="text-sm text-gray-400 truncate">
                        {previewText}
                    </p>
                    </div>
                </div>
                </div>
            );
            })}
        </div>
      </aside>

      <main className="flex-1 flex flex-col h-[calc(100vh-4rem)] md:h-screen">
        {currentCustomer ? (
          <>
            <div className="bg-[#1A1D2D] border-b border-[#2A2F45] p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 flex items-center justify-center text-white font-medium">
                  {currentCustomer.customer_name[0]?.toUpperCase() || '?'}
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-white">{currentCustomer.customer_name}</h1>
                  <span className={clsx(
                    "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs",
                    currentCustomer.opted_in ? "bg-emerald-400/10 text-emerald-400" : "bg-red-400/10 text-red-400"
                  )}>
                    {currentCustomer.opted_in ? <><Check className="w-3 h-3" /> Opted In</> : <><AlertCircle className="w-3 h-3" /> Not Opted In</>}
                  </span>
                </div>
              </div>
            </div>

            <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-2">
              {timelineEntries.map((entry, index) => {
                const isActualDraft = entry.type === "ai_draft" && entry.source === "ai_draft_suggestion"; // Assuming 'ai_draft_suggestion' for actual drafts
                const isSentByBusiness = entry.type === "sent";

                return (
                  // --- FIX 2: MODIFIED MESSAGE BUBBLE RENDERING START ---
                  <div
                    key={`${entry.type}-${entry.id}-${index}`} // Consider using just entry.id if unique enough
                    className={clsx(
                        "flex flex-col w-full mb-1", // mb-1 provides spacing between distinct bubbles
                        entry.type === "customer" ? "items-start" : "items-end")}
                  >
                    { (index === 0 || (entry.timestamp && timelineEntries[index-1]?.timestamp && new Date(entry.timestamp).toDateString() !== new Date(timelineEntries[index-1].timestamp!).toDateString())) && entry.timestamp && (
                          <div className="text-xs text-gray-500 my-3 self-center px-2 py-0.5 bg-[#1A1D2D] border border-[#2A2F45] rounded-full">
                             {new Date(entry.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                          </div>
                      )}
                    <div className={clsx(
                      "max-w-[80%] md:max-w-[70%] px-3.5 py-2 rounded-2xl shadow", // rounded-2xl applies roundness to all corners
                      entry.type === "customer" ? "bg-gradient-to-r from-emerald-500 to-blue-500 text-white" : // Removed rounded-br-none
                      isSentByBusiness ? "bg-[#242842] text-white" : // Removed rounded-bl-none
                      isActualDraft ? "bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white" : // Removed rounded-bl-none
                      "bg-[#242842] text-white" // Removed rounded-bl-none
                    )}>
                      {isActualDraft && (
                        <div className="text-xs font-semibold mb-1 text-purple-200">💡 Draft Reply</div>
                      )}
                      <div className="whitespace-pre-wrap break-words text-sm">{entry.content}</div>

                      {(entry.type === "sent" || entry.type === "customer") && entry.timestamp && (
                        <div className={clsx(
                          "text-xs mt-1.5 flex items-center gap-1",
                          entry.type === "customer" ? "text-gray-200/70 justify-start" : "text-gray-400/70 justify-end",
                        )}>
                          <Clock className="w-2.5 h-2.5" />
                          <span>
                            {new Date(entry.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })}
                          </span>
                          {isSentByBusiness && entry.status === "sent" && (
                            <Check className="w-3.5 h-3.5 text-sky-400 ml-0.5" />
                          )}
                          {isSentByBusiness && entry.status === "auto_replied_faq" && (
                            <CheckCheck className="w-3.5 h-3.5 text-emerald-400 ml-0.5" />
                          )}
                        </div>
                      )}
                      {isActualDraft && (
                        <div className="mt-2 flex items-center gap-3 border-t border-white/10 pt-2">
                          <button
                            onClick={() => handleEditDraft(entry)}
                            className="text-xs font-medium text-purple-200 hover:text-white flex items-center gap-1 transition-colors p-1 hover:bg-white/10 rounded"
                            aria-label="Edit draft"
                          >
                            <Edit3 className="w-3 h-3" /> Edit
                          </button>
                          <button
                            onClick={() => handleDeleteDraft(entry.id)}
                            className="text-xs font-medium text-purple-200 hover:text-white flex items-center gap-1 transition-colors p-1 hover:bg-white/10 rounded"
                            aria-label="Delete draft"
                          >
                            <Trash2 className="w-3 h-3" /> Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  // --- FIX 2: MODIFIED MESSAGE BUBBLE RENDERING END ---
                )
              })}
               {timelineEntries.length === 0 && (
                    <div className="text-center text-gray-400 py-10">No messages in this conversation yet.</div>
                )}
            </div>

            <div className="bg-[#1A1D2D] border-t border-[#2A2F45] p-4">
              {!currentCustomer.opted_in && (
                 <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg px-4 py-3 mb-3 gap-2">
                    <div className="flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        <span className="text-sm">Messaging blocked: Customer has not opted in.</span>
                    </div>
                    <button
                        onClick={async () => {
                        if (!activeCustomerId) return;
                        try {
                            await apiClient.post(`/consent/resend-optin/${activeCustomerId}`);
                            alert("A new opt-in request has been sent to the customer.");
                        } catch (err) {
                            alert("Failed to resend opt-in request. Please try again.");
                        }
                        }}
                        className="w-full sm:w-auto bg-[#242842] hover:bg-[#2A2F45] text-white text-xs px-3 py-1.5 rounded-md transition-colors whitespace-nowrap"
                    >
                        💌 Request Opt-In
                    </button>
                </div>
              )}
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyPress={(e) => { if (e.key === 'Enter' && !isSending && newMessage.trim() && currentCustomer.opted_in) handleSendMessage(); }}
                  placeholder={currentCustomer.opted_in ? "Type your message..." : "Customer not opted in"}
                  className="flex-1 bg-[#242842] border border-[#2A2F45] px-4 py-3 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all text-sm"
                  disabled={!currentCustomer.opted_in || isSending}
                />
                <button
                  onClick={handleSendMessage}
                  disabled={isSending || !newMessage.trim() || !currentCustomer.opted_in}
                  className={clsx(
                    "p-3 rounded-lg transition-all duration-200",
                    "bg-gradient-to-r from-emerald-500 to-blue-500 hover:opacity-90",
                    (isSending || !newMessage.trim() || !currentCustomer.opted_in) && "opacity-50 cursor-not-allowed",
                    isSending && "animate-pulse"
                  )}
                  aria-label="Send message"
                >
                  <Send className="w-5 h-5 text-white" />
                </button>
              </div>
              {sendError && (
                <div className="text-xs text-red-400 mt-2 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> {sendError}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 p-8 text-center">
            <MessageSquare className="w-16 h-16 mb-4 opacity-50" />
            <p className="text-xl font-semibold">Select a conversation</p>
            <p className="text-sm mt-1">Choose a contact from the list to see your message history.</p>
            {customerSummaries.length === 0 && !isLoading && (
                 <p className="text-sm mt-2">No contacts found. Add contacts from the "Contacts" page to begin.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}