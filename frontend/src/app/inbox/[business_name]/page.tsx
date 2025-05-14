// frontend/src/app/inbox/[business_name]/page.tsx
"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Clock, Send, MessageSquare, Check, AlertCircle, Trash2, Edit3, CheckCheck, User, Phone, MessageCircle } from "lucide-react";
import clsx from "clsx";
import { format, isValid, parseISO } from 'date-fns';

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
  type: "sent" | "customer" | "ai_draft" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
  content: any;
  status?: string;
  scheduled_time?: string | null;
  sent_time?: string | null;
  source?: string;
  customer_id: number;
  is_hidden?: boolean;
  response?: string;
  ai_response?: string;
}

type TimelineEntry = {
  id: string | number;
  type: "customer" | "sent" | "ai_draft" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
  content: string;
  timestamp: string | null;
  customer_id: number;
  is_hidden?: boolean;
  status?: string;
  source?: string;
  is_faq_answer?: boolean;
  appended_opt_in_prompt?: boolean;
};

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "Invalid date";
  try {
    const now = new Date();
    if (format(date, 'yyyy-MM-dd') === format(now, 'yyyy-MM-dd')) {
      return format(date, "p");
    }
    if (now.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000) {
      return format(date, "eee");
    }
    return format(date, "MMM d");
  } catch (e) {
    console.error("Error formatting date:", dateString, e);
    return "Invalid date";
  }
};

const formatMessageTimestamp = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "";
  try {
    return format(date, "MMM d, p");
  } catch (e) {
    return "";
  }
};

export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
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

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    requestAnimationFrame(() => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
      }
    });
  }, [timelineEntries]);

  const fetchAndSetCustomerSummaries = async (bId: number) => {
    try {
      const res = await apiClient.get(`/review/full-customer-history?business_id=${bId}`);
      const customerDataArray: CustomerSummary[] = res.data || [];

      const summariesWithPreview = customerDataArray.map(cs => {
        const validMessages = Array.isArray(cs.messages) ? cs.messages : [];
        const lastMsgArray = validMessages
          .filter(m => ['sent', 'customer', 'outbound_ai_reply', 'scheduled', 'scheduled_pending'].includes(m.type) && !m.is_hidden)
          .sort((a, b) => {
            const timeA = new Date(a.sent_time || a.scheduled_time || 0).getTime();
            const timeB = new Date(b.sent_time || b.scheduled_time || 0).getTime();
            return timeB - timeA;
          });
        const lastMsg = lastMsgArray.length > 0 ? lastMsgArray[0] : null;

        let previewContent = "";
        if (lastMsg?.content) {
          if (typeof lastMsg.content === 'string') {
            try {
              const parsed = JSON.parse(lastMsg.content);
              if (parsed && typeof parsed === 'object' && typeof parsed.text === 'string') {
                previewContent = parsed.text;
              } else {
                previewContent = lastMsg.content;
              }
            } catch (e) {
              previewContent = lastMsg.content;
            }
          } else if (typeof lastMsg.content === 'object' && lastMsg.content !== null) {
            if (typeof (lastMsg.content as any).text === 'string') {
              previewContent = (lastMsg.content as any).text;
            } else {
              previewContent = JSON.stringify(lastMsg.content);
            }
          }
        } else if (lastMsg?.response && lastMsg.type === 'customer') {
          previewContent = lastMsg.response;
        }

        return {
          ...cs,
          content: previewContent.slice(0, 40) + (previewContent.length > 40 ? "..." : ""),
          sent_time: lastMsg?.sent_time || lastMsg?.scheduled_time || cs.consent_updated || "1970-01-01T00:00:00.000Z"
        }
      });

      summariesWithPreview.sort((a, b) => {
        const timeA = new Date(a.sent_time).getTime();
        const timeB = new Date(b.sent_time).getTime();
        const validTimeA = isNaN(timeA) ? 0 : timeA;
        const validTimeB = isNaN(timeB) ? 0 : timeB;
        return validTimeB - validTimeA;
      });
      setCustomerSummaries(summariesWithPreview);
      return summariesWithPreview;
    } catch (error) {
      console.error("Failed to fetch customer summaries:", error);
      throw error;
    }
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
        const id = bizRes.data?.business_id;
        setBusinessId(id);

        if (id) {
          const initialSummaries = await fetchAndSetCustomerSummaries(id);
          const urlCustomerIdString = searchParams.get('activeCustomer');

          if (urlCustomerIdString) {
            const urlCustomerId = parseInt(urlCustomerIdString, 10);
            const customerExists = initialSummaries.some(cs => cs.customer_id === urlCustomerId);
            if (customerExists) {
              setActiveCustomerId(urlCustomerId);
            } else if (initialSummaries.length > 0 && initialSummaries[0].customer_id) {
              setActiveCustomerId(initialSummaries[0].customer_id);
            } else {
              setActiveCustomerId(null);
            }
          } else if (initialSummaries.length > 0 && initialSummaries[0].customer_id) {
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
  }, [business_name, searchParams]);

  useEffect(() => {
    if (!businessId) return;
    const intervalId = setInterval(async () => {
      try {
        if (businessId && document.visibilityState === 'visible') {
          await fetchAndSetCustomerSummaries(businessId);
        }
      } catch (error) {
        console.error("Polling failed:", error);
      }
    }, 5000);
    return () => clearInterval(intervalId);
  }, [businessId]);

  useEffect(() => {
    const currentCustomerData = customerSummaries.find(cs => cs.customer_id === activeCustomerId);
    let newTimelineEntries: TimelineEntry[] = [];

    if (currentCustomerData && Array.isArray(currentCustomerData.messages)) {
      newTimelineEntries = currentCustomerData.messages
        .filter(msg => !msg.is_hidden && !(msg.type === 'ai_draft' && msg.source === 'ai_draft_suggestion'))
        .map((msg: BackendMessage): TimelineEntry | null => {
          if (!msg.type || typeof msg.id === 'undefined') return null;

          let processedContent = "";
          let isFaqAnswer = false;
          let appendedOptInPrompt = false;

          if (typeof msg.content === 'string') {
            try {
              const parsedJson = JSON.parse(msg.content);
              if (parsedJson && typeof parsedJson === 'object') {
                if (typeof parsedJson.text === 'string') {
                  processedContent = parsedJson.text;
                  isFaqAnswer = !!parsedJson.is_faq_answer;
                  appendedOptInPrompt = !!parsedJson.appended_opt_in_prompt;
                }
                else if (parsedJson.text && typeof parsedJson.text === 'object' && typeof (parsedJson.text as any).text === 'string') {
                  processedContent = (parsedJson.text as any).text;
                } else {
                  processedContent = msg.content;
                }
              } else {
                processedContent = msg.content;
              }
            } catch (e) {
              processedContent = msg.content;
            }
          } else if (typeof msg.content === 'object' && msg.content !== null) {
            if (typeof (msg.content as any).text === 'string') {
              processedContent = (msg.content as any).text;
              isFaqAnswer = !!(msg.content as any).is_faq_answer;
              appendedOptInPrompt = !!(msg.content as any).appended_opt_in_prompt;
            }
            else if (typeof (msg.content as any).text === 'object' && typeof (msg.content as any).text.text === 'string') {
              processedContent = (msg.content as any).text.text;
            }
            else {
              processedContent = JSON.stringify(msg.content);
            }
          } else if (msg.type === "customer" && msg.response) {
            processedContent = msg.response;
          } else {
            processedContent = "[No content]";
          }

          return {
            id: String(msg.id),
            type: msg.type as TimelineEntry['type'],
            content: processedContent,
            timestamp: msg.sent_time || msg.scheduled_time || null,
            customer_id: currentCustomerData.customer_id,
            is_hidden: msg.is_hidden || false,
            status: msg.status,
            source: msg.source,
            is_faq_answer: isFaqAnswer,
            appended_opt_in_prompt: appendedOptInPrompt,
          };
        }).filter(Boolean) as TimelineEntry[];


      const aiDraftEntries: TimelineEntry[] = (currentCustomerData.messages || [])
        .filter(msg => msg.type === 'ai_draft' && msg.source === 'ai_draft_suggestion' && !msg.is_hidden)
        .map((msg: BackendMessage): TimelineEntry | null => {
          if (typeof msg.id === 'undefined') return null;

          let draftContent = "";
          if (typeof msg.content === 'string') {
            try {
              const parsed = JSON.parse(msg.content);
              if (parsed && typeof parsed === 'object' && typeof parsed.text === 'string') {
                draftContent = parsed.text;
              } else {
                draftContent = msg.content;
              }
            } catch (e) {
              draftContent = msg.content;
            }
          } else if (typeof msg.content === 'object' && msg.content !== null && typeof (msg.content as any).text === 'string') {
            draftContent = (msg.content as any).text;
          } else if (msg.ai_response) {
            draftContent = msg.ai_response;
          } else if (msg.response) {
            draftContent = msg.response;
          } else {
            draftContent = "Error loading draft content.";
          }

          return {
            id: `eng-ai-${msg.id}`,
            type: 'ai_draft',
            content: draftContent,
            timestamp: msg.scheduled_time || msg.sent_time || null,
            customer_id: currentCustomerData.customer_id,
            is_hidden: false,
            status: msg.status,
            source: msg.source || 'ai_draft_suggestion',
          }
        }).filter(Boolean) as TimelineEntry[];


      const combinedTimelineEntries = [...newTimelineEntries, ...aiDraftEntries];

      // Explicitly type the sort callback parameters and return type
      combinedTimelineEntries.sort((a: TimelineEntry, b: TimelineEntry): number => {
        const timeNumA = a.timestamp ? parseISO(a.timestamp).getTime() : NaN;
        const timeNumB = b.timestamp ? parseISO(b.timestamp).getTime() : NaN;

        const validTimeA = !isNaN(timeNumA) ? timeNumA : (a.type === 'ai_draft' ? Infinity : 0);
        const validTimeB = !isNaN(timeNumB) ? timeNumB : (b.type === 'ai_draft' ? Infinity : 0);

        if (validTimeA === Infinity && validTimeB === Infinity) {
          if (a.id != null && b.id != null) {
            const idAAsString = a.id.toString();
            const idBAsString = b.id.toString();
            return idAAsString.localeCompare(idBAsString);
          }
          return 0;
        }
        if (validTimeA === Infinity) return 1;
        if (validTimeB === Infinity) return -1;

        if (validTimeA === 0 && validTimeB === 0) {
          if (a.id != null && b.id != null) {
            const idAAsString = a.id.toString();
            const idBAsString = b.id.toString();
            return idAAsString.localeCompare(idBAsString);
          }
          return 0;
        }
        if (validTimeA === 0) return -1;
        if (validTimeB === 0) return 1;

        return validTimeA - validTimeB;
      });

      setTimelineEntries(combinedTimelineEntries);
    }
  }, [customerSummaries, activeCustomerId]);


  useEffect(() => {
    setNewMessage("");
    setSelectedDraftId(null);
    if (activeCustomerId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [activeCustomerId]);

  const handleSendMessage = async () => {
    const messageToSend = newMessage.trim();
    if (!messageToSend || isSending) return;

    const currentCust = customerSummaries.find(cs => cs.customer_id === activeCustomerId);
    if (currentCust && !currentCust.opted_in && currentCust.consent_status !== 'pending_opt_in') {
      setSendError(`Cannot send message: ${currentCust.customer_name} has not opted in.`);
      return;
    }

    setIsSending(true);
    setSendError(null);
    const isSendingDraft = selectedDraftId != null;
    const targetCustomerId = activeCustomerId;
    if (!targetCustomerId) {
      setSendError("No active customer selected.");
      setIsSending(false);
      return;
    }

    try {
      if (isSendingDraft && selectedDraftId) {
        let numericIdToSend: number;
        if (typeof selectedDraftId === 'string' && selectedDraftId.startsWith('eng-ai-')) {
          numericIdToSend = parseInt(selectedDraftId.replace('eng-ai-', ''), 10);
        } else if (typeof selectedDraftId === 'number') {
          numericIdToSend = selectedDraftId;
        } else {
          setSendError("Error: Could not identify the draft to send.");
          setIsSending(false);
          return;
        }

        if (isNaN(numericIdToSend)) {
          setSendError("Error: Invalid draft ID.");
          setIsSending(false);
          return;
        }
        await apiClient.put(`/engagement-workflow/reply/${numericIdToSend}/send`, { updated_content: messageToSend });

      } else {
        await apiClient.post(`/conversations/customer/${targetCustomerId}/reply`, { message: messageToSend });
      }

      setNewMessage("");
      setSelectedDraftId(null);
      setTimeout(() => {
        if (chatContainerRef.current) {
          chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
        if (inputRef.current) inputRef.current.focus();
      }, 0);

      if (businessId) await fetchAndSetCustomerSummaries(businessId);
      setLastSeenMap(prev => ({ ...prev, [targetCustomerId]: new Date().toISOString() }));

    } catch (err: any) {
      const response = err?.response;
      const status = response?.status;
      const detail = response?.data?.detail || err.message || "An error occurred.";
      setSendError(`Failed to send: ${detail}. Status: ${status || 'N/A'}`);
      if ((status === 403 || status === 409 || status === 404) && businessId) {
        await fetchAndSetCustomerSummaries(businessId);
      }
    } finally {
      setIsSending(false);
    }
  };

  const handleEditDraft = (draft: TimelineEntry) => {
    if (draft.type === 'ai_draft' && draft.customer_id === activeCustomerId) {
      setSelectedDraftId(draft.id);
      setNewMessage(draft.content);
      setTimeout(() => {
        if (chatContainerRef.current) {
          const draftElement = chatContainerRef.current.querySelector(`[data-message-id="${draft.id}"]`);
          if (draftElement) {
            draftElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }
        if (inputRef.current) inputRef.current.focus();
      }, 0);
    } else {
      console.warn("Attempted to edit a non-draft message or for a non-active customer:", draft);
    }
  };

  const handleDeleteDraft = async (draftTimelineEntryId: string | number) => {
    let numericDraftId: number;

    if (typeof draftTimelineEntryId === 'string' && draftTimelineEntryId.startsWith('eng-ai-')) {
      numericDraftId = parseInt(draftTimelineEntryId.replace('eng-ai-', ''), 10);
    } else if (typeof draftTimelineEntryId === 'number') {
      numericDraftId = draftTimelineEntryId;
    }
    else {
      alert("Cannot delete draft: Invalid ID format.");
      return;
    }

    if (isNaN(numericDraftId)) {
      alert("Cannot delete draft: ID is not a valid number after parsing.");
      return;
    }

    const entryToDelete = timelineEntries.find(e => e.id === draftTimelineEntryId);
    if (!(entryToDelete && entryToDelete.type === 'ai_draft')) {
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
      } catch (err: any) {
        const errorDetail = err.response?.data?.detail || err.message || "An unknown error occurred.";
        alert(`Failed to delete draft: ${errorDetail}`);
      }
    }
  };

  const currentCustomer = useMemo(() => {
    return customerSummaries.find(cs => cs.customer_id === activeCustomerId);
  }, [customerSummaries, activeCustomerId]);

  useEffect(() => {
    if (customerSummaries.length > 0 && !activeCustomerId) {
      const urlCustomerIdString = searchParams.get('activeCustomer');
      if (urlCustomerIdString) {
        const urlCustomerId = parseInt(urlCustomerIdString, 10);
        const customerExists = customerSummaries.some(cs => cs.customer_id === urlCustomerId);
        if (customerExists) {
          setActiveCustomerId(urlCustomerId);
        } else {
          setActiveCustomerId(customerSummaries[0].customer_id);
        }
      } else {
        setActiveCustomerId(customerSummaries[0].customer_id);
      }
    }
    if (activeCustomerId && searchParams.get('activeCustomer') === String(activeCustomerId)) {
      const urlEngagementId = searchParams.get('engagementId');
      if (urlEngagementId && chatContainerRef.current) {
        const engagementElement = chatContainerRef.current.querySelector(`[data-message-id="${urlEngagementId}"], [data-message-id="eng-ai-${urlEngagementId}"]`);
        if (engagementElement) {
          setTimeout(() => {
            engagementElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 200);
        }
      }
    }

  }, [customerSummaries, searchParams, activeCustomerId]);


  if (isLoading && customerSummaries.length === 0) {
    return <div className="h-screen flex items-center justify-center bg-[#0B0E1C] text-white text-lg">Loading Inbox... <span className="animate-pulse">⏳</span></div>;
  }

  if (fetchError && customerSummaries.length === 0) {
    return <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
      <AlertCircle className="w-12 h-12 mb-3 text-red-500" />
      <p className="text-xl font-semibold">Oops! Something went wrong.</p>
      <p className="text-sm mt-1">{fetchError}</p>
      <p className="text-xs mt-3">Please try refreshing the page. If the problem persists, contact support.</p>
    </div>;
  }


  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
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
        "flex flex-col h-full",
        "overflow-y-auto"
      )}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
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
            <p className="p-4 text-gray-400 text-center">No conversations yet.</p>
          )}
          {customerSummaries.map((cs) => {
            const previewText = cs.content || "No recent messages";
            const customerLastSeenString = lastSeenMap[cs.customer_id];
            const messageTimestampString = cs.sent_time;

            let isUnread = false;
            if (messageTimestampString && cs.messages && cs.messages.length > 0) {
              const messageDate = parseISO(messageTimestampString);
              if (isValid(messageDate)) {
                const lastSeenDate = customerLastSeenString ? parseISO(customerLastSeenString) : null;
                if (!lastSeenDate || !isValid(lastSeenDate) || messageDate.getTime() > lastSeenDate.getTime()) {
                  isUnread = true;
                }
              }
            }
            if (cs.customer_id === activeCustomerId) {
              isUnread = false;
            }

            return (
              <button
                key={cs.customer_id}
                onClick={() => {
                  setActiveCustomerId(cs.customer_id);
                  setShowMobileDrawer(false);
                  setLastSeenMap(prev => ({ ...prev, [cs.customer_id]: new Date().toISOString() }));
                }}
                className={clsx(
                  "w-full text-left p-3 hover:bg-[#242842] transition-colors border-b border-[#2A2F45]",
                  activeCustomerId === cs.customer_id ? "bg-[#2A2F45] ring-2 ring-blue-500" : "bg-transparent",
                )}
              >
                <div className="flex justify-between items-center">
                  <h3 className={clsx("text-sm text-white truncate", isUnread ? "font-semibold" : "font-medium")}>
                    {cs.customer_name || "Unknown Customer"}
                  </h3>
                  {cs.sent_time && (
                    <span className={clsx("text-xs whitespace-nowrap ml-2", isUnread ? "text-blue-400" : "text-gray-400")}>
                      {formatDate(cs.sent_time)}
                    </span>
                  )}
                </div>
                <p className={clsx("text-xs truncate mt-1", isUnread ? "text-gray-200" : "text-gray-400")}>
                  {previewText}
                </p>
              </button>
            );
          })}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-[#0F1221] h-full md:h-auto md:min-h-0">
        {activeCustomerId && currentCustomer ? (
          <>
            <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
              <h3 className="text-lg font-semibold text-white">{currentCustomer.customer_name}</h3>
              <p className="text-xs text-gray-400">{currentCustomer.phone} -
                <span className={clsx("ml-1", currentCustomer.opted_in ? "text-green-400" : "text-red-400")}>
                  {currentCustomer.consent_status === 'pending_opt_in' ? 'Pending Opt-In' : (currentCustomer.opted_in ? 'Opted-In' : 'Opted-Out')}
                </span>
                {currentCustomer.consent_updated && <span className="ml-2"> (Updated: {formatDate(currentCustomer.consent_updated)})</span>}
              </p>
            </div>

            <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {timelineEntries.map((entry) => (
                <div
                  key={entry.id}
                  data-message-id={entry.id}
                  className={clsx(
                    "p-3 rounded-lg max-w-[70%] break-words text-sm shadow",
                    {
                      "bg-[#2A2F45] text-white self-start mr-auto": entry.type === "customer",
                      "bg-blue-600 text-white self-end ml-auto": entry.type === "sent" || entry.type === "outbound_ai_reply",
                      "bg-yellow-500 text-black self-end ml-auto": entry.type === "ai_draft",
                      "bg-gray-500 text-white self-end ml-auto": entry.type === "scheduled" || entry.type === "scheduled_pending",
                      "bg-red-700 text-white self-end ml-auto": entry.type === "failed_to_send",
                      "bg-purple-600 text-white self-start mr-auto": entry.type === "unknown_business_message",
                    },
                    "flex flex-col"
                  )}
                >
                  <p className="whitespace-pre-wrap">{entry.content}</p>
                  {entry.timestamp && (
                    <span className="text-xs text-gray-300 mt-1 self-end opacity-80">
                      {formatMessageTimestamp(entry.timestamp)}
                      {entry.type === 'sent' && entry.status === 'delivered' && <CheckCheck className="inline-block w-4 h-4 ml-1 text-green-300" />}
                      {entry.type === 'sent' && (entry.status === 'sent' || entry.status === 'accepted') && <Check className="inline-block w-4 h-4 ml-1 text-gray-300" />}
                      {entry.type === 'sent' && entry.status === 'queued' && <Clock className="inline-block w-3 h-3 ml-1 text-gray-300" />}
                      {(entry.type === 'scheduled' || entry.type === 'scheduled_pending') && <Clock className="inline-block w-3 h-3 ml-1" />}
                      {entry.type === 'failed_to_send' && <AlertCircle className="inline-block w-3 h-3 ml-1 text-red-300" />}
                    </span>
                  )}

                  {entry.is_faq_answer && <p className="text-xs text-blue-300 mt-1 italic self-start"> (Auto-reply: FAQ)</p>}
                  {entry.appended_opt_in_prompt && <p className="text-xs text-gray-400 mt-1 italic self-start"> (Opt-in prompt included)</p>}


                  {entry.type === "ai_draft" && entry.customer_id === activeCustomerId && (
                    <div className="flex gap-2 mt-2 self-end">
                      <button
                        onClick={() => handleEditDraft(entry)}
                        className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors"
                        title="Edit Draft"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => handleDeleteDraft(entry.id)}
                        className="p-1.5 bg-red-800 hover:bg-red-700 rounded text-white transition-colors"
                        title="Delete Draft"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0">
              {sendError && <p className="text-xs text-red-400 mb-2">{sendError}</p>}
              <div className="flex items-center gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && !isSending && handleSendMessage()}
                  placeholder={selectedDraftId ? "Edit draft..." : "Type a message..."}
                  className="flex-1 p-2 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  disabled={isSending || (!currentCustomer?.opted_in && currentCustomer?.consent_status !== 'pending_opt_in')}
                />
                <button
                  onClick={handleSendMessage}
                  disabled={isSending || (!newMessage.trim() && !selectedDraftId) || (!currentCustomer?.opted_in && currentCustomer?.consent_status !== 'pending_opt_in')}
                  className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white disabled:opacity-50 transition-colors"
                >
                  {isSending ? <Clock className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                </button>
              </div>
              {selectedDraftId && (
                <button
                  onClick={() => { setNewMessage(""); setSelectedDraftId(null); if (inputRef.current) inputRef.current.focus(); }}
                  className="text-xs text-gray-400 hover:text-gray-200 mt-1"
                >
                  Cancel edit
                </button>
              )}
              {!currentCustomer?.opted_in && currentCustomer?.consent_status !== 'pending_opt_in' && (
                <p className="text-xs text-red-400 mt-1">
                  Cannot send messages. Customer has not opted in.
                </p>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
            <MessageCircle className="w-16 h-16 mb-4 text-gray-500" />
            <p className="text-lg">Select a conversation</p>
            <p className="text-sm">Choose a customer from the list to view messages.</p>
            {customerSummaries.length === 0 && !isLoading && !fetchError && (
              <p className="text-sm mt-2">No conversations to display.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}