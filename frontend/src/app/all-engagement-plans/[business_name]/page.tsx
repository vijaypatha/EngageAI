"use client";
// @ts-ignore
import { zonedTimeToUtc } from "date-fns-tz";
import { useEffect, useState } from "react";
import { format, parseISO, startOfWeek, endOfWeek, addWeeks } from "date-fns";
import { apiClient } from "@/lib/api";
import { CalendarClock, Trash2, Pencil, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import clsx from "clsx";
import { useParams } from "next/navigation";

interface SMSMessage {
  id: number;
  customer_name: string;
  customer_id: number;
  smsContent: string;
  send_datetime_utc: string;
  status: string;
  is_hidden?: boolean;
  latest_consent_status?: string;
}

interface GroupedMessages {
  [key: string]: SMSMessage[];
}

export default function AllEngagementPlansPage() {
  const [messages, setMessages] = useState<SMSMessage[]>([]);
  const [grouped, setGrouped] = useState<GroupedMessages>({});
  const [loading, setLoading] = useState(true);
  const { business_name } = useParams();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState<string>("");
  const [editedTime, setEditedTime] = useState<string>("");
  const [hiddenIds, setHiddenIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    const loadMessages = async () => {
      const { data } = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
      const businessId = data.business_id;
      try {
        const res = await apiClient.get(`/review/all-engagements?business_id=${businessId}`);
        console.log("📦 Loaded messages from backend:", res.data);
        
        console.log("💾 Raw messages:", res.data.engagements);

        const filtered = res.data.engagements.filter(
          (msg: SMSMessage) => msg.status !== "sent" || (msg.status === "sent" && !msg.is_hidden)
        );
        setMessages(filtered);
      } catch (err) {
        console.error("❌ Failed to fetch messages", err);
      } finally {
        setLoading(false);
      }
    };
    if (business_name) loadMessages();
  }, [business_name]);

  useEffect(() => {
    const groupByTimeframe = (msgs: SMSMessage[]) => {
      console.log("🗂 Grouping messages by calendar weeks...");
      const grouped: GroupedMessages = { "This Week": [], "Next Week": [], Later: [] };
      const now = new Date();
      const thisWeekStart = startOfWeek(now, { weekStartsOn: 0 });
      const thisWeekEnd = endOfWeek(now, { weekStartsOn: 0 });
      const nextWeekEnd = endOfWeek(addWeeks(now, 1), { weekStartsOn: 0 });

      msgs
        .slice()
        .sort((a, b) => new Date(a.send_datetime_utc).getTime() - new Date(b.send_datetime_utc).getTime())
        .forEach((msg) => {
          const date = parseISO(msg.send_datetime_utc);
          if (date >= thisWeekStart && date <= thisWeekEnd) {
            grouped["This Week"].push(msg);
          } else if (date > thisWeekEnd && date <= nextWeekEnd) {
            grouped["Next Week"].push(msg);
          } else {
            grouped["Later"].push(msg);
          }
        });

      setGrouped(grouped);
      console.log("📊 Grouped result:", grouped);
    };
    if (messages.length > 0) {
      groupByTimeframe(messages);
    }
  }, [messages]);

  const handleHide = async (id: number) => {
    try {
      await apiClient.put(`/review/hide-sent/${id}?hide=true`);
      setHiddenIds(prev => new Set(prev).add(id));
      console.log(`🙈 Message ${id} marked hidden`);
    } catch (err) {
      console.error("❌ Failed to hide message", err);
    }
  };

  const handleDelete = async (msg: SMSMessage) => {
    const source = msg.status === "scheduled" ? "scheduled" : "roadmap";
    try {
      const res = await apiClient.delete(`/review/${msg.id}?source=${source}`);
      console.log(`🗑️ Deleted message ID=${res.data.id} from ${res.data.deleted_from}`);
      setMessages((prev) => prev.filter((m) => m.id !== msg.id));
    } catch (err) {
      console.error("❌ Failed to delete", err);
    }
  };

  const handleSchedule = async (id: number) => {
    try {
      const res = await apiClient.put(`/review/${id}/schedule`);
      const newId = res.data.scheduled_sms_id;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, id: newId, status: "scheduled" } : m
        )
      );
    } catch (err) {
      console.error("❌ Failed to schedule message", err);
    }
  };

  const handleEdit = (msg: SMSMessage) => {
    setEditingId(msg.id);
    setEditedContent(msg.smsContent);
    setEditedTime(msg.send_datetime_utc);
  };

  const handleSave = async (id: number) => {
    try {
      const localDate = new Date(editedTime);
      const utcDate = zonedTimeToUtc(localDate, "America/Denver").toISOString();

      const msg = messages.find((m) => m.id === id);
      const source = msg?.status === "scheduled" ? "scheduled" : "roadmap";

      await apiClient.put(`/review/update-time/${id}?source=${source}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDate,
      });

      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, smsContent: editedContent, send_datetime_utc: utcDate } : m
        )
      );
      setEditingId(null);
    } catch (err) {
      console.error("❌ Failed to save message", err);
    }
  };

  const handleCancel = () => {
    setEditingId(null);
    setEditedContent("");
    setEditedTime("");
  };

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-10 flex justify-center">
      <div className="w-full max-w-5xl">
      <h1 className="text-3xl font-bold mb-2">📤 Engagement Plans</h1>
      <p className="text-neutral mb-6">Grouped SMS plans across all customers</p>

      {loading && <p className="text-gray-400">Loading...</p>}

      {!loading && messages.length === 0 && (
        <p className="text-neutral">No engagement messages yet.</p>
      )}

      {Object.entries(grouped).map(([timeframe, msgs]) => {
        const gradientClass =
          timeframe === "This Week"
            ? "from-purple-600 to-pink-500"
            : timeframe === "Next Week"
            ? "from-blue-600 to-cyan-500"
            : "from-gray-600 to-slate-400";

        return (
          <div key={timeframe} className="mb-10">
            <h2 className="text-xl font-semibold mb-4">{timeframe}</h2>
            <div className="relative border-l-4 border-purple-500 ml-8 mt-12">
              <div className="space-y-4">
                {msgs.filter(msg => !hiddenIds.has(msg.id)).map((msg) => {
                  const dateObj = parseISO(msg.send_datetime_utc);
                  const month = format(dateObj, "LLL").toUpperCase();
                  const day = format(dateObj, "d");

                  return (
                    <div key={msg.id} className="relative mb-12 pl-10">
                      <div className={`absolute -left-8 top-4 w-14 h-14 rounded-full bg-gradient-to-br ${gradientClass} flex flex-col items-center justify-center text-white font-bold text-xs shadow-md`}>
                        <span>{month}</span>
                        <span className="text-lg">{day}</span>
                      </div>
                      <div
                        className={clsx(
                          "ml-4 border rounded-lg shadow-md p-4 w-[90%] max-w-2xl",
                          msg.status === "scheduled"
                            ? "bg-gradient-to-br from-green-900/30 to-green-700/20 border-green-600/40"
                            : msg.status === "sent"
                            ? "bg-gradient-to-br from-blue-900/30 to-blue-600/20 border-blue-500/40"
                            : "bg-zinc-900 border-zinc-700"
                        )}
                      >
                        <div className="flex justify-between items-center mb-1">
                          <p className="text-sm text-white font-semibold">
                            {format(parseISO(msg.send_datetime_utc), "eeee, h:mm a")}
                          </p>
                          <span className={clsx(
                            "text-xs font-semibold uppercase px-2 py-1 rounded-md shadow-sm",
                            msg.status === "scheduled"
                              ? "text-white bg-green-600"
                              : "text-yellow-200 bg-yellow-600/20"
                          )}>
                            {msg.status.replace("_", " ")}
                          </span>
                        </div>
                        {editingId === msg.id ? (
                          <>
                            <textarea
                              value={editedContent}
                              onChange={(e) => setEditedContent(e.target.value)}
                              className="w-full p-2 text-sm text-white bg-zinc-800 border border-zinc-600 rounded mb-2"
                              rows={3}
                            />
                            <input
                              type="datetime-local"
                              value={editedTime}
                              onChange={(e) => setEditedTime(e.target.value)}
                              className="w-full p-2 text-sm text-white bg-zinc-800 border border-zinc-600 rounded mb-4"
                            />
                            <div className="flex justify-end gap-2">
                              <Button size="sm" onClick={handleCancel}>Cancel</Button>
                              <Button className="bg-green-600 hover:bg-green-700 text-white" size="sm" onClick={() => handleSave(msg.id)}>Save</Button>
                            </div>
                          </>
                        ) : (
                          <>
                            <p className="text-white text-base mb-2">{msg.smsContent}</p>
                            <div className="flex justify-between items-center mt-4">
                              <div className="flex items-center gap-2 text-white font-bold text-lg">
                                <span className="text-xl">👤</span>
                                <span>{msg.customer_name}</span>
                                <span className="ml-3 text-sm font-medium">
                                  {msg.latest_consent_status === "opted_in" ? (
                                    <span className="text-green-400">✅ Opted In</span>
                                  ) : msg.latest_consent_status === "opted_out" ? (
                                    <span className="text-red-400">❌ Declined</span>
                                  ) : (
                                    <span className="text-yellow-300">⏳ Waiting</span>
                                  )}
                                </span>
                              </div>
                              <div className="flex gap-2">
                                {msg.status === "sent" ? (
                                  <Button className="bg-gray-600 hover:bg-gray-700 text-white" size="sm" onClick={() => handleHide(msg.id)}>Hide</Button>
                                ) : (
                                  <Button className="bg-red-600 hover:bg-red-700 text-white" size="sm" onClick={() => handleDelete(msg)}>Remove</Button>
                                )}
                                {msg.status !== "sent" && (
                                  <Button className="bg-blue-600 hover:bg-blue-700 text-white" size="sm" onClick={() => handleEdit(msg)}>Edit</Button>
                                )}
                                {msg.status === "pending_review" && (
                                  <Button
                                    size="sm"
                                    disabled={msg.latest_consent_status === "opted_out"}
                                    onClick={() => handleSchedule(msg.id)}
                                    className={`text-white ${
                                      msg.latest_consent_status === "opted_out"
                                        ? "bg-gray-600 cursor-not-allowed"
                                        : "bg-green-600 hover:bg-green-700"
                                    }`}
                                  >
                                    Schedule
                                  </Button>
                                )}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
      {!loading && Object.values(grouped).every(arr => arr.length === 0) && (
        <p className="text-neutral">No messages to display in any timeframe.</p>
      )}
      </div>
    </div>
  );
}