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
    console.log("📍 Conversations page loaded");
    const loadInbox = async () => {
      const pathParts = window.location.pathname.split("/");
      const businessName = pathParts.includes("dashboard") ? pathParts[2] : null;
      console.log("🧠 businessName:", businessName);
      if (!businessName) return;

      try {
        const res = await apiClient.get("/conversations", {
          params: { business_name: businessName },
        });
        console.log("📬 conversations response:", res.data);
        setInbox(res.data.conversations);
      } catch (err) {
        console.error("Failed to load conversations:", err);
      }
    };
  
    loadInbox();
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
              className="bg-zinc-900 p-4 rounded-lg border border-zinc-700 hover:border-blue-500 transition cursor-pointer shadow-sm"
              onClick={() => router.push(`/conversations/${item.customer_id}`)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-lg text-white">{item.customer_name}</h2>
                  <p className="text-sm text-zinc-300 mt-1 line-clamp-2">{item.last_message}</p>
                </div>
                <div className="text-right text-xs text-zinc-400 ml-4">
                  <p>{formatTime(item.timestamp)}</p>
                  <div className="flex justify-end items-center gap-1 mt-1 text-blue-400">
                    {item.status === "pending_review" ? <Clock size={14} /> : <Send size={14} />}
                    <span>{item.status === "pending_review" ? "Awaiting reply" : "You replied"}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
