"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, Clock, Send } from "lucide-react";

interface InboxEntry {
  customer_id: number;
  customer_name: string;
  last_message: string;
  status: "pending_review" | "replied";
  timestamp?: string;
}

export default function ConversationInbox() {
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  const router = useRouter();
  const { business_name } = useParams();

  useEffect(() => {
    console.log("📍 Conversations page loaded");
    const loadInbox = async () => {
      console.log("🧠 businessName:", business_name);
      if (!business_name) return;

      try {
        const res = await apiClient.get("/conversations/inbox", {
          params: { business_name },
        });
        console.log("📬 conversations response:", res.data);
        setInbox(res.data.conversations);
      } catch (err) {
        console.error("Failed to load conversations:", err);
      }
    };

    loadInbox();
  }, [business_name]);

  const formatTime = (ts?: string) => {
    if (!ts) return "";
    const date = new Date(ts);
    return date.toLocaleString();
  };

  return (
    <div className="p-4">
      <h2 className="text-2xl font-semibold mb-4">Open Conversations</h2>
      {inbox.length === 0 ? (
        <p className="text-muted-foreground">No active conversations yet.</p>
      ) : (
        <div className="space-y-4">
          {inbox.map((entry) => (
            <div
              key={entry.customer_id}
              className="p-4 border rounded-lg shadow cursor-pointer hover:bg-accent"
              onClick={() => router.push(`/conversations/${entry.customer_id}`)}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-medium">{entry.customer_name}</span>
                <span className="text-sm text-muted-foreground">{formatTime(entry.timestamp)}</span>
              </div>
              <div className="text-sm text-muted-foreground">{entry.last_message}</div>
              <div className="mt-2 flex gap-2 text-xs text-muted-foreground items-center">
                {entry.status === "pending_review" ? (
                  <>
                    <MessageSquare className="w-4 h-4" /> Needs review
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" /> Replied
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}