// frontend/src/components/inbox/CustomerIntelligencePane.tsx
"use client";

import React, { useEffect, useState, useCallback, memo } from 'react';
import { apiClient } from '@/lib/api';
import { Loader2, Tag, User, LifeBuoy, Zap, Edit, Info, CheckCircle, AlertCircle as ErrorCircle } from 'lucide-react';
import clsx from 'clsx';

// --- Type Definitions ---
interface CustomerDetails {
  id: number;
  customer_name: string;
  lifecycle_stage: string | null;
  interaction_history: string | null;
  pain_points: string | null;
  tags: { id: number; name: string }[];
  business_id: number;
}

interface TagData {
  id: number;
  name: string;
}

interface CustomerIntelligencePaneProps {
  customerId: number | null; // Allow null to prevent initial fetch errors
  isNewlyCreated: boolean;
}

// --- Reusable UI Components ---
const QuickButton = ({ onClick, children, className = "" }: { onClick: () => void; children: React.ReactNode; className?: string }) => (
  <button
    onClick={onClick}
    className={clsx(
      "text-xs bg-gray-600/70 hover:bg-gray-500/90 text-slate-200 py-1 px-2.5 rounded-full transition-colors border border-gray-500/80",
      className
    )}
  >
    {children}
  </button>
);

const SectionHeader = ({ icon: Icon, title, subtitle }: { icon: React.ElementType, title: string, subtitle?: string }) => (
  <div className="border-b border-slate-600/50 pb-2 mb-3">
    <h4 className="text-md font-bold text-white flex items-center">
      <Icon size={16} className="mr-2.5 text-cyan-400" />
      {title}
    </h4>
    {subtitle && <p className="text-xs text-slate-400 mt-1 ml-1">{subtitle}</p>}
  </div>
);

const CustomerIntelligencePane: React.FC<CustomerIntelligencePaneProps> = memo(({ customerId, isNewlyCreated }) => {
  const [customer, setCustomer] = useState<CustomerDetails | null>(null);
  const [businessTags, setBusinessTags] = useState<TagData[]>([]);
  // FIX: Internal loading and error states for the panel itself.
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'success' | 'error' | null>(null);
  const [newTagName, setNewTagName] = useState("");

  const fetchCustomerAndTags = useCallback(async (id: number) => {
    setIsLoading(true);
    setError(null);
    setCustomer(null); // Clear previous customer data
    try {
      const customerRes = await apiClient.get(`/customers/${id}`);
      // ADDED: Log the full customer data received from the API
      console.log("DEBUG: CustomerIntelligencePane customerRes.data:", customerRes.data); 

      const businessId = customerRes.data.business_id;
      // EXISTING: Log the extracted businessId
      console.log("DEBUG: CustomerIntelligencePane businessId for tags fetch:", businessId); 

      const tagsRes = await apiClient.get(`/business/${businessId}/tags`);
      setCustomer(customerRes.data);
      setBusinessTags(tagsRes.data);
    } catch (err: any) {
      console.error("Failed to fetch customer intelligence data:", err);
      setError("Could not load customer details.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // FIX: Only fetch data if we have a valid customerId.
    if (customerId) {
      fetchCustomerAndTags(customerId);
    } else {
      setIsLoading(false);
    }
  }, [customerId, fetchCustomerAndTags]);
  
  // All other handlers (handleFieldChange, handleToggleTag, etc.) remain the same...

  const handleFieldChange = (field: keyof CustomerDetails, value: string) => {
    if (customer) {
      setCustomer({ ...customer, [field]: value });
    }
  };

  const handleToggleTag = async (tag: TagData) => {
    if (!customer) return;
    const currentTagIds = new Set(customer.tags.map(t => t.id));
    const updatedTags = currentTagIds.has(tag.id)
      ? customer.tags.filter(t => t.id !== tag.id)
      : [...customer.tags, tag];
    
    setCustomer({ ...customer, tags: updatedTags });

    try {
      await apiClient.post(`/customers/${customerId}/tags`, { tag_ids: updatedTags.map(t => t.id) });
    } catch (err) {
      console.error("Failed to update tags:", err);
      // Revert on error
      fetchCustomerAndTags(customer.id); 
      setError("Failed to update tags.");
    }
  };
  
  const handleCreateTag = async () => {
    if (!newTagName.trim() || !customer) return;
    setIsSaving(true);
    try {
      const res = await apiClient.post(`/business/${customer.business_id}/tags`, { name: newTagName });
      const newTag = res.data;
      setBusinessTags(prev => [...prev, newTag]);
      await handleToggleTag(newTag);
      setNewTagName("");
    } catch (error: any) {
        setError(error.response?.data?.detail || "Failed to create tag.");
        console.error("Failed to create tag:", error);
    } finally {
        setIsSaving(false);
    }
  };

  const handleSave = async () => {
    if (!customer) return;
    setIsSaving(true);
    setSaveStatus(null);
    const payload = {
      customer_name: customer.customer_name,
      lifecycle_stage: customer.lifecycle_stage,
      pain_points: customer.pain_points,
      interaction_history: customer.interaction_history,
    };
    try {
      await apiClient.put(`/customers/${customerId}`, payload);
      setSaveStatus('success');
    } catch (error) {
      console.error("Failed to save customer details:", error);
      setSaveStatus('error');
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveStatus(null), 3000);
    }
  };

  const appendToNotes = (field: 'pain_points' | 'interaction_history', text: string) => {
    if(customer) {
        const existingText = customer[field] || "";
        const newText = existingText ? `${existingText}\n- ${text}` : `- ${text}`;
        handleFieldChange(field, newText);
    }
  };

  // FIX: Render states are now self-contained within the panel.
  if (isLoading) return <div className="p-6 flex justify-center items-center h-full"><Loader2 className="animate-spin text-cyan-400" size={32} /></div>;
  if (error) return <div className="p-6 text-red-400 text-center">{error}</div>;
  if (!customer) return <div className="p-6 text-slate-400">No customer selected.</div>; // Fallback message

  const customerTagIds = new Set(customer.tags.map(t => t.id));

  return (
    <div className="p-4 bg-slate-800 w-full flex flex-col h-full text-slate-200">
      <div className="flex-shrink-0 mb-4">
        <h4 className="text-lg font-bold text-white flex items-center"><Info size={18} className="mr-2 text-cyan-400" /> Customer Intelligence</h4>
        {isNewlyCreated && (
            <p className="text-sm text-cyan-300 mt-2 bg-cyan-900/50 p-2 rounded-md border border-cyan-700/50">New contact created. Add details to make future AI messages smarter.</p>
        )}
      </div>
      
      <div className="flex-1 space-y-5 overflow-y-auto pr-2 -mr-2 aai-scrollbars-dark">
        {/* All other sections remain the same */}
        <div>
          <label htmlFor="customerName" className="block text-sm font-medium text-slate-300 mb-1">Full Name</label>
          <input
            id="customerName" type="text" value={customer.customer_name} 
            onChange={(e) => handleFieldChange('customer_name', e.target.value)}
            className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm"
          />
        </div>
        
        <div className="space-y-3">
          <SectionHeader icon={LifeBuoy} title="Lifecycle Stage" />
          <div className="flex flex-wrap gap-2">
            {['New Lead', 'Prospect', 'Active Client', 'Past Client', 'VIP'].map((stage) => (
              <QuickButton key={stage} onClick={() => handleFieldChange('lifecycle_stage', stage)} className={clsx(customer.lifecycle_stage === stage && "bg-cyan-600 text-white border-cyan-500")}>
                {stage}
              </QuickButton>
            ))}
          </div>
        </div>

        <div className="space-y-3">
            <SectionHeader icon={Tag} title="Tags" subtitle="Categorize for better targeting."/>
            <div className="flex flex-wrap gap-2">
            {businessTags.map(tag => (
                <QuickButton key={tag.id} onClick={() => handleToggleTag(tag)} className={clsx("flex items-center gap-1.5", customerTagIds.has(tag.id) && "bg-cyan-600 text-white border-cyan-500")}>
                    {tag.name}
                </QuickButton>
            ))}
            </div>
            <div className="flex gap-2 items-center mt-2">
              <input
                  type="text" value={newTagName} onChange={(e) => setNewTagName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateTag()}
                  placeholder="Create new tag..."
                  className="flex-grow bg-slate-700 border-slate-600 rounded-md px-3 py-1.5 text-sm text-white focus:ring-2 focus:ring-cyan-500"
              />
              <button onClick={handleCreateTag} disabled={isSaving || !newTagName.trim()} className="p-2 bg-cyan-600 hover:bg-cyan-700 rounded-md disabled:bg-gray-500 text-white">+</button>
            </div>
        </div>
        
        <div className="space-y-3">
            <SectionHeader icon={Zap} title="Personalization Insights" subtitle="Helps AI craft more relevant messages."/>
            <textarea
                id="painPoints" rows={3} value={customer.pain_points || ''} 
                onChange={(e) => handleFieldChange('pain_points', e.target.value)}
                placeholder="e.g., Interested in [service], concerned about [cost/time]..."
                className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm"
            />
            <div className="flex flex-wrap gap-2"><QuickButton onClick={() => appendToNotes('pain_points', 'Price sensitive')}>+ Price sensitive</QuickButton><QuickButton onClick={() => appendToNotes('pain_points', 'Needs quick turnaround')}>+ Quick turnaround</QuickButton></div>
        </div>

        <div className="space-y-3">
            <SectionHeader icon={Edit} title="Interaction Log" subtitle="Log important dates, preferences, or touchpoints."/>
            <textarea
                id="notes" rows={4} value={customer.interaction_history || ''} 
                onChange={(e) => handleFieldChange('interaction_history', e.target.value)}
                placeholder="e.g., Birthday is on [Date], Called and left voicemail..."
                className="w-full bg-slate-700 border-slate-600 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-cyan-500 text-sm"
            />
            <div className="flex flex-wrap gap-2"><QuickButton onClick={() => appendToNotes('interaction_history', 'Birthday: ')}>+ Birthday</QuickButton><QuickButton onClick={() => appendToNotes('interaction_history', 'Follow-up needed by: ')}>+ Follow-up</QuickButton><QuickButton onClick={() => appendToNotes('interaction_history', 'Called, left VM on: ')}>+ Called</QuickButton></div>
        </div>
      </div>
      
      <div className="flex-shrink-0 mt-4 pt-4 border-t border-slate-600/50">
        <button
          onClick={handleSave} disabled={isSaving}
          className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-500 text-white font-bold py-2 px-4 rounded-md flex items-center justify-center transition-colors"
        >
          {isSaving ? <Loader2 className="animate-spin mr-2" /> : 'Save Details'}
        </button>
        {saveStatus === 'success' && <p className="text-sm text-green-400 mt-2 flex items-center justify-center"><CheckCircle size={16} className="mr-1" /> Details saved!</p>}
        {saveStatus === 'error' && <p className="text-sm text-red-400 mt-2 flex items-center justify-center"><ErrorCircle size={16} className="mr-1" /> Failed to save.</p>}
      </div>
    </div>
  );
});

export { CustomerIntelligencePane };