"use client";

import { useEffect, useState, useMemo } from "react";
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

  useEffect(() => {
    const fetchBusinessAndMessages = async () => {
      if (!business_name) return;
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
      }
    };
    fetchBusinessAndMessages();
  }, [business_name]);

  useEffect(() => {
    if (!businessId) return;
    const interval = setInterval(async () => {
      const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
      const messageData = res.data || [];
      
      // Map the data to include opted_in status
      const mappedData = messageData.map((msg: any) => ({
        ...msg,
        latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
      }));
      
      setMessages(mappedData);
    }, 4000);
    return () => clearInterval(interval);
  }, [businessId]);

  const fetchScheduledSms = async (customerId: number) => {
    const res = await apiClient.get(`/message-workflow/sent/${customerId}`);
    setScheduledSms(res.data || []);
  };

  const filteredMessages = useMemo(
    () => messages.filter(msg => msg.customer_id === activeCustomerId),
    [messages, activeCustomerId]
  );

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
        }
      }
    }

    const fetchConversationHistory = async () => {
      if (!activeCustomerId) return;
      try {
        const res = await apiClient.get(`/conversations/customer/${activeCustomerId}`);
        const conversationEntries = (res.data.messages || []).map((msg: any, index: number) => ({
          id: msg.id || `temp-${index}`,
          type: msg.type,
          content: msg.text || msg.content,
          timestamp: msg.timestamp || msg.sent_time,
          customer_id: activeCustomerId,
          is_hidden: msg.is_hidden
        }));

        const scheduled: TimelineEntry[] = scheduledSms
          .filter(sms => sms.status === "sent" && sms.customer_id === activeCustomerId)
          .map(sms => ({
            id: `sms-${sms.id}`,
            type: "sent",
            content: sms.message,
            timestamp: sms.send_time || null,
            customer_id: sms.customer_id,
            is_hidden: sms.is_hidden
          })) as TimelineEntry[];

        const allEntries = [...base, ...conversationEntries, ...scheduled];
        const sortedEntries = allEntries.sort((a, b) => {
          if (!a.timestamp) return 1;
          if (!b.timestamp) return -1;
          return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
        });

        setTimelineEntries(sortedEntries);
      } catch (err) {
        console.error("Failed to fetch conversation history:", err);
      }
    };

    fetchConversationHistory();
  }, [messages, activeCustomerId, scheduledSms]);

  const handleSendMessage = async () => {
    console.log('handleSendMessage', { selectedDraftId, pendingReplyCustomerId, newMessage });
    if (!newMessage.trim()) return;
    setIsSending(true);
    setSendError(null);

    try {
      if (selectedDraftId && pendingReplyCustomerId) {
        const draftMsg = messages.find((msg) => msg.id === selectedDraftId);
        if (!draftMsg) throw new Error("Draft not found");

        await apiClient.put(`/engagement-workflow/${selectedDraftId}/edit-ai-draft`, { ai_response: newMessage.trim() });
        console.log("🌍 API BASE", process.env.NEXT_PUBLIC_API_BASE);
        console.log("📤 Sending AI reply", {
          selectedDraftId,
          endpoint: `/engagement-workflow/reply/${selectedDraftId}/send`,
          payload: { updated_content: newMessage.trim() },
        });
        await apiClient.put(`/engagement-workflow/reply/${selectedDraftId}/send`, {
          updated_content: newMessage.trim(),
        });

        // Optimistically remove the draft with the sent id and status "pending_review"
        setMessages((prev) =>
          prev.filter(
            (msg) =>
              !(
                msg.id === selectedDraftId &&
                msg.status === "pending_review"
              )
          )
        );
        setTimelineEntries((prev) =>
          prev.filter(
            (entry) =>
              !(
                entry.type === "ai_draft" &&
                Number(entry.id) === selectedDraftId // 👈 Ensure match works with string/number
              )
          )
        );

        // After sending, re-fetch messages from backend to update UI and remove sent drafts
        if (businessId) {
          const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
          const messageData = res.data || [];
          const mappedData = messageData.map((msg: any) => ({
            ...msg,
            latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
          }));
          setMessages(mappedData);
        }

        setNewMessage("");
        setSelectedDraftId(null);
        setPendingReplyCustomerId(null);
        setLastSeenMap(prev => ({ ...prev, [activeCustomerId!]: new Date().toISOString() }));
      } else if (activeCustomerId) {
        const response = await apiClient.post(`/engagement-workflow/manual-reply/${activeCustomerId}`, {
          message: newMessage.trim(),
        });

        // After sending, re-fetch messages from backend to update UI and remove sent drafts
        if (businessId) {
          const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
          const messageData = res.data || [];
          const mappedData = messageData.map((msg: any) => ({
            ...msg,
            latest_consent_status: msg.opted_in ? "opted_in" : "opted_out"
          }));
          setMessages(mappedData);
        }

        setMessages(prev => [...prev, {
          id: response.data.id,
          customer_id: activeCustomerId!,
          customer_name: filteredMessages[0]?.customer_name || "Unknown",
          phone: filteredMessages[0]?.phone || "",
          content: newMessage.trim(),
          type: "outbound",
          status: "sent",
          sent_time: new Date().toISOString(),
          latest_consent_status: "",
          is_hidden: false,
          source: "manual",
          opted_in: false
        }]);
        // Remove all ai_draft entries for this customer
        setTimelineEntries((prev) =>
          prev.filter((entry) =>
            !(entry.type === "ai_draft" && entry.customer_id === activeCustomerId)
          )
        );
      }
    } catch (err) {
      const status = (err as any)?.response?.status;
      const detail = (err as any)?.response?.data?.detail || (err as any).message || err;

      console.error("❌ API error", detail);

      if (status === 409) {
        setSendError("This draft is no longer valid. It may have already been sent or expired.");
      } else if (status === 404) {
        setSendError("Draft not found. Please refresh and try again.");
      } else {
        setSendError("Failed to send message.");
      }
    } finally {
      setIsSending(false);
    }
  };

  const getLatestMessagesByCustomer = () => {
    const grouped = new Map<number, Message>();
    messages.forEach((msg) => {
      if (!msg.customer_id) return;
      const existing = grouped.get(msg.customer_id);
      if (!existing || (msg.sent_time && existing.sent_time && new Date(msg.sent_time) > new Date(existing.sent_time))) {
        grouped.set(msg.customer_id, msg);
      }
    });
    return Array.from(grouped.values());
  };

  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
      {/* Mobile Header - Only shows on mobile */}
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
        {/* Sidebar Header - Only visible on desktop */}
        <div className="hidden md:block p-4 border-b border-[#2A2F45]">
          <h2 className="text-xl font-semibold text-white">Inbox</h2>
        </div>

        {/* Mobile Close Button */}
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
          {getLatestMessagesByCustomer().map((msg) => (
            <div
              key={`${msg.customer_id}-${msg.id}`}
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
                <div className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 
                  flex items-center justify-center text-white font-medium">
                  {msg.customer_name[0]?.toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white truncate">
                      {msg.customer_name}
                    </span>
                    {msg.sent_time && !lastSeenMap[msg.customer_id] && (
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    )}
                  </div>
                  <p className="text-sm text-gray-400 truncate">
                    {msg.content?.slice(0, 40)}
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
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-blue-500 
                flex items-center justify-center text-white font-medium">
                {filteredMessages[0]?.customer_name[0]?.toUpperCase()}
              </div>
              <div className="flex-1">
                <h1 className="text-lg font-semibold text-white">
                  {filteredMessages[0]?.customer_name || "..."}
                </h1>
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs",
                    (filteredMessages[0]?.opted_in || filteredMessages[0]?.latest_consent_status === "opted_in")
                      ? "bg-emerald-400/10 text-emerald-400"
                      : "bg-red-400/10 text-red-400"
                  )}>
                    {(filteredMessages[0]?.opted_in || filteredMessages[0]?.latest_consent_status === "opted_in")
                      ? <><Check className="w-3 h-3" /> Opted In</> 
                      : <><AlertCircle className="w-3 h-3" /> Not Opted In</>}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {timelineEntries
            .filter(entry => !entry.is_hidden) // Filter out hidden messages
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
                        // Always convert entry.id to a valid number or null
                        const idNum = Number(entry.id);
                        console.log('Edit & Send clicked', { entryId: entry.id, idNum, type: typeof entry.id });
                        setSelectedDraftId(Number.isNaN(idNum) ? null : idNum); // Track the draft ID
                        setPendingReplyCustomerId(entry.customer_id); // Track customer to reply to
                        setActiveCustomerId(entry.customer_id);
                        setNewMessage(entry.content);
                      }}
                      className="mt-2 text-xs font-medium text-white/90 hover:text-white 
                        flex items-center gap-1 transition-colors"
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
                      className="mt-1 text-xs font-medium text-white/90 hover:text-white 
                        flex items-center gap-1 transition-colors"
                    >
                      🗑️ Delete Draft
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Message Input Area */}
        <div className="bg-[#1A1D2D] border-t border-[#2A2F45] p-4">
          {/* Opt-in Warning */}
          {activeCustomerId && (() => {
            const customerMsgs = messages.filter(m => m.customer_id === activeCustomerId);
            const latestMsg = customerMsgs[0];
            const optedIn = latestMsg?.opted_in || latestMsg?.latest_consent_status === "opted_in";

            if (!optedIn) {
              return (
                <div className="flex flex-col md:flex-row items-start md:items-center justify-between 
                  bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg px-4 py-3 mb-4 gap-3">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span className="text-sm">Messaging is blocked (not opted in)</span>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        await apiClient.post(`/resend-optin/${activeCustomerId}`);
                        alert("Opt-in request sent again.");
                      } catch (err) {
                        alert("Failed to resend opt-in request.");
                      }
                    }}
                    className="w-full md:w-auto bg-[#242842] hover:bg-[#2A2F45] text-white text-sm 
                      px-4 py-2 rounded-lg transition-colors whitespace-nowrap"
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
              className="flex-1 bg-[#242842] border border-[#2A2F45] px-4 py-3 rounded-lg 
                text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50 
                focus:ring-1 focus:ring-emerald-500/50 transition-all"
            />
            <button
              onClick={() => {
                console.log("🚀 Clicked send button");
                console.log("🧪 newMessage:", newMessage);
                console.log("🧪 isSending:", isSending);
                console.log("🧪 button disabled:", isSending || !newMessage.trim());
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