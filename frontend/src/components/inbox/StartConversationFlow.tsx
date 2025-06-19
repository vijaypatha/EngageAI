// frontend/src/components/inbox/StartConversationFlow.tsx
"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { apiClient } from '@/lib/api';
import clsx from 'clsx';
import { UserPlus, Phone, User, MessageSquare, Sparkles, Lightbulb, CheckCircle, AlertCircle, Loader2, Calendar, Edit3, X, Zap, Tag as TagIcon, Clock, Briefcase, ArrowLeft, Route, Send } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import DatePicker from 'react-datepicker';
import "react-datepicker/dist/react-datepicker.css";
import { normalizePhoneNumber } from '@/lib/utils';
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import { Tag } from "@/types";
import { TagInput } from "@/components/ui/TagInput";

// --- Type Definitions ---
interface RoadmapMessage {
    id: number;
    smsContent: string;
    smsTiming: string;
    relevance: string;
    send_datetime_utc: string;
}

type FlowStage = 'input_contact' | 'action_choice' | 'ai_roadmap_suggestion' | 'ai_single_message_suggestion';
type UserPath = 'roadmap' | 'single_message';

interface StartConversationFlowProps {
  businessId: number | null;
  businessName: string;
  representativeName: string;
  onClose: (refresh?: boolean) => void;
  onConversationStarted: (customerId: number) => void;
}

const PAIN_POINT_SUGGESTIONS = [ "Price sensitivity", "Budget is a key concern", "Needs more detailed info", "Needs quick turnaround", "Too busy to find time", "Afraid of contracts", "Currently comparing options", "Needs Follow-ups", "Looking for specific feature", "Unsure about the process" ];
const QUICK_NOTE_SUGGESTIONS = [ "Birthday is on [Date]", "Key interest: [Specify Topic]", "Follow-up needed by [Date]", "Called, left voicemail on [Date]", "Emailed about [Topic] on [Date]", "Send SMS in Spanish", "Send a nudge on big holidays", "Send a Nudge once a Quarter", "Met at [Event/Location]", "Referred by [Name]" ];

// --- Reusable UI Components ---
const QuickTagButton = ({ onClick, children, isSelected }: { onClick: () => void; children: React.ReactNode; isSelected: boolean }) => (
  <button onClick={onClick} className={clsx("text-xs font-semibold py-1 px-3 rounded-full transition-all", isSelected ? "bg-cyan-500 text-white ring-2 ring-offset-2 ring-offset-gray-800 ring-cyan-500" : "bg-slate-600 hover:bg-slate-500 text-slate-200")}>{children}</button>
);
const QuickAddButton = ({ onClick, children }: { onClick: () => void; children: React.ReactNode; }) => ( <button onClick={onClick} className="text-xs bg-slate-600/70 hover:bg-slate-500/90 text-slate-200 py-1 px-2.5 rounded-full transition-colors border border-slate-500/80"> + {children} </button> );

export const StartConversationFlow: React.FC<StartConversationFlowProps> = ({ businessId, businessName, representativeName, onClose, onConversationStarted }) => {
  
  const [currentStage, setCurrentStage] = useState<FlowStage>('input_contact');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [lifecycleStage, setLifecycleStage] = useState<string>('New Lead');
  const [painPoints, setPainPoints] = useState('');
  const [interactionHistory, setInteractionHistory] = useState('');
  const [tags, setTags] = useState<Tag[]>([]);
  const [timezone, setTimezone] = useState<string>('America/Denver');
  
  const [identifiedCustomerId, setIdentifiedCustomerId] = useState<number | null>(null);

  const [generatedRoadmap, setGeneratedRoadmap] = useState<RoadmapMessage[]>([]);
  const [singleAiMessage, setSingleAiMessage] = useState('');
  const [userSelectedSendTime, setUserSelectedSendTime] = useState<Date | null>(null);

  const handleContactIntelSubmit = async () => {
    if (!businessId || !phone.trim()) {
      setError("A valid phone number is required.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const contactPayload = {
        phone_number: normalizePhoneNumber(phone), business_id: businessId,
        customer_name: name, lifecycle_stage: lifecycleStage,
        pain_points: painPoints, interaction_history: interactionHistory,
        timezone: timezone,
      };
      const contactRes = await apiClient.post('/customers/find-or-create-by-phone', contactPayload);
      const customer = contactRes.data;
      setIdentifiedCustomerId(customer.id);
      setName(customer.customer_name);
      
      if (tags.length > 0) await apiClient.post(`/customers/${customer.id}/tags`, { tag_ids: tags.map(t => t.id) });
      setCurrentStage('action_choice');

    } catch (err: any) {
      setError(err.response?.data?.detail || "An error occurred while saving contact.");
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleActionChoice = async (path: 'roadmap' | 'single_message') => {
      if (!identifiedCustomerId || !businessId) {
          setError("Customer or Business ID is missing.");
          return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const roadmapRes = await apiClient.post('/ai/roadmap', { customer_id: identifiedCustomerId, business_id: businessId, context: { topic: "initial outreach" } });
        
        if (path === 'roadmap') {
            setGeneratedRoadmap(roadmapRes.data?.roadmap || []);
            setCurrentStage('ai_roadmap_suggestion');
        } else {
            const firstMessage = roadmapRes.data?.roadmap?.[0]?.smsContent || `Hi ${name || 'there'}, this is ${representativeName} from ${businessName}. Thanks for reaching out!`;
            setSingleAiMessage(firstMessage);
            setCurrentStage('ai_single_message_suggestion');
        }
      } catch(err: any) {
          setError(err.response?.data?.detail || "Failed to generate AI content.");
      } finally {
          setIsLoading(false);
      }
  };

  const handleScheduleRoadmap = async () => {
    if (!identifiedCustomerId || generatedRoadmap.length === 0) return;
    setIsLoading(true);
    try {
      // Use the endpoint that accepts edited content and dates.
      const payload = { 
        edited_messages: generatedRoadmap.map(msg => ({
            roadmap_message_id: msg.id,
            content: msg.smsContent,
            send_datetime_utc: msg.send_datetime_utc
        }))
      };
      await apiClient.post('/roadmap-editor/schedule-edited', payload);
      onConversationStarted(identifiedCustomerId);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to schedule roadmap.");
    } finally {
      setIsLoading(false);
    }
  };
  
  // New handler to update both message content and time in the roadmap state.
  const handleRoadmapChange = (index: number, field: 'smsContent' | 'send_datetime_utc', value: string | Date) => {
    setGeneratedRoadmap(currentRoadmap => 
        currentRoadmap.map((msg, i) => {
            if (i === index) {
                const updatedMsg = { ...msg };
                if (field === 'smsContent' && typeof value === 'string') {
                    updatedMsg.smsContent = value;
                } else if (field === 'send_datetime_utc' && value instanceof Date) {
                    updatedMsg.send_datetime_utc = value.toISOString();
                }
                return updatedMsg;
            }
            return msg;
        })
    );
  };

  const handleSendSingleMessage = async (isScheduling: boolean) => {
    if (!identifiedCustomerId || !businessId || !singleAiMessage.trim()) return;
    setIsLoading(true);
    const endpoint = isScheduling ? `/conversations/customer/${identifiedCustomerId}/schedule-message` : `/conversations/customer/${identifiedCustomerId}/send-message`;
    const payload = { message: singleAiMessage, ...(isScheduling && userSelectedSendTime && { send_datetime_utc: userSelectedSendTime.toISOString() }) };
    try {
      await apiClient.post(endpoint, payload);
      onConversationStarted(identifiedCustomerId);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Action failed.");
    } finally {
      setIsLoading(false);
    }
  };

  const appendToTextarea = (setter: React.Dispatch<React.SetStateAction<string>>, text: string) => setter(prev => prev ? `${prev}\n- ${text}` : `- ${text}`);
  const optInPreviewMessage = useMemo(() => `This is ${representativeName} from ${businessName} — thanks for connecting! Msg & data rates may apply. Reply STOP to unsubscribe.`, [businessName, representativeName]);

  const renderContent = () => {
    switch (currentStage) {
      case 'input_contact':
        return (
          <>
            <div className="flex-shrink-0 mb-4">
                <h4 className="text-lg font-bold text-white flex items-center"><UserPlus size={18} className="mr-2 text-cyan-400" />Start New Conversation</h4>
                <p className="text-sm text-slate-400 mt-1">First, let's gather some details about your new contact.</p>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto pr-2 -mr-4 aai-scrollbars-dark">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label className="block text-sm font-medium text-slate-300 mb-1"><Phone size={14} className="inline mr-2" /> Phone Number *</label><input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(123) 456-7890" className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm" /></div>
                    <div><label className="block text-sm font-medium text-slate-300 mb-1"><User size={14} className="inline mr-2" /> Full Name</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Jane Doe" className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm" /></div>
                </div>
                <div className="p-3 bg-slate-800/50 border border-slate-700/70 rounded-lg space-y-4">
                    <h3 className="text-md font-semibold text-cyan-300 flex items-center"><Lightbulb size={16} className="mr-2 text-yellow-400"/>Quick Intel</h3>
                    <div><label className="block text-sm font-medium text-slate-300 mb-2"><Briefcase size={14} className="inline mr-2" /> Lifecycle Stage</label><div className="flex flex-wrap gap-2">{['New Lead', 'Prospect', 'Active Client', 'Past Client', 'VIP'].map(stage => (<QuickTagButton key={stage} onClick={() => setLifecycleStage(stage)} isSelected={lifecycleStage === stage}>{stage}</QuickTagButton>))}</div></div>
                    <div><label className="block text-sm font-medium text-slate-300 mb-1"><Zap size={14} className="inline mr-2" />Key Topics / Needs</label><textarea rows={2} value={painPoints} onChange={(e) => setPainPoints(e.target.value)} className="w-full bg-slate-700 border-slate-600 rounded-md p-2 text-sm" /><div className="flex flex-wrap gap-1.5 mt-1.5">{PAIN_POINT_SUGGESTIONS.map(s => <QuickAddButton key={s} onClick={() => appendToTextarea(setPainPoints, s)}>{s}</QuickAddButton>)}</div></div>
                    <div><label className="block text-sm font-medium text-slate-300 mb-1"><MessageSquare size={14} className="inline mr-2" />Notes / History</label><textarea rows={2} value={interactionHistory} onChange={(e) => setInteractionHistory(e.target.value)} className="w-full bg-slate-700 border-slate-600 rounded-md p-2 text-sm" /><div className="flex flex-wrap gap-1.5 mt-1.5">{QUICK_NOTE_SUGGESTIONS.map(s => <QuickAddButton key={s} onClick={() => appendToTextarea(setInteractionHistory, s)}>{s}</QuickAddButton>)}</div></div>
                    {businessId && <div><label className="block text-sm font-medium text-slate-300 mb-2"><TagIcon size={14} className="inline mr-2" />Tags</label><TagInput businessId={businessId} initialTags={tags} onChange={setTags} /></div>}
                    <div><label className="block text-sm font-medium text-slate-300 mb-1"><Clock size={14} className="inline mr-2" />Timezone</label><select value={timezone} onChange={(e) => setTimezone(e.target.value)} className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm"><option value="">Select</option>{US_TIMEZONES.map(tz => <option key={tz} value={tz}>{TIMEZONE_LABELS[tz] || tz}</option>)}</select></div>
                </div>
            </div>
            <div className="flex-shrink-0 mt-4 pt-4 border-t border-slate-700"><button onClick={handleContactIntelSubmit} disabled={isLoading || !phone.trim()} className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-500 text-white font-bold py-2.5 px-4 rounded-md flex items-center justify-center">Next: Choose Action</button></div>
          </>
        );

      case 'action_choice':
        return (
            <>
                <div className="flex-shrink-0 mb-6 text-center">
                    <h4 className="text-xl font-bold text-white">Contact Saved!</h4>
                    <p className="text-sm text-slate-400 mt-2">What would you like to do for <span className="font-semibold text-cyan-300">{name}</span>?</p>
                </div>
                <div className="flex-1 flex flex-col md:flex-row gap-4 justify-center items-center">
                    <button onClick={() => handleActionChoice('roadmap')} disabled={isLoading} className="w-full md:w-1/2 p-6 flex flex-col items-center justify-center bg-slate-700/50 hover:bg-slate-700 border border-slate-600 rounded-lg transition-all text-center">
                        {isLoading ? <Loader2 size={32} className="text-purple-400 mb-3 animate-spin" /> : <Route size={32} className="text-purple-400 mb-3" />}
                        <h5 className="font-semibold text-white">Generate AI Roadmap</h5>
                        <p className="text-xs text-slate-400 mt-1">Create a multi-message follow-up plan.</p>
                    </button>
                    <button onClick={() => handleActionChoice('single_message')} disabled={isLoading} className="w-full md:w-1/2 p-6 flex flex-col items-center justify-center bg-slate-700/50 hover:bg-slate-700 border border-slate-600 rounded-lg transition-all text-center">
                        {isLoading ? <Loader2 size={32} className="text-green-400 mb-3 animate-spin" /> : <Send size={32} className="text-green-400 mb-3" />}
                        <h5 className="font-semibold text-white">Draft First Message</h5>
                        <p className="text-xs text-slate-400 mt-1">Get AI help to write and send one message.</p>
                    </button>
                </div>
                <div className="text-center mt-4"><button onClick={() => setCurrentStage('input_contact')} className="text-slate-400 hover:text-white text-sm">Back to Edit Contact</button></div>
            </>
        );

      case 'ai_roadmap_suggestion':
        return (
            <>
                <div className="flex-shrink-0 mb-4">
                    <h4 className="text-lg font-bold text-white flex items-center"><Route size={18} className="mr-2 text-purple-400" />Editable AI-Generated Roadmap</h4>
                    <p className="text-sm text-slate-400 mt-1">Review and edit the AI's plan for <span className="font-semibold text-cyan-300">{name}</span>.</p>
                </div>
                <div className="flex-1 space-y-3 overflow-y-auto pr-2 -mr-4 aai-scrollbars-dark">
                    {isLoading ? <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin" /></div> : generatedRoadmap.map((msg, index) => (
                        <div key={msg.id} className="p-3 bg-slate-700/50 rounded-md">
                            {/* FIX: DatePicker for editable time with clear formatting. */}
                            <div className="flex items-center gap-3">
                                <Calendar size={16} className="text-cyan-400 shrink-0" />
                                <DatePicker
                                    selected={parseISO(msg.send_datetime_utc)}
                                    onChange={(date: Date | null) => {
                                        if (date) handleRoadmapChange(index, 'send_datetime_utc', date);
                                    }}
                                    showTimeSelect
                                    dateFormat="EEE, MMM d, yyyy @ h:mm aa"
                                    className="w-full bg-slate-900/50 border border-slate-600 rounded-md px-3 py-1.5 text-cyan-300 text-sm font-semibold focus:ring-2 focus:ring-cyan-500"
                                />
                            </div>
                            <textarea
                                value={msg.smsContent}
                                onChange={(e) => handleRoadmapChange(index, 'smsContent', e.target.value)}
                                className="w-full bg-slate-900/50 border border-slate-600 rounded-md p-2 mt-2 text-slate-200 text-sm focus:ring-2 focus:ring-cyan-500"
                                rows={3}
                            />
                            <p className="text-xs text-slate-400 italic mt-2">Purpose: {msg.relevance}</p>
                        </div>
                    ))}
                    {generatedRoadmap.length === 0 && !isLoading && <div className="text-center text-slate-400 p-4">AI could not generate a roadmap based on the provided info.</div>}
                </div>
                <div className="flex-shrink-0 mt-4 pt-4 border-t border-slate-700 space-y-2">
                    <button onClick={handleScheduleRoadmap} disabled={isLoading || generatedRoadmap.length === 0} className="w-full bg-cyan-600 hover:bg-cyan-700 text-white font-bold py-2.5 px-4 rounded-md flex items-center justify-center">{isLoading ? <Loader2 className="animate-spin" /> : 'Schedule Edited Roadmap'}</button>
                    <button onClick={() => setCurrentStage('action_choice')} className="w-full text-slate-400 hover:text-white text-sm flex items-center justify-center gap-2"><ArrowLeft size={14}/>Back to Action Choice</button>
                </div>
            </>
        );
      
      case 'ai_single_message_suggestion':
        return (
          <>
            <div className="flex-shrink-0 mb-4"><h4 className="text-lg font-bold text-white flex items-center"><Sparkles size={18} className="mr-2 text-purple-400" />AI Message Suggestion</h4></div>
            <div className="flex-1 space-y-4 overflow-y-auto pr-2 -mr-4 aai-scrollbars-dark">
                <textarea rows={6} value={singleAiMessage} onChange={(e) => setSingleAiMessage(e.target.value)} className="w-full bg-slate-700 border-slate-600 rounded-md p-3 text-white focus:ring-2 focus:ring-cyan-500 text-sm" />
                <div><label className="block text-sm font-medium text-slate-300 mb-1">Schedule for later (optional)</label><DatePicker selected={userSelectedSendTime} onChange={(date: Date | null) => setUserSelectedSendTime(date)} showTimeSelect dateFormat="Pp" className="w-full bg-slate-900 border-slate-600 rounded-md px-3 py-2 text-white text-sm" popperClassName="datepicker-popper" calendarClassName="datepicker-calendar" wrapperClassName="w-full" placeholderText="Leave blank to send now" /></div>
            </div>
            <div className="flex-shrink-0 mt-4 pt-4 border-t border-slate-700 space-y-3">
              <button onClick={() => handleSendSingleMessage(false)} disabled={isLoading} className="w-full bg-green-600 hover:bg-green-700 disabled:bg-slate-500 text-white font-bold py-2.5 px-4 rounded-md flex items-center justify-center">{isLoading ? <Loader2 className="animate-spin" /> : '✅ Send Now'}</button>
              <button onClick={() => handleSendSingleMessage(true)} disabled={isLoading || !userSelectedSendTime} className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-500 text-white font-bold py-2.5 px-4 rounded-md flex items-center justify-center">{isLoading ? <Loader2 className="animate-spin" /> : `🗓️ Schedule for ${userSelectedSendTime ? format(userSelectedSendTime, 'MMM d, h:mm a') : '...'}`}</button>
              <button onClick={() => setCurrentStage('action_choice')} className="w-full text-slate-400 hover:text-white text-sm flex items-center justify-center gap-2 py-1"><ArrowLeft size={14}/>Back to Action Choice</button>
            </div>
          </>
        );

      default: return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center animate-fade-in">
      <div className="relative w-full max-w-2xl h-full md:h-auto md:max-h-[90vh] bg-slate-800 rounded-lg shadow-xl flex flex-col p-6">
        <button onClick={() => onClose(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white z-10" aria-label="Close"><X size={24} /></button>
        {error && <div className="bg-red-900/50 text-red-300 p-3 rounded-md mb-4 flex items-center"><AlertCircle size={16} className="mr-2" />{error}</div>}
        {renderContent()}
      </div>
    </div>
  );
};
