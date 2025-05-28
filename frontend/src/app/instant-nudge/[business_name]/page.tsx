"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient, getBusinessTags, getCustomersByBusiness } from "@/lib/api";
import { Tag, Customer } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Info, Trash2, MessageSquarePlus, Settings2, CalendarClock, Send, CheckCircle2, Clock3 } from "lucide-react"; // Added more icons
import { cn } from "@/lib/utils";

interface NudgeBlock {
  id: string;
  topic: string;
  message: string;
  customerIds: number[];
  schedule: boolean;
  datetime: string;
  isDrafting?: boolean;
  isSending?: boolean;
  isScheduled?: boolean;
  isSent?: boolean;
  error?: string | null;
  processedMessageIds?: number[];
}

// Helper function (remains the same)
function getLocalDateForInput(isoDate?: string | null): string {
  if (!isoDate) return '';
  try {
    const dt = new Date(isoDate);
    const year = dt.getFullYear();
    const month = (dt.getMonth() + 1).toString().padStart(2, '0');
    const day = dt.getDate().toString().padStart(2, '0');
    const hours = dt.getHours().toString().padStart(2, '0');
    const minutes = dt.getMinutes().toString().padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  } catch (e) {
    console.error("Error formatting date for input:", e);
    return "";
  }
}

export default function InstantNudgePage() {
  const { business_name: businessSlug } = useParams();
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
  const router = useRouter();

  // --- Fetch Business ID (logic remains same) ---
  useEffect(() => {
    const slugParam = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!slugParam) {
        setError("Business identifier missing from URL.");
        setIsLoadingContacts(false);
        setIsLoadingTags(false);
        return;
    }
    setIsLoadingContacts(true);
    setIsLoadingTags(true);
    setError(null);
    apiClient
      .get<{ business_id: number }>(`/business-profile/business-id/slug/${slugParam}`)
      .then((res) => setBusinessId(res.data.business_id))
      .catch((err) => {
        console.error("❌ Failed to resolve business ID:", err);
        setError("Could not load business identifier. Please check the URL or try again.");
        setIsLoadingContacts(false);
        setIsLoadingTags(false);
      });
  }, [businessSlug]);

  // --- Fetch Contacts and Tags (logic remains same) ---
  useEffect(() => {
    if (!businessId) return;
    let isMounted = true;
    const fetchData = async () => {
      setIsLoadingContacts(true);
      setIsLoadingTags(true);
      setError(null);
      try {
        const [customersData, tagsData] = await Promise.all([
          getCustomersByBusiness(businessId),
          getBusinessTags(businessId)
        ]);
        if (!isMounted) return;
        const optedIn = customersData.filter(c => c.latest_consent_status === 'opted_in');
        setAllOptedInContacts(optedIn);
        setAvailableTags(tagsData);
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

  // --- Filtering Logic (remains same) ---
  const filteredContacts = useMemo(() => {
    if (selectedFilterTags.length === 0) return allOptedInContacts;
    const selectedTagIds = new Set(selectedFilterTags.map(t => t.id));
    return allOptedInContacts.filter(customer => {
      const customerTagIds = new Set(customer.tags?.map(t => t.id) ?? []);
      return Array.from(selectedTagIds).every(filterTagId => customerTagIds.has(filterTagId));
    });
  }, [allOptedInContacts, selectedFilterTags]);

  // --- Handlers (logic remains same, ensure state updates are correct) ---
  const updateNudgeBlock = (index: number, field: keyof NudgeBlock, value: any) => {
     setNudgeBlocks(prev => {
       const copy = [...prev];
       const block = { ...copy[index] };
       (block as any)[field] = value;
       if (['topic', 'message', 'customerIds', 'schedule', 'datetime'].includes(field as string)) {
           block.isDrafting = false; block.isSending = false;
           block.isScheduled = false; block.isSent = false; block.error = null;
       }
       copy[index] = block;
       return copy;
     });
   };

  const handleDraft = async (index: number) => { /* ... (existing logic) ... */
    const block = nudgeBlocks[index];
    if (!block.topic || !businessId) { updateNudgeBlock(index, 'error', 'Topic is required to draft a message.'); return; }
    updateNudgeBlock(index, 'isDrafting', true); updateNudgeBlock(index, 'error', null);
    try {
      const res = await apiClient.post<{ message_draft?: string }>("/instant-nudge/generate-targeted-draft", {
        topic: block.topic, business_id: businessId, customer_ids: block.customerIds, filter_tags: null, // Assuming filter_tags is handled or null for now
      });
      if (res.data.message_draft) updateNudgeBlock(index, 'message', res.data.message_draft);
      else throw new Error("AI did not return a message draft. Please try a different topic or write manually.");
    } catch (err: any) { console.error("❌ Draft failed:", err); updateNudgeBlock(index, 'error', err?.response?.data?.detail || "Draft generation failed.");
    } finally { updateNudgeBlock(index, 'isDrafting', false); }
  };

  const handleSendOrSchedule = async (index: number) => { /* ... (existing logic, check status updates) ... */
    const block = nudgeBlocks[index];
    if (!businessId || !block.message || block.customerIds.length === 0) {
      updateNudgeBlock(index, 'error', 'Message and at least one Recipient are required.'); return;
    }
    if (block.schedule && !block.datetime) {
      updateNudgeBlock(index, 'error', 'Please select a date and time for scheduling.'); return;
    }
    updateNudgeBlock(index, 'isSending', true); updateNudgeBlock(index, 'error', null);
    const payload = {
      customer_ids: block.customerIds, message: block.message, business_id: businessId,
      send_datetime_utc: block.schedule && block.datetime ? new Date(block.datetime).toISOString() : null
    };
    try {
      const res = await apiClient.post<{ status: string; details: any }>("/instant-nudge/send-batch", payload);
      const { details } = res.data;
      if (details) {
        if (details.processed_message_ids) updateNudgeBlock(index, 'processedMessageIds', details.processed_message_ids);
        if (block.schedule) {
          if (details.scheduled_count > 0 && details.scheduled_count === block.customerIds.length) { updateNudgeBlock(index, 'isScheduled', true); updateNudgeBlock(index, 'error', null); }
          else if (details.scheduled_count > 0) { updateNudgeBlock(index, 'isScheduled', true); updateNudgeBlock(index, 'error', `Scheduled for ${details.scheduled_count}/${block.customerIds.length}. ${details.failed_count} failed.`); }
          else { updateNudgeBlock(index, 'isScheduled', false); updateNudgeBlock(index, 'error', `Scheduling failed. ${details.failed_count > 0 ? `${details.failed_count} recipient(s) failed.` : 'No recipients scheduled.'}`);}
        } else { // Instant send
          if (details.sent_count > 0 && details.sent_count === block.customerIds.length) { updateNudgeBlock(index, 'isSent', true); updateNudgeBlock(index, 'error', null); }
          else if (details.sent_count > 0) { updateNudgeBlock(index, 'isSent', true); updateNudgeBlock(index, 'error', `Sent to ${details.sent_count}/${block.customerIds.length}. ${details.failed_count} failed.`); }
          else { updateNudgeBlock(index, 'isSent', false); updateNudgeBlock(index, 'error', `Send failed. ${details.failed_count > 0 ? `${details.failed_count} recipient(s) failed.` : 'Message not sent.'}`);}
        }
      } else { updateNudgeBlock(index, 'error', 'Unexpected response from server.'); if (block.schedule) updateNudgeBlock(index, 'isScheduled', false); else updateNudgeBlock(index, 'isSent', false); }
    } catch (err: any) {
      console.error("❌ Send/Schedule API call failed:", err);
      const errorDetail = err?.response?.data?.detail || "Operation failed. Check connection or server logs.";
      updateNudgeBlock(index, 'error', errorDetail);
      if (block.schedule) updateNudgeBlock(index, 'isScheduled', false); else updateNudgeBlock(index, 'isSent', false);
    } finally { updateNudgeBlock(index, 'isSending', false); }
  };

   const addNudgeBlock = () => setNudgeBlocks(prev => [...prev, { id: crypto.randomUUID(), topic: "", message: "", customerIds: [], schedule: false, datetime: "" }]);
   const removeNudgeBlock = (index: number) => setNudgeBlocks(prev => prev.filter((_, i) => i !== index));
   const handleFilterTagToggle = (tag: Tag) => setSelectedFilterTags(prev => prev.some(t => t.id === tag.id) ? prev.filter(t => t.id !== tag.id) : [...prev, tag]);
   const handleSelectAllFiltered = (index: number) => {
       const block = nudgeBlocks[index]; const allFilteredIds = filteredContacts.map(c => c.id);
       const allSelectedCurrently = block.customerIds.length === allFilteredIds.length && allFilteredIds.every(id => block.customerIds.includes(id));
       updateNudgeBlock(index, 'customerIds', allSelectedCurrently ? [] : allFilteredIds);
   };
   const handleCustomerSelectionChange = (index: number, customerId: number) => {
        const block = nudgeBlocks[index]; const currentIds = new Set(block.customerIds);
        if (currentIds.has(customerId)) currentIds.delete(customerId); else currentIds.add(customerId);
        updateNudgeBlock(index, 'customerIds', Array.from(currentIds));
   };

  const isLoadingInitial = (isLoadingContacts || isLoadingTags) && !businessId;
  const initialError = error && !businessId;

  if (isLoadingInitial) {
    return (
        <div className="flex-1 p-6 bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center font-sans">
          <div className="text-center">
              <Loader2 className="animate-spin h-12 w-12 text-purple-400 mx-auto mb-6" />
              <h1 className="text-2xl font-bold text-slate-300">Loading Nudge Setup...</h1>
              <p className="text-slate-400">Getting things ready for you.</p>
          </div>
        </div>
    );
  }
  if (initialError) {
    return (
      <div className="flex-1 p-6 bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center font-sans">
        <div className="max-w-md mx-auto text-center bg-slate-800 p-8 rounded-xl shadow-2xl border border-slate-700">
          <Info className="h-16 w-16 text-red-500 mx-auto mb-6" /> {/* Changed icon */}
          <h2 className="text-2xl font-semibold text-red-400 mb-3">Initialization Error</h2>
          <p className="text-slate-300 mb-6 bg-red-900/30 border border-red-700/50 p-3 rounded-md">
            {error}
          </p>
           <Button
            onClick={() => window.location.reload()}
            className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all"
           >
            Retry
           </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-12">
        <header className="text-center mb-10">
            <h1 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-3">
                Instant Nudge Composer
            </h1>
            <p className="text-slate-400 max-w-2xl mx-auto">
                Target specific customer segments, draft tailored messages with AI, and send instantly or schedule for later.
            </p>
        </header>

       <div className="bg-sky-800/20 border border-sky-700/40 rounded-xl p-4 mb-8 text-sm text-sky-200 shadow-lg">
         <p className="flex items-center"><Info className="h-5 w-5 mr-3 flex-shrink-0 text-sky-400" />
            <span>Only opted-in contacts are available for messaging ({allOptedInContacts.length} total). Filters apply to this list.</span>
         </p>
       </div>

      <div className="mb-10 p-5 bg-slate-800/70 rounded-xl border border-slate-700/80 shadow-xl">
        <label className="block text-lg font-semibold text-slate-200 mb-4">Filter Opted-In Customers by Tags</label>
        {isLoadingTags ? <Loader2 className="h-5 w-5 animate-spin text-purple-400" /> : availableTags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
                {availableTags.map(tag => {
                    const isSelected = selectedFilterTags.some(t => t.id === tag.id);
                    return (
                        <Button
                            key={tag.id}
                            variant="outline"
                            size="sm"
                            onClick={() => handleFilterTagToggle(tag)}
                            className={cn(
                                "rounded-full text-xs font-medium px-3.5 py-1.5 h-auto transition-all duration-200",
                                isSelected
                                ? "bg-purple-600 border-purple-500 text-white hover:bg-purple-700"
                                : "bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500"
                            )}
                        >
                            {tag.name}
                        </Button>
                    );
                })}
            </div>
         ) : ( <p className="text-slate-400 text-sm">No tags created for this business yet.</p> )
        }
         {selectedFilterTags.length > 0 && (
            <Button variant="ghost" size="sm" className="text-xs text-purple-400 hover:text-purple-300 mt-4 p-0 h-auto" onClick={() => setSelectedFilterTags([])}>
                Clear All Filters
            </Button>
         )}
      </div>

      {nudgeBlocks.map((block, index) => (
        <div
            key={block.id}
            className={cn(
                "p-5 rounded-xl mb-8 border shadow-xl transition-all duration-300 relative backdrop-blur-sm",
                block.isSent ? "bg-green-800/30 border-green-700/50" :
                block.isScheduled ? "bg-sky-800/30 border-sky-700/50" :
                "bg-slate-800/60 border-slate-700/70 hover:border-purple-500/50 hover:shadow-purple-500/10"
            )}
        >
            <h2 className="text-xl font-semibold text-slate-200 mb-5 border-b border-slate-700 pb-3">Message Block #{index + 1}</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-5">
                {/* Left Column: Customer Selection & Topic */}
                <div className="space-y-5">
                    <div>
                        <Label className="text-base font-medium text-slate-300 block mb-2">Target Customers <span className="text-sm text-slate-400">({filteredContacts.length} matching)</span></Label>
                        <div className="bg-slate-700/50 rounded-lg p-3 border border-slate-600/60 max-h-48 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/50">
                        {isLoadingContacts ? <Loader2 className="h-5 w-5 animate-spin text-purple-400 mx-auto" /> : filteredContacts.length > 0 ? ( <>
                            <label className="flex items-center text-slate-100 mb-2 font-medium cursor-pointer hover:bg-slate-600/50 p-1.5 rounded-md transition-colors">
                            <input type="checkbox" className="mr-2.5 h-4 w-4 accent-purple-500 bg-slate-800 border-slate-600 rounded focus:ring-purple-500 focus:ring-offset-slate-700"
                                checked={filteredContacts.length > 0 && block.customerIds.length === filteredContacts.length && filteredContacts.every(fc => block.customerIds.includes(fc.id))}
                                ref={el => { if (el) el.indeterminate = block.customerIds.length > 0 && block.customerIds.length < filteredContacts.length; }}
                                onChange={() => handleSelectAllFiltered(index)}
                                disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                            Select All ({block.customerIds.length})
                            </label> <hr className="border-slate-600 my-1.5"/>
                            {filteredContacts.map(c => (
                            <label key={c.id} className="flex items-center text-slate-200 mb-1 cursor-pointer hover:bg-slate-600/50 p-1.5 rounded-md transition-colors text-sm">
                                <input type="checkbox" className="mr-2.5 h-4 w-4 accent-purple-500 bg-slate-800 border-slate-600 rounded focus:ring-purple-500 focus:ring-offset-slate-700"
                                value={c.id} checked={block.customerIds.includes(c.id)}
                                onChange={() => handleCustomerSelectionChange(index, c.id)}
                                disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                                {c.customer_name}
                            </label>))} </>
                        ) : ( <p className="text-slate-400 text-sm text-center py-2"> {selectedFilterTags.length > 0 ? "No opted-in contacts match selected tags." : "No opted-in contacts found."} </p> )}
                        </div>
                    </div>
                    <div>
                        <Label htmlFor={`topic-input-${index}`} className="text-base font-medium text-slate-300 block mb-1.5">AI Topic</Label>
                        <Input id={`topic-input-${index}`} placeholder="e.g., July 4th Promo, New Product Alert"
                            className="bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm"
                            value={block.topic} onChange={e => updateNudgeBlock(index, 'topic', e.target.value)}
                            disabled={block.isSent || block.isScheduled || block.isSending || block.isDrafting} />
                    </div>
                    <Button
                        variant="outline"
                        className="w-full border-sky-600/80 bg-sky-700/20 hover:bg-sky-600/40 text-sky-200 hover:text-sky-100 rounded-md shadow transition-colors group"
                        onClick={() => handleDraft(index)}
                        disabled={!block.topic || !businessId || block.isSent || block.isScheduled || block.isSending || block.isDrafting}
                    >
                        {block.isDrafting ? <Loader2 className="h-5 w-5 mr-2 animate-spin" /> : <Settings2 className="h-5 w-5 mr-2 text-sky-400 group-hover:rotate-45 transition-transform duration-300" />}
                        {block.isDrafting ? "Drafting with AI..." : "Generate Draft with AI"}
                    </Button>
                </div>

                {/* Right Column: Message & Scheduling */}
                <div className="space-y-5">
                    <div>
                        <Label htmlFor={`message-textarea-${index}`} className="text-base font-medium text-slate-300 block mb-1.5">Message Content</Label>
                        <Textarea
                            id={`message-textarea-${index}`}
                            placeholder="AI will generate a draft here, or you can write your own. Use {customer_name} for personalization."
                            className="bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm min-h-[120px] scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/50"
                            value={block.message}
                            onChange={e => updateNudgeBlock(index, 'message', e.target.value)}
                            disabled={block.isSent || block.isScheduled || block.isSending}
                        />
                        <p className="text-xs text-slate-400 mt-1.5 text-right">{block.message.length} characters</p>
                    </div>
                    <div>
                        <Label className="text-base font-medium text-slate-300 block mb-2">Send Options</Label>
                        <div className="flex flex-col sm:flex-row sm:items-center gap-x-4 gap-y-3 p-3 bg-slate-700/50 border border-slate-600/60 rounded-lg">
                            <Label className="text-slate-200 flex items-center gap-2 cursor-pointer">
                                <input type="radio" name={`schedule-option-${index}`}
                                    className="h-4 w-4 accent-pink-500 bg-slate-800 border-slate-600 focus:ring-pink-500 focus:ring-offset-slate-700"
                                    checked={!block.schedule} onChange={() => updateNudgeBlock(index, 'schedule', false)}
                                    disabled={block.isSent || block.isScheduled || block.isSending} /> Send Now
                            </Label>
                            <Label className="text-slate-200 flex items-center gap-2 cursor-pointer">
                                <input type="radio" name={`schedule-option-${index}`}
                                     className="h-4 w-4 accent-purple-500 bg-slate-800 border-slate-600 focus:ring-purple-500 focus:ring-offset-slate-700"
                                    checked={block.schedule} onChange={() => updateNudgeBlock(index, 'schedule', true)}
                                    disabled={block.isSent || block.isScheduled || block.isSending} /> Schedule Later
                            </Label>
                            {block.schedule && (
                                <Input type="datetime-local"
                                    className="bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-1.5 text-sm h-9 sm:ml-auto"
                                    value={block.datetime} onChange={e => updateNudgeBlock(index, 'datetime', e.target.value)}
                                    min={new Date(Date.now() + 60000).toISOString().slice(0, 16)}
                                    disabled={block.isSent || block.isScheduled || block.isSending} required={block.schedule}
                                />
                            )}
                        </div>
                    </div>
                </div>
            </div>

           <div className="flex flex-col sm:flex-row justify-end items-center gap-3 border-t border-slate-700 pt-4 mt-6">
                {block.error && <p className="text-sm text-red-400 mr-auto text-left basis-full sm:basis-auto mb-2 sm:mb-0">{block.error}</p>}
                <div className="flex items-center gap-3 ml-auto">
                    {block.isSent && <span className="text-sm font-semibold px-3 py-1.5 rounded-md bg-green-500/20 text-green-300 flex items-center"><CheckCircle2 size={16} className="mr-1.5"/>Sent</span>}
                    {block.isScheduled && <span className="text-sm font-semibold px-3 py-1.5 rounded-md bg-sky-500/20 text-sky-300 flex items-center"><Clock3 size={16} className="mr-1.5"/>Scheduled</span>}
                    <Button
                        className={cn(
                            "px-5 py-2.5 rounded-lg text-sm font-semibold text-white transition-all duration-200 shadow-md flex items-center justify-center min-w-[160px]",
                            (block.isSent || block.isScheduled) ? 'bg-slate-600 text-slate-400 cursor-not-allowed' :
                            block.schedule ? 'bg-purple-600 hover:bg-purple-700 focus-visible:ring-purple-400' :
                            'bg-pink-600 hover:bg-pink-700 focus-visible:ring-pink-400'
                        )}
                        onClick={() => handleSendOrSchedule(index)}
                        disabled={block.isSent || block.isScheduled || block.isSending || !block.message || block.customerIds.length === 0 || (block.schedule && !block.datetime)}
                    >
                        {block.isSending ? <Loader2 className="h-5 w-5 animate-spin mr-2"/> :
                         block.isSent ? <CheckCircle2 size={18} className="mr-2"/> :
                         block.isScheduled ? <Clock3 size={18} className="mr-2"/> :
                         block.schedule ? <CalendarClock size={18} className="mr-2"/> : <Send size={18} className="mr-2"/>
                        }
                        {block.isSending ? (block.schedule ? "Scheduling..." : "Sending...") :
                         block.isSent ? "Message Sent" :
                         block.isScheduled ? "Message Scheduled" :
                         block.schedule ? "Schedule Nudge" : "Send Nudge Now"}
                    </Button>
                    {!block.isSent && !block.isScheduled && nudgeBlocks.length > 1 && (
                        <Button variant="ghost" size="icon" className="text-slate-400 hover:text-red-400 hover:bg-red-700/20 h-10 w-10 rounded-lg" onClick={() => removeNudgeBlock(index)} title="Remove this message block">
                            <Trash2 size={18}/>
                        </Button>
                    )}
                </div>
           </div>
        </div>
      ))}

      <div className="mt-10 text-center">
        <Button
            id="add-another"
            variant="outline"
            className="text-purple-300 border-2 border-dashed border-purple-500/60 hover:border-purple-400/80 hover:bg-purple-600/10 hover:text-purple-200 rounded-lg px-6 py-3 font-medium transition-all duration-200 group"
            onClick={addNudgeBlock}
        >
          <MessageSquarePlus size={20} className="mr-2 transition-transform duration-300 group-hover:scale-110" /> Add Another Message Block
        </Button>
      </div>
    </div>
    </div>
  );
}