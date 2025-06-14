// frontend/src/components/composer/NudgeComposer.tsx
"use client";

import { useState, useEffect, useCallback, useMemo } from 'react';
import { apiClient } from '@/lib/api';
import { Customer, Tag } from '@/types'; // Import Customer and Tag interfaces
import { Loader2, Info, Trash2, MessageSquarePlus, Settings2, CalendarClock, Send, CheckCircle2, Clock3, Filter, UserX, Eye, Users, MessageSquare } from 'lucide-react'; // All Lucide icons used
import { cn } from "@/lib/utils"; // Used for conditional classes
import { Button } from "@/components/ui/button"; // Assuming you have shadcn/ui Button
import { Input } from "@/components/ui/input"; // Assuming you have shadcn/ui Input
import { Label } from "@/components/ui/label"; // Assuming you have shadcn/ui Label
import { Textarea } from "@/components/ui/textarea"; // Assuming you have shadcn/ui Textarea

interface NudgeComposerProps {
    businessId: number;
    onClose: () => void; // Function to close the composer (e.g., in a modal)
}

// Helper function to estimate SMS segments (simplified)
const getSmsSegments = (text: string): number => {
    if (!text || text.length === 0) return 0;
    const isPotentiallyUnicode = /[^\x00-\x7F\u00A0-\u00FFƏəȘșȚț€]/.test(text);
    if (isPotentiallyUnicode) {
        if (text.length <= 70) return 1;
        return Math.ceil(text.length / 67);
    } else {
        if (text.length <= 160) return 1;
        return Math.ceil(text.length / 153);
    }
};

// Interface for a single Nudge Block
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
  selectedFilterTags: Tag[]; 
  selectedLifecycleStages: string[];
}

// Options for Lifecycle Stage Filter
const LIFECYCLE_STAGES_FILTER_OPTIONS = ["New Lead", "Active Client", "Past Client", "Prospect", "VIP"];


// Customer Multi-Select component (Defined once, outside the main NudgeComposer component)
const CustomerMultiSelect = ({ customers, selected, onSelect, disabled }: { customers: Customer[], selected: number[], onSelect: (ids: number[]) => void, disabled?: boolean }) => {
    const [searchTerm, setSearchTerm] = useState("");
    const filteredCustomers = customers.filter(c => 
        c.customer_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.phone?.includes(searchTerm)
    );

    const handleToggle = (id: number) => {
        if (disabled) return;
        const newSelection = selected.includes(id)
            ? selected.filter(cid => cid !== id)
            : [...selected, id];
        onSelect(newSelection);
    };

    return (
        <div className="border border-gray-600 rounded-lg p-2 bg-gray-900">
            <input 
                type="text"
                placeholder="Search customers..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full bg-gray-800 text-white p-2 rounded-md mb-2 focus:ring-2 focus:ring-blue-500 outline-none"
                disabled={disabled}
            />
            <div className="max-h-48 overflow-y-auto">
                {filteredCustomers.map(customer => (
                    <div key={customer.id} className="flex items-center p-2 rounded-md hover:bg-gray-700">
                        <input
                            type="checkbox"
                            checked={selected.includes(customer.id)}
                            onChange={() => handleToggle(customer.id)}
                            className="mr-3 h-4 w-4 rounded bg-gray-700 border-gray-500 text-blue-500 focus:ring-blue-600"
                            disabled={disabled}
                        />
                        <div className="flex-1">
                            <p className="text-sm font-medium text-white">{customer.customer_name}</p>
                            <p className="text-xs text-gray-400">{customer.phone}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};


export default function NudgeComposer({ businessId, onClose }: NudgeComposerProps) {
    const [nudgeBlocks, setNudgeBlocks] = useState<NudgeBlock[]>([
        { id: crypto.randomUUID(), topic: "", message: "", customerIds: [], schedule: false, datetime: "", selectedFilterTags: [], selectedLifecycleStages: [] }
    ]);
    const [allOptedInContacts, setAllOptedInContacts] = useState<Customer[]>([]);
    const [availableTags, setAvailableTags] = useState<Tag[]>([]);

    const [isLoadingContacts, setIsLoadingContacts] = useState(true);
    const [isLoadingTags, setIsLoadingTags] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!businessId) return;
        let isMounted = true;
        const fetchData = async () => {
            setIsLoadingContacts(true); 
            setIsLoadingTags(true); 
            setError(null);
            try {
                const customersData = await apiClient.get<Customer[]>(`/customers/by-business/${businessId}`); 
                const optedIn = customersData.data.filter(c => c.opted_in === true); 
                if (!isMounted) return;
                setAllOptedInContacts(optedIn);

                const tagsData = await apiClient.get<Tag[]>(`/tags/business/${businessId}/tags`); 
                if (!isMounted) return;
                setAvailableTags(tagsData.data);

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


    const updateNudgeBlock = (index: number, field: keyof NudgeBlock, value: any) => {
        setNudgeBlocks(prev => {
            const copy = [...prev]; 
            const block = { ...copy[index] }; 
            (block as any)[field] = value;
            if (['topic', 'message', 'customerIds', 'schedule', 'datetime'].includes(field as string)) {
                block.isDrafting = false; 
                block.isSending = false; 
                block.isScheduled = false; 
                block.isSent = false; 
                block.error = null;
            }
            copy[index] = block; 
            return copy;
        });
    };

    const handleGenerateDraft = async (index: number) => {
        const block = nudgeBlocks[index];
        if (!block.topic || !businessId) { 
            updateNudgeBlock(index, 'error', 'Topic is required to draft a message.'); 
            return; 
        }
        updateNudgeBlock(index, 'isDrafting', true); 
        updateNudgeBlock(index, 'error', null);
        try {
            const res = await apiClient.post<{ message_draft?: string }>("/composer/generate-draft", { 
                topic: block.topic, 
            });
            if (res.data.message_draft) updateNudgeBlock(index, 'message', res.data.message_draft);
            else throw new Error("AI did not return a message draft. Please try a different topic or write manually.");
        } catch (err: any) { 
            console.error("❌ Draft failed:", err); 
            updateNudgeBlock(index, 'error', err?.response?.data?.detail || "Draft generation failed.");
        } finally { 
            updateNudgeBlock(index, 'isDrafting', false); 
        }
    };

    const handleSendOrSchedule = async (index: number) => {
        const block = nudgeBlocks[index];
        if (!businessId || !block.message || block.customerIds.length === 0) { 
            updateNudgeBlock(index, 'error', 'Message and at least one Recipient are required.'); 
            return; 
        }
        if (block.schedule && !block.datetime) { 
            updateNudgeBlock(index, 'error', 'Please select a date and time for scheduling.'); 
            return; 
        }
        updateNudgeBlock(index, 'isSending', true); 
        updateNudgeBlock(index, 'error', null);
        
        const payload = { 
            customer_ids: block.customerIds, 
            message: block.message, 
            business_id: businessId, 
            send_datetime_utc: block.schedule && block.datetime ? new Date(block.datetime).toISOString() : null 
        };
        
        console.log("Sending nudge with payload:", payload);
        try {
            const res = await apiClient.post<{ status: string; details: any }>("/instant-nudge/send-batch", payload);
            const { details } = res.data;
            if (details) {
                if (details.processed_message_ids) updateNudgeBlock(index, 'processedMessageIds', details.processed_message_ids);
                if (block.schedule) {
                    if (details.scheduled_count > 0 && details.scheduled_count === block.customerIds.length) { 
                        updateNudgeBlock(index, 'isScheduled', true); 
                        updateNudgeBlock(index, 'error', null); 
                    } else if (details.scheduled_count > 0) { 
                        updateNudgeBlock(index, 'isScheduled', true); 
                        updateNudgeBlock(index, 'error', `Scheduled for ${details.scheduled_count}/${block.customerIds.length}. ${details.failed_count > 0 ? `${details.failed_count} failed.` : ''}`); 
                    } else { 
                        updateNudgeBlock(index, 'isScheduled', false); 
                        updateNudgeBlock(index, 'error', `Scheduling failed. ${details.failed_count > 0 ? `${details.failed_count} recipient(s) failed.` : 'No recipients scheduled.'}`);
                    }
                } else { // Instant send
                    if (details.sent_count > 0 && details.sent_count === block.customerIds.length) { 
                        updateNudgeBlock(index, 'isSent', true); 
                        updateNudgeBlock(index, 'error', null); 
                    } else if (details.sent_count > 0) { 
                        updateNudgeBlock(index, 'isSent', true); 
                        updateNudgeBlock(index, 'error', `Sent to ${details.sent_count}/${block.customerIds.length}. ${details.failed_count > 0 ? `${details.failed_count} failed.` : ''}`); 
                    } else { 
                        updateNudgeBlock(index, 'isSent', false); 
                        updateNudgeBlock(index, 'error', `Send failed. ${details.failed_count > 0 ? `${details.failed_count} recipient(s) failed.` : 'Message not sent.'}`);
                    }
                }
            } else { 
                updateNudgeBlock(index, 'error', 'Unexpected response from server.'); 
                if (block.schedule) updateNudgeBlock(index, 'isScheduled', false); 
                else updateNudgeBlock(index, 'isSent', false); 
            }
        } catch (err: any) {
            console.error("❌ Send/Schedule API call failed:", err);
            const errorDetail = err?.response?.data?.detail || "Operation failed. Check connection or server logs.";
            updateNudgeBlock(index, 'error', errorDetail);
            if (block.schedule) updateNudgeBlock(index, 'isScheduled', false); 
            else updateNudgeBlock(index, 'isSent', false);
        } finally { 
            updateNudgeBlock(index, 'isSending', false); 
        }
    };

    // Add/Remove nudge blocks
    const addNudgeBlock = () => setNudgeBlocks(prev => [...prev, { id: crypto.randomUUID(), topic: "", message: "", customerIds: [], schedule: false, datetime: "", selectedFilterTags: [], selectedLifecycleStages: [] }]);
    const removeNudgeBlock = (index: number) => setNudgeBlocks(prev => prev.filter((_, i) => i !== index));

    // Per-block filter handlers
    const handleFilterTagToggle = (blockIndex: number, tag: Tag) => {
        setNudgeBlocks(prevBlocks => {
            const newBlocks = [...prevBlocks];
            const block = { ...newBlocks[blockIndex] };
            const currentTags = new Set(block.selectedFilterTags.map(t => t.id));
            if (currentTags.has(tag.id)) {
                block.selectedFilterTags = block.selectedFilterTags.filter(t => t.id !== tag.id);
            } else {
                block.selectedFilterTags = [...block.selectedFilterTags, tag];
            }
            newBlocks[blockIndex] = block;
            return newBlocks;
        });
    };
    const clearTagFilters = (blockIndex: number) => {
        setNudgeBlocks(prevBlocks => {
            const newBlocks = [...prevBlocks];
            newBlocks[blockIndex] = { ...newBlocks[blockIndex], selectedFilterTags: [] };
            return newBlocks;
        });
    };

    const handleLifecycleStageToggle = (blockIndex: number, stage: string) => {
        setNudgeBlocks(prevBlocks => {
            const newBlocks = [...prevBlocks];
            const block = { ...newBlocks[blockIndex] };
            if (block.selectedLifecycleStages.includes(stage)) {
                block.selectedLifecycleStages = block.selectedLifecycleStages.filter(s => s !== stage);
            } else {
                block.selectedLifecycleStages = [...block.selectedLifecycleStages, stage];
            }
            newBlocks[blockIndex] = block;
            return newBlocks;
        });
    };
    const clearLifecycleFilters = (blockIndex: number) => {
        setNudgeBlocks(prevBlocks => {
            const newBlocks = [...prevBlocks];
            newBlocks[blockIndex] = { ...newBlocks[blockIndex], selectedLifecycleStages: [] };
            return newBlocks;
        });
    };

    // Customer selection handlers (uses blockFilteredContacts)
    const handleSelectAllFiltered = (blockIndex: number) => {
        const block = nudgeBlocks[blockIndex]; 
        const blockFilteredContacts = allOptedInContacts.filter(customer => {
            const customerTagIds = new Set(customer.tags?.map(t => t.id) ?? []);
            const selectedTagIds = new Set(block.selectedFilterTags.map(t => t.id));
            const tagsMatch = block.selectedFilterTags.length === 0 || Array.from(selectedTagIds).every(filterTagId => customerTagIds.has(filterTagId));

            const lifecycleMatch = block.selectedLifecycleStages.length === 0 || (customer.lifecycle_stage && block.selectedLifecycleStages.includes(customer.lifecycle_stage));
            return tagsMatch && lifecycleMatch;
        });

        const allFilteredIds = blockFilteredContacts.map(c => c.id);
        const allSelectedCurrently = block.customerIds.length === allFilteredIds.length && allFilteredIds.every(id => block.customerIds.includes(id));
        updateNudgeBlock(blockIndex, 'customerIds', allSelectedCurrently ? [] : allFilteredIds);
    };

    const handleCustomerSelectionChange = (blockIndex: number, customerId: number) => {
        const block = nudgeBlocks[blockIndex]; 
        const currentIds = new Set(block.customerIds);
        if (currentIds.has(customerId)) currentIds.delete(customerId); 
        else currentIds.add(customerId);
        updateNudgeBlock(blockIndex, 'customerIds', Array.from(currentIds));
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
                    <Info className="h-16 w-16 text-red-500 mx-auto mb-6" />
                    <h2 className="text-2xl font-semibold text-red-400 mb-3">Initialization Error</h2>
                    <p className="text-slate-300 mb-6 bg-red-900/30 border border-red-700/50 p-3 rounded-md">
                        {error}
                    </p>
                    <Button onClick={() => window.location.reload()}
                        className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all">
                        Retry
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-12">
                <header className="text-center mb-10">
                    <h1 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-3">
                        Nudge Composer
                    </h1>
                    <p className="text-slate-400 max-w-2xl mx-auto">
                        Craft and send targeted SMS messages. Filter your audience, personalize your communication, and send now or schedule for later.
                    </p>
                </header>

                <div className="bg-sky-800/20 border border-sky-700/40 rounded-xl p-4 mb-10 text-sm text-sky-200 shadow-lg">
                    <p className="flex items-center"><Info className="h-5 w-5 mr-3 flex-shrink-0 text-sky-400" />
                        <span>Only opted-in contacts are available for selection ({allOptedInContacts.length} total). Filters will apply per message block.</span>
                    </p>
                </div>

                {/* --- Nudge Blocks --- */}
                {nudgeBlocks.map((block, index) => {
                    // Filter contacts for this specific block (moved inside map)
                    const blockFilteredContacts = allOptedInContacts.filter(customer => {
                        const customerTagIds = new Set(customer.tags?.map(t => t.id) ?? []);
                        const selectedTagIds = new Set(block.selectedFilterTags.map(t => t.id));
                        // Customer must have ALL selected tags, or no tags selected means all contacts match tag filter
                        const tagsMatch = block.selectedFilterTags.length === 0 || Array.from(selectedTagIds).every(filterTagId => customerTagIds.has(filterTagId));

                        const lifecycleMatch = block.selectedLifecycleStages.length === 0 || (customer.lifecycle_stage && block.selectedLifecycleStages.includes(customer.lifecycle_stage));
                        return tagsMatch && lifecycleMatch;
                    });

                    const charCount = block.message.length;
                    const segmentCount = getSmsSegments(block.message);
                    let previewName = "[Customer Name]";
                    let sampleCustomerForPreview: Customer | undefined = undefined;

                    if (block.customerIds.length > 0) {
                        sampleCustomerForPreview = blockFilteredContacts.find(c => c.id === block.customerIds[0]);
                    } else if (blockFilteredContacts.length > 0) {
                        sampleCustomerForPreview = blockFilteredContacts[0];
                    }
                    if (sampleCustomerForPreview) {
                        previewName = sampleCustomerForPreview.customer_name;
                    }
                    const personalizedPreview = block.message.replace(/{customer_name}/gi, previewName);

                    return (
                        <div key={block.id} className={cn("p-6 rounded-xl mb-10 border shadow-xl transition-all duration-300 relative backdrop-blur-sm", block.isSent ? "bg-green-800/30 border-green-700/50" : block.isScheduled ? "bg-sky-800/30 border-sky-700/50" : "bg-slate-800/60 border-slate-700/70 hover:border-purple-500/50 hover:shadow-purple-500/10")}>
                            <h2 className="text-xl font-semibold text-slate-100 mb-6 border-b border-slate-700 pb-4 flex justify-between items-center">
                                <span>Message Block #{index + 1}</span>
                                {nudgeBlocks.length > 1 && !block.isSent && !block.isScheduled && (
                                    <Button variant="ghost" size="icon" className="text-slate-400 hover:text-red-400 hover:bg-red-700/20 rounded-lg h-9 w-9" onClick={() => removeNudgeBlock(index)} title="Remove this message block">
                                        <Trash2 size={18}/>
                                    </Button>
                                )}
                            </h2>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6">
                                {/* FIRST TILE: "To" Section */}
                                <div className="space-y-6 p-4 rounded-lg bg-slate-700/50 border border-slate-600/70 shadow-inner">
                                    <h3 className="text-lg font-semibold text-slate-100 mb-3 flex items-center"><Users size={20} className="mr-2 opacity-80" />To:</h3>
                                    
                                    {/* Tag Filter - PER BLOCK */}
                                    <div>
                                        <Label className="block text-sm font-medium text-slate-300 mb-2">Filter by Tags <span className="text-slate-400 text-xs">(contacts must have ALL selected tags)</span></Label>
                                        {isLoadingTags ? <Loader2 className="h-5 w-5 animate-spin text-purple-400" /> : availableTags.length > 0 ? (
                                            <div className="flex flex-wrap gap-2">
                                                {availableTags.map(tag => {
                                                    const isSelected = block.selectedFilterTags.some(t => t.id === tag.id);
                                                    return (<Button key={tag.id} variant="outline" size="sm" onClick={() => handleFilterTagToggle(index, tag)}
                                                        className={cn("rounded-full text-xs font-medium px-3.5 py-1.5 h-auto transition-all", isSelected ? "bg-purple-600 border-purple-500 text-white hover:bg-purple-700" : "bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500")}>{tag.name}</Button>);
                                                })}
                                            </div>
                                        ) : ( <p className="text-slate-400 text-sm italic">No tags available for this business.</p> )}
                                        {block.selectedFilterTags.length > 0 && (<Button variant="link" size="sm" className="text-xs text-purple-400 hover:text-purple-300 mt-2.5 p-0 h-auto" onClick={() => clearTagFilters(index)}>Clear Tag Filters</Button> )}
                                    </div>

                                    {/* Lifecycle Stage Filter - PER BLOCK */}
                                    <div>
                                        <label className="block text-sm font-medium text-slate-300 mb-2">Filter by Lifecycle Stage <span className="text-slate-400 text-xs">(contacts must be in ANY selected stage)</span></label>
                                        {LIFECYCLE_STAGES_FILTER_OPTIONS.length > 0 ? (
                                            <div className="flex flex-wrap gap-2">
                                                {LIFECYCLE_STAGES_FILTER_OPTIONS.map(stage => {
                                                    const isSelected = block.selectedLifecycleStages.includes(stage);
                                                    return (<Button key={stage} variant="outline" size="sm" onClick={() => handleLifecycleStageToggle(index, stage)}
                                                        className={cn("rounded-full text-xs font-medium px-3.5 py-1.5 h-auto transition-all", isSelected ? "bg-purple-600 border-purple-500 text-white hover:bg-purple-700" : "bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500")}>{stage}</Button>);
                                                })}
                                            </div>
                                        ) : ( <p className="text-slate-400 text-sm italic">No lifecycle stages defined for filtering.</p> )}
                                        {block.selectedLifecycleStages.length > 0 && (<Button variant="link" size="sm" className="text-xs text-purple-400 hover:text-purple-300 mt-2.5 p-0 h-auto" onClick={() => clearLifecycleFilters(index)}>Clear Lifecycle Filters</Button> )}
                                    </div>

                                    {/* Customer Selection for this block (uses blockFilteredContacts) */}
                                    <div>
                                        <Label className="text-base font-medium text-slate-200 block mb-2">Select Recipients <span className="text-sm text-slate-400">({blockFilteredContacts.length} matching filters)</span></Label>
                                        <div className="bg-slate-800/60 rounded-lg p-3.5 border border-slate-700/70 max-h-52 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-500 scrollbar-track-slate-700">
                                            {isLoadingContacts ? <div className="flex justify-center items-center h-20"><Loader2 className="h-6 w-6 animate-spin text-purple-400" /></div> :
                                             blockFilteredContacts.length > 0 ? (
                                                <>
                                                    <label className="flex items-center text-slate-100 mb-2.5 font-medium cursor-pointer hover:bg-slate-600/60 p-2 rounded-md transition-colors">
                                                    <input type="checkbox" className="mr-3 h-4 w-4 accent-purple-500 bg-slate-800 border-slate-500 rounded focus:ring-purple-500 focus:ring-offset-slate-700"
                                                        checked={blockFilteredContacts.length > 0 && block.customerIds.length === blockFilteredContacts.length && blockFilteredContacts.every(fc => block.customerIds.includes(fc.id))}
                                                        ref={el => { if (el) el.indeterminate = block.customerIds.length > 0 && block.customerIds.length < blockFilteredContacts.length; }}
                                                        onChange={() => handleSelectAllFiltered(index)} disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                                                    Select All ({block.customerIds.length})
                                                    </label> <hr className="border-slate-600/80 my-2"/>
                                                    {blockFilteredContacts.map(c => (
                                                    <label key={c.id} className="flex items-center text-slate-200 mb-1.5 cursor-pointer hover:bg-slate-600/60 p-2 rounded-md transition-colors text-sm">
                                                        <input type="checkbox" className="mr-3 h-4 w-4 accent-purple-500 bg-slate-800 border-slate-500 rounded focus:ring-purple-500 focus:ring-offset-slate-700"
                                                        value={c.id} checked={block.customerIds.includes(c.id)}
                                                        onChange={() => handleCustomerSelectionChange(index, c.id)} disabled={block.isSent || block.isScheduled || isLoadingContacts} />
                                                        {c.customer_name}
                                                    </label>))}
                                                </>
                                            ) : ( 
                                                <div className="text-center py-8 text-slate-400 flex flex-col items-center justify-center h-full">
                                                    <UserX className="h-14 w-14 text-slate-500 mb-4" />
                                                    <p className="text-sm font-semibold text-slate-300">No Contacts Match Filters</p>
                                                    <p className="text-xs mt-1">Adjust filters or check global contact list.</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* SECOND TILE: "What" Section */}
                                <div className="space-y-6 p-4 rounded-lg bg-slate-700/50 border border-slate-600/70 shadow-inner">
                                    <h3 className="text-lg font-semibold text-slate-100 mb-3 flex items-center"><MessageSquare size={20} className="mr-2 opacity-80" />What:</h3>
                                    {/* AI Topic field */}
                                    <div>
                                        <Label htmlFor={`topic-input-${index}`} className="text-base font-medium text-slate-200 block mb-1.5">AI Topic <span className="text-xs text-slate-400">(for message generation)</span></Label>
                                        <Input id={`topic-input-${index}`} placeholder="e.g., Holiday Special, Appointment Reminder"
                                            className="bg-slate-800 border-slate-700 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm py-2.5 px-3"
                                            value={block.topic} onChange={e => updateNudgeBlock(index, 'topic', e.target.value)} disabled={block.isSent || block.isScheduled || block.isSending || block.isDrafting} />
                                    </div>
                                    <Button variant="outline" className="w-full py-2.5 border-sky-500/70 bg-sky-600/20 hover:bg-sky-600/40 text-sky-200 hover:text-sky-100 rounded-md shadow-md transition-colors group text-sm font-semibold"
                                        onClick={() => handleGenerateDraft(index)} disabled={!block.topic || !businessId || block.isSent || block.isScheduled || block.isSending || block.isDrafting}>
                                        {block.isDrafting ? <Loader2 className="h-5 w-5 mr-2 animate-spin" /> : <Settings2 className="h-5 w-5 mr-2 text-sky-300 group-hover:rotate-45 transition-transform duration-300" />}
                                        {block.isDrafting ? "Drafting with AI..." : "Generate Draft with AI"}
                                    </Button>

                                    {/* Message Content & Preview */}
                                    <div>
                                        <Label htmlFor={`message-textarea-${index}`} className="text-base font-medium text-slate-200 block mb-1.5">Message Content</Label>
                                        <Textarea id={`message-textarea-${index}`} placeholder="AI draft will appear here, or write your own. Use {customer_name} for personalization."
                                            className="bg-slate-800 border-slate-700 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm min-h-[140px] p-3 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/50"
                                            value={block.message} onChange={e => updateNudgeBlock(index, 'message', e.target.value)} disabled={block.isSent || block.isScheduled || block.isSending} />
                                        <p className="text-xs text-slate-400 mt-2 text-right">
                                            Chars: {charCount} | Segments: {segmentCount}
                                        </p>
                                    </div>

                                    {(block.message.includes("{customer_name}") || block.message.includes("{{customer_name}}")) && (
                                        <div>
                                            <Label className="text-sm font-medium text-purple-300 block mb-1.5 flex items-center"><Eye size={16} className="mr-2"/>Live Preview</Label>
                                            <div className="bg-slate-800/40 p-3 rounded-md text-slate-200 text-sm border border-slate-700/50 min-h-[50px] whitespace-pre-wrap shadow-inner">
                                                {personalizedPreview || <span className="italic text-slate-400">Type message & select customer to see preview...</span>}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                            
                            {/* THIRD TILE: "When" Section - Always full width below the two columns */}
                            <div className="mt-6 p-4 rounded-lg bg-slate-700/50 border border-slate-600/70 shadow-inner"> 
                                <h3 className="text-lg font-semibold text-slate-100 mb-3 flex items-center"><CalendarClock size={20} className="mr-2 opacity-80" />When:</h3>
                                <div className="flex flex-col sm:flex-row sm:items-center gap-x-6 gap-y-3 p-3.5 bg-slate-800/60 border border-slate-700/70 rounded-lg shadow-sm">
                                    <Label className="text-slate-100 flex items-center gap-2.5 cursor-pointer">
                                        <input type="radio" name={`schedule-option-${index}`} className="h-4 w-4 accent-pink-500 bg-slate-800 border-slate-500 focus:ring-pink-500 focus:ring-offset-slate-700 rounded-sm" checked={!block.schedule} onChange={() => updateNudgeBlock(index, 'schedule', false)} disabled={block.isSent || block.isScheduled || block.isSending} /> Send Now
                                    </Label>
                                    <Label className="text-slate-100 flex items-center gap-2.5 cursor-pointer">
                                        <input type="radio" name={`schedule-option-${index}`} className="h-4 w-4 accent-purple-500 bg-slate-800 border-slate-500 focus:ring-purple-500 focus:ring-offset-slate-700 rounded-sm" checked={block.schedule} onChange={() => updateNudgeBlock(index, 'schedule', true)} disabled={block.isSent || block.isScheduled || block.isSending} /> Schedule Later
                                    </Label>
                                    {block.schedule && (
                                        <Input type="datetime-local" className="bg-slate-800 border-slate-700 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-2 text-sm h-9 sm:ml-auto" value={block.datetime} onChange={e => updateNudgeBlock(index, 'datetime', e.target.value)} min={new Date(Date.now() + 60000).toISOString().slice(0, 16)} disabled={block.isSent || block.isScheduled || block.isSending} required={block.schedule} />
                                    )}
                                </div>
                            </div>

                            {/* Actions and Status */}
                            <div className="flex flex-col sm:flex-row justify-end items-center gap-x-4 gap-y-2 border-t border-slate-700/80 pt-5 mt-8">
                                {block.error && <p className="text-sm text-red-400 mr-auto text-left basis-full sm:basis-auto mb-2 sm:mb-0 pr-2">{block.error}</p>}
                                <div className="flex items-center gap-3 ml-auto">
                                    {block.isSent && <span className="text-sm font-semibold px-3 py-1.5 rounded-md bg-green-500/20 text-green-300 flex items-center"><CheckCircle2 size={16} className="mr-1.5"/>Sent</span>}
                                    {block.isScheduled && <span className="text-sm font-semibold px-3 py-1.5 rounded-md bg-sky-500/20 text-sky-300 flex items-center"><Clock3 size={16} className="mr-1.5"/>Scheduled</span>}
                                    <Button className={cn("px-6 py-2.5 rounded-lg text-sm font-semibold text-white transition-all duration-200 shadow-md flex items-center justify-center min-w-[170px]", (block.isSent || block.isScheduled) ? 'bg-slate-500 text-slate-300 cursor-not-allowed' : block.schedule ? 'bg-purple-600 hover:bg-purple-700 focus-visible:ring-purple-400' : 'bg-pink-600 hover:bg-pink-700 focus-visible:ring-pink-400')}
                                        onClick={() => handleSendOrSchedule(index)} disabled={block.isSent || block.isScheduled || block.isSending || !block.message || block.customerIds.length === 0 || (block.schedule && !block.datetime)}>
                                        {block.isSending ? <Loader2 className="h-5 w-5 animate-spin mr-2"/> : block.isSent ? <CheckCircle2 size={18} className="mr-2"/> : block.isScheduled ? <Clock3 size={18} className="mr-2"/> : block.schedule ? <CalendarClock size={18} className="mr-2"/> : <Send size={18} className="mr-2"/>}
                                        {block.isSending ? (block.schedule ? "Scheduling..." : "Sending...") : block.isSent ? "Message Sent" : block.isScheduled ? "Message Scheduled" : block.schedule ? "Schedule Nudge" : "Send Nudge Now"}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    );
                })}

                <div className="mt-12 text-center">
                    <Button id="add-another" variant="outline" className="text-purple-300 border-2 border-dashed border-purple-500/60 hover:border-purple-400/80 hover:bg-purple-600/10 hover:text-purple-200 rounded-lg px-6 py-3 font-medium transition-all duration-200 group" onClick={addNudgeBlock}>
                        <MessageSquarePlus size={20} className="mr-2 transition-transform duration-300 group-hover:scale-110" /> Add Another Message Block
                    </Button>
                </div>
            </div>
        </div>
    );
}