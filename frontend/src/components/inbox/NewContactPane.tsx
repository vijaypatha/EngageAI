// frontend/src/components/inbox/NewContactPane.tsx
"use client";

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api';
import { Loader2, CheckCircle, AlertCircle, Info } from 'lucide-react';
import clsx from 'clsx';

interface NewContactPaneProps {
  customerId: number;
  isNewlyCreated?: boolean; // Added new prop
}

// A map for user-friendly labels for each lifecycle stage
const lifecycleStageOptions = {
  'New Lead': 'New Lead',
  'Active Client': 'Active Client',
  'Past Client': 'Past Client',
  'Prospect': 'Prospect',
  'VIP': 'VIP',
};

// A map for user-friendly labels for key topics/needs
const keyTopicsOptions = {
  'Price sensitivity': 'Price sensitivity',
  'Too busy to find time': 'Too busy to find time',
  'Afraid of contracts': 'Afraid of contracts',
  'Needs Follow-ups': 'Needs Follow-ups',
  'Needs more detailed info': 'Needs more detailed info',
  'Budget is a key concern': 'Budget is a key concern',
  'Looking for quick turnaround': 'Looking for quick turnaround',
  'Currently comparing options': 'Currently comparing options',
};

const QuickNoteButton = ({ onClick, children }: { onClick: () => void; children: React.ReactNode }) => (
  <button
    onClick={onClick}
    className="text-xs bg-gray-600 hover:bg-gray-500 text-white py-1 px-2 rounded-full transition-colors"
  >
    {children}
  </button>
);

export default function NewContactPane({ customerId, isNewlyCreated }: NewContactPaneProps) {
  const [customerName, setCustomerName] = useState('');
  const [lifecycleStage, setLifecycleStage] = useState('');
  const [notes, setNotes] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'success' | 'error' | null>(null);

  useEffect(() => {
    // This effect can be used to fetch initial data if needed, but for a new contact, fields will be empty.
    // Resetting state when the customerId changes.
    setCustomerName('');
    setLifecycleStage('');
    setNotes('');
    setSaveStatus(null);
  }, [customerId]);

  const appendToNotes = (text: string) => {
    setNotes(prev => prev ? `${prev}\n${text}` : text);
  };

  const handleSave = async () => {
    if (!customerName && !lifecycleStage && !notes) {
      alert("Please fill in at least one field to save.");
      return;
    }

    setIsSaving(true);
    setSaveStatus(null);

    const payload: { customer_name?: string; lifecycle_stage?: string; interaction_history?: string } = {};
    if (customerName) payload.customer_name = customerName;
    if (lifecycleStage) payload.lifecycle_stage = lifecycleStage;
    if (notes) payload.interaction_history = notes;

    try {
      await apiClient.put(`/customers/${customerId}`, payload);
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 3000); // Hide status message after 3 seconds
    } catch (error) {
      console.error("Failed to save customer details:", error);
      setSaveStatus('error');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="p-4 bg-gray-800 border-l border-gray-700 w-full md:w-80 lg:w-96 flex flex-col h-full">
      <div className="flex-shrink-0 mb-4">
        <h4 className="text-lg font-bold text-white flex items-center">
          <Info size={18} className="mr-2 text-cyan-400" />
          Personalize Contact
        </h4>
        {isNewlyCreated && ( // Conditionally render the new message
            <p className="text-sm text-cyan-300 mt-2">
                New contact created. Let's add some personalization to make our future messages smarter.
            </p>
        )}
        <p className="text-xs text-gray-400 mt-2">Add details to help the AI craft smarter, more personal messages.</p>
      </div>
      
      <div className="flex-1 space-y-4 overflow-y-auto pr-2">
        <div>
          <label htmlFor="customerName" className="block text-sm font-medium text-gray-300 mb-1">Full Name</label>
          <input
            id="customerName"
            type="text"
            value={customerName}
            onChange={(e) => setCustomerName(e.target.value)}
            placeholder="e.g., Jane Doe"
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Lifecycle Stage</label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(lifecycleStageOptions).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setLifecycleStage(key)}
                className={clsx(
                  "text-xs font-semibold py-1 px-3 rounded-full transition-all",
                  lifecycleStage === key ? "bg-cyan-500 text-white ring-2 ring-offset-2 ring-offset-gray-800 ring-cyan-500" : "bg-gray-600 hover:bg-gray-500 text-gray-200"
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label htmlFor="notes" className="block text-sm font-medium text-gray-300 mb-1">Quick Notes / Interaction Log</label>
          <textarea
            id="notes"
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Log important dates, preferences, or past touchpoints..."
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
          />
          <div className="flex flex-wrap gap-2 mt-2">
             <QuickNoteButton onClick={() => appendToNotes('Birthday is on [Date]')}>+ Birthday</QuickNoteButton>
             <QuickNoteButton onClick={() => appendToNotes('Follow-up needed by [Date]')}>+ Follow-up</QuickNoteButton>
             <QuickNoteButton onClick={() => appendToNotes('Key interest: ')}>+ Key Interest</QuickNoteButton>
             <QuickNoteButton onClick={() => appendToNotes('Called, left voicemail on [Date]')}>+ Called</QuickNoteButton>
          </div>
        </div>
      </div>
      
      <div className="flex-shrink-0 mt-4">
        <button
          onClick={handleSave}
          disabled={isSaving}
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