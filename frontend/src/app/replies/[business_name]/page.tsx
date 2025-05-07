"use client";

import React from "react"; // Import React
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";

// 🧠 Type definitions for incoming customer replies
interface CustomerReply {
  id: number; // This is likely the engagement_id from the backend
  customer_id: number;
  customer_name: string;
  phone: string; // Assuming phone is part of customer details if needed, not directly from /review/customer-replies
  last_message: string; // This might be redundant if `response` is the customer's message
  ai_response?: string; // AI's drafted (or previously sent) reply
  response?: string; // Customer's actual message to the business
  timestamp?: string; // Timestamp of the customer's message
  lifecycle_stage?: string;
  pain_points?: string;
  interaction_history?: string;
  status?: string; // Engagement status, e.g., "pending_review", "sent"
}

export default function RepliesPage() {
  const { business_name } = useParams<{ business_name: string }>(); // Type params
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [replies, setReplies] = useState<CustomerReply[]>([]);
  const [editedReplies, setEditedReplies] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [sentIds, setSentIds] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 🔄 Load business ID and pending customer replies
  useEffect(() => {
    const fetchData = async () => {
      if (!business_name) {
        setIsLoading(false);
        setError("Business name not found in URL.");
        console.error("[DEBUG] Business name not found in URL."); // DEBUG
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        console.log("[DEBUG] 🔄 Fetching business ID for:", business_name);
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data.business_id;
        setBusinessId(id);
        console.log("[DEBUG] Business ID fetched:", id); // DEBUG

        if (id) {
          console.log("[DEBUG] 📥 Fetching customer replies for business_id:", id);
          const replyRes = await apiClient.get(`/review/customer-replies?business_id=${id}`);
          console.log("[DEBUG] Raw API response for customer replies:", replyRes); // DEBUG

          // Filter for replies that are actionable:
          const rawRepliesFromAPI = replyRes.data ?? [];
          console.log("[DEBUG] Raw replies from API (before filter):", JSON.stringify(rawRepliesFromAPI, null, 2)); // DEBUG

          const actionableReplies = rawRepliesFromAPI.filter(
            (reply: CustomerReply) => {
              // DEBUG: Log each reply being considered by the filter
              // console.log("[DEBUG] Filtering reply:", JSON.stringify(reply, null, 2));
              // console.log("[DEBUG] Reply ID during filter:", reply.id, "Type:", typeof reply.id);
              return reply.response && reply.status === "pending_review";
            }
          );

          console.log("[DEBUG] ✅ Loaded actionable replies (after filter, before setReplies):", JSON.stringify(actionableReplies, null, 2)); // DEBUG

          // DEBUG: Sanity check each actionable reply object's ID
          actionableReplies.forEach((r: CustomerReply, index: number) => {
            console.log(`[DEBUG] Actionable Reply ${index} ID:`, r.id, "Type:", typeof r.id, "Full Object:", JSON.stringify(r));
            if (typeof r.id === 'undefined' || r.id === null || !Number.isInteger(r.id)) {
              console.error(`[DEBUG] Problematic actionable reply object found at index ${index}:`, r);
            }
          });

          setReplies(actionableReplies);
        } else {
          setError("Could not fetch business ID.");
          console.error("[DEBUG] Could not fetch business ID."); // DEBUG
          setReplies([]);
        }
      } catch (err: any) {
        console.error("❌ Failed to load replies or business ID (in useEffect catch):", err); // DEBUG: More specific error location
        setError(err.message || "Failed to load data.");
        setReplies([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [business_name]);

  // ✅ Send reply
  const handleSend = async (replyId: number) => {
    // DEBUG: Log entry into handleSend and the ID received
    console.log("[DEBUG] handleSend called with replyId:", replyId, "Type:", typeof replyId);

    if (typeof replyId !== 'number' || !Number.isInteger(replyId)) {
        console.error("[DEBUG] ❌ Invalid replyId in handleSend:", replyId);
        setError("Cannot send reply: Invalid reply identifier.");
        return;
    }

    try {
      const currentReply = replies.find((r) => r.id === replyId);
      if (!currentReply) {
        console.error("❌ Reply not found in state for ID:", replyId);
        return;
      }

      const contentToSend = editedReplies[replyId]?.trim() || currentReply.ai_response?.trim() || "";

      if (!contentToSend) {
        console.warn("⚠️ Attempted to send empty reply for ID:", replyId);
        return;
      }
      
      console.log("📤 Sending reply for engagement_id:", replyId, "Content:", contentToSend);
      await apiClient.put(`/engagement-workflow/reply/${replyId}/send`, { updated_content: contentToSend });
      console.log("✅ Reply sent, will remove from UI shortly:", replyId);
      
      setSentIds((prev) => [...prev, replyId]);

      setTimeout(() => {
        setReplies((prev) => prev.filter((r) => r.id !== replyId));
        setSentIds((prev) => prev.filter((id) => id !== replyId));
      }, 800);
    } catch (err) {
      console.error("❌ Failed to send reply for:", replyId, err);
    }
  };

  if (isLoading) {
    return <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12 text-center">Loading replies...</div>;
  }

  if (error) {
    return <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12 text-center text-red-400">Error: {error}</div>;
  }

  // DEBUG: Log the replies state just before rendering the list
  console.log("[DEBUG] Replies state before rendering list:", JSON.stringify(replies, null, 2));


  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12">
      <h1 className="text-4xl font-bold mb-2">🧠 Customers Awaiting Reply</h1>
      <p className="text-gray-400 mb-6">
        {replies.length === 0
          ? "No customers waiting on your reply right now."
          : `${replies.length} customer${replies.length > 1 ? "s" : ""} replied. Let's help you respond.`}
      </p>

      <div className="space-y-6">
        {replies.map((reply) => {
          // DEBUG: Log each reply object and its ID when mapping for render
          const mapKeyId = reply.id;
          console.log(
            "[DEBUG] Mapping reply for render. Key being used (reply.id):", mapKeyId,
            "Type:", typeof mapKeyId,
            "Is Integer:", Number.isInteger(mapKeyId),
            "Full reply object in map:", JSON.stringify(reply)
          );
          if (typeof mapKeyId !== 'number' || !Number.isInteger(mapKeyId)) {
            console.error("[DEBUG] ❌ Invalid key for React list during map. ID:", mapKeyId, "Object:", reply);
            // You might want to skip rendering this item or render a placeholder
            // return <div key={Math.random()} className="text-red-500 p-4 bg-red-900 rounded-md">Error: Invalid reply data (ID missing)</div>;
          }

          return (
            // Ensure key is valid; if reply.id can be undefined, provide a fallback or filter earlier
            <React.Fragment key={mapKeyId ?? Math.random()}> {/* Using mapKeyId, fallback to random if still an issue */}
              <div
                className={`bg-zinc-900 border border-zinc-700 rounded-xl p-6 transition-all duration-500 ease-out ${
                  sentIds.includes(mapKeyId) ? "opacity-0 scale-95" : "opacity-100" // Use mapKeyId if valid
                }`}
              >
                {sentIds.includes(mapKeyId) && ( // Use mapKeyId if valid
                  <div className="text-center text-3xl mb-4 animate-bounce">🎉 Sent!</div>
                )}
                <h2 className="text-xl font-semibold text-white">👤 {reply.customer_name}</h2>
                {reply.lifecycle_stage && (
                  <p className="text-sm text-zinc-400 ml-6 mt-1">{reply.lifecycle_stage}</p>
                )}
                <p className="text-sm text-zinc-400">🧠 Notes: {reply.pain_points ?? reply.interaction_history ?? "N/A"}</p>

                <p className="mt-6 text-sm text-blue-400 font-semibold uppercase tracking-wide">🕒 Last Message Received</p>
                {reply.response ? (
                  <p className="text-sm text-zinc-300 mt-1">"{reply.response}"</p>
                ) : (
                  <p className="text-sm text-zinc-500 italic mt-1">No customer message available for this entry.</p>
                )}
                {reply.timestamp && (
                  <p className="text-xs text-zinc-500 mt-1">
                    Received {formatDistanceToNow(new Date(reply.timestamp), { addSuffix: true })}
                  </p>
                )}

                <p className="mt-5 text-sm text-zinc-300 font-medium">🤖 AI Suggested Reply / Your Draft:</p>
                {editingId === mapKeyId ? ( // Use mapKeyId if valid
                  <textarea
                    className="w-full mt-1 p-3 rounded-md bg-zinc-800 border border-zinc-600 text-white focus:ring-emerald-500 focus:border-emerald-500"
                    rows={4}
                    value={editedReplies[mapKeyId] ?? reply.ai_response ?? ""} // Use mapKeyId if valid
                    onChange={(e) =>
                      setEditedReplies((prev) => ({ ...prev, [mapKeyId]: e.target.value })) // Use mapKeyId if valid
                    }
                    autoFocus
                  />
                ) : (
                  <p className="text-sm text-white bg-zinc-800 border border-zinc-700 p-3 mt-1 rounded-md whitespace-pre-wrap min-h-[60px]">
                    {reply.ai_response?.trim() ? reply.ai_response : <span className="text-zinc-400 italic">No AI draft available. Click 'Edit' to compose.</span>}
                  </p>
                )}

                <div className="mt-4 flex flex-wrap justify-between items-center gap-2">
                  {editingId === mapKeyId ? ( // Use mapKeyId if valid
                    <div className="flex items-center gap-3">
                      <button
                        className="text-sm text-green-400 hover:text-green-500 px-3 py-1 rounded hover:bg-zinc-700"
                        onClick={async () => {
                          const editedContent = editedReplies[mapKeyId]?.trim(); // Use mapKeyId

                          // DEBUG: Log details inside "Save Draft" onClick
                          const currentReplyIdForSave = mapKeyId; // This is the ID from the map iteration
                          console.log(
                            "[DEBUG] 'Save Draft' clicked. Reply ID from map:", currentReplyIdForSave,
                            "Type:", typeof currentReplyIdForSave,
                            "Is Integer:", Number.isInteger(currentReplyIdForSave),
                            "Content:", editedContent
                          );

                          if (
                            typeof currentReplyIdForSave !== "number" ||
                            !Number.isInteger(currentReplyIdForSave)
                          ) {
                            console.error(
                              "[DEBUG] ❌ Invalid reply ID detected inside 'Save Draft' onClick. Halting API call.",
                              "ID:", currentReplyIdForSave
                            );
                            setError("Failed to save draft: Invalid reply identifier.");
                            return; 
                          }
                          // END OF DEBUG LOGS FOR Save Draft onClick

                          if (editedContent && editedContent !== (reply.ai_response ?? "")) {
                            try {
                              await apiClient.put(`/engagement-workflow/reply/${currentReplyIdForSave}/edit`, {
                                ai_response: editedContent,
                              });
                              setReplies((prev) =>
                                prev.map((r) =>
                                  r.id === currentReplyIdForSave ? { ...r, ai_response: editedContent } : r
                                )
                              );
                              console.log("💾 Draft saved and UI updated for ID:", currentReplyIdForSave);
                            } catch (err) {
                              console.error("❌ Failed to save draft to backend:", err);
                              // setError("Failed to save draft. Please try again."); // Optionally set user-facing error
                            }
                          }
                          setEditingId(null);
                        }}
                      >
                        💾 Save Draft
                      </button>
                      <button
                        className="text-sm text-red-400 hover:text-red-500 px-3 py-1 rounded hover:bg-zinc-700"
                        onClick={() => {
                          setEditedReplies((prev) => ({ ...prev, [mapKeyId]: reply.ai_response ?? "" })); // Use mapKeyId
                          setEditingId(null);
                        }}
                      >
                        ❌ Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      className="text-sm text-yellow-300 hover:text-yellow-400 px-3 py-1 rounded hover:bg-zinc-700"
                      onClick={() => {
                        // DEBUG: Log when starting edit
                        console.log("[DEBUG] 'Edit' clicked. Reply ID:", mapKeyId, "Type:", typeof mapKeyId);
                        if (typeof mapKeyId !== 'number' || !Number.isInteger(mapKeyId)) {
                            console.error("[DEBUG] ❌ Invalid ID when starting edit for reply:", mapKeyId);
                        }
                        setEditedReplies(prev => ({...prev, [mapKeyId]: reply.ai_response ?? ""})); // Use mapKeyId
                        setEditingId(mapKeyId); // Use mapKeyId
                      }}
                    >
                      ✏️ Edit
                    </button>
                  )}
                  
                  <button
                    className={`px-4 py-2 rounded text-white font-medium transition ${
                      (editingId === mapKeyId && (!(editedReplies[mapKeyId]?.trim()) || editedReplies[mapKeyId]?.trim() === (reply.ai_response ?? ""))) ||
                      (editingId !== mapKeyId && !(reply.ai_response?.trim()))
                        ? "bg-blue-400 cursor-not-allowed opacity-60"
                        : "bg-blue-600 hover:bg-blue-700"
                    }`}
                    disabled={
                      editingId === mapKeyId
                        ? !(editedReplies[mapKeyId]?.trim())
                        : !(reply.ai_response?.trim())
                    }
                    onClick={() => handleSend(mapKeyId)} // Pass mapKeyId (which should be reply.id)
                  >
                    ✅ Send Reply
                  </button>
                </div>
              </div>
            </React.Fragment>
          );
        })}
        {replies.length === 0 && !isLoading && (
          <div className="text-center mt-10 text-green-400 text-lg">🎉 All caught up! No pending replies.</div>
        )}
      </div>
    </div>
  );
}