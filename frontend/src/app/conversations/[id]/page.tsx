'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';

interface Message {
  id: number;
  text: string;
  from_business: boolean;
  timestamp: string;
}

export default function ConversationPage() {
  const { id } = useParams();
  const customerId = parseInt(id as string);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchMessages = async () => {
    try {
      const res = await apiClient.get(`/conversations/${customerId}`);
      setMessages(res.data.conversations || []);
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  };

  useEffect(() => {
    fetchMessages();
    const interval = setInterval(fetchMessages, 5000);
    return () => clearInterval(interval);
  }, [customerId]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!newMessage.trim()) return;
    try {
      await apiClient.post(`/conversations/${customerId}/reply`, {
        reply_text: newMessage,
      });
      setNewMessage('');
      fetchMessages();
    } catch (err) {
      console.error('Failed to send reply:', err);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-4 text-white">💬 Conversation</h1>
      <div className="bg-gray-800 rounded-lg p-4 h-[500px] overflow-y-scroll space-y-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`max-w-[80%] p-3 rounded-lg text-sm ${
              msg.from_business
                ? 'ml-auto bg-blue-500 text-white'
                : 'mr-auto bg-gray-300 text-black'
            }`}
          >
            <div>{msg.text}</div>
            <div className="text-xs mt-1 opacity-60 text-right">
              {new Date(msg.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}
        <div ref={scrollRef} />
      </div>

      <div className="flex mt-4 gap-2">
        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type a message..."
          className="flex-1 p-2 rounded border border-gray-400"
        />
        <button
          onClick={sendMessage}
          className="bg-green-600 text-white px-4 py-2 rounded"
        >
          Send
        </button>
      </div>
    </div>
  );
}
