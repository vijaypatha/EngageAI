// 📄 File: /app/conversations/page.tsx

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, Clock, Send } from "lucide-react";

interface InboxEntry {
  customer_id: number;
  customer_name: string;
  last_message: string;
  status: string;
  timestamp?: string;
}

export default function ConversationInbox() {
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  const router = useRouter();

  useEffect(() => {
    apiClient.get("/conversations").then((res) => setInbox(res.data.conversations));
  }, []);

  const formatTime = (ts?: string) => {
    if (!ts) return "";
    const dt = new Date(ts);
    return dt.toLocaleString();
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white p-6">
      <h1 className="text-3xl font-bold mb-6">📨 Open Conversations</h1>

      {inbox.length === 0 ? (
        <p className="text-zinc-400">No active conversations yet.</p>
      ) : (
        <div className="space-y-4">
          {inbox.map((item) => (
            <div
              key={item.customer_id}
              className="bg-zinc-800 p-4 rounded-lg border border-zinc-700 hover:border-blue-400 transition cursor-pointer"
              onClick={() => router.push(`/conversations/${item.customer_id}`)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-lg">{item.customer_name}</span>
                <span className="text-xs text-zinc-400">{formatTime(item.timestamp)}</span>
              </div>
              <p className="text-zinc-300 text-sm line-clamp-2 mb-1">{item.last_message}</p>
              <div className="text-xs text-blue-400 flex items-center gap-1">
                {item.status === "pending_review" ? <Clock size={14} /> : <Send size={14} />}
                <span>{item.status === "pending_review" ? "Awaiting reply" : "You replied"}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
