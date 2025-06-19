// frontend/src/components/composer/NudgeComposer.tsx
"use client";

import { useState, useEffect, useMemo } from 'react';
import { apiClient } from '@/lib/api';
import { Customer, Tag, BusinessProfile } from '@/types';
import {
    Loader2, Sparkles, CalendarClock, CheckCircle, XCircle, Edit, AlertCircle,
    Users, Tag as TagIcon, PencilLine, MessageSquare, Send, ChevronDown, ChevronUp
} from 'lucide-react';
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { format, parseISO } from 'date-fns';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

// Interfaces
interface NudgeComposerProps { businessId: number; onClose: () => void; }
interface RoadmapMessageOut { id: number; smsContent: string; smsTiming: string; send_datetime_utc: string; }
interface ComposerRoadmapResponse { customer_id: number; customer_name: string; roadmap_messages: RoadmapMessageOut[]; }
interface BatchRoadmapResponse { status: string; message: string; generated_roadmaps: ComposerRoadmapResponse[]; }
interface NudgeBlock { topic: string; selectedCustomerIds: number[]; selectedFilterTags: Tag[]; selectedLifecycleStage: string | null; }
interface EditableRoadmapMessage { id: number; content: string; send_datetime_utc: string; }
interface InstantNudgeMessage { customer_id: number; content: string; send_datetime_utc: string; }

// Helper component for audience targeting
const AudienceTargetingSection = ({
    availableTags,
    lifecycleStages,
    selectedFilterTags,
    selectedLifecycleStage,
    customerIds,
    handleTagToggle,
    handleLifecycleStageToggle,
    handleSelectAllFiltered,
    handleIndividualCustomerToggle,
    filteredCustomers
}: {
    availableTags: Tag[];
    lifecycleStages: string[];
    selectedFilterTags: Tag[];
    selectedLifecycleStage: string | null;
    customerIds: number[];
    handleTagToggle: (tag: Tag) => void;
    handleLifecycleStageToggle: (stage: string) => void;
    handleSelectAllFiltered: (e: React.ChangeEvent<HTMLInputElement>) => void;
    handleIndividualCustomerToggle: (customerId: number, isChecked: boolean) => void;
    filteredCustomers: Customer[];
}) => {
    const filteredCustomersCount = filteredCustomers.length;
    const selectedCustomersCount = customerIds.length;

    return (
        <div className="space-y-6">
            <h3 className="text-xl font-bold text-slate-200 flex items-center">
                <Users className="w-5 h-5 mr-3 text-purple-400" /> Step 1: Target Your Audience
            </h3>
            {availableTags.length > 0 && (
                <div>
                    <Label className="text-base font-semibold text-slate-300 flex items-center mb-4">
                        <TagIcon className="w-4 h-4 mr-2 text-slate-400" /> Filter by Tags
                    </Label>
                    <div className="flex flex-wrap gap-3">
                        {availableTags.map(tag => (
                            <Button
                                key={tag.id}
                                onClick={() => handleTagToggle(tag)}
                                className={cn(
                                    "transition-all duration-200 rounded-full px-4 py-1.5 text-sm",
                                    selectedFilterTags.some(t => t.id === tag.id)
                                        ? 'bg-purple-600 hover:bg-purple-700 text-white shadow-md'
                                        : 'bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300'
                                )}
                            >
                                {tag.name}
                            </Button>
                        ))}
                    </div>
                </div>
            )}
            <div>
                <Label className="text-base font-semibold text-slate-300 flex items-center mb-4 mt-4">
                    <CalendarClock className="w-4 h-4 mr-2 text-slate-400" /> Filter by Lifecycle Stage
                </Label>
                <div className="flex flex-wrap gap-3">
                    {lifecycleStages.map(stage => (
                        <Button
                            key={stage}
                            onClick={() => handleLifecycleStageToggle(stage)}
                            className={cn(
                                "transition-all duration-200 rounded-full px-4 py-1.5 text-sm",
                                selectedLifecycleStage === stage
                                    ? 'bg-purple-600 hover:bg-purple-700 text-white shadow-md'
                                    : 'bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300'
                            )}
                        >
                            {stage}
                        </Button>
                    ))}
                </div>
            </div>
            <div className="mt-6">
                <Label className="text-base font-semibold text-slate-300 flex items-center mb-4">
                    Select Recipients <span className="ml-2 px-3 py-1 bg-purple-800/40 text-purple-300 rounded-full text-xs font-bold">
                        {selectedCustomersCount}/{filteredCustomersCount}
                    </span>
                </Label>
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 max-h-60 overflow-y-auto custom-scrollbar shadow-inner">
                    <div className="flex items-center pb-3 mb-3 border-b border-slate-700/60">
                        <input
                            type="checkbox"
                            id="selectAll"
                            className="form-checkbox h-4 w-4 text-purple-500 bg-slate-700 border-slate-500 rounded focus:ring-purple-500 cursor-pointer"
                            checked={selectedCustomersCount === filteredCustomersCount && filteredCustomersCount > 0}
                            onChange={handleSelectAllFiltered}
                            aria-label="Select All Filtered Customers"
                        />
                        <Label htmlFor="selectAll" className="ml-3 text-slate-200 font-medium text-base cursor-pointer">
                            Select All Filtered
                        </Label>
                    </div>
                    <div className="space-y-2">
                        {filteredCustomersCount === 0 && <p className="text-slate-400 text-sm text-center py-4">No customers found matching filters.</p>}
                        {filteredCustomers.map(customer => (
                            <div key={customer.id} className="flex items-center py-1">
                                <input
                                    type="checkbox"
                                    id={`customer-${customer.id}`}
                                    className="form-checkbox h-4 w-4 text-purple-500 bg-slate-700 border-slate-500 rounded focus:ring-purple-500 cursor-pointer"
                                    checked={customerIds.includes(customer.id)}
                                    onChange={(e) => handleIndividualCustomerToggle(customer.id, e.target.checked)}
                                    aria-labelledby={`customer-label-${customer.id}`}
                                />
                                <Label id={`customer-label-${customer.id}`} htmlFor={`customer-${customer.id}`} className="ml-3 text-slate-300 text-sm cursor-pointer">
                                    {customer.customer_name}
                                </Label>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};


export default function NudgeComposer({ businessId }: NudgeComposerProps) {
    const [nudgeBlock, setNudgeBlock] = useState<NudgeBlock>({ topic: "", selectedCustomerIds: [], selectedFilterTags: [], selectedLifecycleStage: null });
    const [allOptedInContacts, setAllOptedInContacts] = useState<Customer[]>([]);
    const [availableTags, setAvailableTags] = useState<Tag[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [editableRoadmaps, setEditableRoadmaps] = useState<Record<number, EditableRoadmapMessage[]>>({});
    const [isGeneratingRoadmaps, setIsGeneratingRoadmaps] = useState(false);
    const [roadmapError, setRoadmapError] = useState<string | null>(null);
    const [isScheduling, setIsScheduling] = useState(false);
    const [schedulingSuccess, setSchedulingSuccess] = useState<string | null>(null);
    const [schedulingError, setSchedulingError] = useState<string | null>(null);
    
    const [aiDraftMessage, setAiDraftMessage] = useState<string>('');
    const [instantNudgeScheduleTime, setInstantNudgeScheduleTime] = useState<string>(
        format(new Date(new Date().getTime() + 60 * 1000), "yyyy-MM-dd'T'HH:mm")
    );
    const [expandedCustomers, setExpandedCustomers] = useState<Set<number>>(new Set());

    const lifecycleStages = ["New Lead", "Active Client", "Past Client", "Prospect", "VIP"];

    useEffect(() => {
        if (!businessId) return;
        const fetchData = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const [customersRes, tagsRes] = await Promise.all([
                    apiClient.get<Customer[]>(`/customers/by-business/${businessId}`),
                    apiClient.get<Tag[]>(`/tags/business/${businessId}/tags`),
                ]);
                const optedIn = customersRes.data.filter((c: Customer) => c.opted_in);
                setAllOptedInContacts(optedIn);
                setAvailableTags(tagsRes.data);
                setNudgeBlock(prev => ({ ...prev, selectedCustomerIds: optedIn.map(c => c.id) }));
            } catch (err: any) {
                console.error("Error fetching composer data:", err);
                setError(err.response?.data?.detail || "Failed to load required composer data.");
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, [businessId]);

    const filteredCustomers = useMemo(() => {
        let customers = allOptedInContacts;
        if (nudgeBlock.selectedFilterTags.length > 0) {
            const selectedTagIds = new Set(nudgeBlock.selectedFilterTags.map(t => t.id));
            customers = customers.filter(customer => {
                const customerTagIds = new Set(customer.tags?.map(t => t.id) || []);
                return Array.from(selectedTagIds).every(tagId => customerTagIds.has(tagId));
            });
        }
        if (nudgeBlock.selectedLifecycleStage) {
            customers = customers.filter(customer => customer.lifecycle_stage === nudgeBlock.selectedLifecycleStage);
        }
        return customers;
    }, [nudgeBlock.selectedFilterTags, nudgeBlock.selectedLifecycleStage, allOptedInContacts]);

    useEffect(() => {
        const filteredCustomerIds = new Set(filteredCustomers.map(c => c.id));
        setNudgeBlock(prev => ({
            ...prev,
            selectedCustomerIds: prev.selectedCustomerIds.filter(id => filteredCustomerIds.has(id)),
        }));
    }, [filteredCustomers]);

    const handleTagToggle = (tag: Tag) => {
        setNudgeBlock(prev => {
            const isSelected = prev.selectedFilterTags.some(t => t.id === tag.id);
            const newTags = isSelected
                ? prev.selectedFilterTags.filter(t => t.id !== tag.id)
                : [...prev.selectedFilterTags, tag];
            return { ...prev, selectedFilterTags: newTags };
        });
    };

    const handleLifecycleStageToggle = (stage: string) => {
        setNudgeBlock(prev => ({
            ...prev,
            selectedLifecycleStage: prev.selectedLifecycleStage === stage ? null : stage
        }));
    };

    const handleSelectAllFiltered = (e: React.ChangeEvent<HTMLInputElement>) => {
        setNudgeBlock(prev => ({ ...prev, selectedCustomerIds: e.target.checked ? filteredCustomers.map(c => c.id) : [] }));
    };

    const handleIndividualCustomerToggle = (customerId: number, isChecked: boolean) => {
        setNudgeBlock(prev => ({
            ...prev,
            selectedCustomerIds: isChecked ? [...prev.selectedCustomerIds, customerId] : prev.selectedCustomerIds.filter(id => id !== customerId)
        }));
    };

    const updateTopic = (topic: string) => setNudgeBlock(prev => ({ ...prev, topic }));

    const resetRoadmapStates = () => {
        setEditableRoadmaps({});
        setRoadmapError(null);
        setSchedulingSuccess(null);
        setSchedulingError(null);
        setExpandedCustomers(new Set());
    };

    const handleGenerateAiRoadmapBatch = async () => {
        if (nudgeBlock.selectedCustomerIds.length === 0) return setRoadmapError('No customers selected.');
        setIsGeneratingRoadmaps(true);
        resetRoadmapStates();
        try {
            const response = await apiClient.post<BatchRoadmapResponse>('/composer/generate-roadmap-batch', {
                business_id: businessId,
                customer_ids: nudgeBlock.selectedCustomerIds,
                topic: ""
            });
            if (response.data.status === 'success' && response.data.generated_roadmaps.length > 0) {
                const initialEditableState: Record<number, EditableRoadmapMessage[]> = {};
                const initialExpandedCustomers = new Set<number>();
                response.data.generated_roadmaps.forEach(roadmap => {
                    initialEditableState[roadmap.customer_id] = roadmap.roadmap_messages.map(msg => ({
                        id: msg.id, content: msg.smsContent, send_datetime_utc: msg.send_datetime_utc,
                    }));
                    initialExpandedCustomers.add(roadmap.customer_id);
                });
                setEditableRoadmaps(initialEditableState);
                setExpandedCustomers(initialExpandedCustomers);
                setRoadmapError(null);
            } else {
                setRoadmapError(response.data.message || "The AI did not generate any roadmaps.");
            }
        } catch (err: any) {
            setRoadmapError(err.response?.data?.detail || "An unexpected error occurred.");
        } finally {
            setIsGeneratingRoadmaps(false);
        }
    };

    const handleGenerateOneTimeDraft = async () => {
        if (!nudgeBlock.topic) return setRoadmapError('Please enter a topic to generate a draft.');
        setIsGeneratingRoadmaps(true);
        setAiDraftMessage('');
        setRoadmapError(null);
        setSchedulingSuccess(null);
        setSchedulingError(null);
        try {
            const response = await apiClient.post('/composer/generate-draft', { business_id: businessId, topic: nudgeBlock.topic });
            setAiDraftMessage(response.data.message_draft);
        } catch (err: any) {
            setRoadmapError(err.response?.data?.detail || "Failed to generate AI draft.");
        } finally {
            setIsGeneratingRoadmaps(false);
        }
    };

    const handleSendInstantNudge = async (scheduleNow: boolean) => {
        if (!aiDraftMessage || nudgeBlock.selectedCustomerIds.length === 0) {
            return setSchedulingError(!aiDraftMessage ? "No message to send." : "No customers selected.");
        }
        setIsScheduling(true);
        setSchedulingError(null);
        setSchedulingSuccess(null);
        const messagesToSend: InstantNudgeMessage[] = nudgeBlock.selectedCustomerIds.map(customerId => ({
            customer_id: customerId, content: aiDraftMessage,
            send_datetime_utc: scheduleNow ? new Date().toISOString() : new Date(instantNudgeScheduleTime).toISOString(),
        }));
        try {
            await apiClient.post('/composer/schedule-instant-nudge', { messages: messagesToSend });
            setSchedulingSuccess(`Nudge successfully ${scheduleNow ? "sent" : "scheduled"} to ${messagesToSend.length} customers.`);
            setAiDraftMessage('');
        } catch (err: any) {
            setSchedulingError(err.response?.data?.detail || `Failed to ${scheduleNow ? "send" : "schedule"} nudge.`);
        } finally {
            setIsScheduling(false);
        }
    };

    const formatDisplayTime = (utcIsoString: string) => {
        try {
            const date = parseISO(utcIsoString);
            return new Intl.DateTimeFormat('en-US', {
                weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', hour12: true, timeZoneName: 'short'
            }).format(date);
        } catch (e) { return "Invalid date"; }
    };
    
    const handleRoadmapEdit = (customerId: number, messageId: number, field: 'content' | 'time', value: string) => {
        setEditableRoadmaps(prev => ({
            ...prev,
            [customerId]: prev[customerId].map(msg => msg.id === messageId
                ? { ...msg, [field === 'content' ? 'content' : 'send_datetime_utc']: field === 'time' ? new Date(value).toISOString() : value }
                : msg
            )
        }));
    };

    const handleFinalizeAndSchedule = async () => {
        const messagesToSchedule = Object.values(editableRoadmaps).flat().map(msg => ({ roadmap_message_id: msg.id, content: msg.content, send_datetime_utc: msg.send_datetime_utc }));
        if (messagesToSchedule.length === 0) return setSchedulingError("No messages to schedule.");
        setIsScheduling(true);
        setSchedulingError(null);
        setSchedulingSuccess(null);
        try {
            const response = await apiClient.post('/roadmap-editor/schedule-edited', { edited_messages: messagesToSchedule });
            setSchedulingSuccess(`Successfully scheduled ${response.data.scheduled_count} messages!`);
            if (response.data.failed_count > 0) setSchedulingError(`Could not schedule ${response.data.failed_count} messages.`);
            setEditableRoadmaps({});
        } catch (err: any) {
            setSchedulingError(err.response?.data?.detail || "A critical error occurred during scheduling.");
        } finally {
            setIsScheduling(false);
        }
    };

    const toggleCustomerExpansion = (customerId: number) => {
        setExpandedCustomers(prev => {
            const newSet = new Set(prev);
            if (newSet.has(customerId)) newSet.delete(customerId); else newSet.add(customerId);
            return newSet;
        });
    };

    if (isLoading) return <div className="flex items-center justify-center h-full"><Loader2 className="w-8 h-8 animate-spin text-purple-400" /><p className="ml-4 text-lg">Loading Composer...</p></div>;
    if (error) return <div className="p-8 text-center"><AlertCircle className="w-12 h-12 mx-auto text-red-500" /><h2 className="mt-4 text-xl font-semibold">Error Loading Composer</h2><p className="mt-2 text-red-300 font-mono">{error}</p></div>;

    const audienceProps = {
        availableTags, lifecycleStages, filteredCustomers,
        selectedFilterTags: nudgeBlock.selectedFilterTags,
        selectedLifecycleStage: nudgeBlock.selectedLifecycleStage,
        customerIds: nudgeBlock.selectedCustomerIds,
        handleTagToggle, handleLifecycleStageToggle, handleSelectAllFiltered, handleIndividualCustomerToggle
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
            <h1 className="text-4xl font-extrabold text-white mb-3">AI Nudge Composer</h1>
            <p className="text-lg text-slate-400 mb-10">Select an audience and choose a method to engage them.</p>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
                {/* COLUMN A: Instant Nudge */}
                <Card className="bg-slate-800/80 border-slate-700 text-white shadow-lg">
                    <CardHeader>
                        <CardTitle className="flex items-center text-2xl font-bold text-purple-300">
                            <MessageSquare className="w-6 h-6 mr-3" />Create an Instant Nudge
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <AudienceTargetingSection {...audienceProps} />
                        
                        <div className="border-t border-slate-700/60 my-6"></div>

                        <div className="space-y-4">
                            <h3 className="text-xl font-bold text-slate-200 flex items-center">
                                <PencilLine className="w-5 h-5 mr-3 text-purple-400" /> Step 2: Draft and Send Instant Nudge
                            </h3>
                            <div>
                                <Label htmlFor="instant-nudge-topic" className="text-sm font-medium text-slate-300 mb-2 block">Topic / Goal (for AI draft)</Label>
                                <Input id="instant-nudge-topic" placeholder="e.g., welcome new lead" value={nudgeBlock.topic} onChange={(e) => updateTopic(e.target.value)} className="bg-slate-900 border-slate-600"/>
                            </div>
                            <Textarea placeholder="Click 'Draft with AI' or write your own message..." value={aiDraftMessage} onChange={(e) => setAiDraftMessage(e.target.value)} className="bg-slate-900 border-slate-600 min-h-[100px]" />
                            <div className="flex flex-col sm:flex-row gap-2">
                                <Button onClick={handleGenerateOneTimeDraft} disabled={isGeneratingRoadmaps || !nudgeBlock.topic} className="w-full sm:w-auto"><Sparkles className="h-4 w-4 mr-2" />Draft with AI</Button>
                                <Button onClick={() => handleSendInstantNudge(true)} disabled={!aiDraftMessage || nudgeBlock.selectedCustomerIds.length === 0 || isScheduling} className="w-full sm:w-auto bg-purple-600 hover:bg-purple-700"><Send className="h-4 w-4 mr-2"/>Send Now</Button>
                            </div>
                            <div className="flex flex-col sm:flex-row gap-2 pt-2">
                                <Input type="datetime-local" value={instantNudgeScheduleTime} onChange={(e) => setInstantNudgeScheduleTime(e.target.value)} className="bg-slate-900 border-slate-600" disabled={isScheduling}/>
                                <Button onClick={() => handleSendInstantNudge(false)} disabled={!aiDraftMessage || nudgeBlock.selectedCustomerIds.length === 0 || isScheduling} className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700"><CalendarClock className="h-4 w-4 mr-2"/>Schedule</Button>
                            </div>
                             {(schedulingError || schedulingSuccess) && <p className={`text-sm mt-2 text-center ${schedulingError ? 'text-red-400' : 'text-green-400'}`}>{schedulingError || schedulingSuccess}</p>}
                        </div>
                    </CardContent>
                </Card>

                {/* COLUMN B: Personalized Nudge Plan */}
                <Card className="bg-slate-800/80 border-slate-700 text-white shadow-lg">
                    <CardHeader>
                        <CardTitle className="flex items-center text-2xl font-bold text-purple-300">
                           <Sparkles className="w-6 h-6 mr-3" />Create Personalized Nudge Plan
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <AudienceTargetingSection {...audienceProps} />

                        <div className="border-t border-slate-700/60 my-6"></div>

                        <div className="space-y-4">
                            <h3 className="text-xl font-bold text-slate-200 flex items-center">
                                <Edit className="w-5 h-5 mr-3 text-purple-400" />Step 2: Create and Schedule Nudge Plan
                            </h3>
                            <CardDescription className="text-slate-400 text-sm">Generate a multi-step sequence of messages tailored to each selected customer.</CardDescription>
                            <Button size="lg" className="w-full" onClick={handleGenerateAiRoadmapBatch} disabled={isGeneratingRoadmaps || nudgeBlock.selectedCustomerIds.length === 0}>
                                {isGeneratingRoadmaps ? <Loader2 className="h-5 w-5 mr-2 animate-spin" /> : <Sparkles className="h-5 w-5 mr-2" />}
                                {isGeneratingRoadmaps ? 'Generating Plans...' : `Generate Plans for ${nudgeBlock.selectedCustomerIds.length} Customers`}
                            </Button>
                            {roadmapError && <p className="text-red-400 text-sm text-center">{roadmapError}</p>}
                        </div>

                        {Object.keys(editableRoadmaps).length > 0 && (
                            <div className="space-y-4 pt-4">
                                <div className="text-center">
                                    <h4 className="text-lg font-semibold text-purple-200">Review & Edit Plans</h4>
                                    <p className="text-sm text-slate-400">Fine-tune each message and its timing.</p>
                                </div>
                                <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
                                    {Object.entries(editableRoadmaps).map(([customerId, messages]) => (
                                        <div key={customerId} className="bg-slate-900/70 rounded-lg border border-slate-700">
                                            <button className="w-full flex justify-between items-center p-3 cursor-pointer" onClick={() => toggleCustomerExpansion(parseInt(customerId))}>
                                                <h5 className="font-bold text-base text-slate-100">{allOptedInContacts.find(c => c.id === parseInt(customerId))?.customer_name}</h5>
                                                {expandedCustomers.has(parseInt(customerId)) ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                                            </button>
                                            {expandedCustomers.has(parseInt(customerId)) && (
                                                <div className="p-3 pt-0 space-y-3">
                                                    {messages.map(msg => (
                                                        <div key={msg.id} className="p-3 bg-slate-800/80 rounded border border-slate-600">
                                                            <Textarea value={msg.content} onChange={(e) => handleRoadmapEdit(parseInt(customerId), msg.id, 'content', e.target.value)} className="w-full bg-slate-900 text-sm" />
                                                            <div className="mt-2 grid grid-cols-2 gap-2 items-center">
                                                                <Input type="datetime-local" value={format(parseISO(msg.send_datetime_utc), "yyyy-MM-dd'T'HH:mm")} onChange={(e) => handleRoadmapEdit(parseInt(customerId), msg.id, 'time', e.target.value)} className="w-full bg-slate-900 text-xs p-2" />
                                                                <div className="text-xs text-purple-300 text-center">{formatDisplayTime(msg.send_datetime_utc)}</div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                                <div className="text-center pt-4">
                                    <Button size="lg" className="bg-green-600 hover:bg-green-700" onClick={handleFinalizeAndSchedule} disabled={isScheduling}>
                                        {isScheduling ? <Loader2 className="h-5 w-5 mr-2 animate-spin"/> : <CheckCircle className="h-5 w-5 mr-2"/>}
                                        {isScheduling ? "Scheduling..." : "Confirm & Schedule All"}
                                    </Button>
                                    {(schedulingError || schedulingSuccess) && <p className={`text-sm mt-2 ${schedulingError ? 'text-red-400' : 'text-green-400'}`}>{schedulingError || schedulingSuccess}</p>}
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}