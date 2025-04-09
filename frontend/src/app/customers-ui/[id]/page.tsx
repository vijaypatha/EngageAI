"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { getCurrentBusiness } from "@/lib/utils"; // ✅ Add this at top


interface SMSItem {
  id: number;
  smsContent: string;
  smsTiming: string;
  status: "pending_review" | "sent" | "scheduled" | "rejected";
  relevance?: string;
  successIndicator?: string;
  send_datetime_utc?: string;
}

function convertToLocalInputFormat(isoString: string) {
  return isoString.slice(0, 16);
}

export default function RoadmapPage() {
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [roadmap, setRoadmap] = useState<SMSItem[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [approveAllDone, setApproveAllDone] = useState(false);
  const [customerName, setCustomerName] = useState("Customer");
  const [loading, setLoading] = useState(true);
  const [generationStatus, setGenerationStatus] = useState<"loading" | "generating" | "done" | "empty">("loading");

  const hasRunRef = useRef(false);

  useEffect(() => {
    if (hasRunRef.current) return;
    hasRunRef.current = true;

    const sessionKey = `roadmap_started_${customerId}`;

    const loadRoadmap = async () => {
      try {
        setLoading(true);
        setGenerationStatus("loading");

        const session = await getCurrentBusiness();
        if (!session?.business_id) {
          throw new Error("Missing business_id from session");
      }
        const businessId = session.business_id;

        const res = await apiClient.get(`/customers/${customerId}`);
        setCustomerName(res.data.customer_name);

        let roadmapRes = await apiClient.get(`/review/engagement-plan/${customerId}`);
        let messages = roadmapRes.data.engagements || [];

        if (messages.length === 0) {
          setGenerationStatus("generating");

          await apiClient.post("/ai_sms/roadmap", {
            customer_id: customerId,
            business_id: Number(businessId),
            force_regenerate: false,
          });

          await new Promise((r) => setTimeout(r, 2000));
          roadmapRes = await apiClient.get(`/review/engagement-plan/${customerId}`);
          messages = roadmapRes.data.engagements || [];
        }

        if (messages.length === 0) {
          setGenerationStatus("empty");
          sessionStorage.removeItem(sessionKey);
        } else {
          setGenerationStatus("done");
          sessionStorage.setItem(sessionKey, "true");
        }

        setRoadmap(messages);
      } catch (err) {
        console.error("Error loading or generating engagement plan", err);
        setGenerationStatus("empty");
        sessionStorage.removeItem(sessionKey);
      } finally {
        setLoading(false);
      }
    };

    sessionStorage.setItem(sessionKey, "true");
    loadRoadmap();
  }, [customerId]);

  const handleUpdate = (index: number, field: keyof SMSItem, value: string) => {
    const updated = [...roadmap];
    updated[index] = { ...updated[index], [field]: value };
    setRoadmap(updated);
  };

  const handleApprove = (id: number) => {
    apiClient.put(`/review/${id}/approve`, {}).then(() => {
      setRoadmap((prev) => prev.map((sms) => sms.id === id ? { ...sms, status: "scheduled" } : sms));
    });
  };

  const handleReject = (id: number) => {
    apiClient.put(`/review/${id}/reject`, {}).then(() => {
      setRoadmap((prev) => prev.map((sms) => sms.id === id ? { ...sms, status: "rejected" } : sms));
    });
  };

  const handleApproveAll = () => {
    apiClient.post(`/review/approve-all/${customerId}`)
      .then(() => {
        setRoadmap((prev) => prev.map((sms) => ({ ...sms, status: "scheduled" })));
        setApproveAllDone(true);
      })
      .catch((err) => console.error("Failed to approve all", err));
  };

  const groupByMonth = (items: SMSItem[]) => {
    const today = new Date();
    const thisMonth = today.getMonth();
    const nextMonth = (thisMonth + 1) % 12;

    const monthMap: { [label: string]: SMSItem[] } = {
      "📅 This Month": [],
      "📆 Next Month": [],
      "🔮 Later": [],
    };

    items.forEach((sms) => {
      if (!sms.send_datetime_utc) return;
      const smsDate = new Date(sms.send_datetime_utc);
      const smsMonth = smsDate.getMonth();

      if (smsMonth === thisMonth) {
        monthMap["📅 This Month"].push(sms);
      } else if (smsMonth === nextMonth) {
        monthMap["📆 Next Month"].push(sms);
      } else {
        monthMap["🔮 Later"].push(sms);
      }
    });

    return monthMap;
  };

  const grouped = groupByMonth(roadmap);

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 p-8 text-white font-sans pb-32">
      <h1 className="text-4xl font-extrabold mb-8 text-white">
        📩 Review Engagement Plan for {customerName}
      </h1>

      {loading ? (
        <p className="text-zinc-400 text-sm">⏳ Loading engagement plan...</p>
      ) : generationStatus === "generating" ? (
        <p className="text-indigo-400 text-sm animate-pulse">🪄 Generating engagement plan with AI...</p>
      ) : generationStatus === "empty" ? (
        <p className="text-rose-400 text-sm">⚠️ No messages were generated. Try regenerating or check customer details.</p>
      ) : null}

      <div className="space-y-10">
        {Object.entries(grouped).map(([label, messages]) => (
          <div key={label}>
            <h2 className="text-2xl font-bold text-indigo-300 mb-4">{label}</h2>
            <div className="space-y-6">
              {messages.map((sms, idx) => {
                const formattedTime = sms.send_datetime_utc
                  ? new Intl.DateTimeFormat("en-US", {
                      weekday: "long",
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    }).format(new Date(sms.send_datetime_utc))
                  : sms.smsTiming;

                return (
                  <div
                    key={`sms-${sms.id}-${idx}`}
                    className={`rounded-xl shadow-md p-6 border border-zinc-700 bg-zinc-800 hover:shadow-xl transition-all ${
                      sms.status === "scheduled" ? "opacity-70" : ""
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-lg font-semibold text-indigo-400">SMS {idx + 1}</h3>
                      {editingIndex === idx ? (
                        <input
                        type="datetime-local"
                        value={convertToLocalInputFormat(sms.send_datetime_utc || new Date().toISOString())}
                        onChange={(e) => handleUpdate(idx, "send_datetime_utc", e.target.value)}
                        className="bg-zinc-900 text-white border border-zinc-600 px-2 py-1 rounded"
                        step="60"
                        min={convertToLocalInputFormat(new Date().toISOString())}  // optional: limit to future
                        />
                      ) : (
                        <p className="text-sm text-zinc-400">{formattedTime}</p>
                      )}
                    </div>

                    <div className="mb-4">
                      <p className="text-sm text-zinc-400 mb-1 font-semibold uppercase">Message</p>
                      {editingIndex === idx ? (
                        <Textarea
                          value={sms.smsContent}
                          onChange={(e) => handleUpdate(idx, "smsContent", e.target.value)}
                          className="text-sm bg-zinc-900 border-zinc-700 text-white"
                        />
                      ) : (
                        <p className="text-base text-zinc-200 whitespace-pre-wrap leading-relaxed">
                          {sms.smsContent}
                        </p>
                      )}

                      {editingIndex !== idx && (
                        <div className="text-sm text-zinc-400 mt-2 space-y-1">
                          {sms.relevance && (
                            <p><span className="font-semibold text-white">📌 Why it matters:</span> {sms.relevance}</p>
                          )}
                          {sms.successIndicator && (
                            <p><span className="font-semibold text-white">🎯 Success signal:</span> {sms.successIndicator}</p>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex justify-between items-center flex-wrap gap-4">
                      <span
                        className={`text-xs font-semibold px-3 py-1 rounded-full ${
                          sms.status === "scheduled"
                            ? "bg-green-800 text-green-300"
                            : sms.status === "pending_review"
                            ? "bg-yellow-800 text-yellow-300"
                            : sms.status === "rejected"
                            ? "bg-red-800 text-red-300"
                            : "bg-zinc-700 text-zinc-300"
                        }`}
                      >
                        {sms.status === "scheduled"
                          ? "✅ Scheduled"
                          : sms.status === "rejected"
                          ? "❌ Rejected"
                          : sms.status === "sent"
                          ? "📤 Sent"
                          : "🕒 Pending"}
                      </span>

                      <div className="flex gap-2">
                        {sms.status !== "scheduled" && (
                          editingIndex === idx ? (
                            <>
                              <Button
                                className="bg-green-600 hover:bg-green-700 text-white text-sm"
                                onClick={() => {
                                  const sms = roadmap[idx];
                                  console.log("🧪 Saving datetime:", sms.send_datetime_utc, "→", sms.send_datetime_utc);
                                  apiClient
                                    .put(`/review/update-time/${sms.id}`, {
                                      send_datetime_utc: sms.send_datetime_utc,
                                    }, {
                                      params: { source: "roadmap" },
                                      headers: { "Content-Type": "application/json" },
                                    })
                                    .then(() => {
                                      console.log("✅ Time updated for SMS", sms.id);
                                      setEditingIndex(null);
                                    })
                                    .catch((err) => {
                                      console.error("❌ Failed to update time", err);
                                    });
                                }}
                              >
                                Save ✅
                              </Button>
                              <Button
                                variant="outline"
                                className="text-sm text-white border-zinc-600"
                                onClick={() => {
                                  const sms = roadmap[idx];
                                  console.log("🧪 Saving datetime:", sms.send_datetime_utc, "→", sms.send_datetime_utc);
                                  apiClient
                                    .put(`/review/update-time/${sms.id}`, {
                                      send_datetime_utc: sms.send_datetime_utc
                                    }, {
                                      params: { source: "roadmap" },
                                      headers: { "Content-Type": "application/json" },
                                    })
                                    .then(() => {
                                      console.log("✅ Time updated for SMS", sms.id);
                                      setEditingIndex(null);
                                    })
                                    .catch((err) => {
                                      console.error("❌ Failed to update time", err);
                                    });
                                }}
                              >
                                Cancel
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition text-sm"
                                onClick={() => handleApprove(sms.id)}
                              >
                                ✅ Schedule
                              </Button>
                              <Button
                                className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm"
                                onClick={() => setEditingIndex(idx)}
                              >
                                ✏️ Edit
                              </Button>
                              <Button
                                variant="outline"
                                className="border-rose-500 text-rose-500 text-sm"
                                onClick={() => handleReject(sms.id)}
                              >
                                ❌ Reject
                              </Button>
                            </>
                          )
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {!approveAllDone && roadmap.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 animate-bounce">
          <Button
            className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition px-8 py-4 text-lg rounded-full shadow-2xl"
            onClick={handleApproveAll}
          >
            ✅ Schedule All
          </Button>
        </div>
      )}
    </div>
  );
}
