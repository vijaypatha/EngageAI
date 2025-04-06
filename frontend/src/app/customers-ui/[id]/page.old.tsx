// /customers-ui/[id]/page.tsx — Enhanced customer engagement plan with grouping, polish, and per-SMS approval/rejection

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface SMSItem {
  id: number;
  smsContent: string;
  smsTiming: string;
  status: "pending_review" | "sent" | "approved" | "rejected";
}

export default function RoadmapPage() {
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [roadmap, setRoadmap] = useState<SMSItem[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [approveAllDone, setApproveAllDone] = useState(false);
  const [customerName, setCustomerName] = useState("Customer");

  useEffect(() => {
    apiClient.post("/ai_sms/roadmap", { customer_id: customerId })
      .then((res) => setRoadmap(res.data.roadmap))
      .catch((err) => console.error("Failed to fetch roadmap", err));

    apiClient.get(`/customers/${customerId}`)
      .then((res) => setCustomerName(res.data.customer_name));
  }, [customerId]);

  const handleUpdate = (index: number, field: "smsContent" | "smsTiming", value: string) => {
    const updated = [...roadmap];
    updated[index] = { ...updated[index], [field]: value };
    setRoadmap(updated);
  };

  const handleApprove = (id: number) => {
    apiClient.put(`/review/${id}/approve`, {}).then(() => {
      setRoadmap((prev) => prev.map((sms) => sms.id === id ? { ...sms, status: "approved" } : sms));
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
        setRoadmap((prev) => prev.map((sms) => ({ ...sms, status: "approved" })));
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
      const match = sms.smsTiming.match(/Day (\d+)/);
      const day = match ? parseInt(match[1]) : 0;
      const messageDate = new Date();
      messageDate.setDate(today.getDate() + (day - 1));
      const smsMonth = messageDate.getMonth();

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

      <div className="space-y-10">
        {Object.entries(grouped).map(([label, messages]) => (
          <div key={label}>
            <h2 className="text-2xl font-bold text-indigo-300 mb-4">{label}</h2>
            <div className="space-y-6">
              {messages.map((sms, idx) => (
                <div
                  key={`sms-${sms.id}-${idx}`}
                  className={`rounded-xl shadow-md p-6 border border-zinc-700 bg-zinc-800 hover:shadow-xl transition-all ${
                    sms.status === "approved" ? "opacity-70" : ""
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-lg font-semibold text-indigo-400">SMS {idx + 1}</h3>
                    <p className="text-sm text-zinc-400">
                      {editingIndex === idx ? (
                        <input
                          type="text"
                          value={sms.smsTiming}
                          onChange={(e) => handleUpdate(idx, "smsTiming", e.target.value)}
                          className="border rounded px-2 py-1 text-sm w-40 bg-zinc-900 border-zinc-600 text-white"
                        />
                      ) : (
                        sms.smsTiming
                      )}
                    </p>
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
                  </div>

                  <div className="flex justify-between items-center flex-wrap gap-4">
                    <span
                      className={`text-xs font-semibold px-3 py-1 rounded-full ${
                        sms.status === "approved"
                          ? "bg-green-800 text-green-300"
                          : sms.status === "pending_review"
                          ? "bg-yellow-800 text-yellow-300"
                          : sms.status === "rejected"
                          ? "bg-red-800 text-red-300"
                          : "bg-zinc-700 text-zinc-300"
                      }`}
                    >
                      {sms.status === "approved"
                        ? "✅ Approved"
                        : sms.status === "rejected"
                        ? "❌ Rejected"
                        : sms.status === "sent"
                        ? "📤 Sent"
                        : "🕒 Pending"}
                    </span>

                    <div className="flex gap-2">
                      {sms.status !== "approved" && (
                        editingIndex === idx ? (
                          <>
                            <Button
                              className="bg-green-600 hover:bg-green-700 text-white text-sm"
                              onClick={() => setEditingIndex(null)}
                            >
                              Save ✅
                            </Button>
                            <Button
                              variant="outline"
                              className="text-sm text-white border-zinc-600"
                              onClick={() => setEditingIndex(null)}
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
                              ✅ Approve
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
              ))}
            </div>
          </div>
        ))}
      </div>

      {!approveAllDone && (
        <div className="fixed bottom-6 right-6 z-50 animate-bounce">
          <Button
            className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition px-8 py-4 text-lg rounded-full shadow-2xl"
            onClick={handleApproveAll}
          >
            ✅ Approve All
          </Button>
        </div>
      )}
    </div>
  );
}
