"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";

// 🧠 Type definitions for incoming customer replies
interface CustomerReply {
  id: number;
  customer_id: number;
  customer_name: string;
  phone: string;
  last_message: string;
  ai_response?: string;
  response?: string; // add this line to reflect backend change
  timestamp?: string; // Added timestamp field
  lifecycle_stage?: string; // Added lifecycle stage field
  pain_points?: string; // Added pain points field
  interaction_history?: string; // Added interaction history field
}

export default function RepliesPage() {
  const { business_name } = useParams();
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [replies, setReplies] = useState<CustomerReply[]>([]);
  const [editedReplies, setEditedReplies] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [sentIds, setSentIds] = useState<number[]>([]); // Step 1: Add sentIds state

  // 🔄 Load business ID and pending customer replies
  useEffect(() => {
    const fetchData = async () => {
      try {
        console.log("🔄 Fetching business ID for:", business_name);
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data.business_id;
        setBusinessId(id);

        console.log("📥 Fetching customer replies for business_id:", id);
        const replyRes = await apiClient.get(`/review/customer-replies?business_id=${id}`);
        setReplies(replyRes.data ?? []);
        console.log("✅ Loaded replies:", replyRes.data);
      } catch (err) {
        console.error("❌ Failed to load replies or business ID", err);
      }
    };

    if (business_name) fetchData();
  }, [business_name]);

  // ✅ Send reply manually
  const handleSend = async (id: number) => {
    try {
      const content = editedReplies[id]?.trim() || replies.find((r) => r.id === id)?.ai_response || "";
      console.log("📤 Sending reply for engagement_id:", id, "Content:", content);
      await apiClient.put(`/engagement/reply/${id}/send`, { content });
      console.log("✅ Reply sent, will remove from UI shortly:", id);
      
      setSentIds((prev) => [...prev, id]); // Step 2: Add sentIds

      // 🧹 Remove from list after sending with a delay
      setTimeout(() => {
        setReplies((prev) => prev.filter((r) => r.id !== id));
      }, 800);
    } catch (err) {
      console.error("❌ Failed to send reply for:", id, err);
    }
  };

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12">
      <h1 className="text-4xl font-bold mb-2">🧠 Customers Awaiting Reply</h1>
      <p className="text-gray-400 mb-6">
        {Array.isArray(replies)
          ? replies.length === 0
            ? "No customers waiting on your reply right now."
            : `${replies.length} customer${replies.length > 1 ? "s" : ""} replied. Let’s help you respond.`
          : "⚠️ Unable to load replies."}
      </p>

      <div className="space-y-6">
        {Array.isArray(replies) && replies.length > 0 && replies.map((reply) => (
          <div
            key={reply.id}
            className={`bg-zinc-900 border border-zinc-700 rounded-xl p-6 transition-all duration-500 ease-out ${
              sentIds.includes(reply.id) ? "opacity-0 scale-95" : "opacity-100"
            }`}
          >
            {sentIds.includes(reply.id) && (
              <div className="text-center text-3xl mb-4 animate-bounce">🎉 Sent!</div>
            )}
            {/* 👤 Name + Stage */}
            <h2 className="text-xl font-semibold text-white">👤 {reply.customer_name}</h2>
            {reply.lifecycle_stage && (
              <p className="text-sm text-zinc-400 ml-6 mt-1">{reply.lifecycle_stage}</p>
            )}
            <p className="text-sm text-zinc-400">📱 {reply.phone}</p>
            <p className="text-sm text-zinc-400">🧠 Notes: {reply.pain_points ?? reply.interaction_history}</p>

            {/* 🕒 Last Message */}
            <p className="mt-6 text-sm text-blue-400 font-semibold uppercase tracking-wide">🕒 Last Message Received</p>
            {reply.response ? (
              <p className="text-sm text-zinc-300 mt-1">"{reply.response}"</p>
            ) : (
              <p className="text-sm text-zinc-500 italic mt-1">No message available.</p>
            )}
            {reply.timestamp && (
              <p className="text-xs text-zinc-500 mt-1">
                Received {formatDistanceToNow(new Date(reply.timestamp), { addSuffix: true })}
              </p>
            )}

            {/* 🤖 AI Reply */}
            <p className="mt-5 text-sm text-zinc-300 font-medium">🤖 AI Suggested Reply:</p>
            {editingId === reply.id ? (
              <textarea
                className="w-full mt-1 p-3 rounded-md bg-zinc-800 border border-zinc-600 text-white"
                rows={4}
                value={editedReplies[reply.id] ?? reply.ai_response ?? ""}
                onChange={(e) =>
                  setEditedReplies((prev) => ({ ...prev, [reply.id]: e.target.value }))
                }
              />
            ) : (
              <p className="text-sm text-white bg-zinc-800 border border-zinc-700 p-3 mt-1 rounded-md whitespace-pre-wrap">
                {reply.ai_response ?? "No AI draft available."}
              </p>
            )}

            {/* ✅ Buttons */}
            <div className="mt-4 flex justify-between items-center">
              {editingId === reply.id ? (
                <div className="flex items-center gap-3">
                  <button
                    className="text-sm text-green-400 hover:text-green-500"
                    onClick={async () => {
                      const edited = editedReplies[reply.id]?.trim();
                      if (edited && edited !== reply.ai_response) {
                        try {
                          await apiClient.put(`/engagement/reply/${reply.id}/edit`, {
                            ai_response: edited,
                          });
                          setReplies((prev) =>
                            prev.map((r) =>
                              r.id === reply.id ? { ...r, ai_response: edited } : r
                            )
                          );
                          console.log("💾 Backend saved and UI updated for ID:", reply.id);
                        } catch (err) {
                          console.error("❌ Failed to save to backend:", err);
                        }
                      }
                      setEditingId(null);
                    }}
                  >
                    💾 Save
                  </button>
                  <button
                    className="text-sm text-red-400 hover:text-red-500"
                    onClick={() => {
                      setEditedReplies((prev) => ({ ...prev, [reply.id]: reply.ai_response ?? "" }));
                      setEditingId(null);
                    }}
                  >
                    ❌ Cancel
                  </button>
                </div>
              ) : (
                <button
                  className="text-sm text-yellow-300 hover:text-yellow-400"
                  onClick={() => setEditingId(reply.id)}
                >
                  ✏️ Edit
                </button>
              )}
              
              <button
                className={`px-4 py-2 rounded text-white transition ${
                  editingId === reply.id && (editedReplies[reply.id] ?? "") === (reply.ai_response ?? "")
                    ? "bg-blue-400 cursor-not-allowed opacity-50"
                    : "bg-blue-600 hover:bg-blue-700"
                }`}
                disabled={!editedReplies[reply.id]?.trim()}
                onClick={() => handleSend(reply.id)}
              >
                ✅ Send Reply
              </button>
            </div>
          </div>
        ))}
        {Array.isArray(replies) && replies.length === 0 && (
          <div className="text-center mt-10 text-green-400 text-lg">🎉 All caught up! No pending replies.</div>
        )}
      </div>
    </div>
  );
}