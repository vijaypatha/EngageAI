"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Clock, Send, MessageSquare, Check, AlertCircle } from "lucide-react";
import clsx from "clsx";
import { formatDistanceToNow } from "date-fns";

interface Message {
  id: number;
  customer_id: number;
  customer_name: string;
  phone: string;
  content: string; // May represent latest message content in the summary view
  type: "outbound" | "inbound"; // May represent latest message type
  status: string; // May represent latest message status
  scheduled_time?: string;
  sent_time?: string; // May represent latest message time
  source: string;
  is_hidden?: boolean;
  latest_consent_status: string;
  opted_in: boolean;
  response?: string;
  messages?: Message[]; // Nested messages if the API provides them this way
}

type TimelineEntry = {
  type: "customer" | "sent" | "ai_draft" | "scheduled";
  content: string;
  timestamp: string | null;
  id: number | string;
  customer_id: number;
  is_hidden?: boolean;
};

export default function InboxPage() {
  const { business_name } = useParams();
  // 'messages' state likely holds customer summary objects from /review/full-customer-history
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [scheduledSms, setScheduledSms] = useState<any[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [pendingReplyCustomerId, setPendingReplyCustomerId] = useState<number | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [lastSeenMap, setLastSeenMap] = useState<Record<number, string>>({});
  const [showMobileDrawer, setShowMobileDrawer] = useState(false);

  // Ref for scrolling (Approach 3: Ref on Container)
  const chatContainerRef = useRef<null | HTMLDivElement>(null);

  useEffect(() => {
    // Scroll effect - kept from previous attempt, maybe revisit if still problematic
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries, activeCustomerId]);


  useEffect(() => {
    const fetchBusinessAndMessages = async () => {
      if (!business_name) return;
      try {
        console.log("Fetching business ID for slug:", business_name);
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data.business_id;
        console.log("Business ID fetched:", id);
        setBusinessId(id);

        console.log("Fetching full customer history for business ID:", id);
        const res = await apiClient.get(`/review/full-customer-history?business_id=${id}`);
        const messageData = res.data || [];
        console.log(`Workspaceed ${messageData.length} customer history entries.`);
        console.log("Sample entry:", messageData[0]); // Log first entry to see structure

        // Basic mapping - ensure core fields exist
        const mappedData = messageData.map((msg: any) => ({
          ...msg,
          customer_id: msg.customer_id, // Ensure these exist
          customer_name: msg.customer_name || "Unknown Customer", // Provide fallback name
          latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
        }));

        setMessages(mappedData);

        if (mappedData.length > 0) {
           // Check if the first customer is valid before setting active
           if (mappedData[0].customer_id) {
             console.log("Setting active customer:", mappedData[0].customer_id);
             setActiveCustomerId(mappedData[0].customer_id);
             fetchScheduledSms(mappedData[0].customer_id);
           } else {
             console.warn("First customer entry has no ID, cannot set active customer.");
             setActiveCustomerId(null);
             setTimelineEntries([]);
           }
        } else {
           console.log("No customer history entries found, clearing active customer.");
           setActiveCustomerId(null);
           setTimelineEntries([]);
        }
      } catch (error) {
         console.error("Failed to fetch initial business and messages:", error);
         // Handle error appropriately, maybe show a message to the user
      }
    };
    fetchBusinessAndMessages();
  }, [business_name]);

  useEffect(() => {
    if (!businessId) return;
    const interval = setInterval(async () => {
      try {
        // console.log("Polling for history updates for business ID:", businessId);
        const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
        const messageData = res.data || [];

        const mappedData = messageData.map((msg: any) => ({
          ...msg,
          customer_id: msg.customer_id,
          customer_name: msg.customer_name || "Unknown Customer",
          latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
        }));

        setMessages(mappedData);
      } catch (error) {
         console.error("Failed to fetch messages during polling:", error);
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [businessId]);

  const fetchScheduledSms = async (customerId: number) => {
    try {
      console.log("Fetching scheduled SMS for customer:", customerId);
      const res = await apiClient.get(`/message-workflow/sent/${customerId}`);
      setScheduledSms(res.data || []);
      console.log("Scheduled SMS fetched:", res.data);
    } catch (error) {
       console.error(`Failed to fetch scheduled SMS for customer ${customerId}:`, error);
       setScheduledSms([]);
    }
  };

  // filteredMessages now relies on the top-level 'messages' state structure
  const filteredMessages = useMemo(
     () => messages.filter(customerSummary => customerSummary.customer_id === activeCustomerId),
     [messages, activeCustomerId]
  );

  // Reverted useEffect hook for building timeline
   useEffect(() => {
    const base: TimelineEntry[] = [];

    // Find the data object for the active customer from the main 'messages' state
    const customerData = messages.find(m => m.customer_id === activeCustomerId);

    // Check if customerData exists AND if it has a nested 'messages' array
    // This structure MUST match what the /review/full-customer-history returns
    if (customerData && Array.isArray(customerData.messages)) {
       console.log(`Building base timeline from nested messages for customer ${activeCustomerId}`);
      for (const msg of customerData.messages) { // Iterate nested messages
        if (msg.is_hidden) continue;

        if (msg.type === "inbound") {
          base.push({
            id: msg.id, type: "customer", content: msg.content,
            timestamp: msg.sent_time || null, customer_id: msg.customer_id, is_hidden: msg.is_hidden
          });
        } else if (msg.type === "outbound") {
          if (msg.status === "pending_review") {
            base.push({
              id: msg.id, type: "ai_draft", content: msg.content,
              timestamp: null, customer_id: msg.customer_id, is_hidden: msg.is_hidden
            });
          } else if (msg.status === "sent") {
            base.push({
              id: msg.id, type: "sent", content: msg.content,
              timestamp: msg.sent_time || msg.scheduled_time || null, customer_id: msg.customer_id, is_hidden: msg.is_hidden
            });
          }
        }
      }
    } else if(customerData) {
        // Handle cases where customerData exists but doesn't have a nested 'messages' array
        // Maybe the top-level 'messages' state *is* the flat list? Adapt if necessary.
        console.warn("Timeline build: Customer data found, but 'messages' property is missing or not an array.", customerData);
        // If 'messages' state IS the flat list of all messages for the business, the logic needs a full rewrite here.
        // Assuming for now the nested structure was intended by the API.
    }


    const fetchConversationHistory = async () => {
      if (!activeCustomerId) {
          console.log("No active customer, setting timeline to base entries.");
          setTimelineEntries(base.sort((a, b) => {
            if (!a.timestamp && !b.timestamp) return 0;
            if (!a.timestamp) return 1; // Place entries without timestamp last
            if (!b.timestamp) return -1;
            try {
               const dateA = new Date(a.timestamp);
               const dateB = new Date(b.timestamp);
               if (isNaN(dateA.getTime())) return 1; // Invalid dates last
               if (isNaN(dateB.getTime())) return -1;
               return dateA.getTime() - dateB.getTime();
            } catch (e) { return 0; } // Fallback on error
        }));
          return;
      };
      try {
        console.log("Fetching additional history from /conversations/customer/", activeCustomerId);
        const res = await apiClient.get(`/conversations/customer/${activeCustomerId}`);
        const conversationEntries = (res.data.messages || []).map((msg: any, index: number) => ({
          id: msg.id || `conv-${index}`,
          type: msg.type === "customer" ? "customer" : (msg.type === "ai_draft" ? "ai_draft" : "sent"),
          content: msg.text || msg.content,
          timestamp: msg.timestamp || msg.sent_time || msg.created_at || null,
          customer_id: activeCustomerId,
          is_hidden: msg.is_hidden || false
        }));
        console.log(`Workspaceed ${conversationEntries.length} additional conversation entries.`);

        const scheduled: TimelineEntry[] = scheduledSms
          .filter(sms => sms.status === "sent" && sms.customer_id === activeCustomerId)
          .map(sms => ({
            id: `sch-${sms.id}`, type: "sent", content: sms.message,
            timestamp: sms.send_time || null, customer_id: sms.customer_id, is_hidden: sms.is_hidden || false
          })) as TimelineEntry[];
        console.log(`Adding ${scheduled.length} sent scheduled SMS entries.`);

        const allEntries = [...base, ...conversationEntries, ...scheduled];
        const uniqueEntries = Array.from(new Map(allEntries.map(entry => [`${entry.type}-${entry.id}`, entry])).values());
        const sortedEntries = uniqueEntries.sort((a, b) => {
           if (!a.timestamp && !b.timestamp) return 0;
           if (!a.timestamp) return 1;
           if (!b.timestamp) return -1;
           try { // Add try-catch for date parsing
              const dateA = new Date(a.timestamp);
              const dateB = new Date(b.timestamp);
              if (isNaN(dateA.getTime())) return 1; // Invalid date sort last
              if (isNaN(dateB.getTime())) return -1; // Invalid date sort last
              return dateA.getTime() - dateB.getTime();
           } catch (e) {
              console.error("Date sorting error:", e, a, b);
              return 0;
           }
        });

        console.log(`Total unique timeline entries: ${sortedEntries.length}`);
        setTimelineEntries(sortedEntries);
      } catch (err) {
        console.error("Failed to fetch conversation history:", err);
        setTimelineEntries(base.sort((a, b) => {
          if (!a.timestamp && !b.timestamp) return 0;
          if (!a.timestamp) return 1; // Place entries without timestamp last
          if (!b.timestamp) return -1;
          try {
             const dateA = new Date(a.timestamp);
             const dateB = new Date(b.timestamp);
             if (isNaN(dateA.getTime())) return 1; // Invalid dates last
             if (isNaN(dateB.getTime())) return -1;
             return dateA.getTime() - dateB.getTime();
          } catch (e) { return 0; } // Fallback on error
      }));
      }
    };

    fetchConversationHistory();

  }, [messages, activeCustomerId, scheduledSms]);


  const handleSendMessage = async () => {
    console.log('handleSendMessage triggered', { selectedDraftId, pendingReplyCustomerId, newMessage, activeCustomerId });
    const messageToSend = newMessage.trim();
    if (!messageToSend) return;

    if (isSending) {
      console.log("Send already in progress, aborting.");
      return;
    }

    setIsSending(true);
    setSendError(null);

    const isSendingDraft = selectedDraftId && pendingReplyCustomerId;
    const isSendingManual = !isSendingDraft && activeCustomerId;

    const currentDraftId = selectedDraftId;
    const currentPendingCustomerId = pendingReplyCustomerId;
    const currentActiveCustomerId = activeCustomerId;

    try {
      if (isSendingDraft) {
        console.log(`Attempting to send draft ID: ${currentDraftId} for customer ID: ${currentPendingCustomerId}`);
        await apiClient.put(`/engagement-workflow/reply/${currentDraftId}/send`, {
          updated_content: messageToSend,
        });
        console.log(`✅ Draft ${currentDraftId} sent successfully via API.`);
        setNewMessage("");
        setSelectedDraftId(null);
        setPendingReplyCustomerId(null);

      } else if (isSendingManual) {
        console.log(`Attempting to send manual reply to customer ID: ${currentActiveCustomerId}`);
        await apiClient.post(`/engagement-workflow/manual-reply/${currentActiveCustomerId}`, {
          message: messageToSend,
        });
        console.log(`✅ Manual message sent successfully to customer ${currentActiveCustomerId} via API.`);
        setNewMessage("");

      } else {
        console.error("Send triggered without a valid target (no draft selected and no active customer).");
        throw new Error("Cannot send message: No recipient context.");
      }

      if (businessId) {
        console.log(`🔄 Re-fetching history for business ${businessId} after message send.`);
        try {
          const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
          const messageData = res.data || [];
          const mappedData = messageData.map((msg: any) => ({
            ...msg,
             customer_id: msg.customer_id,
             customer_name: msg.customer_name || "Unknown Customer",
            latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
          }));
          setMessages(mappedData);
          console.log(`✅ History updated for business ${businessId}. Messages count: ${mappedData.length}`);
        } catch (fetchError) {
           console.error("❌ Failed to re-fetch customer history after sending:", fetchError);
           setSendError("Message sent, but failed to refresh conversation history.");
        }
      }

      const customerIdToUpdate = isSendingDraft ? currentPendingCustomerId : currentActiveCustomerId;
      if (customerIdToUpdate) {
          setLastSeenMap(prev => ({ ...prev, [customerIdToUpdate]: new Date().toISOString() }));
      }

    } catch (err) {
      console.error("❌ Error during send process:", err);
      const response = (err as any)?.response;
      const status = response?.status;
      const detail = response?.data?.detail || (err as any).message || "An unknown error occurred.";
      console.error(`❌ API Error Details: Status ${status}, Detail: ${detail}`);

      if (status === 409) {
        setSendError("This draft is no longer valid. It may have already been sent or expired. Refreshing data...");
         if (businessId) {
            console.log(`🔄 Triggering refresh due to ${status} error.`);
             try {
                 const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
                 setMessages(res.data || []);
             } catch (refreshError) {
                 console.error("Failed to refresh after 409 error:", refreshError);
             }
         }
         setSelectedDraftId(null);
         setPendingReplyCustomerId(null);
         setNewMessage("");

      } else if (status === 404) {
        setSendError("Draft or customer not found. Please refresh and try again.");
         if (businessId) {
            console.log(`🔄 Triggering refresh due to ${status} error.`);
             try {
                 const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
                 setMessages(res.data || []);
             } catch (refreshError) {
                 console.error("Failed to refresh after 404 error:", refreshError);
             }
         }
         setSelectedDraftId(null);
         setPendingReplyCustomerId(null);
         setNewMessage("");

      } else {
        setSendError(`Failed to send message: ${detail}`);
      }
    } finally {
      setIsSending(false);
      console.log("handleSendMessage finished.");
    }
  };

  // Revised: More robust function to get customer summaries for the sidebar
  const getLatestMessagesByCustomer = () => {
    // This function should ideally return unique customer entries from the 'messages' state.
    // Assuming 'messages' state holds the array of customer summary objects
    // returned by `/review/full-customer-history`.

    const customerMap = new Map<number, Message>();
    messages.forEach((customerData) => {
      // Basic validation of the customer data object
      if (customerData && customerData.customer_id && typeof customerData.customer_name === 'string') {
         // Use a Map to ensure we only list each customer once in the sidebar
         if (!customerMap.has(customerData.customer_id)) {
             customerMap.set(customerData.customer_id, customerData);
         } else {
             // If customer already exists, potentially update if this entry is more recent?
             // Requires a timestamp field at this top level, e.g., customerData.last_message_time
             // For now, just keep the first one encountered.
         }
      } else {
         console.warn("Skipping invalid customer summary entry in messages state:", customerData);
      }
    });

    const customerList = Array.from(customerMap.values());
    console.log(`Sidebar customer list size: ${customerList.length}`); // Log size
    return customerList;
  };


  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      {/* Mobile Header */}
      <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45]">
        <h1 className="text-xl font-semibold text-white">Inbox</h1>
        <button
          onClick={() => setShowMobileDrawer(!showMobileDrawer)}
          className="p-2 hover:bg-[#242842] rounded-lg transition-colors"
        >
          <MessageSquare className="w-5 h-5 text-white" />
        </button>
      </div>

      {/* Sidebar */}
      <aside className={clsx(
        "w-full md:w-80 bg-[#1A1D2D] border-r border-[#2A2F45]",
        "md:relative fixed inset-0 z-50",
        "transition-transform duration-300 ease-in-out",
        showMobileDrawer ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        "flex flex-col h-full md:h-screen"
      )}>
        {/* Desktop Header */}
        <div className="hidden md:block p-4 border-b border-[#2A2F45]">
          <h2 className="text-xl font-semibold text-white">Inbox</h2>
        </div>
        {/* Mobile Header inside drawer */}
        <div className="md:hidden flex justify-between items-center p-4 border-b border-[#2A2F45]">
          <h2 className="text-xl font-semibold text-white">Contacts</h2>
          <button
            onClick={() => setShowMobileDrawer(false)}
            className="p-2 hover:bg-[#242842] rounded-lg"
          >
            ✕
          </button>
        </div>

        {/* Contact List */}
        <div className="flex-1 overflow-y-auto">
          {getLatestMessagesByCustomer().map((msg) => ( // msg is a customer summary object
            <div
              key={msg.customer_id} // Use unique customer ID
              onClick={() => {
                setActiveCustomerId(msg.customer_id);
                setSelectedDraftId(null);
                setNewMessage("");
                setPendingReplyCustomerId(null);
                fetchScheduledSms(msg.customer_id);
                setLastSeenMap(prev => ({ ...prev, [msg.customer_id]: new Date().toISOString() }));
                setShowMobileDrawer(false);
              }}
              className={clsx(
                "p-4 cursor-pointer border-b border-[#2A2F45] last:border-b-0",
                "hover:bg-[#242842] transition-colors",
                msg.customer_id === activeCustomerId && "bg-[#242842]"
              )}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 flex items-center justify-center text-white font-medium">
                   {/* Safer Access */}
                  {msg.customer_name?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white truncate">
                      {/* Safer Access */}
                      {msg.customer_name || 'Unknown'}
                    </span>
                    {/* Unread indicator logic would go here, comparing last message timestamp to lastSeenMap */}
                  </div>
                  <p className="text-sm text-gray-400 truncate">
                    {/* Use content field from the customer summary object if API provides it */}
                    {/* Otherwise, this might need fetching the actual latest message */}
                    {msg.content?.slice(0, 40) || 'No recent messages'}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col h-[calc(100vh-4rem)] md:h-screen">
        {/* Chat Header */}
        {activeCustomerId && (
          <div className="bg-[#1A1D2D] border-b border-[#2A2F45] p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 flex items-center justify-center text-white font-medium">
                 {messages.find(m => m.customer_id === activeCustomerId)?.customer_name[0]?.toUpperCase() || '?'}
              </div>
              <div className="flex-1">
                <h1 className="text-lg font-semibold text-white">
                   {messages.find(m => m.customer_id === activeCustomerId)?.customer_name || "Loading..."}
                </h1>
                <div className="flex items-center gap-2">
                   {(() => {
                      const currentCustomer = messages.find(m => m.customer_id === activeCustomerId);
                      const optedIn = currentCustomer?.opted_in || currentCustomer?.latest_consent_status === "opted_in";
                      return (
                         <span className={clsx(
                           "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs",
                           optedIn ? "bg-emerald-400/10 text-emerald-400" : "bg-red-400/10 text-red-400"
                         )}>
                           {optedIn ? <><Check className="w-3 h-3" /> Opted In</> : <><AlertCircle className="w-3 h-3" /> Not Opted In</>}
                         </span>
                      );
                   })()}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Messages Area - Scrollable Container */}
        <div
          ref={chatContainerRef} // Ref attached
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
          {timelineEntries
            .filter(entry => !entry.is_hidden)
            .map((entry) => (
            <div
              key={`${entry.type}-${entry.id}`}
              className={clsx(
                "flex flex-col",
                entry.type === "customer" ? "items-start" : "items-end"
              )}
            >
              {entry.timestamp && (
                <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                   {(() => { // Safer date formatting
                      try {
                         return new Date(entry.timestamp).toLocaleString();
                      } catch {
                         return 'Invalid Date';
                      }
                   })()}
                </div>
              )}
              <div
                className={clsx(
                  "max-w-[85%] md:max-w-md px-4 py-2.5 rounded-2xl",
                  entry.type === "customer" && "bg-gradient-to-r from-emerald-500 to-blue-500 text-white",
                  entry.type === "sent" && "bg-[#242842] text-white",
                  entry.type === "ai_draft" && "bg-gradient-to-r from-purple-500 to-fuchsia-500 text-white"
                )}
              >
                {entry.type === "ai_draft" && (
                  <div className="text-xs font-medium mb-1">💡 Draft Reply</div>
                )}
                <div className="whitespace-pre-wrap break-words">{entry.content}</div>
                {entry.type === "ai_draft" && (
                  <>
                    <button
                      onClick={() => {
                        const idNum = Number(entry.id);
                        setSelectedDraftId(Number.isNaN(idNum) ? null : idNum);
                        setPendingReplyCustomerId(entry.customer_id);
                        setActiveCustomerId(entry.customer_id);
                        setNewMessage(entry.content);
                      }}
                      className="mt-2 text-xs font-medium text-white/90 hover:text-white flex items-center gap-1 transition-colors"
                    >
                      ✏️ Edit & Send
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          await apiClient.delete(`/engagement-workflow/${entry.id}`);
                          setTimelineEntries((prev) =>
                            prev.filter((e) => !(e.id === entry.id && e.type === "ai_draft"))
                          );
                        } catch (err) {
                          console.error("❌ Failed to delete draft", err);
                          alert("Failed to delete draft.");
                        }
                      }}
                      className="mt-1 text-xs font-medium text-white/90 hover:text-white flex items-center gap-1 transition-colors"
                    >
                      🗑️ Delete Draft
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
          {/* Removed the empty div target */}
        </div>

        {/* Message Input Area */}
        <div className="bg-[#1A1D2D] border-t border-[#2A2F45] p-4">
          {/* Opt-in Warning */}
          {activeCustomerId && (() => {
            const currentCustomer = messages.find(m => m.customer_id === activeCustomerId);
            const optedIn = currentCustomer?.opted_in || currentCustomer?.latest_consent_status === "opted_in";

            if (!optedIn) {
              return (
                <div className="flex flex-col md:flex-row items-start md:items-center justify-between bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg px-4 py-3 mb-4 gap-3">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span className="text-sm">Messaging is blocked (not opted in)</span>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        await apiClient.post(`/consent/resend-optin/${activeCustomerId}`);
                        alert("Opt-in request sent again.");
                      } catch (err) {
                        console.error("Failed to resend opt-in:", err);
                        alert("Failed to resend opt-in request.");
                      }
                    }}
                    className="w-full md:w-auto bg-[#242842] hover:bg-[#2A2F45] text-white text-sm px-4 py-2 rounded-lg transition-colors whitespace-nowrap"
                  >
                    💌 Request Opt-In
                  </button>
                </div>
              );
            }
            return null;
          })()}

          {/* Message Input */}
          <div className="flex gap-2">
            <input
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 bg-[#242842] border border-[#2A2F45] px-4 py-3 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all"
            />
            <button
              onClick={() => {
                console.log("🚀 Clicked send button");
                handleSendMessage();
              }}
              disabled={isSending || !newMessage.trim()}
              className={clsx(
                "p-3 rounded-lg transition-all duration-200",
                "bg-gradient-to-r from-emerald-500 to-blue-500 hover:opacity-90",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                isSending && "animate-pulse"
              )}
            >
              <Send className="w-5 h-5 text-white" />
            </button>
          </div>

          {/* Error Message */}
          {sendError && (
            <div className="text-xs text-red-400 mt-2 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {sendError}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}