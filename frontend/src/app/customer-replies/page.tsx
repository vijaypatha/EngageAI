"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getCurrentBusiness } from "@/lib/utils"; // ✅ NEW


interface Engagement {
  id: number;
  customer_name: string;
  response: string;
  ai_response: string;
  status: "pending_review" | "scheduled" | "rejected" | "sent";
  customer_id: number;
  sent_at?: string;
  isEditing?: boolean;
  editedResponse?: string;
}

export default function CustomerRepliesPage() {
  const [replies, setReplies] = useState<Engagement[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectAll, setSelectAll] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});

  useEffect(() => {
    const loadReplies = async () => {
      const session = await getCurrentBusiness(); // ✅ Secure cookie-based session
      if (!session?.business_id) return;
  
      try {
        const res = await apiClient.get("/review/customer-replies", {
          params: { business_id: session.business_id },
        });
  
        setReplies(res.data);
  
        const initialCollapse: Record<number, boolean> = {};
        res.data.forEach((reply: Engagement) => {
          if (!initialCollapse.hasOwnProperty(reply.customer_id)) {
            initialCollapse[reply.customer_id] = true;
          }
        });
        setCollapsed(initialCollapse);
      } catch (err) {
        console.error("❌ Failed to load replies:", err);
      }
    };
  
    loadReplies(); // ✅ Call once on mount
  }, []);
  

  const groupedReplies = replies.reduce((acc, reply) => {
    if (!acc[reply.customer_id]) {
      acc[reply.customer_id] = {
        customer_name: reply.customer_name || `Customer ${reply.customer_id}`,
        messages: []
      };
    }
    acc[reply.customer_id].messages.push(reply);
    return acc;
  }, {} as Record<number, { customer_name: string; messages: Engagement[] }>);

  const toggleCollapse = (customerId: number) => {
    setCollapsed((prev) => ({ ...prev, [customerId]: !prev[customerId] }));
  };

  const handleApprove = (id: number) => {
    const engagement = replies.find((r) => r.id === id);
    if (!engagement || engagement.status === "sent") return;

    apiClient.put(`/engagement/reply/${id}/send`).then(() => {
      setReplies((prev) =>
        prev.map((r) =>
          r.id === id
            ? { ...r, status: "sent", sent_at: new Date().toISOString() }
            : r
        )
      );
      setSelectedIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    });
  };

  const handleSendSelected = () => {
    const ids = Array.from(selectedIds);
    const toSend = replies.filter(r => ids.includes(r.id) && r.status !== "sent");

    Promise.all(toSend.map(r =>
      apiClient.put(`/engagement/reply/${r.id}/send`)
    )).then(() => {
      setReplies((prev) =>
        prev.map((r) =>
          ids.includes(r.id) && r.status !== "sent"
            ? { ...r, status: "sent", sent_at: new Date().toISOString() }
            : r
        )
      );
      setSelectedIds(new Set());
      setSelectAll(false);
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectAll) {
      setSelectedIds(new Set());
      setSelectAll(false);
    } else {
      const allPendingIds = replies.filter(r => r.status !== "sent").map(r => r.id);
      setSelectedIds(new Set(allPendingIds));
      setSelectAll(true);
    }
  };

  const handleEdit = (id: number) => {
    setReplies((prev) =>
      prev.map((r) =>
        r.id === id ? { ...r, isEditing: true, editedResponse: r.ai_response } : r
      )
    );
  };

  const handleEditChange = (id: number, value: string) => {
    setReplies((prev) =>
      prev.map((r) => (r.id === id ? { ...r, editedResponse: value } : r))
    );
  };

  const handleSaveEdit = (id: number) => {
    const item = replies.find((r) => r.id === id);
    if (!item || !item.editedResponse) return;

    apiClient
      .put(`/engagement/reply/${id}/edit`, {
        ai_response: item.editedResponse,
      })
      .then(() => {
        setReplies((prev) =>
          prev.map((r) =>
            r.id === id
              ? {
                  ...r,
                  ai_response: item.editedResponse!,
                  isEditing: false,
                  editedResponse: undefined,
                }
              : r
          )
        );
      });
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "";
    const localDate = new Date(iso);
    return `Sent on ${localDate.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })}`;
  };

  const uniqueCustomerCount = new Set(replies.map((r) => r.customer_id)).size;

  return (
    <div className="min-h-screen bg-zinc-950 text-white p-4 sm:p-8 pb-24 relative">
      <div className="flex items-center justify-between mb-4 sm:mb-6">
        <div>
          <h1 className="text-2xl sm:text-4xl font-extrabold">📋 AI Replies for Review</h1>
          <p className="text-zinc-400 mt-2 text-sm max-w-xl">
            Quickly review and manage AI-generated replies to customer messages.
          </p>
          {uniqueCustomerCount > 0 && (
            <p className="text-green-400 font-semibold mt-1 text-sm">
              📣 {uniqueCustomerCount === 1
                ? "1 customer is waiting for your reply."
                : `${uniqueCustomerCount} customers are waiting for your reply.`}
            </p>
          )}
        </div>
        {replies.length > 0 && (
          <div>
            <Button
              variant="outline"
              onClick={toggleSelectAll}
              className="text-sm border-zinc-600 text-black hover:text-black bg-white"
            >
              {selectAll ? "Unselect All" : "Select All"}
            </Button>
          </div>
        )}
      </div>

      {replies.length === 0 ? (
        <p className="text-zinc-500 text-sm">No replies waiting for review.</p>
      ) : (
        <div className="flex flex-col gap-4">
          <ScrollArea className="w-full rounded-xl border border-zinc-700">
            {Object.entries(groupedReplies).map(([customerId, group]) => (
              <div key={customerId} className="border-b border-zinc-700">
                <div
                  className="cursor-pointer bg-zinc-800 px-4 py-3 font-semibold text-white flex justify-between items-center"
                  onClick={() => toggleCollapse(Number(customerId))}
                >
                  <span>
                    {group.customer_name}{" "}
                    <span className="text-green-400">
                      ({group.messages.length} message{group.messages.length > 1 ? "s" : ""})
                    </span>
                  </span>
                  <span>{collapsed[Number(customerId)] ? "▶" : "▼"}</span>
                </div>

                {!collapsed[Number(customerId)] && (
                  <table className="min-w-full table-auto text-sm">
                    <thead className="bg-zinc-900 text-zinc-400 uppercase text-xs">
                      <tr>
                        <th className="px-4 py-3 text-left"></th>
                        <th className="px-4 py-3 text-left">Message</th>
                        <th className="px-4 py-3 text-left">AI Drafted Reply</th>
                        <th className="px-4 py-3 text-left">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.messages.map((item) => (
                        <tr key={item.id} className="border-t border-zinc-700">
                          <td className="px-4 py-4">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(item.id)}
                              onChange={() => toggleSelect(item.id)}
                              disabled={item.status === "sent"}
                            />
                          </td>
                          <td className={`px-4 py-4 max-w-sm whitespace-pre-wrap ${item.status === "sent" ? "text-zinc-400" : "text-zinc-200"}`}>
                            {item.response}
                          </td>
                          <td className={`px-4 py-4 max-w-sm whitespace-pre-wrap ${item.status === "sent" ? "text-zinc-400" : "text-indigo-100"}`}>
                            {item.isEditing ? (
                              <textarea
                                className="w-full bg-zinc-800 text-white p-2 rounded border border-zinc-700"
                                value={item.editedResponse}
                                onChange={(e) => handleEditChange(item.id, e.target.value)}
                              />
                            ) : (
                              <>
                                {item.ai_response}
                                {item.status === "sent" && item.sent_at && (
                                  <p className="text-xs text-zinc-500 mt-1">{formatDate(item.sent_at)}</p>
                                )}
                              </>
                            )}
                          </td>
                          <td className="px-4 py-4 flex gap-2">
                            {item.status === "sent" ? (
                              <Button
                                className="bg-blue-600 text-white cursor-not-allowed"
                                disabled
                              >
                                📤 Sent
                              </Button>
                            ) : item.isEditing ? (
                              <Button
                                className="bg-blue-600 hover:bg-blue-700 text-white"
                                onClick={() => handleSaveEdit(item.id)}
                              >
                                💾 Save
                              </Button>
                            ) : (
                              <>
                                <Button
                                  className="bg-yellow-600 hover:bg-yellow-700 text-white"
                                  onClick={() => handleEdit(item.id)}
                                >
                                  ✏️ Edit
                                </Button>
                                <Button
                                  className="bg-green-600 hover:bg-green-700 text-white"
                                  onClick={() => handleApprove(item.id)}
                                >
                                  ✅ Send
                                </Button>
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </ScrollArea>
        </div>
      )}

      {selectedIds.size > 0 && (
        <div className="fixed bottom-4 right-4 z-50">
          <Button
            className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 text-base rounded-full shadow-xl"
            onClick={handleSendSelected}
          >
            📤 Send Selected ({selectedIds.size})
          </Button>
        </div>
      )}
    </div>
  );
}
