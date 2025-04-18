 "use client";
import { useEffect, useState } from "react";
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
}

export default function InstantNudgePage() {
  const { business_name } = useParams();
  console.log("📛 Loaded Instant Nudge for business:", business_name);

  const [nudgeBlocks, setNudgeBlocks] = useState<NudgeBlock[]>([
    { topic: "", message: "", customerIds: [], schedule: false, datetime: "" }
  ]);
  const [contacts, setContacts] = useState<Customer[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);

  useEffect(() => {
    if (!business_name) return;
    apiClient
      .get(`/business/resolve-id/${business_name}`)
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
    apiClient.get(`/customers/by-business/${businessId}`).then(res => {
      setContacts(res.data);
    }).catch(err => {
      console.error("Failed to fetch contacts:", err);
      setContacts([]);
    });
  }, [businessId]);

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
      console.error("Failed to generate draft:", err);
    }
  };

  const handleSend = async () => {
    const payload = nudgeBlocks.map(b => ({
      customer_ids: b.customerIds,
      message: b.message,
      send_datetime_utc: b.schedule && b.datetime ? new Date(b.datetime).toISOString() : null
    }));
    try {
      await apiClient.post("/nudge/instant-multi", { messages: payload });
      console.log("Nudges sent/scheduled successfully!");
    } catch (err) {
      console.error("Failed to send/schedule nudges:", err);
    }
  };

  return (
    <div className="max-w-2xl mx-auto py-10">
      <h1 className="text-3xl font-bold text-center text-white mb-2">Instant Nudge</h1>
      <p className="text-center text-gray-400 mb-6">
        Create personalized nudges to stay in touch with your customers.
      </p>
      <p className="text-center text-white font-medium mb-8">
        {nudgeBlocks.length} messages for {nudgeBlocks.reduce((acc, b) => acc + b.customerIds.length, 0)} customers
      </p>

      {nudgeBlocks.map((block: NudgeBlock, i: number) => (
        <div key={i} className="bg-[#111827] p-4 rounded-xl mb-6 border border-gray-700">
          <label className="text-sm font-medium text-gray-300 block mb-2">Select customers</label>
          <div className="bg-[#1f2937] rounded p-3 border border-gray-600 mb-4">
            <label className="flex items-center text-white mb-2">
              <input
                type="checkbox"
                checked={block.customerIds.length === contacts.length}
                onChange={() => {
                  const copy = [...nudgeBlocks];
                  copy[i].customerIds =
                    block.customerIds.length === contacts.length ? [] : contacts.map(c => c.id);
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
          />

          <Button
            variant= "ghost"
            className="mb-3 text-white border-gray-500 hover:bg-gray-700"
            onClick={() => handleDraft(i)}
            disabled={!block.topic || block.customerIds.length === 0}
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
              />
            )}
          </div>
        </div>
      ))}

      <Button
        variant="ghost"
        className="text-blue-400 hover:text-blue-300 mb-4"
        onClick={() => setNudgeBlocks([...nudgeBlocks, { topic: "", message: "", customerIds: [], schedule: false, datetime: "" }])}
      >
        + Add another message block
      </Button>

      <Button
        className="w-full bg-gradient-to-r from-green-400 to-blue-500 hover:from-green-500 hover:to-blue-600 text-black font-semibold py-2 px-4 rounded"
        onClick={handleSend}
        disabled={nudgeBlocks.length === 0 || nudgeBlocks.every(b => !b.message || b.customerIds.length === 0)}
      >
        Send & Schedule All
      </Button>
    </div>
  );
}