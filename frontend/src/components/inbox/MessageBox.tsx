import React, { useState, useEffect, useRef } from 'react';
import { InboxCustomerSummary } from '@/types';
import { Send, Clock } from 'lucide-react';

interface MessageBoxProps {
  customer?: InboxCustomerSummary;
  selectedDraftId: string | number | null;
  onSendMessage: (message: string, recipientPhone?: string) => Promise<void>;
  onCancelEdit: () => void;
  initialMessage?: string;
  isNewMessageMode?: boolean;
}

export default function MessageBox({ customer, selectedDraftId, onSendMessage, onCancelEdit, initialMessage = "", isNewMessageMode = false }: MessageBoxProps) {
  const [newMessage, setNewMessage] = useState(initialMessage);
  const [recipientPhone, setRecipientPhone] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setNewMessage(initialMessage);
    setSendError(null);
    inputRef.current?.focus();
  }, [initialMessage, customer?.customer_id]);

  const canSendMessage = isNewMessageMode ? true : customer?.consent_status !== 'opted_out';
  const disabledReason = "Cannot send messages. Customer has opted out.";

  const handleSend = async () => {
    const messageToSend = newMessage.trim();
    if (!messageToSend || isSending) return;

    if (!canSendMessage) {
      setSendError(disabledReason);
      return;
    }

    setIsSending(true);
    setSendError(null);
    try {
      await onSendMessage(messageToSend, isNewMessageMode ? recipientPhone : undefined);
      setNewMessage("");
      if (isNewMessageMode) setRecipientPhone("");
    } catch (err: any) {
      setSendError(err.response?.data?.detail || "Failed to send message.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0">
      {sendError && <p className="text-xs text-red-400 mb-2">{sendError}</p>}
      <div className="flex flex-col gap-2">
        {isNewMessageMode && (
          <input
            type="tel"
            value={recipientPhone}
            onChange={(e) => setRecipientPhone(e.target.value)}
            placeholder="Enter phone number..."
            className="p-2 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />
        )}
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && !isSending && handleSend()}
            placeholder={selectedDraftId ? "Edit draft..." : canSendMessage ? "Type a message..." : disabledReason}
            className="flex-1 p-2 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none disabled:opacity-70"
            disabled={isSending || !canSendMessage}
          />
          <button onClick={handleSend} disabled={isSending || !newMessage.trim() || !canSendMessage || (isNewMessageMode && !recipientPhone)} className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white disabled:opacity-50 transition-colors">
            {isSending ? <Clock className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </div>
      </div>
      {selectedDraftId && <button onClick={onCancelEdit} className="text-xs text-gray-400 hover:text-gray-200 mt-1">Cancel edit</button>}
    </div>
  );
}