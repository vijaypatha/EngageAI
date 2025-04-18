"use client";
// This page handles the Instant Nudge feature for a specific business, allowing users to send or schedule messages to customers.

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

interface Customer {
  id: number;
  customer_name: string;
}

interface NudgeBlock {
  topic: string;
  message: string;
  customerIds: number[];
  schedule: boolean;
  datetime: string;
  sent?: boolean;
  tempScheduled?: boolean;
  scheduledSmsId?: number;
}

export default function InstantNudgePage() {
  const { business_name } = useParams();
  
  const [nudgeBlocks, setNudgeBlocks] = useState<NudgeBlock[]>([
    { topic: "", message: "", customerIds: [], schedule: false, datetime: "" }
  ]);
  const [contacts, setContacts] = useState<Customer[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);

  useEffect(() => {
    if (!business_name) return;
    // Fetching business ID from slug
    apiClient
      .get(`/business-profile/business-id/slug/${business_name}`)
      .then((res) => {
        console.log("📛 Resolved business_id:", res.data.business_id);
        setBusinessId(res.data.business_id);
      })
      .catch((err) => {
        console.error("❌ Failed to resolve business ID from slug:", err);
      });
  }, [business_name]);

  useEffect(() => {
    if (!businessId) return;
    // Fetching contacts for the business
    apiClient.get(`/customers/by-business/${businessId}`).then(res => {
      console.log("📞 Fetched contacts:", res.data);
      setContacts(res.data);
    }).catch(err => {
      console.error("❌ Failed to fetch contacts:", err);
      setContacts([]);
    });
  }, [businessId]);

  useEffect(() => {
    if (!businessId) return;
    // Load existing scheduled messages into UI blocks on refresh
    apiClient.get(`/nudge/instant-status/slug/${business_name}`)
      .then(res => {
        console.log("📩 Restoring scheduled messages:", res.data);
        const restoredBlocks: NudgeBlock[] = res.data
          .filter((m: any) => !m.is_hidden)
          .map((m: any) => ({
          topic: "", // can't recover original topic
          message: m.message,
          customerIds: [m.customer_id],
          schedule: true,
          datetime: m.send_time,
          sent: m.status === "sent",
          scheduledSmsId: m.id,
          tempScheduled: m.status !== "sent"
        }));
        setNudgeBlocks(prev => [...restoredBlocks, ...prev]);
      })
      .catch(err => {
        console.error("❌ Failed to restore scheduled messages:", err);
      });
  }, [businessId]);

  const pollInstantStatus = async () => {
    // Polling the status of instant nudges
    console.log("🔄 Polling instant status...");
    try {
      const res = await apiClient.get(`/nudge/instant-status/slug/${business_name}`);
      const statusMap = new Map<number, string>();
      res.data.forEach((m: any) => {
        statusMap.set(m.id, m.status);
      });
      setNudgeBlocks(prev =>
        prev.map(block => {
          if (block.scheduledSmsId && statusMap.get(block.scheduledSmsId) === "sent") {
            console.log("✅ Marking block as sent:", block.scheduledSmsId);
            return { ...block, sent: true, tempScheduled: false };
          }
          return block;
        })
      );
    } catch (err) {
      console.error("❌ Failed to poll instant status:", err);
    }
  };

  useEffect(() => {
    // Periodically polling for instant status every 15 seconds
    const fetchMessages = async () => {
      try {
        const { data } = await apiClient.get(`/nudge/instant-status/slug/${business_name}`);
        const statusMap = new Map<number, string>();
        data.forEach((m: any) => {
          statusMap.set(m.id, m.status);
        });
        setNudgeBlocks(prev =>
          prev.map(block =>
            block.scheduledSmsId && statusMap.get(block.scheduledSmsId) === "sent"
              ? { ...block, sent: true, tempScheduled: false }
              : block
          )
        );
      } catch (err) {
        console.error("❌ Failed to fetch instant status:", err);
      }
    };

    const interval = setInterval(() => {
      console.log("🔁 Starting periodic poll");
      fetchMessages();
    }, 15000); // every 15s
    fetchMessages(); // initial fetch
    return () => clearInterval(interval);
  }, [business_name]);

  const handleDraft = async (i: number) => {
    const block = nudgeBlocks[i];
    if (!block.topic || !businessId) return;
    try {
      const res = await apiClient.post("/instant-nudge/generate-message", {
        topic: block.topic,
        business_id: businessId,
        customer_ids: block.customerIds
      });
      const copy = [...nudgeBlocks];
      copy[i].message = res.data.message;
      setNudgeBlocks(copy);
    } catch (err) {
      console.error("❌ Failed to generate draft:", err);
    }
  };

  const handleSendOrSchedule = async (i: number) => {
    const block = nudgeBlocks[i];
    if (!businessId || !block.message || block.customerIds.length === 0) return;
    const payload = [{
      customer_ids: block.customerIds,
      message: block.message,
      send_datetime_utc: block.schedule && block.datetime ? new Date(block.datetime).toISOString() : null
    }];
    console.log("🧪 Schedule:", block.schedule, "Datetime:", block.datetime);
    console.log("📤 Sending payload:", payload);
    try {
      const res = await apiClient.post("/nudge/instant-multi", { messages: payload });
      const scheduledId = res.data.scheduled_sms_ids?.[0]; // assuming one per block
      const copy = [...nudgeBlocks];
      copy[i] = {
        ...copy[i],
        scheduledSmsId: scheduledId,
        tempScheduled: block.schedule ? true : false,
        sent: !block.schedule
      };
      await new Promise(resolve => setTimeout(resolve, 3000)); // ⏱️ wait 3s for backend to store scheduled message
      const statusRes = await apiClient.get(`/nudge/instant-status/slug/${business_name}`);
      if (block.schedule && block.datetime) {
        const scheduledDate = new Date(block.datetime).getTime();
        const now = Date.now();
        const delay = Math.max(0, scheduledDate - now + 30000); // 30s buffer
        console.log(`⏱️ Polling status in ${delay}ms for SMS ID: ${block.scheduledSmsId}`);
        setTimeout(() => {
          pollInstantStatus();
        }, delay);
      }
      setNudgeBlocks(copy);
      setTimeout(() => {
        const container = document.getElementById("add-another");
        container?.scrollIntoView({ behavior: "smooth" });
      }, 300);
    } catch (err) {
      console.error("❌ Failed to send/schedule nudge:", err);
    }
  };

  return (
    <div className="max-w-2xl mx-auto py-10">
      <h1 className="text-3xl font-bold text-center text-white mb-2">Instant Nudge</h1>
      <p className="text-center text-gray-400 mb-6">
        Send instant nudges or plan your nudges based your needs.
      </p>
      <p className="text-center text-white font-medium mb-8">
        {nudgeBlocks.length} messages for {nudgeBlocks.reduce((acc, b) => acc + b.customerIds.length, 0)} customers
      </p>

      {nudgeBlocks.map((block: NudgeBlock, i: number) => (
        <div
          key={i}
          className={`p-4 rounded-xl mb-6 border shadow transition-all duration-300 ${
            block.sent || block.tempScheduled
              ? "bg-green-950 border-green-500 opacity-90"
              : "bg-[#111827] border-gray-700"
          }`}
        >
          <label className="text-sm font-medium text-gray-300 block mb-2">Select customers</label>
          <div className="bg-[#1f2937] rounded p-3 border border-gray-600 mb-4">
            <label className="flex items-center text-white mb-2">
              <input
                type="checkbox"
                checked={block.customerIds.length === contacts.length}
                onChange={() => {
                  const copy = [...nudgeBlocks];
                  copy[i].customerIds = block.customerIds.length === contacts.length ? [] : contacts.map(c => c.id);
                  setNudgeBlocks(copy);
                }}
              />
              <span className="ml-2">Select All</span>
            </label>
            {contacts.map(c => (
              <label key={c.id} className="flex items-center text-white mb-1">
                <input
                  type="checkbox"
                  value={c.id}
                  checked={block.customerIds.includes(c.id)}
                  onChange={() => {
                    const copy = [...nudgeBlocks];
                    const ids = new Set(copy[i].customerIds);
                    ids.has(c.id) ? ids.delete(c.id) : ids.add(c.id);
                    copy[i].customerIds = Array.from(ids);
                    setNudgeBlocks(copy);
                  }}
                />
                <span className="ml-2">{c.customer_name}</span>
              </label>
            ))}
          </div>

          <label htmlFor={`topic-input-${i}`} className="text-sm font-medium text-gray-300 block mb-1">Topic</label>
          <Input
            id={`topic-input-${i}`}
            placeholder="e.g., Follow up after meeting, Special offer"
            className="mb-2 bg-[#1f2937] border-gray-600 text-white"
            value={block.topic}
            onChange={e => {
              const copy = [...nudgeBlocks];
              copy[i].topic = e.target.value;
              setNudgeBlocks(copy);
            }}
            disabled={block.sent || block.tempScheduled}
          />

          <Button
            variant="ghost"
            className="mb-3 text-white bg-gradient-to-r from-green-400 to-blue-500 hover:from-green-500 hover:to-blue-600"
            onClick={() => handleDraft(i)}
            disabled={!block.topic || block.customerIds.length === 0 || block.sent || block.tempScheduled}
          >
            ✍️ Draft with AI
          </Button>

          <label htmlFor={`message-textarea-${i}`} className="text-sm font-medium text-gray-300 block mb-1">Message</label>
          <Textarea
            id={`message-textarea-${i}`}
            placeholder="Use {Customer name} to personalize."
            className="mb-3 bg-[#1f2937] border-gray-600 text-white min-h-[100px]"
            value={block.message}
            onChange={e => {
              const copy = [...nudgeBlocks];
              copy[i].message = e.target.value;
              setNudgeBlocks(copy);
            }}
            disabled={block.sent || block.tempScheduled}
          />

          <div className="flex flex-wrap items-center gap-4 mt-3">
            <label className="text-white flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name={`schedule-option-${i}`}
                className="accent-blue-500"
                checked={!block.schedule}
                onChange={() => {
                  const copy = [...nudgeBlocks];
                  copy[i].schedule = false;
                  setNudgeBlocks(copy);
                }}
                disabled={block.sent || block.tempScheduled}
              /> Send Now
            </label>
            <label className="text-white flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name={`schedule-option-${i}`}
                className="accent-blue-500"
                checked={block.schedule}
                onChange={() => {
                  const copy = [...nudgeBlocks];
                  copy[i].schedule = true;
                  setNudgeBlocks(copy);
                }}
                disabled={block.sent || block.tempScheduled}
              /> Schedule for Later
            </label>
            {block.schedule && (
              <input
                type="datetime-local"
                className="ml-2 bg-[#1f2937] text-white p-1 rounded border border-gray-600"
                value={block.datetime}
                onChange={e => {
                  const copy = [...nudgeBlocks];
                  copy[i].datetime = e.target.value;
                  setNudgeBlocks(copy);
                }}
                min={new Date().toISOString().slice(0, 16)}
                disabled={block.sent || block.tempScheduled}
              />
            )}

            <Button
              className={`ml-auto ${block.sent
                ? "bg-gradient-to-r from-green-400 to-green-600 text-white cursor-default"
                : "bg-red-600 hover:bg-red-700 text-white"} px-4 py-1 rounded`}
              onClick={() => handleSendOrSchedule(i)}
              disabled={block.sent || !block.message || block.customerIds.length === 0}
            >
              {block.sent ? "✅ Scheduled" : block.schedule ? "Schedule" : "Send"}
            </Button>
          </div>
          {block.tempScheduled && !block.sent && (
            <p className="text-sm text-yellow-400 mt-1">
              ⏳ Scheduled – waiting to send…
            </p>
          )}
          {block.sent && (
            <p className="text-sm text-green-400 mt-1">
              📤 Sent successfully
            </p>
          )}

          {block.schedule && !block.sent && block.datetime && (
            <p className="text-sm text-blue-400 mt-1">
              📅 Scheduled for {new Date(block.datetime).toLocaleString()}
            </p>
          )}

          {(block.sent || block.tempScheduled) && (
            <div className="flex items-center gap-3 mt-2">
              {!block.sent && (
                <>
                  <Button
                    className="bg-yellow-500 hover:bg-yellow-600 text-white"
                    onClick={() => {
                      const copy = [...nudgeBlocks];
                      copy[i].sent = false;
                      copy[i].tempScheduled = false;
                      setNudgeBlocks(copy);
                    }}
                  >
                    ✏️ Edit
                  </Button>
                  <Button
                    className="bg-gray-700 hover:bg-gray-800 text-white"
                    onClick={() => {
                      const copy = [...nudgeBlocks];
                      copy.splice(i, 1);
                      setNudgeBlocks(copy);
                    }}
                  >
                    🗑️ Delete
                  </Button>
                </>
              )}
              {block.sent && (
                <Button
                  className="bg-gray-700 hover:bg-gray-800 text-white"
                  onClick={() => {
                    const copy = [...nudgeBlocks];
                    copy.splice(i, 1); // You may replace this with a `hidden` flag in future
                    setNudgeBlocks(copy);
                  }}
                >
                  🙈 Hide
                </Button>
              )}
            </div>
          )}
        </div>
      ))}

      <Button
        id="add-another"
        variant="ghost"
        className="text-white text-lg font-semibold bg-gradient-to-r from-green-400 to-blue-500 hover:from-green-500 hover:to-blue-600 px-6 py-3 rounded animate-pulse"
        onClick={() => setNudgeBlocks([...nudgeBlocks, { topic: "", message: "", customerIds: [], schedule: false, datetime: "" }])}
      >
        💬 Add another message
      </Button>
    </div>
  );
}
