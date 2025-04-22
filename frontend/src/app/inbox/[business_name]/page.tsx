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
  response: string;
  ai_response?: string;
  status: string;
  sent_at?: string;
  opted_in: boolean;
}

type TimelineEntry = {
  type: "customer" | "sent" | "ai_draft";
  content: string;
  timestamp: string | null;
  id: number | string;
  customer_id: number;
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
      setMessages(res.data || []);
      if (res.data.length > 0) {
        setActiveCustomerId(res.data[0].customer_id);
        fetchScheduledSms(res.data[0].customer_id);
      }
    };
    fetchBusinessAndMessages();
  }, [business_name]);

  useEffect(() => {
    if (!businessId) return;
    const interval = setInterval(async () => {
      const res = await apiClient.get(`/review/full-customer-history?business_id=${businessId}`);
      setMessages(res.data || []);
    }, 4000);
    return () => clearInterval(interval);
  }, [businessId]);

  const fetchScheduledSms = async (customerId: number) => {
    const res = await apiClient.get(`/sent/${customerId}`);
    setScheduledSms(res.data || []);
  };

  const filteredMessages = useMemo(
    () => messages.filter(msg => msg.customer_id === activeCustomerId),
    [messages, activeCustomerId]
  );

  useEffect(() => {
    const base = filteredMessages.flatMap((msg) => {
      const entries: TimelineEntry[] = [];

      if (msg.response) {
        entries.push({ id: msg.id, type: "customer", content: msg.response, timestamp: msg.sent_at || null, customer_id: msg.customer_id });
      }

      if (msg.ai_response && msg.status === "pending_review") {
        entries.push({ id: msg.id, type: "ai_draft", content: msg.ai_response, timestamp: null, customer_id: msg.customer_id });
      }

      if (msg.ai_response && msg.status === "sent") {
        entries.push({ id: msg.id, type: "sent", content: msg.ai_response, timestamp: msg.sent_at || null, customer_id: msg.customer_id });
      }

      return entries;
    });

    const scheduled: TimelineEntry[] = scheduledSms
      .filter(sms => sms.status === "sent" && sms.customer_id === activeCustomerId)
      .map(sms => ({
        id: `sms-${sms.id}`,
        type: "sent",
        content: sms.message,
        timestamp: sms.send_time || null,
        customer_id: sms.customer_id
      })) as TimelineEntry[];

    const merged: TimelineEntry[] = [...base, ...scheduled].sort((a, b) => {
      if (!a.timestamp) return 1;
      if (!b.timestamp) return -1;
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

    setTimelineEntries(merged);
  }, [messages, scheduledSms, activeCustomerId]);

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;
    setIsSending(true);
    setSendError(null);

    try {
      if (selectedDraftId && pendingReplyCustomerId) {
        const draftMsg = messages.find((msg) => msg.id === selectedDraftId);
        if (!draftMsg) throw new Error("Draft not found");

        await apiClient.put(`/review/engagement/update-draft/${draftMsg.id}`, { ai_response: newMessage.trim() });
        await apiClient.put(`/engagement/reply/${draftMsg.id}/send`, { response: newMessage.trim() });

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === draftMsg.id
              ? { ...msg, ai_response: newMessage.trim(), sent_at: new Date().toISOString(), status: "sent" }
              : msg
          )
        );
      } else if (activeCustomerId) {
        const response = await apiClient.post(`/engagement/manual-reply/${activeCustomerId}`, {
          message: newMessage.trim(),
        });

        setMessages(prev => [...prev, {
          id: response.data.id,
          customer_id: activeCustomerId!,
          customer_name: filteredMessages[0]?.customer_name || "Unknown",
          response: newMessage.trim(),
          status: "sent",
          sent_at: new Date().toISOString(),
          opted_in: false,
        }]);
      }

      setNewMessage("");
      setSelectedDraftId(null);
      setPendingReplyCustomerId(null);
      setLastSeenMap(prev => ({ ...prev, [activeCustomerId!]: new Date().toISOString() }));
    } catch (err) {
      console.error("❌ Failed to send message", err);
      setSendError("Failed to send message.");
    } finally {
      setIsSending(false);
    }
  };

  const getLatestMessagesByCustomer = () => {
    const grouped = new Map<number, Message>();
    messages.forEach((msg) => {
      if (!msg.customer_id) return;
      const existing = grouped.get(msg.customer_id);
      if (!existing || (msg.sent_at && existing.sent_at && new Date(msg.sent_at) > new Date(existing.sent_at))) {
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
                    {msg.sent_at && !lastSeenMap[msg.customer_id] && (
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    )}
                  </div>
                  <p className="text-sm text-gray-400 truncate">
                    {msg.response?.slice(0, 40) || msg.ai_response?.slice(0, 40)}
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
                    filteredMessages[0]?.opted_in 
                      ? "bg-emerald-400/10 text-emerald-400"
                      : "bg-red-400/10 text-red-400"
                  )}>
                    {filteredMessages[0]?.opted_in 
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
          {timelineEntries.map((entry) => (
            <div key={`${entry.type}-${entry.id}`} 
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
              <div className={clsx(
                "max-w-[85%] md:max-w-md px-4 py-2.5 rounded-2xl",
                entry.type === "customer" && "bg-[#242842] text-white",
                entry.type === "sent" && "bg-gradient-to-r from-emerald-500 to-blue-500 text-white",
                entry.type === "ai_draft" && "bg-gradient-to-r from-purple-500 to-fuchsia-500 text-white"
              )}>
                {entry.type === "ai_draft" && (
                  <div className="text-xs font-medium mb-1">💡 Draft Reply</div>
                )}
                <div className="whitespace-pre-wrap break-words">{entry.content}</div>
                {entry.type === "ai_draft" && (
                  <button
                    onClick={() => {
                      setPendingReplyCustomerId(entry.customer_id);
                      setActiveCustomerId(entry.customer_id);
                      setNewMessage(entry.content);
                      setSelectedDraftId(typeof entry.id === 'string' ? parseInt(entry.id) : entry.id);
                    }}
                    className="mt-2 text-xs font-medium text-white/90 hover:text-white 
                      flex items-center gap-1 transition-colors"
                  >
                    ✏️ Edit & Send
                  </button>
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
            const optedIn = latestMsg?.opted_in ?? false;

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
              onClick={handleSendMessage}
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