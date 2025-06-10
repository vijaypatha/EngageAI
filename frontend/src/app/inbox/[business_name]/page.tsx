// frontend/src/app/inbox/[business_name]/page.tsx
"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { apiClient, useBusinessIdFromSlug, useInboxSummaries, useCustomerConversation, FrontendMessage } from "@/lib/api"; // Added useCustomerConversation and FrontendMessage
import useSWR, { mutate } from 'swr';
import { Clock, Send, MessageSquare, Check, AlertCircle, Trash2, Edit3, CheckCheck, User, Phone, MessageCircle, ChevronLeft, ChevronRight } from "lucide-react";
import clsx from "clsx";
import { format, isValid, parseISO } from 'date-fns';
import { CustomerListSkeleton } from '@/components/CustomerListSkeleton';
import { MessagePanelSkeleton } from '@/components/MessagePanelSkeleton';
import { FixedSizeList as List } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';

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

  // SWR hook for Business ID
  const { data: businessData, error: businessError, isLoading: businessIsLoading } = useBusinessIdFromSlug(business_name as string);
  const businessId = businessData?.business_id;

  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 20;

  const {
      data: paginatedData,
      error: historyError,
      isLoading: historyIsLoading,
      mutate: mutateSummaries // Renamed for clarity
  } = useInboxSummaries(businessId, currentPage, ITEMS_PER_PAGE);

  const customerSummariesFromHook = paginatedData?.items ?? [];
  const totalCustomers = paginatedData?.total ?? 0;
  const totalPages = paginatedData?.pages ?? 0;

  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [selectedDraftId, setSelectedDraftId] = useState<string | number | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const [lastSeenMap, setLastSeenMap] = useState<Record<number, string>>({});
  const [showMobileDrawer, setShowMobileDrawer] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // This customerSummaries is now just the current page's items.
  // The full list for sorting/preview generation was done by the backend.
  const customerSummaries = useMemo(() => {
    return customerSummariesFromHook.map(cs => ({
      ...cs, // cs already has last_message_content and last_message_timestamp from backend
      content: cs.last_message_content ? (cs.last_message_content.slice(0, 40) + (cs.last_message_content.length > 40 ? "..." : "")) : "No recent messages",
      sent_time: cs.last_message_timestamp || "1970-01-01T00:00:00.000Z" // Ensure sent_time for sorting/display
    }));
  }, [customerSummariesFromHook]);


  useEffect(() => {
    // When page changes, or new data comes in, if active customer is not in the current view, deselect.
    // Or, ideally, fetch their specific data - this will be handled by a new hook later.
    if (activeCustomerId && customerSummaries.length > 0 && !customerSummaries.find(cs => cs.customer_id === activeCustomerId)) {
      // setActiveCustomerId(null); // Option 1: Deselect if not on current page
      // Option 2: Keep active, timeline will show loading/fetch its own data (handled by next subtask)
    }

    // If no active customer and there are summaries, select the first one.
    if (!activeCustomerId && customerSummaries.length > 0 && customerSummaries[0].customer_id) {
       const urlCustomerIdString = searchParams.get('activeCustomer');
       if (urlCustomerIdString) {
            const urlCustomerId = parseInt(urlCustomerIdString, 10);
            const customerExistsOnPage = customerSummaries.some(cs => cs.customer_id === urlCustomerId);
            if (customerExistsOnPage) {
              setActiveCustomerId(urlCustomerId);
            } else {
                 // If not on current page, we might not auto-select, or select first of current page
                 // For now, let's select first of current page if no specific valid one is found on this page
                setActiveCustomerId(customerSummaries[0].customer_id);
            }
       } else {
        setActiveCustomerId(customerSummaries[0].customer_id);
       }
    }
  }, [currentPage, customerSummaries, activeCustomerId, searchParams]);


  useEffect(() => {
    // This effect tries to set an initial active customer based on URL or first in list
    // It should run when businessId is resolved and initial data might be available
    if (businessId && !historyIsLoading && customerSummaries && customerSummaries.length > 0 && !activeCustomerId) {
      const urlCustomerIdString = searchParams.get('activeCustomer');
      if (urlCustomerIdString) {
        const urlCustomerId = parseInt(urlCustomerIdString, 10);
        // Check if this customer is in the currently loaded page of summaries
        const customerExistsOnPage = customerSummaries.some(cs => cs.customer_id === urlCustomerId);
        if (customerExistsOnPage) {
          setActiveCustomerId(urlCustomerId);
        } else {
          // If not on current page, we could fetch that page, or just default to first on current.
          // For now, defaulting to first on current page.
          setActiveCustomerId(customerSummaries[0].customer_id);
        }
      } else if (customerSummaries.length > 0 && customerSummaries[0].customer_id) {
        setActiveCustomerId(customerSummaries[0].customer_id);
      }
    } else if (!businessIsLoading && !businessId && businessError) {
        console.error("Error fetching business ID:", businessError);
    } else if (businessId && !historyIsLoading && historyError && (!customerSummaries || customerSummaries.length === 0)) {
        console.error("Error fetching customer summaries:", historyError);
    }
  }, [business_name, searchParams, businessId, businessIsLoading, businessError, customerSummaries, historyIsLoading, historyError, activeCustomerId]);


  const {
    data: activeCustomerConversation,
    error: conversationError,
    isLoading: conversationIsLoading,
    mutate: mutateConversation
  } = useCustomerConversation(activeCustomerId);

  const timelineEntries = useMemo(() => {
    if (!activeCustomerConversation || !activeCustomerConversation.messages) {
      return [];
    }
    // Reuse the existing processing logic if BackendMessage and FrontendMessage are compatible
    // Or adapt as necessary. Assuming FrontendMessage from api.ts matches BackendMessage structure for now.
    return activeCustomerConversation.messages.map((msg: FrontendMessage): TimelineEntry => {
        let processedContent = "";
        let isFaqAnswer = false;
        let appendedOptInPrompt = false;

        // This content processing logic is similar to what was in the old useMemo for timelineEntries
        // It might need adjustment based on the exact structure of `msg.content` from the new endpoint
        if (typeof msg.content === 'string') {
            try {
                const parsedJson = JSON.parse(msg.content);
                if (parsedJson && typeof parsedJson === 'object') {
                    if (typeof parsedJson.text === 'string') {
                        processedContent = parsedJson.text;
                        isFaqAnswer = !!parsedJson.is_faq_answer; // Assuming these fields might exist
                        appendedOptInPrompt = !!parsedJson.appended_opt_in_prompt;
                    } else { // If 'text' is not a string, stringify the whole content
                        processedContent = JSON.stringify(parsedJson);
                    }
                } else { // If not an object, use as is
                    processedContent = msg.content;
                }
            } catch (e) { // If not JSON, use as is
                processedContent = msg.content;
            }
        } else if (typeof msg.content === 'object' && msg.content !== null) {
             if (typeof (msg.content as any).text === 'string') {
                processedContent = (msg.content as any).text;
                isFaqAnswer = !!(msg.content as any).is_faq_answer;
                appendedOptInPrompt = !!(msg.content as any).appended_opt_in_prompt;
            } else {
                 processedContent = JSON.stringify(msg.content);
            }
        } else if (msg.message_type === "customer" && (msg as any).response) { // Assuming 'response' field for customer messages if content is not direct
             processedContent = (msg as any).response;
        } else {
            processedContent = "[No content]";
        }

        return {
            id: String(msg.id), // Ensure ID is string for key prop
            type: msg.message_type as TimelineEntry['type'], // Cast if types are aligned
            content: processedContent,
            timestamp: msg.sent_at || msg.scheduled_time || msg.created_at, // Prefer sent_at, then scheduled_time, then created_at
            customer_id: msg.customer_id,
            is_hidden: msg.is_hidden || false,
            status: msg.status,
            // source: msg.source, // If source is available on FrontendMessage
            is_faq_answer: isFaqAnswer,
            appended_opt_in_prompt: appendedOptInPrompt,
        };
    }).sort((a, b) => { // Sort by timestamp
        const timeA = a.timestamp ? parseISO(a.timestamp).getTime() : 0;
        const timeB = b.timestamp ? parseISO(b.timestamp).getTime() : 0;
        return timeA - timeB;
    });
  }, [activeCustomerConversation]);


  useEffect(() => {
    requestAnimationFrame(() => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
      }
    });
  }, [timelineEntries]);

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

    const currentCust = customerSummaries.find(cs => cs.customer_id === activeCustomerId); // customerSummaries is now from paginatedData
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

    // Simplified optimistic update: just revalidate current page data
    // The detailed optimistic update adding the message to timelineEntries will be part of the
    // useCustomerConversation hook implementation in the next subtask.
    // For now, the visual feedback of the message appearing in timeline might be delayed until revalidation.
    setNewMessage(""); // Clear input immediately

    const optimisticUiMessage: TimelineEntry = { // More aligned with TimelineEntry for UI
      id: `optimistic-${Date.now()}`,
      type: 'sent',
      content: messageToSend,
      timestamp: new Date().toISOString(),
      customer_id: targetCustomerId,
      status: 'sending', // Custom status for optimistic UI
    };

    if (targetCustomerId === activeCustomerId) {
      mutateConversation(async (currentConversationData) => {
        const updatedMessages = [...(currentConversationData?.messages || []), optimisticUiMessage as FrontendMessage]; // Cast needed if not fully compatible
        return {
          ...(currentConversationData || { customer_id: targetCustomerId, messages: [] }), // Provide default if undefined
          messages: updatedMessages,
          customer_id: targetCustomerId
        };
      }, false);
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

      mutateSummaries(); // Revalidate SWR cache for the summaries list
      if (targetCustomerId === activeCustomerId) {
        mutateConversation(); // Revalidate the active conversation
      }
      setLastSeenMap(prev => ({ ...prev, [targetCustomerId]: new Date().toISOString() }));

    } catch (err: any) {
      const response = err?.response;
      const status = response?.status;
      const detail = response?.data?.detail || err.message || "An error occurred.";
      setSendError(`Failed to send: ${detail}. Status: ${status || 'N/A'}`);
      // Revert optimistic update or show error on the message itself if possible
      if (targetCustomerId === activeCustomerId) {
        mutateConversation(); // Revalidate to clear optimistic message on error
      }
      if ((status === 403 || status === 409 || status === 404)) {
        mutateSummaries();
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

    const entryToDelete = timelineEntries.find(e => e.id === draftTimelineEntryId); // Check against current timeline
    if (!(entryToDelete && entryToDelete.type === 'ai_draft')) {
      alert("This message is not a draft and cannot be deleted this way.");
      return;
    }

    if (window.confirm("Delete this draft? This action cannot be undone.")) {
      try {
        await apiClient.delete(`/engagement-workflow/${numericDraftId}`);
        if (selectedDraftId === draftTimelineEntryId) {
          setNewMessage("");
          setSelectedDraftId(null);
        }
        // Revalidate both conversation and summaries
        if (activeCustomerId === entryToDelete.customer_id) {
            mutateConversation();
        }
        mutateSummaries();
      } catch (err: any) {
        const errorDetail = err.response?.data?.detail || err.message || "An unknown error occurred.";
        alert(`Failed to delete draft: ${errorDetail}`);
      }
    }
  };

  const currentCustomer = useMemo(() => {
    // Find in the current page of summaries
    return customerSummaries.find(cs => cs.customer_id === activeCustomerId);
  }, [customerSummaries, activeCustomerId]);

  useEffect(() => {
    // This effect handles scrolling to a specific engagement if URL params are present
    if (activeCustomerId && searchParams.get('activeCustomer') === String(activeCustomerId)) {
      const urlEngagementId = searchParams.get('engagementId');
      if (urlEngagementId && chatContainerRef.current) {
        const engagementElement = chatContainerRef.current.querySelector(`[data-message-id="${urlEngagementId}"], [data-message-id="eng-ai-${urlEngagementId}"]`);
        if (engagementElement) {
          setTimeout(() => {
            engagementElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 200); // Short delay to ensure DOM is ready
        }
      }
    }
  }, [searchParams, activeCustomerId, timelineEntries]);


  // Customer Row for react-window
  const CustomerRow = ({ index, style }: { index: number, style: React.CSSProperties }) => {
    const cs = customerSummaries[index]; // customerSummaries is now from paginatedData.items
    if (!cs) return null;

    const previewText = cs.content || "No recent messages"; // cs.content is already formatted preview
    const customerLastSeenString = lastSeenMap[cs.customer_id];
    const messageTimestampString = cs.sent_time; // cs.sent_time is last_message_timestamp
    let isUnread = (cs as any).unread_message_count > 0; // Assuming unread_message_count is on the item

    // This unread logic might be simplified if backend provides clear unread status per summary
    if (messageTimestampString) {
      const messageDate = parseISO(messageTimestampString);
      if (isValid(messageDate)) {
        const lastSeenDate = customerLastSeenString ? parseISO(customerLastSeenString) : null;
        if (lastSeenDate && isValid(lastSeenDate) && messageDate.getTime() <= lastSeenDate.getTime()) {
          isUnread = false; // User has seen this or newer
        }
      }
    }
    if (cs.customer_id === activeCustomerId) { // If it's the active chat, mark as read
      isUnread = false;
    }

    return (
      <div style={style}>
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
      </div>
    );
  };

  if (businessIsLoading || (businessId && historyIsLoading && !paginatedData && !historyError && !conversationError)) {
    return (
      <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
        <aside className="w-full md:w-80 bg-[#1A1D2D] border-r border-[#2A2F45] flex flex-col h-full">
          <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
            <div className="h-6 bg-gray-700 rounded w-1/3 animate-pulse"></div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <CustomerListSkeleton count={ITEMS_PER_PAGE} />
          </div>
        </aside>
        <main className="flex-1 flex flex-col bg-[#0F1221] h-full md:h-auto md:min-h-0">
          <MessagePanelSkeleton />
        </main>
      </div>
    );
  }

  if ((businessError || historyError || conversationError) && (!paginatedData || paginatedData.items.length === 0) && !activeCustomerConversation) {
    return <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
      <AlertCircle className="w-12 h-12 mb-3 text-red-500" />
      <p className="text-xl font-semibold">Oops! Something went wrong.</p>
      <p className="text-sm mt-1">{businessError?.message || (historyError as any)?.message || (conversationError as any)?.message || "Failed to load data."}</p>
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
        // "overflow-y-auto" // AutoSizer will manage scrolling for the List
      )}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
          <h2 className="text-xl font-semibold text-white">{showMobileDrawer ? "Contacts" : `Inbox (${totalCustomers})`}</h2>
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

        <div className="flex-1 h-full w-full"> {/* Ensure AutoSizer has dimensions */}
          {historyIsLoading && (!paginatedData || paginatedData.items.length === 0) ? (
            <div className="flex-1 overflow-y-auto">
                <CustomerListSkeleton count={ITEMS_PER_PAGE} />
            </div>
          ) : customerSummaries.length === 0 && !historyIsLoading ? (
            <p className="p-4 text-gray-400 text-center">No conversations yet.</p>
          ) : (
            <AutoSizer>
              {({ height, width }) => (
                <List
                  height={height}
                  itemCount={customerSummaries.length}
                  itemSize={68}
                  width={width}
                  className="scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-gray-800"
                >
                  {CustomerRow}
                </List>
              )}
            </AutoSizer>
          )}
        </div>
        {totalPages > 1 && (
            <div className="p-2 flex justify-between items-center border-t border-[#2A2F45] shrink-0">
                <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1 || historyIsLoading}
                    className="p-2 text-xs text-gray-300 hover:bg-[#242842] rounded disabled:opacity-50 flex items-center"
                >
                    <ChevronLeft size={16} className="mr-1" /> Previous
                </button>
                <span className="text-xs text-gray-400">
                    Page {currentPage} of {totalPages}
                </span>
                <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages || historyIsLoading}
                    className="p-2 text-xs text-gray-300 hover:bg-[#242842] rounded disabled:opacity-50 flex items-center"
                >
                    Next <ChevronRight size={16} className="ml-1" />
                </button>
            </div>
        )}
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

            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {/* Timeline entries will be populated by a new hook in the next subtask */}
              {conversationIsLoading && <div className="flex-1 flex items-center justify-center text-gray-400">Loading messages...</div>}
              {!conversationIsLoading && conversationError && <div className="flex-1 flex items-center justify-center text-red-400">Error loading messages.</div>}
              {!conversationIsLoading && !conversationError && timelineEntries.length === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-500">
                  <MessageSquare size={48} />
                  <p className="mt-2">No messages in this conversation yet.</p>
                </div>
              )}
              {timelineEntries.map((entry) => (
                <div
                key={entry.id}
                data-message-id={entry.id}
                className={clsx(
                  "p-3 rounded-lg max-w-[70%] break-words text-sm shadow",
                  "flex flex-col",
                  (entry.type === "customer" || entry.type === "unknown_business_message") && "self-start mr-auto",
                  (entry.type === "sent" || entry.type === "outbound_ai_reply" || entry.type === "ai_draft" || entry.type === "scheduled" || entry.type === "scheduled_pending" || entry.type === "failed_to_send") && "self-end ml-auto",
                  {
                    "bg-[#2A2F45] text-white": entry.type === "customer",
                    "bg-blue-600 text-white": entry.type === "sent" || entry.type === "outbound_ai_reply",
                    "bg-yellow-500 text-black": entry.type === "ai_draft",
                    "bg-gray-500 text-white": entry.type === "scheduled" || entry.type === "scheduled_pending",
                    "bg-red-700 text-white": entry.type === "failed_to_send",
                    "bg-purple-600 text-white": entry.type === "unknown_business_message",
                    "animate-pulse bg-blue-800": entry.status === 'sending' // Optimistic UI
                  }
                )}
              >
                  <p className="whitespace-pre-wrap">{entry.content}</p>
                  {entry.timestamp && (
                    <span className="text-xs text-gray-300 mt-1 self-end opacity-80">
                      {formatMessageTimestamp(entry.timestamp)}
                      {entry.type === 'sent' && entry.status === 'delivered' && <CheckCheck className="inline-block w-4 h-4 ml-1 text-green-300" />}
                      {entry.type === 'sent' && (entry.status === 'sent' || entry.status === 'accepted') && <Check className="inline-block w-4 h-4 ml-1 text-gray-300" />}
                      {entry.type === 'sent' && entry.status === 'queued' && <Clock className="inline-block w-3 h-3 ml-1 text-gray-300" />}
                      {entry.type === 'sent' && entry.status === 'sending' && <Clock className="inline-block w-3 h-3 ml-1 text-gray-300" />}
                      {(entry.type === 'scheduled' || entry.type === 'scheduled_pending') && <Clock className="inline-block w-3 h-3 ml-1" />}
                      {entry.type === 'failed_to_send' && <AlertCircle className="inline-block w-3 h-3 ml-1 text-red-300" />}
                    </span>
                  )}
                  {entry.is_faq_answer && <p className="text-xs text-blue-300 mt-1 italic self-start"> (Auto-reply: FAQ)</p>}
                  {entry.appended_opt_in_prompt && <p className="text-xs text-gray-400 mt-1 italic self-start"> (Opt-in prompt included)</p>}
                  {entry.type === "ai_draft" && entry.customer_id === activeCustomerId && (
                    <div className="flex gap-2 mt-2 self-end">
                      <button onClick={() => handleEditDraft(entry)} className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors" title="Edit Draft"><Edit3 size={14} /></button>
                      <button onClick={() => handleDeleteDraft(entry.id)} className="p-1.5 bg-red-800 hover:bg-red-700 rounded text-white transition-colors" title="Delete Draft"><Trash2 size={14} /></button>
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
            {customerSummaries.length === 0 && !historyIsLoading && !businessError && !historyError && !businessIsLoading && (
              <p className="text-sm mt-2">No conversations to display for this business.</p>
            )}
             {historyIsLoading && <p className="text-sm mt-2">Loading conversations...</p>}
          </div>
        )}
      </main>
    </div>
  );
}