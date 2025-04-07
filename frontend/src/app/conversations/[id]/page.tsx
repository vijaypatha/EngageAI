// 📄 File: /app/conversations/[id]/page.tsx — improved alignment, bubble color, and AI/manual distinction

"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getCurrentBusiness } from "@/lib/utils"; // ✅ Add at top


interface Message {
  sender: "customer" | "ai" | "owner";
  text: string;
  timestamp: string | null;
  status?: string;
}

export default function ConversationPage() {
  const { id } = useParams();
  const customerId = parseInt(id as string);
  const [messages, setMessages] = useState<Message[]>([]);
  const [customerName, setCustomerName] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editedMessage, setEditedMessage] = useState("");
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout;
  
    const fetchConversation = async () => {
      const session = await getCurrentBusiness();
      if (!session?.business_id) return;
  
      const res = await apiClient.get(`/conversations/${customerId}`, {
        params: { business_id: session.business_id },
      });
  
      setMessages(res.data.messages);
      setCustomerName(res.data.customer.name);
    };
  
    fetchConversation(); // fetch on mount
    interval = setInterval(fetchConversation, 1000); // refresh every 1s
  
    return () => clearInterval(interval);
  }, [customerId]);
  

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendEdited = async (index: number) => {
    const msg = messages[index];
    await apiClient.post(`/conversations/${customerId}/reply`, { message: editedMessage });
    setEditingIndex(null);
    setEditedMessage("");
    const updated = await apiClient.get(`/conversations/${customerId}`);
    setMessages(updated.data.messages);
  };

  const handleManualSend = async () => {
    if (!inputText.trim()) return;
    await apiClient.post(`/conversations/${customerId}/reply`, { message: inputText });
    setInputText("");
    const updated = await apiClient.get(`/conversations/${customerId}`);
    setMessages(updated.data.messages);
  };

  return (
    <div className="min-h-screen bg-black text-white p-6 flex flex-col">
      <h1 className="text-3xl font-bold mb-4">💬 Chat with {customerName}</h1>

      <div className="flex-1 space-y-4 overflow-y-auto mb-4">
        {messages.map((msg, i) => {
          const isCustomer = msg.sender === "customer";
          const isAI = msg.sender === "ai";
          const isManual = msg.sender === "owner";
          const isPending = msg.status === "pending_review";

          return (
            <div key={i} className={`flex ${isCustomer ? "justify-start" : "justify-end"}`}>
              <div
                className={`max-w-[75%] p-4 rounded-lg whitespace-pre-wrap text-sm
                  ${isCustomer ? "bg-zinc-700 text-white" : ""}
                  ${isAI && !isPending ? "bg-blue-800 text-blue-100" : ""}
                  ${isAI && isPending ? "bg-blue-900 text-blue-100" : ""}
                  ${isManual ? "bg-green-800 text-green-100" : ""}`}
              >
                <div className="flex justify-between items-start">
                  <p className="flex-1">{msg.text}</p>
                  {isAI && isPending && (
                    <div className="flex gap-2 ml-4">
                      <Button size="sm" className="bg-yellow-500 text-black hover:bg-yellow-400" onClick={() => {
                        setEditingIndex(i);
                        setEditedMessage(msg.text);
                      }}>Edit</Button>
                      <Button size="sm" className="bg-green-500 text-black hover:bg-green-400" onClick={() => sendEdited(i)}>
                        Send
                      </Button>
                    </div>
                  )}
                </div>

                {editingIndex === i && (
                  <div className="mt-2 space-y-2">
                    <Input value={editedMessage} onChange={(e) => setEditedMessage(e.target.value)} />
                    <Button size="sm" onClick={() => sendEdited(i)} className="bg-purple-500 hover:bg-purple-600 text-white">
                      Confirm Send
                    </Button>
                  </div>
                )}

                {isPending && <p className="text-xs italic text-yellow-300 mt-1">Pending Approval</p>}
                {msg.timestamp && <p className="text-xs text-zinc-400 mt-1 text-right">{new Date(msg.timestamp).toLocaleString()}</p>}
                {!isCustomer && (
                  <p className="text-xs text-zinc-400 mt-1 text-right italic">
                    {isAI ? "AI Response" : "Manual Reply"}
                  </p>
                )}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Manual message input box */}
      <div className="flex gap-2 border-t border-zinc-700 pt-4">
        <Input
          placeholder="Write a message..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
        />
        <Button onClick={handleManualSend} className="bg-blue-600 hover:bg-blue-700 text-white">
          Send manually
        </Button>
      </div>
    </div>
  );
}