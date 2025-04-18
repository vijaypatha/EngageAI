"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { format } from "date-fns";
// @ts-ignore
import { zonedTimeToUtc } from "date-fns-tz";

interface RoadmapMessage {
  id: number;
  smsTiming: string;
  smsContent: string;
  status: string;
  send_datetime_utc?: string;
}

export default function ContactEngagementPage() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState<RoadmapMessage[]>([]);
  const [customerName, setCustomerName] = useState("");
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState<string>("");
  const [editedTime, setEditedTime] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get(`/review/engagement-plan/${id}`);
        const data = res.data.engagements;

        if (data && data.length > 0) {
          setMessages([...data].sort((a, b) => new Date(a.send_datetime_utc || "").getTime() - new Date(b.send_datetime_utc || "").getTime()));
        }
        const custRes = await apiClient.get(`/customers/${id}`);
        setCustomerName(custRes.data.customer_name);
      } catch (err) {
        console.error("Failed to fetch engagement plan", err);
      } finally {
        setLoading(false);
      }
    };

    if (id) load();
  }, [id]);

  const regeneratePlan = async () => {
    setLoading(true);
    try {
      await apiClient.post(`/ai_sms/roadmap`, {
        customer_id: id,
        force_regenerate: true,
      });

      const refreshed = await apiClient.get(`/review/engagement-plan/${id}`);
      setMessages(Array.isArray(refreshed.data.engagements) ? [...refreshed.data.engagements].sort((a, b) => new Date(a.send_datetime_utc || "").getTime() - new Date(b.send_datetime_utc || "").getTime()) : []);
    } catch (err) {
      console.error("Failed to regenerate engagement plan", err);
    } finally {
      setLoading(false);
    }
  };

  const handleEditClick = (msg: RoadmapMessage) => {
    setEditingMessageId(msg.id);
    setEditedContent(msg.smsContent);
    setEditedTime(msg.send_datetime_utc || "");
  };

  const handleSaveEdit = async (msgId: number) => {
    try {
      const localDate = new Date(editedTime);
      const utcDate = zonedTimeToUtc(localDate, "America/Denver").toISOString();

      const msg = messages.find((m) => m.id === msgId);
      const source = msg?.status === "scheduled" ? "scheduled" : "roadmap";

      await apiClient.put(`/review/update-time/${msgId}?source=${source}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDate,
      });

      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, smsContent: editedContent, send_datetime_utc: utcDate } : m
        )
      );
      setEditingMessageId(null);
    } catch (err) {
      console.error("❌ Failed to save edited message time", err);
    }
  };

  const handleCancelEdit = () => {
    setEditingMessageId(null);
  };

  const handleApprove = async (msgId: number) => {
    try {
      const res = await apiClient.put(`/review/${msgId}/schedule`);
      const newId = res.data.scheduled_sms_id;

      setMessages(prev =>
        prev.map(msg =>
          msg.id === msgId ? { ...msg, id: newId, status: "scheduled" } : msg
        )
      );
    } catch (err) {
      console.error("❌ Failed to schedule message", err);
    }
  };

  const handleDelete = async (msgId: number) => {
    try {
      const res = await apiClient.delete(`/review/${msgId}?source=roadmap`);
      console.log(`🗑️ Deleted message ID=${res.data.id} from ${res.data.deleted_from}`);
      setMessages((prev) => prev.filter((msg) => msg.id !== msgId));
    } catch (err) {
      console.error("❌ Failed to delete message", err);
    }
  };

  const sortedMessages = [...messages].sort((a, b) => new Date(a.send_datetime_utc || "").getTime() - new Date(b.send_datetime_utc || "").getTime());

  const grouped = sortedMessages.reduce((acc: Record<string, RoadmapMessage[]>, msg) => {
    const dateObj = msg.send_datetime_utc ? new Date(msg.send_datetime_utc) : null;
    const groupKey = dateObj ? format(dateObj, "MMM yyyy") : "Unknown";
    if (!acc[groupKey]) acc[groupKey] = [];
    acc[groupKey].push(msg);
    return acc;
  }, {});

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6 bg-nudge-gradient text-white min-h-screen">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">📬 Engagement Plan for {customerName}</h1>
        <button
          onClick={regeneratePlan}
          className="bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-semibold py-2 px-4 rounded-lg shadow-md transition duration-300"
        >
          🔄 Regenerate Plan
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center mt-10 space-y-3 animate-pulse">
          <div className="text-4xl">🔮</div>
          <p className="text-lg font-medium text-neutral">Generating personalized engagement plan...</p>
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-neutral italic">No messages planned. Try regenerating the roadmap.</p>
      ) : (
        Object.entries(grouped).map(([month, msgs]) => (
          <div key={month}>
            <h2 className="text-xl font-semibold text-white border-b border-white/20 mb-4 mt-12">{month}</h2>
            <div className="relative border-l-4 border-purple-500 ml-8">
              {msgs.map((msg) => {
                const dateObj = msg.send_datetime_utc ? new Date(msg.send_datetime_utc) : null;
                const weekday = dateObj ? format(dateObj, "EEEE") : "";
                const time = dateObj ? format(dateObj, "h:mm a") : "";

                return (
                  <div key={msg.id} className="relative mb-12 pl-10 mt-12">
                    <div className="absolute -left-6 top-1/2 transform -translate-y-1/2 flex flex-col items-center gap-1">
                      <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-600 to-pink-500 flex flex-col items-center justify-center text-white font-bold text-xs shadow-md">
                        <span>{format(new Date(msg.send_datetime_utc!), "LLL").toUpperCase()}</span>
                        <span className="text-lg">{format(new Date(msg.send_datetime_utc!), "d")}</span>
                      </div>
                      <div className="w-px flex-1 bg-purple-500 mt-2"></div>
                    </div>
                    <div
                      className={`ml-4 rounded-lg shadow-md p-4 border ${
                        msg.status === "scheduled"
                          ? "bg-green-900 border-green-600"
                          : msg.status === "sent"
                          ? "bg-blue-900 border-blue-700"
                          : "bg-zinc-800 border-neutral"
                      }`}
                    >
                      <div className="flex justify-between items-center mb-1">
                        <p className="text-sm text-white font-semibold">
                          {weekday}, {time}
                        </p>
                        <span
                          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-sm tracking-wide ${
                            msg.status === "scheduled"
                              ? "bg-green-600 text-white"
                              : msg.status === "sent"
                              ? "bg-yellow-600 text-white"
                              : "bg-yellow-600 text-white"
                          }`}
                        >
                          {msg.status.replace("_", " ")}
                        </span>
                      </div>
                      {editingMessageId === msg.id ? (
                        <>
                          <textarea
                            value={editedContent}
                            onChange={(e) => setEditedContent(e.target.value)}
                            className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-2"
                            rows={3}
                          />
                          <input
                            type="datetime-local"
                            value={editedTime}
                            onChange={(e) => setEditedTime(e.target.value)}
                            className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-4"
                          />
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={handleCancelEdit}
                              className="text-sm px-3 py-1 bg-gray-500 hover:bg-gray-600 rounded text-white shadow"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleSaveEdit(msg.id)}
                              className="text-sm px-3 py-1 bg-primary hover:bg-primary/80 rounded text-white shadow"
                            >
                              Save
                            </button>
                          </div>
                        </>
                      ) : (
                        <>
                          <p className="text-white text-sm leading-relaxed mb-4">{msg.smsContent}</p>
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => handleDelete(msg.id)}
                              className="text-sm px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-white shadow"
                            >
                              🗑️ Remove
                            </button>
                            <button
                              onClick={() => handleEditClick(msg)}
                              className="text-sm px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-white shadow"
                            >
                              🪄 Edit
                            </button>
                            <button
                              onClick={() => handleApprove(msg.id)}
                              className="text-sm px-3 py-1 bg-primary hover:bg-primary/80 rounded text-white shadow"
                            >
                              Schedule
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}