"use client";
// Instant Nudge page with Tag Filtering - CORRECTED

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
// Import necessary API functions and types
// Import API functions
import { apiClient, getBusinessTags, getCustomersByBusiness } from "@/lib/api"; 
// Import Types
import { Tag, Customer } from "@/types"; 
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label"; // Ensure Label is imported
import { Loader2, Info, Trash2 } from "lucide-react"; // Added Info, Trash2
import { cn } from "@/lib/utils"; // Ensure correct path

// Assuming OptInStatus is defined somewhere, otherwise remove its usage or define it
// Example placeholder: type OptInStatus = 'opted_in' | 'opted_out' | 'pending' | 'waiting' | 'error';
// const getOptInStatus = (customer: Customer): OptInStatus => { /* ... your logic ... */ return 'opted_in'; };

interface NudgeBlock {
  id: string; // Unique ID for React keys
  topic: string;
  message: string;
  customerIds: number[]; // Holds the IDs SELECTED from the filtered list
  schedule: boolean;
  datetime: string; // Store as string YYYY-MM-DDTHH:mm
  // Status tracking
  isDrafting?: boolean;
  isSending?: boolean;
  isScheduled?: boolean;
  isSent?: boolean;
  error?: string | null;
  // Backend reference
  processedMessageIds?: number[];
}

// Helper function (move to utils if used elsewhere)
function getLocalDateForInput(isoDate?: string | null): string {
  if (!isoDate) return '';
  try {
    // Handles both 'Z' and offset like '+00:00' by parsing then formatting
    const dt = new Date(isoDate);
    // Format to YYYY-MM-DDTHH:mm suitable for datetime-local input
    // Need to adjust for local timezone offset implicitly handled by Date object here
    const year = dt.getFullYear();
    const month = (dt.getMonth() + 1).toString().padStart(2, '0');
    const day = dt.getDate().toString().padStart(2, '0');
    const hours = dt.getHours().toString().padStart(2, '0');
    const minutes = dt.getMinutes().toString().padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  } catch (e) {
    console.error("Error formatting date for input:", e);
    return ""; // Fallback
  }
}


export default function InstantNudgePage() {
  const { business_name: businessSlug } = useParams(); // Use slug
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [nudgeBlocks, setNudgeBlocks] = useState<NudgeBlock[]>([
    { id: crypto.randomUUID(), topic: "", message: "", customerIds: [], schedule: false, datetime: "" }
  ]);
  const [allOptedInContacts, setAllOptedInContacts] = useState<Customer[]>([]);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [selectedFilterTags, setSelectedFilterTags] = useState<Tag[]>([]);
  const [isLoadingContacts, setIsLoadingContacts] = useState(true);
  const [isLoadingTags, setIsLoadingTags] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter(); // If needed for navigation

  // --- Fetch Business ID ---
  useEffect(() => {
    const slugParam = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!slugParam) return;
    setIsLoadingContacts(true); // Use combined loading indicator
    setIsLoadingTags(true);
    setError(null);
    apiClient
      .get<{ business_id: number }>(`/business-profile/business-id/slug/${slugParam}`)
      .then((res) => setBusinessId(res.data.business_id))
      .catch((err) => {
        console.error("❌ Failed to resolve business ID:", err);
        setError("Could not load business identifier.");
        setIsLoadingContacts(false);
        setIsLoadingTags(false);
      });
  }, [businessSlug]);

  // --- Fetch Contacts and Tags ---
  useEffect(() => {
    if (!businessId) return;
    let isMounted = true;
    const fetchData = async () => {
      setIsLoadingContacts(true);
      setIsLoadingTags(true);
      setError(null); // Clear previous errors on new fetch
      try {
        const [customersData, tagsData] = await Promise.all([
          getCustomersByBusiness(businessId), // Fetches customers (includes tags)
          getBusinessTags(businessId)         // Fetches all tags
        ]);
        if (!isMounted) return;

        // Filter for opted-in based on your logic (adjust if needed)
        const optedIn = customersData.filter(c => c.latest_consent_status === 'opted_in');
        setAllOptedInContacts(optedIn);
        setAvailableTags(tagsData);
        console.log(`📞 Fetched ${optedIn.length} opted-in contacts. 🏷️ Fetched ${tagsData.length} tags.`);

      } catch (err: any) {
        console.error("❌ Failed to fetch contacts or tags:", err);
        if (isMounted) setError(err?.response?.data?.detail || "Failed to load contacts or tags.");
      } finally {
        if (isMounted) {
          setIsLoadingContacts(false);
          setIsLoadingTags(false);
        }
      }
    };
    fetchData();
    return () => { isMounted = false };
  }, [businessId]);

  // --- Filtering Logic (Remains the same) ---
  const filteredContacts = useMemo(() => {
    if (selectedFilterTags.length === 0) return allOptedInContacts;
    const selectedTagIds = new Set(selectedFilterTags.map(t => t.id));
    return allOptedInContacts.filter(customer => {
      const customerTagIds = new Set(customer.tags?.map(t => t.id) ?? []);
      return Array.from(selectedTagIds).every(filterTagId => customerTagIds.has(filterTagId));
    });
  }, [allOptedInContacts, selectedFilterTags]);

  // --- Handlers (Keep updateNudgeBlock, handleDraft, handleSendOrSchedule, addNudgeBlock, removeNudgeBlock, handleFilterTagToggle, handleSelectAllFiltered, handleCustomerSelectionChange) ---
  // Ensure these functions correctly update the state based on the NudgeBlock interface
   const updateNudgeBlock = (index: number, field: keyof NudgeBlock, value: any) => {
     setNudgeBlocks(prev => {
       const copy = [...prev];
       const block = { ...copy[index] }; // Create copy of the block
       (block as any)[field] = value; // Update the field
       // Reset status flags if relevant fields change
       if (['topic', 'message', 'customerIds', 'schedule', 'datetime'].includes(field as string)) {
           block.isDrafting = false; block.isSending = false;
           block.isScheduled = false; block.isSent = false; block.error = null;
       }
       copy[index] = block; // Replace the block in the copied array
       return copy;
     });
   };

  const handleDraft = async (index: number) => {
    const block = nudgeBlocks[index];
    if (!block.topic || !businessId) { updateNudgeBlock(index, 'error', 'Topic is required.'); return; }
    updateNudgeBlock(index, 'isDrafting', true); updateNudgeBlock(index, 'error', null);
    try {
      const res = await apiClient.post<{ message_draft?: string }>("/instant-nudge/generate-targeted-draft", {
        topic: block.topic, business_id: businessId, customer_ids: block.customerIds, filter_tags: null,
      });
      if (res.data.message_draft) updateNudgeBlock(index, 'message', res.data.message_draft);
      else throw new Error("AI did not return a message draft.");
    } catch (err: any) { console.error("❌ Draft failed:", err); updateNudgeBlock(index, 'error', err?.response?.data?.detail || "Draft failed.");
    } finally { updateNudgeBlock(index, 'isDrafting', false); }
  };

  const handleSendOrSchedule = async (index: number) => {
    const block = nudgeBlocks[index];
    if (!businessId || !block.message || block.customerIds.length === 0) { updateNudgeBlock(index, 'error', 'Message & recipients required.'); return; }
    if (block.schedule && !block.datetime) { updateNudgeBlock(index, 'error', 'Select schedule date/time.'); return; }
    updateNudgeBlock(index, 'isSending', true); updateNudgeBlock(index, 'error', null);
    const payload = {
      customer_ids: block.customerIds, message: block.message, business_id: businessId,
      send_datetime_utc: block.schedule && block.datetime ? new Date(block.datetime).toISOString() : null
    };
    try {
      const res = await apiClient.post<{ status: string; details: any }>("/instant-nudge/send-batch", payload);
      if (block.schedule) updateNudgeBlock(index, 'isScheduled', true);
      else updateNudgeBlock(index, 'isSent', true);
      if (res.data.details?.processed_message_ids) updateNudgeBlock(index, 'processedMessageIds', res.data.details.processed_message_ids);
    } catch (err: any) { console.error("❌ Send/Schedule failed:", err); updateNudgeBlock(index, 'error', err?.response?.data?.detail || "Send/Schedule failed.");
    } finally { updateNudgeBlock(index, 'isSending', false); }
  };

   const addNudgeBlock = () => setNudgeBlocks(prev => [...prev, { id: crypto.randomUUID(), topic: "", message: "", customerIds: [], schedule: false, datetime: "" }]);
   const removeNudgeBlock = (index: number) => setNudgeBlocks(prev => prev.filter((_, i) => i !== index));
   const handleFilterTagToggle = (tag: Tag) => setSelectedFilterTags(prev => prev.some(t => t.id === tag.id) ? prev.filter(t => t.id !== tag.id) : [...prev, tag]);
   const handleSelectAllFiltered = (index: number) => {
       const block = nudgeBlocks[index]; const allFilteredIds = filteredContacts.map(c => c.id);
       const allSelected = block.customerIds.length === allFilteredIds.length && allFilteredIds.every(id => block.customerIds.includes(id));
       updateNudgeBlock(index, 'customerIds', allSelected ? [] : allFilteredIds);
   };
   const handleCustomerSelectionChange = (index: number, customerId: number) => {
        const block = nudgeBlocks[index]; const currentIds = new Set(block.customerIds);
        if (currentIds.has(customerId)) currentIds.delete(customerId); else currentIds.add(customerId);
        updateNudgeBlock(index, 'customerIds', Array.from(currentIds));
   };


  // --- Loading / Error / Empty States ---
  const isLoading = isLoadingContacts || isLoadingTags;
  if (isLoading && !businessId) {
    return <div className="flex min-h-screen bg-nudge-gradient items-center justify-center text-white">Loading...</div>;
  }
  if (error && !businessId) {
    return <div className="flex min-h-screen bg-nudge-gradient items-center justify-center text-red-400 p-5 text-center">{error}</div>;
  }


  return (
    <div className="max-w-3xl mx-auto py-10 px-4">
      {/* ... (Header and Info Banner - Keep as is) ... */}
       <h1 className="text-3xl font-bold text-center text-white mb-2">Instant Nudge</h1>
       <p className="text-center text-gray-400 mb-6">Target specific customer segments with tags, draft a message, and send instantly or schedule.</p>
       <div className="bg-blue-900/50 border border-blue-500/50 rounded-lg p-4 mb-8 text-sm text-blue-200">
         <p className="flex items-center"><Info className="h-5 w-5 mr-2 flex-shrink-0" /><span>Only showing contacts who have opted in to receive messages ({allOptedInContacts.length} total).</span></p>
       </div>


      {/* --- Tag Filter Section (Keep as is) --- */}
      <div className="mb-8 p-4 bg-zinc-800/50 rounded-lg border border-neutral-700">
        <label className="block text-sm font-medium text-gray-300 mb-3">Filter Opted-In Customers by Tags (Optional)</label>
        {isLoadingTags ? <p className="text-gray-400 text-sm">Loading tags...</p> : availableTags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
                {availableTags.map(tag => ( <Button key={tag.id} variant={selectedFilterTags.some(t => t.id === tag.id) ? "default" : "secondary"} size="sm" onClick={() => handleFilterTagToggle(tag)} className={cn("rounded-full h-7 px-3", selectedFilterTags.some(t => t.id === tag.id) && "bg-blue-600 hover:bg-blue-700")}>{tag.name}</Button>))}
            </div> ) : ( <p className="text-gray-400 text-sm">No tags created yet.</p> )
        }
         {selectedFilterTags.length > 0 && (<Button variant="ghost" size="sm" className="text-xs text-blue-400 mt-2 p-0 h-auto" onClick={() => setSelectedFilterTags([])}>Clear Filters</Button> )}
      </div>

      {/* --- Nudge Blocks --- */}
      {nudgeBlocks.map((block, index) => (
        // Container Div (Keep outer div structure and conditional styling)
        <div key={block.id} className={`p-4 rounded-xl mb-6 border shadow-lg transition-all duration-300 relative ${ block.isSent ? "bg-green-950/80 border-green-700/50" : block.isScheduled ? "bg-blue-950/80 border-blue-700/50" : "bg-[#111827]/80 border-gray-700/50" }`}>

          {/* Customer Selection */}
           <label className="text-sm font-medium text-gray-300 block mb-2">Select Customers ({filteredContacts.length} matching filters)</label>
           <div className="bg-[#1f2937]/70 rounded p-3 border border-gray-600/50 mb-4 max-h-48 overflow-y-auto">
             {/* ... (Keep customer selection logic/JSX using filteredContacts) ... */}
              {filteredContacts.length > 0 ? ( <>
                 <label className="flex items-center text-white mb-2 font-medium cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                   <input type="checkbox" className="mr-2 accent-blue-500" checked={filteredContacts.length > 0 && block.customerIds.length === filteredContacts.length && filteredContacts.every(fc => block.customerIds.includes(fc.id))} ref={el => { if (el) el.indeterminate = block.customerIds.length > 0 && block.customerIds.length < filteredContacts.length; }} onChange={() => handleSelectAllFiltered(index)} disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                   Select All ({block.customerIds.length} / {filteredContacts.length})
                 </label> <hr className="border-gray-600 my-1"/> {filteredContacts.map(c => (
                   <label key={c.id} className="flex items-center text-white mb-1 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                     <input type="checkbox" className="mr-2 accent-blue-500" value={c.id} checked={block.customerIds.includes(c.id)} onChange={() => handleCustomerSelectionChange(index, c.id)} disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                     <span className="ml-2">{c.customer_name}</span>
                   </label>))} </>
             ) : ( <p className="text-gray-400 text-sm text-center py-2"> {isLoadingContacts ? "Loading contacts..." : selectedFilterTags.length > 0 ? "No opted-in contacts match selected tags." : "No opted-in contacts found."} </p> )}
           </div>

           {/* Topic */}
           <div className="mb-3">
             <Label htmlFor={`topic-input-${index}`} className="text-sm font-medium text-gray-300 block mb-1">1. Topic for AI</Label>
             <Input id={`topic-input-${index}`} placeholder="e.g., Follow up, Special holiday offer" className="bg-[#1f2937]/70 border-gray-600/50 text-white" value={block.topic} onChange={e => updateNudgeBlock(index, 'topic', e.target.value)} disabled={block.isSent || block.isScheduled || block.isSending || block.isDrafting} />
           </div>

           {/* Draft Button */}
           <Button variant="ghost" className="mb-4 text-white border-blue-500/50 hover:bg-blue-500/20" onClick={() => handleDraft(index)} disabled={!block.topic || !businessId || block.isSent || block.isScheduled || block.isSending || block.isDrafting} size="sm" >
             {block.isDrafting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : "✍️ "} Draft with AI
           </Button>

           {/* Message */}
           <div className="mb-4">
              {/* --- CORRECTED Label htmlFor --- */}
              <Label htmlFor={`message-textarea-${index}`} className="text-sm font-medium text-gray-300 block mb-1">2. Message</Label>
              <Textarea
                id={`message-textarea-${index}`} // ID matches htmlFor
                placeholder="Draft message with AI or write your own. Use {customer_name} for personalization." // Corrected placeholder text
                className="bg-[#1f2937]/70 border-gray-600/50 text-white min-h-[100px]" // Corrected bg color/opacity syntax
                value={block.message}
                onChange={e => updateNudgeBlock(index, 'message', e.target.value)} // Corrected onChange syntax
                disabled={block.isSent || block.isScheduled || block.isSending}
              />
              {/* --- CORRECTED classname and removed trailing p tag --- */}
              <p className="text-xs text-gray-400 mt-1">{block.message.length} characters</p>
            </div>

           {/* --- Scheduling Options (Corrected) --- */}
           <div className="mb-4">
                <Label className="text-sm font-medium text-gray-300 block mb-2">3. Send Options</Label>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  {/* Send Now Radio */}
                  <Label className="text-white flex items-center gap-2 cursor-pointer">
                    <input
                        type="radio"
                        name={`schedule-option-${index}`}
                        className="accent-blue-500" // standard class for radio
                        checked={!block.schedule}
                        onChange={() => updateNudgeBlock(index, 'schedule', false)} // Correct syntax
                        disabled={block.isSent || block.isScheduled || block.isSending}
                     /> {/* Self-close input */}
                     Send Now
                  </Label>
                  {/* Schedule Radio */}
                  <Label className="text-white flex items-center gap-2 cursor-pointer">
                    <input
                         type="radio"
                         name={`schedule-option-${index}`}
                         className="accent-blue-500" // standard class for radio
                         checked={block.schedule}
                         onChange={() => updateNudgeBlock(index, 'schedule', true)} // Correct syntax
                         disabled={block.isSent || block.isScheduled || block.isSending}
                    /> {/* Self-close input */}
                     Schedule
                  </Label>
                  {/* Datetime Input (shows only when schedule is true) */}
                  {block.schedule && (
                    <Input
                        type="datetime-local"
                        className="bg-[#1f2937]/70 text-white p-1 rounded border border-gray-600/50 w-auto text-sm h-8" // Added height class
                        value={block.datetime} // Bind value
                        onChange={e => updateNudgeBlock(index, 'datetime', e.target.value)} // Correct onChange
                        min={new Date(Date.now() + 60000).toISOString().slice(0, 16)} // Min 1 min from now
                        disabled={block.isSent || block.isScheduled || block.isSending}
                        required={block.schedule} // Make required only if scheduling
                    />
                  )}
                </div>
            </div>
           {/* --- End Scheduling Options --- */}

           {/* Actions and Status */}
           <div className="flex justify-end items-center gap-2 border-t border-gray-700/50 pt-3 mt-3 flex-wrap">
                {block.error && <p className="text-xs text-red-400 mr-auto basis-full text-right mb-1">{block.error}</p>}
                {block.isSent && <span className="text-xs font-medium mr-auto px-2 py-0.5 rounded bg-green-500/20 text-green-300">Sent</span>}
                {block.isScheduled && <span className="text-xs font-medium mr-auto px-2 py-0.5 rounded bg-blue-500/20 text-blue-300">Scheduled</span>}

               <Button
                 className={`px-5 py-2 rounded-md font-semibold text-white transition-all duration-200 ${ (block.isSent || block.isScheduled) ? 'bg-gray-500 cursor-not-allowed' : block.schedule ? 'bg-blue-600 hover:bg-blue-700' : 'bg-red-600 hover:bg-red-700' }`}
                 onClick={() => handleSendOrSchedule(index)}
                 disabled={block.isSent || block.isScheduled || block.isSending || !block.message || block.customerIds.length === 0 || (block.schedule && !block.datetime)}
               >
                 {block.isSending ? <Loader2 className="h-4 w-4 animate-spin mr-2"/> : null}
                 {block.isSent ? "Sent" : block.isScheduled ? "Scheduled" : block.schedule ? "Schedule Nudge" : "Send Nudge Now"}
               </Button>
               {/* Remove Button */}
               {!block.isSent && !block.isScheduled && nudgeBlocks.length > 1 && (
                   <Button variant="ghost" size="icon" className="text-gray-400 hover:text-red-500 hover:bg-red-500/10 h-8 w-8" onClick={() => removeNudgeBlock(index)} title="Remove this message block">
                       <Trash2 size={16}/>
                   </Button>
               )}
           </div>

        </div> // End nudge block
      ))}

      {/* Add Another Block Button */}
      <div className="mt-8 text-center">
        <Button id="add-another" variant="ghost" className="text-white border-dashed border-gray-600 hover:border-solid hover:bg-gray-700/50" onClick={addNudgeBlock}>
          + Add Another Message Block
        </Button>
      </div>

    </div> // End main container
  );
}