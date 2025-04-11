"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";

interface Message {
  id: number;
  content: string;
  direction: "inbound" | "outbound";
  timestamp: string;
}

export default function ConversationThread() {
  const { id } = useParams();
  const [messages, setMessages] = useState<Message[]>([]);

  useEffect(() => {
    const loadMessages = async () => {
      const res = await apiClient.get(`/conversations/customer/${id}`);
      setMessages(res.data.messages);
    };
    loadMessages();
  }, [id]);

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-xl font-semibold mb-4">Conversation with Customer #{id}</h2>
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`max-w-md p-3 rounded-lg shadow ${
            msg.direction === "inbound"
              ? "bg-gray-100 self-start"
              : "bg-blue-500 text-white self-end ml-auto"
          }`}
        >
          <div className="text-sm">{msg.content}</div>
          <div className="text-xs text-right opacity-60 mt-1">{new Date(msg.timestamp).toLocaleString()}</div>
        </div>
      ))}
    </div>
  );
}

// "use client";

// import { useEffect, useState, useRef } from "react";
// import { useParams } from "next/navigation";
// import { apiClient, getConversation, sendManualReply } from "@/lib/api"; // Add this
// import { Button } from "@/components/ui/button";
// import { Input } from "@/components/ui/input";
// import { getCurrentBusiness } from "@/lib/utils"; // ✅ Add at top


// interface Message {
//   sender: "customer" | "ai" | "owner";
//   text: string;
//   timestamp: string | null;
//   source: "ai_draft" | "manual_reply" | "scheduled_sms" | "customer_response";
//   direction: "incoming" | "outgoing";
// }

// export default function ConversationPage() {
//   const { id } = useParams();
//   const customerId = parseInt(id as string);
//   const [messages, setMessages] = useState<Message[]>([]);
//   const [customerName, setCustomerName] = useState("");
//   const [editingIndex, setEditingIndex] = useState<number | null>(null);
//   const [editedMessage, setEditedMessage] = useState("");
//   const [inputText, setInputText] = useState("");
//   const messagesEndRef = useRef<HTMLDivElement>(null);

//   useEffect(() => {
//     let interval: NodeJS.Timeout;
  
//     const fetchConversation = async () => {
//       const res = await getConversation(customerId);
//       setMessages(res.messages);
//       setCustomerName(res.customer.name);
//     };
  
//     fetchConversation(); // fetch on mount
//     interval = setInterval(fetchConversation, 20000); // every 20s
  
//     return () => clearInterval(interval);
//   }, [customerId]);
  

//   useEffect(() => {
//     messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
//   }, [messages]);

//   const sendEdited = async (index: number) => {
//     const msg = messages[index];
//     await apiClient.post(`/conversations/${customerId}/reply`, { message: editedMessage });
//     setEditingIndex(null);
//     setEditedMessage("");
//     const updated = await getConversation(customerId);
//     setMessages(updated.messages);
//   };

//   const handleManualSend = async () => {
//     if (!inputText.trim()) return;
//     await sendManualReply(customerId, inputText);
//     setInputText("");
//     const updated = await getConversation(customerId);
//     setMessages(updated.messages);
//   };

//   return (
//     <div className="min-h-screen bg-black text-white p-6 flex flex-col">
//       <h1 className="text-3xl font-bold mb-4">💬 Chat with {customerName}</h1>

//       <div className="flex-1 space-y-4 overflow-y-auto mb-4">
//         {messages.map((msg, i) => {
//           const isIncoming = msg.direction === "incoming";
//           const isOutgoing = msg.direction === "outgoing";
//           const isPending = msg.source === "ai_draft";
//           const isScheduled = msg.source === "scheduled_sms";
//           const isManual = msg.source === "manual_reply";

//           return (
//             <div key={i} className={`flex ${isIncoming ? "justify-start" : "justify-end"}`}>
//               <div
//                 className={`max-w-[75%] p-4 rounded-lg whitespace-pre-wrap text-sm
//                   ${isIncoming ? "bg-zinc-700 text-white" : ""}
//                   ${isPending ? "bg-blue-900 text-blue-100" : ""}
//                   ${isScheduled ? "bg-indigo-700 text-white" : ""}
//                   ${isManual ? "bg-green-800 text-green-100" : ""}`}
//               >
//                 <div className="flex justify-between items-start">
//                   <p className="flex-1">{msg.text}</p>
//                   {isPending && (
//                     <div className="flex gap-2 ml-4">
//                       <Button size="sm" className="bg-yellow-500 text-black hover:bg-yellow-400" onClick={() => {
//                         setEditingIndex(i);
//                         setEditedMessage(msg.text);
//                       }}>Edit</Button>
//                       <Button size="sm" className="bg-green-500 text-black hover:bg-green-400" onClick={() => sendEdited(i)}>
//                         Send
//                       </Button>
//                     </div>
//                   )}
//                 </div>

//                 {editingIndex === i && (
//                   <div className="mt-2 space-y-2">
//                     <Input value={editedMessage} onChange={(e) => setEditedMessage(e.target.value)} />
//                     <Button size="sm" onClick={() => sendEdited(i)} className="bg-purple-500 hover:bg-purple-600 text-white">
//                       Confirm Send
//                     </Button>
//                   </div>
//                 )}

//                 {msg.timestamp && <p className="text-xs text-zinc-400 mt-1 text-right">{new Date(msg.timestamp).toLocaleString()}</p>}
//                 <p className="text-xs text-zinc-400 mt-1 text-right italic">
//                   {msg.source === "ai_draft" ? "AI Draft" :
//                    msg.source === "manual_reply" ? "Manual Reply" :
//                    msg.source === "scheduled_sms" ? "Scheduled" :
//                    "Customer Response"}
//                 </p>
//               </div>
//             </div>
//           );
//         })}
//         <div ref={messagesEndRef} />
//       </div>

//       {/* Manual message input box */}
//       <div className="flex gap-2 border-t border-zinc-700 pt-4">
//         <Input
//           placeholder="Write a message..."
//           value={inputText}
//           onChange={(e) => setInputText(e.target.value)}
//         />
//         <Button onClick={handleManualSend} className="bg-blue-600 hover:bg-blue-700 text-white">
//           Send manually
//         </Button>
//       </div>
//     </div>
//   );
// }