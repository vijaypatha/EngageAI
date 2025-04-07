"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { getCurrentBusiness } from "@/lib/utils"; // ✅ Add at top


interface SMSItem {
  id: number;
  smsContent: string;
  smsTiming: string;
  status: "pending_review" | "sent" | "scheduled" | "rejected";
  customer_name: string;
  send_datetime_utc?: string;
  source: "roadmap" | "scheduled";
}

export default function AllEngagementPlans() {
  const [smsList, setSmsList] = useState<SMSItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
const [editedTime, setEditedTime] = useState<string>("");

    
const fetchSMSList = async () => {
  const session = await getCurrentBusiness();
  if (!session?.business_id) return;

  apiClient
    .get("/review/all-engagements", {
      params: { business_id: session.business_id },
    })
    .then((res) => setSmsList(res.data.engagements))
    .catch(console.error);
};


  useEffect(() => {
    fetchSMSList();
  }, []);

  const groupByMonth = (items: SMSItem[]) => {
    const monthMap: { [label: string]: SMSItem[] } = {
      "📅 This Month": [],
      "📆 Next Month": [],
      "🔮 Later": [],
    };

    const now = new Date();
    const thisMonth = now.getMonth();
    const nextMonth = (thisMonth + 1) % 12;

    items.forEach((sms) => {
      const date = sms.send_datetime_utc ? new Date(sms.send_datetime_utc) : new Date();
      const month = date.getMonth();

      if (month === thisMonth) {
        monthMap["📅 This Month"].push(sms);
      } else if (month === nextMonth) {
        monthMap["📆 Next Month"].push(sms);
      } else {
        monthMap["🔮 Later"].push(sms);
      }
    });

    for (const key in monthMap) {
      monthMap[key].sort((a, b) => {
        const dateA = new Date(a.send_datetime_utc || "");
        const dateB = new Date(b.send_datetime_utc || "");
        return dateA.getTime() - dateB.getTime();
      });
    }

    return monthMap;
  };

  const grouped = groupByMonth(smsList);

  const handleToggleSelect = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleScheduleSelected = () => {
    Promise.all(
      selected.map((id) =>
        apiClient.put(`/review/${id}/approve`, {}).then((res) => res.data.scheduled_sms)
      )
    ).then((newScheduledList) => {
      setSmsList((prev) => {
        const remaining = prev.filter((sms) => !selected.includes(sms.id));
        return [...remaining, ...newScheduledList];
      });
      setSelected([]);
    });
  };

  const handleRejectSelected = () => {
    Promise.all(
      selected.map((id) => {
        const sms = smsList.find((s) => s.id === id);
        if (!sms || sms.source !== "roadmap") return;
        return apiClient.put(`/review/${id}/reject`);
      })
    ).then(() => {
      setSmsList((prev) =>
        prev.map((sms) =>
          selected.includes(sms.id) && sms.source === "roadmap"
            ? { ...sms, status: "rejected" }
            : sms
        )
      );
      setSelected([]);
    });
  };

  const handleDeleteSelected = () => {
    Promise.all(
      selected.map((id) => {
        const sms = smsList.find((s) => s.id === id);
        if (!sms) {
          console.warn(`⚠️ SMS ID ${id} not found in local list`);
          return;
        }

        const source = sms.source?.toLowerCase() || "roadmap";

        return apiClient.delete(`/review/${sms.id}`, {
          params: { source },
        });
      })
    )
      .then(() => {
        setSmsList((prev) => prev.filter((sms) => !selected.includes(sms.id)));
        setSelected([]);
      })
      .catch((error) => {
        console.error("❌ Error deleting selected messages", error);
      });
  };

  const handleSelectAll = () => {
    const allIds = smsList.map((sms) => sms.id);
    setSelected(allIds);
  };

  const handleUpdateTime = (id: number, value: string) => {
    const source = smsList.find((s) => s.id === id)?.source || "roadmap";

    apiClient
      .put(
        `/review/update-time/${id}`,
        { send_datetime_utc: new Date(value).toISOString() },
        { params: { source } }
      )
      .then(() => {
        toast.success("Time updated successfully");
        fetchSMSList();
      })
      .catch((err) => {
        toast.error("Failed to update time");
        console.error("❌ Update failed", err);
      });
  };

  const renderStatus = (status: SMSItem["status"]) => {
    const base = "text-xs font-semibold px-3 py-1 rounded-full";
    switch (status) {
      case "scheduled":
        return <span className={`${base} bg-green-700 text-white`}>📆 Scheduled</span>;
      case "sent":
        return <span className={`${base} bg-blue-700 text-white`}>📤 Sent</span>;
      case "rejected":
        return <span className={`${base} bg-red-700 text-white`}>❌ Rejected</span>;
      default:
        return <span className={`${base} bg-yellow-700 text-white`}>🕒 Pending</span>;
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 p-8 text-white pb-40">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-4xl font-bold">📬 All Engagement Plans</h1>
        <Button variant="secondary" onClick={handleSelectAll}>
          Select All
        </Button>
      </div>

      {Object.entries(grouped).map(([label, group]) => (
        <div key={label} className="mb-12">
          <h2 className="text-2xl font-bold mb-4">{label}</h2>
          <div className="space-y-4">
            {group.map((sms) => (
              <div
                key={sms.id}
                className="rounded-xl p-4 border border-zinc-700 bg-zinc-800 shadow-md"
              >
                <div className="flex justify-between items-center mb-2">
                  <div>
                    <p className="text-xl font-bold text-zinc-100">👤 {sms.customer_name}</p>
                    {editingId === sms.id ? (
                      <div className="flex items-center gap-2">
                        <Input
                          type="datetime-local"
                          value={editedTime}
                          className="text-sm bg-zinc-900 border-zinc-600 text-white"
                          onChange={(e) => setEditedTime(e.target.value)}
                        />
                        <Button
                          className="bg-green-600 px-4 py-1 text-sm"
                          onClick={() => {
                            handleUpdateTime(sms.id, editedTime);
                            setEditingId(null);
                          }}
                        >
                          Save ✅
                        </Button>
                        <Button
                          className="bg-zinc-700 px-3 py-1 text-sm"
                          onClick={() => {
                            setEditingId(null);
                            setEditedTime("");
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <h2
                        className="text-sm font-semibold text-indigo-300 cursor-pointer"
                        onClick={() => {
                          setEditingId(sms.id);
                          setEditedTime(
                            new Date(sms.send_datetime_utc || "").toISOString().slice(0, 16)
                          );
                        }}
                      >
                        {sms.send_datetime_utc
                          ? new Date(sms.send_datetime_utc).toLocaleString("en-US", {
                              timeZone: "America/Denver",
                              weekday: "long",
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            }) + " MDT"
                          : sms.smsTiming}
                      </h2>
                    )}
                  </div>
                  <input
                    type="checkbox"
                    checked={selected.includes(sms.id)}
                    onChange={() => handleToggleSelect(sms.id)}
                  />
                </div>
                <p className="text-white text-base whitespace-pre-wrap mb-3">
                  {sms.smsContent}
                </p>
                {renderStatus(sms.status)}
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="fixed bottom-0 left-0 w-full bg-zinc-900 border-t border-zinc-700 px-6 py-4 flex justify-between items-center z-50">
        <div className="flex gap-3">
          <Button
            variant="secondary"
            className="px-5 py-2 rounded-lg"
            disabled={!selected.length}
            onClick={() => {
              const toEdit = smsList.filter((sms) => selected.includes(sms.id));
              if (!toEdit.length) return;
              const firstTime = toEdit[0].send_datetime_utc || new Date().toISOString();
              const input = prompt("🛠 Enter new time (local):", new Date(firstTime).toISOString().slice(0, 16));
              if (!input) return;

              const utcTime = new Date(input).toISOString();

              Promise.all(toEdit.map((sms) =>
                apiClient.put(`/review/update-time/${sms.id}`, {
                  send_datetime_utc: utcTime,
                }, {
                  params: { source: sms.source || "roadmap" },
                  headers: { "Content-Type": "application/json" },
                })
              )).then(() => {
                toast.success("⏰ Bulk time updated");
                fetchSMSList();
              }).catch(err => {
                console.error("❌ Bulk update error", err);
                toast.error("Bulk update failed");
              });
            }}
          >
            ✏️ Edit Selected (Time)
          </Button>

          <Button
            variant="destructive"
            className="px-5 py-2 rounded-lg"
            disabled={!selected.length}
            onClick={handleDeleteSelected}
          >
            🗑️ Delete Selected
          </Button>
        </div>
        <div className="flex gap-3">
          

          <p className="text-sm text-zinc-400">{selected.length} selected</p>
          <Button
            className="bg-green-600 px-5 py-2 rounded-lg"
            disabled={!selected.length}
            onClick={handleScheduleSelected}
          >
            📆 Schedule Selected
          </Button>
          <Button
            variant="destructive"
            className="px-5 py-2 rounded-lg"
            disabled={!selected.length}
            onClick={handleRejectSelected}
          >
            ❌ Reject Selected
          </Button>
        </div>
      </div>
    </div>
  );
}
