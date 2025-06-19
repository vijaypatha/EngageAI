// frontend/src/components/inbox/MessageBox.tsx
"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, X, Loader2, CheckCircle, CalendarPlus } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { addDays, format } from 'date-fns';
import clsx from 'clsx';

// --- Type Definitions ---
interface MessageBoxProps {
  customer: any;
  onSendMessage: (message: string) => Promise<void>; // Ensure onSendMessage is async
  initialMessage?: string;
  selectedDraftId?: number | null;
  onCancelEdit?: () => void;
  onMessageSent: () => void; // Callback to notify parent (e.g., to refetch history)
}

/**
 * The message input component at the bottom of a conversation view.
 * Now includes a "Post-Send Nurture Prompt" to allow for quick,
 * one-click follow-up scheduling.
 */
const MessageBox: React.FC<MessageBoxProps> = ({
  customer,
  onSendMessage,
  initialMessage = "",
  selectedDraftId = null,
  onCancelEdit = () => {},
  onMessageSent,
}) => {
  // --- STATE MANAGEMENT ---
  const [message, setMessage] = useState(initialMessage);
  const [isSending, setIsSending] = useState(false);
  const [isAiLoading, setIsAiLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // --- NEW: State for the Post-Send Nurture Prompt ---
  const [showNurturePrompt, setShowNurturePrompt] = useState(false);
  const [nurtureStatus, setNurtureStatus] = useState<'idle' | 'scheduling' | 'success' | 'error'>('idle');

  useEffect(() => {
    setMessage(initialMessage);
  }, [initialMessage]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [message]);

  // --- EVENT HANDLERS ---
  const handleSend = async () => {
    if (!message.trim() || isSending) return;
    
    setIsSending(true);
    try {
      await onSendMessage(message);
      setMessage('');
      onMessageSent(); // Notify parent that a message was sent
      // Show the nurture prompt after a successful send
      setShowNurturePrompt(true);
      // Automatically hide the prompt after 10 seconds if no action is taken
      setTimeout(() => setShowNurturePrompt(false), 10000);
    } catch (error) {
        console.error("Failed to send message:", error);
    } finally {
        setIsSending(false);
    }
  };
  
  const handleAiAssist = async () => {
    if (!message.trim() || isAiLoading) return;
    setIsAiLoading(true);
    setTimeout(() => {
      setMessage(prev => `${prev.trim()} - hope you're having a great week! ✨`);
      setIsAiLoading(false);
    }, 1000);
  };

  /**
   * NEW: Handles scheduling a follow-up message from the nurture prompt.
   * @param days - The number of days in the future to schedule the follow-up.
   */
  const handleScheduleFollowUp = async (days: number) => {
    setNurtureStatus('scheduling');
    const followUpDate = addDays(new Date(), days);
    
    // A simple, friendly follow-up message template
    const followUpMessage = `Hi ${customer.customer_name}, just wanted to follow up as promised. Hope you're having a great day!`;

    try {
        // Use the existing backend endpoint for scheduling messages
        await apiClient.post(`/conversations/customer/${customer.id}/schedule-message`, {
            message: followUpMessage,
            send_datetime_utc: followUpDate.toISOString(),
        });
        setNurtureStatus('success');
    } catch (error) {
        console.error("Failed to schedule follow-up:", error);
        setNurtureStatus('error');
    } finally {
        // Hide the entire prompt area after a short delay to show status
        setTimeout(() => {
            setShowNurturePrompt(false);
            setNurtureStatus('idle');
        }, 2500);
    }
  };


  return (
    <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0 space-y-2">
      {/* Editing AI Draft Banner */}
      {selectedDraftId && (
        <div className="text-xs text-purple-300 bg-purple-900/50 rounded-t-md p-2 flex justify-between items-center">
          <span>Editing AI Draft. Hit send to approve and send.</span>
          <button onClick={onCancelEdit} className="p-1 hover:bg-purple-700/50 rounded-full">
            <X size={14} />
          </button>
        </div>
      )}
      
      {/* Main Message Input Area */}
      <div className="flex items-end gap-3">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }}}
          placeholder={`Message ${customer.customer_name}...`}
          className="flex-1 bg-[#2A2F45] text-white placeholder-gray-400 rounded-lg p-3 resize-none overflow-y-auto focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-40"
          rows={1}
        />
        <button
          onClick={handleAiAssist}
          disabled={isAiLoading || !message.trim()}
          className="p-3 bg-[#2A2F45] text-purple-400 rounded-lg hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title="AI Assist"
        >
          {isAiLoading ? <Loader2 className="animate-spin" size={24} /> : <Sparkles size={24} />}
        </button>
        <button
          onClick={handleSend}
          disabled={!message.trim() || isSending}
          className="p-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-500 transition-colors"
          title="Send"
        >
          {isSending ? <Loader2 className="animate-spin" size={24} /> : <Send size={24} />}
        </button>
      </div>
      
      {/* NEW: Post-Send Nurture Prompt */}
      {showNurturePrompt && (
        <div className="p-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-slate-200 transition-all animate-fade-in-up">
          {nurtureStatus === 'idle' && (
             <div className="flex items-center justify-between">
                <div className='flex items-center gap-2'>
                    <CheckCircle size={16} className="text-green-400" />
                    <span className="font-medium">Sent! Schedule a follow-up?</span>
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={() => handleScheduleFollowUp(2)} className="text-xs bg-slate-600 hover:bg-slate-500 px-2 py-1 rounded">In 2 days</button>
                    <button onClick={() => handleScheduleFollowUp(7)} className="text-xs bg-slate-600 hover:bg-slate-500 px-2 py-1 rounded">In 1 week</button>
                    <button onClick={() => setShowNurturePrompt(false)} className="p-1 hover:bg-slate-600 rounded-full"><X size={14} /></button>
                </div>
             </div>
          )}
          {nurtureStatus === 'scheduling' && <div className="flex items-center justify-center gap-2 text-slate-300"><Loader2 size={16} className="animate-spin"/>Scheduling...</div>}
          {nurtureStatus === 'success' && <div className="flex items-center justify-center gap-2 text-green-400"><CalendarPlus size={16} />Follow-up scheduled!</div>}
          {nurtureStatus === 'error' && <div className="flex items-center justify-center gap-2 text-red-400"><X size={16} />Failed to schedule.</div>}
        </div>
      )}
    </div>
  );
};

export default MessageBox;