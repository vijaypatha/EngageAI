"use client";

import React from "react"; // Import React
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
  response?: string;
  timestamp?: string;
  lifecycle_stage?: string;
  pain_points?: string;
  interaction_history?: string;
  status?: string;
}

export default function RepliesPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [replies, setReplies] = useState<CustomerReply[]>([]);
  const [editedReplies, setEditedReplies] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null); // For Clear Draft button
  const [dismissingId, setDismissingId] = useState<number | null>(null); // For Dismiss button
  const [sentIds, setSentIds] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 🔄 Load business ID and pending customer replies
  useEffect(() => {
    const fetchData = async () => {
      if (!business_name) {
        setIsLoading(false);
        setError("Business name not found in URL.");
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const bizRes = await apiClient.get(
          `/business-profile/business-id/slug/${business_name}`
        );
        const id = bizRes.data.business_id;
        setBusinessId(id);

        if (id) {
          const replyRes = await apiClient.get(
            `/review/customer-replies?business_id=${id}`
          );
          const actionableReplies = (replyRes.data ?? []).filter(
            (reply: CustomerReply) =>
              reply.response && reply.status === "pending_review"
          );
          setReplies(actionableReplies);
        } else {
          setError("Could not fetch business ID.");
          setReplies([]);
        }
      } catch (err: any) {
        console.error("❌ Failed to load replies or business ID", err);
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
    if (typeof replyId !== "number" || !Number.isInteger(replyId)) {
      console.error("Cannot send reply: Invalid reply identifier.", replyId);
      setError("Cannot send reply: Invalid reply identifier.");
      return;
    }
    try {
      const currentReply = replies.find((r) => r.id === replyId);
      if (!currentReply) {
        console.error("❌ Reply not found in state for ID:", replyId);
        setError("Could not send reply: Reply data missing.");
        return;
      }

      const contentToSend =
        editedReplies[replyId]?.trim() ||
        currentReply.ai_response?.trim() ||
        "";

      if (!contentToSend) {
        console.warn("⚠️ Attempted to send empty reply for ID:", replyId);
        setError("Cannot send an empty reply.");
        return;
      }

      await apiClient.put(`/engagement-workflow/reply/${replyId}/send`, {
        updated_content: contentToSend,
      });

      setSentIds((prev) => [...prev, replyId]);

      setTimeout(() => {
        setReplies((prev) => prev.filter((r) => r.id !== replyId));
        setSentIds((prev) => prev.filter((id) => id !== replyId));
      }, 800);
    } catch (err) {
      console.error("❌ Failed to send reply for:", replyId, err);
      setError("Failed to send reply. Please try again.");
    }
  };

  // 🗑️ Delete AI Draft
  const handleDeleteDraft = async (replyIdToDelete: number) => {
    if (
      typeof replyIdToDelete !== "number" ||
      !Number.isInteger(replyIdToDelete)
    ) {
      console.error("Delete Draft: Invalid reply ID.", replyIdToDelete);
      setError("Cannot delete draft due to an invalid reply ID.");
      return;
    }

    setDeletingId(replyIdToDelete);

    try {
      await apiClient.delete(`/engagement-workflow/${replyIdToDelete}`);

      setReplies((prevReplies) =>
        prevReplies.map((r) =>
          r.id === replyIdToDelete ? { ...r, ai_response: undefined } : r
        )
      );
      setEditedReplies((prevEdited) => {
        const newEdited = { ...prevEdited };
        if (newEdited[replyIdToDelete] !== undefined) {
          delete newEdited[replyIdToDelete];
        }
        return newEdited;
      });

      if (editingId === replyIdToDelete) {
        setEditingId(null);
      }
    } catch (err: any) {
      console.error("❌ Failed to delete AI draft:", err);
      setError(
        err.response?.data?.detail ||
          "Failed to delete draft. Please try again."
      );
    } finally {
      setDeletingId(null);
    }
  };

  // 👋 Dismiss Engagement from Replies List
  const handleDismissEngagement = async (engagementIdToDismiss: number) => {
    if (
      typeof engagementIdToDismiss !== "number" ||
      !Number.isInteger(engagementIdToDismiss)
    ) {
      console.error(
        "Dismiss Engagement: Invalid engagement ID.",
        engagementIdToDismiss
      );
      setError("Cannot dismiss: Invalid identifier.");
      return;
    }

    setDismissingId(engagementIdToDismiss);

    try {
      await apiClient.put(
        `/engagement-workflow/${engagementIdToDismiss}/status`,
        {
          status: "dismissed", // Or "actioned", "closed_manually" as per backend
        }
      );

      setReplies((prevReplies) =>
        prevReplies.filter((r) => r.id !== engagementIdToDismiss)
      );

      if (editingId === engagementIdToDismiss) {
        setEditingId(null);
      }
      if (editedReplies[engagementIdToDismiss] !== undefined) {
        setEditedReplies((prev) => {
          const newState = { ...prev };
          delete newState[engagementIdToDismiss];
          return newState;
        });
      }
    } catch (err: any) {
      console.error("❌ Failed to dismiss engagement:", err);
      setError(
        err.response?.data?.detail ||
          "Failed to dismiss item. Please try again."
      );
    } finally {
      setDismissingId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12 text-center">
        Loading replies...
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12 text-center text-red-400">
        Error: {error}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12">
      <h1 className="text-4xl font-bold mb-2">🧠 Customers Awaiting Reply</h1>
      <p className="text-gray-400 mb-6">
        {replies.length === 0
          ? "No customers waiting on your reply right now."
          : `${replies.length} customer${
              replies.length > 1 ? "s" : ""
            } replied. Let's help you respond.`}
      </p>

      <div className="space-y-6">
        {replies.map((reply) => {
          if (typeof reply.id !== "number" || !Number.isInteger(reply.id)) {
            console.error(
              "Skipping rendering a reply due to invalid ID:",
              reply
            );
            return null;
          }
          return (
            <React.Fragment key={reply.id}>
              <div
                className={`bg-zinc-900 border border-zinc-700 rounded-xl p-6 transition-all duration-500 ease-out ${
                  sentIds.includes(reply.id)
                    ? "opacity-0 scale-95"
                    : "opacity-100"
                }`}
              >
                {sentIds.includes(reply.id) && (
                  <div className="text-center text-3xl mb-4 animate-bounce">
                    🎉 Sent!
                  </div>
                )}
                <h2 className="text-xl font-semibold text-white">
                  👤 {reply.customer_name}
                </h2>
                {reply.lifecycle_stage && (
                  <p className="text-sm text-zinc-400 ml-6 mt-1">
                    {reply.lifecycle_stage}
                  </p>
                )}
                <p className="text-sm text-zinc-400">
                  🧠 Notes:{" "}
                  {reply.pain_points ?? reply.interaction_history ?? "N/A"}
                </p>

                <p className="mt-6 text-sm text-blue-400 font-semibold uppercase tracking-wide">
                  🕒 Last Message Received
                </p>
                {reply.response ? (
                  <p className="text-sm text-zinc-300 mt-1">
                    "{reply.response}"
                  </p>
                ) : (
                  <p className="text-sm text-zinc-500 italic mt-1">
                    No customer message available for this entry.
                  </p>
                )}
                {reply.timestamp && (
                  <p className="text-xs text-zinc-500 mt-1">
                    Received{" "}
                    {formatDistanceToNow(new Date(reply.timestamp), {
                      addSuffix: true,
                    })}
                  </p>
                )}

                <p className="mt-5 text-sm text-zinc-300 font-medium">
                  🤖 AI Suggested Reply / Your Draft:
                </p>
                {editingId === reply.id ? (
                  <textarea
                    className="w-full mt-1 p-3 rounded-md bg-zinc-800 border border-zinc-600 text-white focus:ring-emerald-500 focus:border-emerald-500"
                    rows={4}
                    value={editedReplies[reply.id] ?? reply.ai_response ?? ""}
                    onChange={(e) =>
                      setEditedReplies((prev) => ({
                        ...prev,
                        [reply.id]: e.target.value,
                      }))
                    }
                    autoFocus
                  />
                ) : (
                  <p className="text-sm text-white bg-zinc-800 border border-zinc-700 p-3 mt-1 rounded-md whitespace-pre-wrap min-h-[60px]">
                    {reply.ai_response?.trim() ? (
                      reply.ai_response
                    ) : (
                      <span className="text-zinc-400 italic">
                        No AI draft available. Click 'Edit' to compose.
                      </span>
                    )}
                  </p>
                )}

                <div className="mt-4 flex flex-wrap justify-between items-center gap-2">
                  {editingId === reply.id ? (
                    <div className="flex items-center gap-3">
                      <button
                        className="text-sm text-green-400 hover:text-green-500 px-3 py-1 rounded hover:bg-zinc-700"
                        onClick={async () => {
                          const editedContent =
                            editedReplies[reply.id]?.trim();

                          if (
                            typeof reply.id !== "number" ||
                            !Number.isInteger(reply.id)
                          ) {
                            console.error(
                              "Save Draft: Invalid reply ID.",
                              reply.id
                            );
                            setError(
                              "Cannot save draft due to an invalid reply ID."
                            );
                            return;
                          }

                          if (
                            editedContent &&
                            editedContent !== (reply.ai_response ?? "")
                          ) {
                            try {
                              await apiClient.put(
                                `/engagement-workflow/reply/${reply.id}/edit`,
                                {
                                  ai_response: editedContent,
                                }
                              );
                              setReplies((prev) =>
                                prev.map((r) =>
                                  r.id === reply.id
                                    ? { ...r, ai_response: editedContent }
                                    : r
                                )
                              );
                            } catch (err) {
                              console.error(
                                "❌ Failed to save draft to backend:",
                                err
                              );
                              setError(
                                "Failed to save draft. Please try again."
                              );
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
                          if (
                            typeof reply.id !== "number" ||
                            !Number.isInteger(reply.id)
                          ) {
                            console.error(
                              "Cancel Edit: Invalid reply ID.",
                              reply.id
                            );
                            return;
                          }
                          setEditedReplies((prev) => ({
                            ...prev,
                            [reply.id]: reply.ai_response ?? "",
                          }));
                          setEditingId(null);
                        }}
                      >
                        ❌ Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      {" "}
                      {/* Wrapper for Edit, Clear Draft, and Dismiss */}
                      <button
                        className="text-sm text-yellow-300 hover:text-yellow-400 px-3 py-1 rounded hover:bg-zinc-700"
                        onClick={() => {
                          if (
                            typeof reply.id !== "number" ||
                            !Number.isInteger(reply.id)
                          ) {
                            console.error(
                              "Edit button: Invalid reply ID.",
                              reply.id
                            );
                            setError(
                              "Cannot edit: Invalid reply identifier."
                            );
                            return;
                          }
                          setEditedReplies((prev) => ({
                            ...prev,
                            [reply.id]: reply.ai_response ?? "",
                          }));
                          setEditingId(reply.id);
                        }}
                      >
                        ✏️ Edit
                      </button>
                      <button // Clear Draft Button
                        className="text-sm text-orange-400 hover:text-orange-500 px-3 py-1 rounded hover:bg-zinc-700 disabled:opacity-50"
                        onClick={() => handleDeleteDraft(reply.id)}
                        disabled={
                          deletingId === reply.id || !reply.ai_response
                        }
                      >
                        {deletingId === reply.id
                          ? "Clearing..."
                          : "🗑️ Clear Draft"}
                      </button>
                      <button // Dismiss Button
                        className="text-sm text-gray-400 hover:text-gray-300 px-3 py-1 rounded hover:bg-zinc-700 disabled:opacity-50"
                        onClick={() => handleDismissEngagement(reply.id)}
                        disabled={dismissingId === reply.id}
                        title="Dismiss this item from the reply list"
                      >
                        {dismissingId === reply.id
                          ? "Dismissing..."
                          : "Done"}
                      </button>
                    </div>
                  )}

                  <button
                    className={`px-4 py-2 rounded text-white font-medium transition ${
                      (editingId === reply.id &&
                        (!(editedReplies[reply.id]?.trim()) ||
                          editedReplies[reply.id]?.trim() ===
                            (reply.ai_response ?? ""))) ||
                      (editingId !== reply.id && !reply.ai_response?.trim())
                        ? "bg-blue-400 cursor-not-allowed opacity-60"
                        : "bg-blue-600 hover:bg-blue-700"
                    }`}
                    disabled={
                      (typeof reply.id !== "number" || !Number.isInteger(reply.id)) ||
                      (editingId === reply.id
                        ? !(editedReplies[reply.id]?.trim())
                        : !reply.ai_response?.trim())
                    }
                    onClick={() => {
                      if (
                        typeof reply.id === "number" &&
                        Number.isInteger(reply.id)
                      ) {
                        handleSend(reply.id);
                      } else {
                        console.error(
                          "Send Reply button: Invalid reply ID.",
                          reply.id
                        );
                        setError(
                          "Cannot send reply: Invalid reply identifier."
                        );
                      }
                    }}
                  >
                    ✅ Send Reply
                  </button>
                </div>
              </div>
            </React.Fragment>
          );
        })}
        {replies.length === 0 && !isLoading && (
          <div className="text-center mt-10 text-green-400 text-lg">
            🎉 All caught up! No pending replies.
          </div>
        )}
      </div>
    </div>
  );
}