// frontend/src/components/inbox/CustomerIntelligencePane.tsx
"use client";

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { Loader2, CheckCircle, AlertCircle, User, Zap, LifeBuoy, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

interface CustomerIntelligencePaneProps {
  customerId: number;
  isNewlyCreated?: boolean;
}

// Maps for UI labels
const lifecycleStageOptions = {
  'New Lead': 'New Lead', 'Prospect': 'Prospect', 'Active Client': 'Active Client',
  'Past Client': 'Past Client', 'VIP': 'VIP', 'Other': 'Other',
};
const keyTopicsOptions = {
  'Price sensitive': 'Price sensitive', 'Too busy': 'Too busy', 'Needs follow-up': 'Needs follow-up',
  'High-intent': 'High-intent', 'Budget concern': 'Budget concern', 'Comparing options': 'Comparing options',
};

const QuickTagButton = ({ onClick, children, isSelected }: { onClick: () => void; children: React.ReactNode; isSelected: boolean }) => (
  <button
    onClick={onClick}
    className={clsx(
      "text-xs font-semibold py-1 px-3 rounded-full transition-all",
      isSelected ? "bg-cyan-500 text-white ring-2 ring-offset-2 ring-offset-gray-800 ring-cyan-500"
                 : "bg-gray-600 hover:bg-gray-500 text-gray-200"
    )}
  >
    {children}
  </button>
);

export default function CustomerIntelligencePane({ customerId, isNewlyCreated = false }: CustomerIntelligencePaneProps) {
  // --- FIX: Added separate state for all fields ---
  const [customerName, setCustomerName] = useState('');
  const [lifecycleStage, setLifecycleStage] = useState('');
  const [notes, setNotes] = useState('');
  const [painPoints, setPainPoints] = useState(''); // State for pain points
  const [tags, setTags] = useState<Set<string>>(new Set());

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'success' | 'error' | null>(null);
  
  // Note: Combined tag serialization into the main notes field for simplicity
  const serializeTagsToNotes = (currentNotes: string, currentTags: Set<string>): string => {
    const tagLine = `[TAGS: ${Array.from(currentTags).join(', ')}]`;
    const notesWithoutTags = currentNotes.replace(/\[TAGS:.*?\]\n*/, '');
    return currentTags.size > 0 ? `${tagLine}\n${notesWithoutTags}` : notesWithoutTags;
  };
  
  const parseTagsFromNotes = (fullNotes: string): { parsedTags: Set<string>; remainingNotes: string } => {
    const tagRegex = /\[TAGS: (.*?)\]\n*/;
    const match = fullNotes.match(tagRegex);
    if (match && match[1]) {
      const parsedTags = new Set(match[1].split(', ').filter(t => t));
      const remainingNotes = fullNotes.replace(tagRegex, '');
      return { parsedTags, remainingNotes };
    }
    return { parsedTags: new Set(), remainingNotes: fullNotes };
  };
  
  // --- FIX: Fetch logic now populates all fields, including pain_points ---
  const fetchCustomerDetails = useCallback(async (id: number) => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get(`/conversations/customers/${id}/details`);
      setCustomerName(data.customer_name || '');
      setLifecycleStage(data.lifecycle_stage || '');
      setPainPoints(data.pain_points || ''); // Populate pain points
      
      const { parsedTags, remainingNotes } = parseTagsFromNotes(data.interaction_history || '');
      setTags(parsedTags);
      setNotes(remainingNotes);
    } catch (error) {
      console.error("Failed to fetch customer details:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (customerId) {
      fetchCustomerDetails(customerId);
    }
  }, [customerId, fetchCustomerDetails]);

  const handleTagToggle = (tag: string) => {
    setTags(prev => {
      const newTags = new Set(prev);
      newTags.has(tag) ? newTags.delete(tag) : newTags.add(tag);
      return newTags;
    });
  };

  // --- FIX: Save handler now sends all fields to the backend ---
  const handleSave = async () => {
    setIsSaving(true);
    setSaveStatus(null);
    const payload = {
      customer_name: customerName,
      lifecycle_stage: lifecycleStage,
      pain_points: painPoints,
      interaction_history: serializeTagsToNotes(notes, tags),
    };

    try {
      // The PUT request to /customers/{id} in customer_routes is generic and will handle these fields
      await apiClient.put(`/customers/${customerId}`, payload);
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (error) {
      console.error("Failed to save customer details:", error);
      setSaveStatus('error');
    } finally {
      setIsSaving(false);
    }
  };
  
  if (isLoading) {
    return <div className="p-4 bg-gray-800 border-l border-gray-700 w-full md:w-80 lg:w-96 flex items-center justify-center h-full"><Loader2 className="animate-spin text-cyan-400" /></div>;
  }

  return (
    <div className="p-4 bg-gray-800 border-l border-gray-700 w-full flex flex-col h-full shadow-2xl">
      <div className="flex-shrink-0 mb-4">
        <h4 className="text-lg font-bold text-white flex items-center">
          <User size={18} className="mr-2 text-cyan-400" />
          Customer Intelligence
        </h4>
        {isNewlyCreated && (
            <p className="text-sm text-cyan-300 mt-2">
                New contact! Add details to make future messages smarter.
            </p>
        )}
      </div>
      
      <div className="flex-1 space-y-5 overflow-y-auto pr-2">
        <div>
          <label htmlFor="customerName" className="block text-sm font-medium text-gray-300 mb-1">Full Name</label>
          <input
            id="customerName" type="text" value={customerName} onChange={(e) => setCustomerName(e.target.value)}
            placeholder="e.g., Jane Doe"
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2 flex items-center"><LifeBuoy size={14} className="mr-2" /> Lifecycle Stage</label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(lifecycleStageOptions).map(([key, label]) => (
              <QuickTagButton key={key} onClick={() => setLifecycleStage(label)} isSelected={lifecycleStage === label}>{label}</QuickTagButton>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2 flex items-center"><Zap size={14} className="mr-2" /> Quick Tags</label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(keyTopicsOptions).map(([key, label]) => (
              <QuickTagButton key={key} onClick={() => handleTagToggle(label)} isSelected={tags.has(label)}>{label}</QuickTagButton>
            ))}
          </div>
        </div>
        
        {/* --- FIX: Added separate text area for Pain Points --- */}
        <div>
          <label htmlFor="painPoints" className="block text-sm font-medium text-gray-300 mb-1 flex items-center"><AlertTriangle size={14} className="mr-2" /> Pain Points</label>
          <textarea
            id="painPoints" rows={3} value={painPoints} onChange={(e) => setPainPoints(e.target.value)}
            placeholder="What challenges is the customer facing?"
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500"
          />
        </div>

        <div>
          <label htmlFor="notes" className="block text-sm font-medium text-gray-300 mb-1">Interaction Log & Notes</label>
          <textarea
            id="notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Log important dates, preferences, or past touchpoints..."
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500"
          />
        </div>
      </div>
      
      <div className="flex-shrink-0 mt-4">
        <button
          onClick={handleSave} disabled={isSaving}
          className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-500 text-white font-bold py-2 px-4 rounded-md flex items-center justify-center transition-colors"
        >
          {isSaving ? <Loader2 className="animate-spin mr-2" /> : 'Save Details'}
        </button>
        {saveStatus === 'success' && <p className="text-sm text-green-400 mt-2 flex items-center"><CheckCircle size={16} className="mr-1" /> Details saved!</p>}
        {saveStatus === 'error' && <p className="text-sm text-red-400 mt-2 flex items-center"><AlertCircle size={16} className="mr-1" /> Failed to save.</p>}
      </div>
    </div>
  );
}