"use client";

import { useEffect, useState, useMemo, useRef } from "react"; // useRef is included
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
  content: string;
  type: "outbound" | "inbound";
  status: string;
  scheduled_time?: string;
  sent_time?: string;
  source: string;
  is_hidden?: boolean;
  latest_consent_status: string;
  opted_in: boolean;
  response?: string;
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

  // --- Scroll to bottom logic START (Approach 3: Ref on Container) ---
  // Ref for the scrollable message container itself
  const chatContainerRef = useRef<null | HTMLDivElement>(null);

  useEffect(() => {
    // Directly manipulate scrollTop when timeline/customer changes
    if (chatContainerRef.current) {
      // Set the scroll position to the maximum height
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries, activeCustomerId]); // Dependencies trigger the effect
  // --- Scroll to bottom logic END (Approach 3) ---


  useEffect(() => {
    const fetchBusinessAndMessages = async () => {
      if (!business_name) return;
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data.business_id;
        setBusinessId(id);

        const res = await apiClient.get(`/review/full-customer-history?business_id=${id}`);
        const messageData = res.data || [];

        const mappedData = messageData.map((msg: any) => ({
          ...msg,
          latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
        }));

        setMessages(mappedData);
        if (mappedData.length > 0) {
          setActiveCustomerId(mappedData[0].customer_id);
          fetchScheduledSms(mappedData[0].customer_id);
        } else {
           setActiveCustomerId(null); // Ensure no customer is active if none found
           setTimelineEntries([]); // Clear timeline if no messages
        }
      } catch (error) {
         console.error("Failed to fetch initial business and messages:", error);
         // Handle error appropriately, maybe show a message to the user
      }
    };
    fetchBusinessAndMessages();
  }, [business_name]); // Dependency: business_name from URL

  useEffect(() => {
    if (!businessId) return;
    const interval = setInterval(async () => {
      try {
        const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
        const messageData = res.data || [];

        const mappedData = messageData.map((msg: any) => ({
          ...msg,
          latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
        }));

        setMessages(mappedData);
      } catch (error) {
         console.error("Failed to fetch messages during polling:", error);
      }
    }, 4000); // Consider increasing interval or using WebSockets later
    return () => clearInterval(interval); // Cleanup interval on component unmount
  }, [businessId]); // Dependency: businessId

  const fetchScheduledSms = async (customerId: number) => {
    try {
      const res = await apiClient.get(`/message-workflow/sent/${customerId}`);
      setScheduledSms(res.data || []);
    } catch (error) {
       console.error(`Failed to fetch scheduled SMS for customer ${customerId}:`, error);
       setScheduledSms([]); // Reset on error
    }
  };

  const filteredMessages = useMemo(
    () => messages.filter(msg => msg.customer_id === activeCustomerId),
    [messages, activeCustomerId]
  );

  // Reverted useEffect hook for building timeline
  useEffect(() => {
    const base: TimelineEntry[] = [];

    const customer = messages.find(m => m.customer_id === activeCustomerId);
    if (customer && Array.isArray((customer as any).messages)) {
      for (const msg of (customer as any).messages) {
        if (msg.is_hidden) continue;

        if (msg.type === "inbound") {
          base.push({
            id: msg.id,
            type: "customer",
            content: msg.content,
            timestamp: msg.sent_time || null,
            customer_id: msg.customer_id,
            is_hidden: msg.is_hidden
          });
        } else if (msg.type === "outbound") {
          if (msg.status === "pending_review") {
            base.push({
              id: msg.id,
              type: "ai_draft",
              content: msg.content,
              timestamp: null,
              customer_id: msg.customer_id,
              is_hidden: msg.is_hidden
            });
          } else if (msg.status === "sent") {
            base.push({
              id: msg.id,
              type: "sent",
              content: msg.content,
              timestamp: msg.sent_time || msg.scheduled_time || null,
              customer_id: msg.customer_id,
              is_hidden: msg.is_hidden
            });
          }
          // Add other statuses like 'delivered', 'failed' if needed
        }
      }
    } else if (customer) {
        console.warn("Timeline Effect: Found customer data, but customer.messages is not an array or missing.", customer);
    }

    const fetchConversationHistory = async () => {
      if (!activeCustomerId) {
          setTimelineEntries(base.sort((a, b) => {
              if (!a.timestamp) return 1;
              if (!b.timestamp) return -1;
              return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
          }));
          return;
      };
      try {
        const res = await apiClient.get(`/conversations/customer/${activeCustomerId}`);
        const conversationEntries = (res.data.messages || []).map((msg: any, index: number) => ({
          id: msg.id || `conv-${index}`,
          type: msg.type === "customer" ? "customer" : (msg.type === "ai_draft" ? "ai_draft" : "sent"), // Adjust based on actual API response structure
          content: msg.text || msg.content,
          timestamp: msg.timestamp || msg.sent_time || msg.created_at || null,
          customer_id: activeCustomerId,
          is_hidden: msg.is_hidden || false
        }));

        const scheduled: TimelineEntry[] = scheduledSms
          .filter(sms => sms.status === "sent" && sms.customer_id === activeCustomerId)
          .map(sms => ({
            id: `sch-${sms.id}`,
            type: "sent",
            content: sms.message,
            timestamp: sms.send_time || null,
            customer_id: sms.customer_id,
            is_hidden: sms.is_hidden || false
          })) as TimelineEntry[];

        const allEntries = [...base, ...conversationEntries, ...scheduled];
        const uniqueEntries = Array.from(new Map(allEntries.map(entry => [`${entry.type}-${entry.id}`, entry])).values());
        const sortedEntries = uniqueEntries.sort((a, b) => {
           if (!a.timestamp && !b.timestamp) return 0;
           if (!a.timestamp) return 1;
           if (!b.timestamp) return -1;
           return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
        });

        setTimelineEntries(sortedEntries);
      } catch (err) {
        console.error("Failed to fetch conversation history:", err);
        setTimelineEntries(base.sort((a, b) => {
            if (!a.timestamp) return 1;
            if (!b.timestamp) return -1;
            return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
        }));
      }
    };

    fetchConversationHistory();

  }, [messages, activeCustomerId, scheduledSms]); // Dependencies


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

  const getLatestMessagesByCustomer = () => {
    const grouped = new Map<number, Message>();
    messages.forEach((customerGroup) => { // Assuming 'messages' is array of customer groups
      if (!customerGroup || !customerGroup.customer_id) return;
      // Find the latest message within this customer's group
      let latestMessageInGroup: Message | null = null;
      if (Array.isArray((customerGroup as any).messages)) {
          for(const msg of (customerGroup as any).messages) {
             if(!msg.sent_time) continue; // Skip messages without sent_time
             const msgSentTime = new Date(msg.sent_time);
             if (msgSentTime.toString() === 'Invalid Date') continue; // Skip invalid dates

             if (!latestMessageInGroup || !latestMessageInGroup.sent_time || msgSentTime > new Date(latestMessageInGroup.sent_time)) {
                latestMessageInGroup = msg;
             }
          }
      }
       // Use the latest message found (or the customer group itself if no messages)
       // This needs refinement based on actual data structure. For now, uses customerGroup as fallback.
       const messageToShow = latestMessageInGroup || customerGroup;
      grouped.set(customerGroup.customer_id, messageToShow);
    });
    return Array.from(grouped.values());
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
          {getLatestMessagesByCustomer().map((msg) => ( // msg here is the representative message
            <div
              key={msg.customer_id}
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
                  {msg.customer_name[0]?.toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white truncate">
                      {msg.customer_name}
                    </span>
                    {/* Unread indicator logic needed here */}
                  </div>
                  <p className="text-sm text-gray-400 truncate">
                    {msg.content?.slice(0, 40)} {/* Shows content of latest message */}
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
                 {/* Use active customer name if available */}
                 {messages.find(m => m.customer_id === activeCustomerId)?.customer_name[0]?.toUpperCase() || '?'}
              </div>
              <div className="flex-1">
                <h1 className="text-lg font-semibold text-white">
                   {messages.find(m => m.customer_id === activeCustomerId)?.customer_name || "Loading..."}
                </h1>
                <div className="flex items-center gap-2">
                   {(() => { // IIFE to get current customer info for status badge
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
          ref={chatContainerRef} // Ref attached to the scrollable container
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
                  {new Date(entry.timestamp).toLocaleString()}
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
                           // Consider re-fetching history after delete if needed
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