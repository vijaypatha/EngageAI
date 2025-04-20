"use client";

import { useEffect, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Clock, Send } from "lucide-react";
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
    <div className="min-h-screen bg-black text-white grid grid-cols-1 md:grid-cols-[300px,1fr]">
      {/* Mobile Drawer Toggle Button */}
      <button
        onClick={() => setShowMobileDrawer(true)}
        className="md:hidden p-2 text-white bg-zinc-800 border border-white rounded-lg m-4 self-start"
      >
        ☰ Inbox
      </button>

      {/* Slide-out Drawer */}
      {showMobileDrawer && (
        <div className="fixed inset-0 bg-black bg-opacity-90 z-50 flex flex-col p-4 overflow-y-auto">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold">Inbox</h2>
            <button onClick={() => setShowMobileDrawer(false)} className="text-white text-lg">✖</button>
          </div>
          {getLatestMessagesByCustomer().map((msg) => {
            const isUnread = msg.sent_at && (!lastSeenMap[msg.customer_id] || new Date(msg.sent_at) > new Date(lastSeenMap[msg.customer_id]));
            return (
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
                className={clsx("p-3 rounded-lg cursor-pointer hover:bg-zinc-800", msg.customer_id === activeCustomerId && "bg-zinc-800")}
              >
                <div className="flex justify-between items-center">
                  <span className="font-semibold">{msg.customer_name}</span>
                  {isUnread && <span className="text-xs text-green-400">●</span>}
                </div>
                <div className="text-sm text-neutral-400">{msg.response?.slice(0, 40) || msg.ai_response?.slice(0, 40)}</div>
                {msg.sent_at && <div className="text-xs text-zinc-600 mt-1">{formatDistanceToNow(new Date(msg.sent_at))} ago</div>}
              </div>
            );
          })}
        </div>
      )}

      {/* Desktop Sidebar */}
      <aside className="hidden md:block border-r border-zinc-800 p-4 space-y-3 bg-zinc-950">
        <h2 className="text-xl font-semibold mb-2">Inbox</h2>
        {getLatestMessagesByCustomer().map((msg) => {
          const isUnread = msg.sent_at && (!lastSeenMap[msg.customer_id] || new Date(msg.sent_at) > new Date(lastSeenMap[msg.customer_id]));
          return (
            <div
              key={`${msg.customer_id}-${msg.id}`}
              onClick={() => {
                setActiveCustomerId(msg.customer_id);
                setSelectedDraftId(null);
                setNewMessage("");
                setPendingReplyCustomerId(null);
                fetchScheduledSms(msg.customer_id);
                setLastSeenMap(prev => ({ ...prev, [msg.customer_id]: new Date().toISOString() }));
              }}
              className={clsx("p-3 rounded-lg cursor-pointer hover:bg-zinc-800", msg.customer_id === activeCustomerId && "bg-zinc-800")}
            >
              <div className="flex justify-between items-center">
                <span className="font-semibold">{msg.customer_name}</span>
                {isUnread && <span className="text-xs text-green-400">●</span>}
              </div>
              <div className="text-sm text-neutral-400">{msg.response?.slice(0, 40) || msg.ai_response?.slice(0, 40)}</div>
              {msg.sent_at && <div className="text-xs text-zinc-600 mt-1">{formatDistanceToNow(new Date(msg.sent_at))} ago</div>}
            </div>
          );
        })}
      </aside>

      <main className="w-full flex flex-col p-4 space-y-4">
        <h1 className="text-2xl font-bold">Chat with {filteredMessages[0]?.customer_name || "…"}</h1>

        {activeCustomerId && (() => {
          const customerMsgs = messages.filter(m => m.customer_id === activeCustomerId);
          const latestMsg = customerMsgs[0];
          const optedIn = latestMsg?.opted_in ?? false;

          return !optedIn ? (
            <div className="flex justify-between items-center bg-zinc-900 border border-red-500 text-sm text-red-400 rounded-md px-4 py-2 mb-2">
              <div>❌ This contact has not opted in. Messaging is blocked.</div>
              <button
                onClick={async () => {
                  try {
                    await apiClient.post(`/resend-optin/${activeCustomerId}`);
                    alert("Opt-in request sent again.");
                  } catch (err) {
                    alert("Failed to resend opt-in request.");
                  }
                }}
                className="ml-4 bg-blue-700 hover:bg-blue-600 text-white text-sm px-4 py-1 rounded-full"
              >
                💌 Request Opt-In Again
              </button>
            </div>
          ) : null;
        })()}

        <div className="flex flex-col gap-4 overflow-y-auto max-h-[calc(100vh-250px)] pr-2">
          {timelineEntries.map((entry) => (
            <div key={`${entry.type}-${entry.id}`} className="flex flex-col">
              {entry.timestamp && (
                <div className={clsx("text-xs", entry.type === "customer" ? "text-left" : "text-right")}>
                  <Clock className="inline w-3 h-3 mr-1" />
                  {new Date(entry.timestamp).toLocaleString()}
                </div>
              )}
              <div
                className={clsx(
                  "max-w-md px-4 py-2 rounded-xl shadow-md",
                  entry.type === "customer" && "bg-zinc-800 self-start",
                  entry.type === "sent" && "bg-green-700 text-white self-end",
                  entry.type === "ai_draft" && "bg-purple-600 text-white self-end"
                )}
              >
                {entry.type === "ai_draft" && <div className="text-xs mb-1">💡 Draft Reply</div>}
                <div className="whitespace-pre-wrap">{entry.content}</div>
                {entry.type === "ai_draft" && (
                  <button
                    className="text-xs underline mt-2"
                    onClick={() => {
                      setPendingReplyCustomerId(entry.customer_id);
                      setActiveCustomerId(entry.customer_id);
                      setNewMessage(entry.content);
                      setSelectedDraftId(typeof entry.id === 'string' ? parseInt(entry.id) : entry.id);
                    }}
                  >
                    ✏️ Edit & Send
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-zinc-800 pt-4">
          <div className="flex gap-2">
            <input
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Type your message..."
              className="w-full bg-zinc-800 px-4 py-2 rounded-full text-sm focus:outline-none text-white"
            />
            <button
              onClick={handleSendMessage}
              className={clsx(
                "p-2 rounded-full bg-gradient-to-br from-purple-600 to-fuchsia-600",
                isSending && "animate-pulse",
                !newMessage.trim() && "opacity-50"
              )}
              disabled={isSending || !newMessage.trim()}
            >
              <Send className="w-4 h-4 text-white" />
            </button>
          </div>
          {sendError && <div className="text-xs text-red-400 mt-1">{sendError}</div>}
        </div>
      </main>
    </div>
  );
}