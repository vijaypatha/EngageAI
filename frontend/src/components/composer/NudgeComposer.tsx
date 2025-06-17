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
interface NudgeBlock { topic: string; customerIds: number[]; selectedFilterTags: Tag[]; selectedLifecycleStage: string | null; }
interface EditableRoadmapMessage { id: number; content: string; send_datetime_utc: string; }

export default function NudgeComposer({ businessId }: NudgeComposerProps) {
    const [nudgeBlock, setNudgeBlock] = useState<NudgeBlock>({ topic: "", customerIds: [], selectedFilterTags: [], selectedLifecycleStage: null });
    const [allOptedInContacts, setAllOptedInContacts] = useState<Customer[]>([]);
    const [availableTags, setAvailableTags] = useState<Tag[]>([]);
    const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [editableRoadmaps, setEditableRoadmaps] = useState<Record<number, EditableRoadmapMessage[]>>({});
    const [isGeneratingRoadmaps, setIsGeneratingRoadmaps] = useState(false);
    const [roadmapError, setRoadmapError] = useState<string | null>(null);
    const [isScheduling, setIsScheduling] = useState(false);
    const [schedulingSuccess, setSchedulingSuccess] = useState<string | null>(null);
    const [schedulingError, setSchedulingError] = useState<string | null>(null);
    const [selectedCustomerIds, setSelectedCustomerIds] = useState<number[]>([]);
    const [aiDraftMessage, setAiDraftMessage] = useState<string>('');
    const [instantNudgeScheduleTime, setInstantNudgeScheduleTime] = useState<string>(
        format(new Date(new Date().getTime() + 60 * 1000), "yyyy-MM-dd'T'HH:mm")
    );
    const [expandedCustomers, setExpandedCustomers] = useState<Set<number>>(new Set());

    const lifecycleStages = ["New Lead", "Active Client", "Past Client", "Prospect", "VIP"]; // Mock stages

    useEffect(() => {
        if (!businessId) return;
        const fetchData = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const [customersRes, tagsRes, businessRes] = await Promise.all([
                    apiClient.get<Customer[]>(`/customers/by-business/${businessId}`),
                    apiClient.get<Tag[]>(`/tags/business/${businessId}/tags`),
                    apiClient.get<BusinessProfile>(`/business-profile/${businessId}`)
                ]);
                const optedIn = customersRes.data.filter((c: Customer) => c.opted_in);
                setAllOptedInContacts(optedIn);
                setAvailableTags(tagsRes.data);
                setBusinessProfile(businessRes.data);
                setSelectedCustomerIds(optedIn.map(c => c.id));
            } catch (err: any) {
                console.error("Error fetching composer data:", err);
                setError(err.response?.data?.detail || "Failed to load required composer data. Please try refreshing the page.");
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
        const currentFilteredIds = new Set(filteredCustomers.map(c => c.id));
        const newSelectedIds = selectedCustomerIds.filter(id => currentFilteredIds.has(id));
        setNudgeBlock(prev => ({ ...prev, customerIds: newSelectedIds }));
    }, [selectedCustomerIds, filteredCustomers]);


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
        if (e.target.checked) {
            setSelectedCustomerIds(filteredCustomers.map(c => c.id));
        } else {
            setSelectedCustomerIds([]);
        }
    };

    const handleIndividualCustomerToggle = (customerId: number, isChecked: boolean) => {
        setSelectedCustomerIds(prev =>
            isChecked ? [...prev, customerId] : prev.filter(id => id !== customerId)
        );
    };

    const updateTopic = (topic: string) => {
        setNudgeBlock(prev => ({ ...prev, topic }));
    }

    const resetComposer = () => {
        setEditableRoadmaps({});
        setRoadmapError(null);
        setSchedulingSuccess(null);
        setSchedulingError(null);
        setAiDraftMessage('');
        setExpandedCustomers(new Set());
    }

    const handleGenerateAiRoadmapBatch = async () => {
        if (nudgeBlock.customerIds.length === 0) {
            return setRoadmapError('No customers selected for roadmap generation. Please adjust your targeting or select recipients.');
        }
        
        setIsGeneratingRoadmaps(true);
        resetComposer();

        try {
            const payload = {
                business_id: businessId,
                customer_ids: nudgeBlock.customerIds,
                topic: "" // Send empty topic as it's no longer 'topic-dependent' for personalized messages
            };
            const response = await apiClient.post<BatchRoadmapResponse>('/composer/generate-roadmap-batch', payload);
            if (response.data.status === 'success' && response.data.generated_roadmaps.length > 0) {
                const initialEditableState: Record<number, EditableRoadmapMessage[]> = {};
                const initialExpandedCustomers = new Set<number>();
                response.data.generated_roadmaps.forEach(roadmap => {
                    initialEditableState[roadmap.customer_id] = roadmap.roadmap_messages.map(msg => ({
                        id: msg.id,
                        content: msg.smsContent,
                        send_datetime_utc: msg.send_datetime_utc,
                    }));
                    initialExpandedCustomers.add(roadmap.customer_id); // Expand all generated roadmaps by default for immediate review
                });
                setEditableRoadmaps(initialEditableState);
                setExpandedCustomers(initialExpandedCustomers);
                setRoadmapError(null);
            } else {
                setRoadmapError(response.data.message || "The AI did not generate any roadmaps.");
            }
        } catch (err: any) {
            setRoadmapError(err.response?.data?.detail || "An unexpected error occurred during generation.");
        } finally {
            setIsGeneratingRoadmaps(false);
        }
    };

    const handleGenerateOneTimeDraft = async () => {
        if (!nudgeBlock.topic) {
            setRoadmapError('Please enter a topic/goal to generate a draft message.');
            return;
        }
        setIsGeneratingRoadmaps(true);
        setAiDraftMessage('');
        try {
            const response = await apiClient.post('/composer/generate-draft', {
                business_id: businessId,
                topic: nudgeBlock.topic
            });
            setAiDraftMessage(response.data.message_draft);
            setRoadmapError(null);
        } catch (err: any) {
            setRoadmapError(err.response?.data?.detail || "Failed to generate AI draft.");
        } finally {
            setIsGeneratingRoadmaps(false);
        }
    };

    const handleSendInstantNudge = async (scheduleNow: boolean) => {
        if (!aiDraftMessage) {
            setSchedulingError("No message draft to send.");
            return;
        }
        if (selectedCustomerIds.length === 0) {
            setSchedulingError("No customers selected to send the nudge to.");
            return;
        }

        setIsScheduling(true);
        setSchedulingError(null);
        setSchedulingSuccess(null);

        const messagesToSend = selectedCustomerIds.map(customerId => {
            const customer = allOptedInContacts.find(c => c.id === customerId);
            const sendTime = scheduleNow ? new Date().toISOString() : new Date(instantNudgeScheduleTime).toISOString();
            return {
                customer_id: customerId,
                content: aiDraftMessage,
                send_datetime_utc: sendTime,
            };
        });

        try {
            console.log(`Simulating ${scheduleNow ? 'sending now' : 'scheduling'} instant nudge to customers:`, messagesToSend);
            await new Promise(resolve => setTimeout(resolve, 1000));
            setSchedulingSuccess(`Successfully ${scheduleNow ? "sent" : "scheduled"} instant nudge to ${messagesToSend.length} customers.`);
            setAiDraftMessage('');
            setInstantNudgeScheduleTime(format(new Date(new Date().getTime() + 60 * 1000), "yyyy-MM-dd'T'HH:mm"));

        } catch (err: any) {
            setSchedulingError(err.response?.data?.detail || `Failed to ${scheduleNow ? "send" : "schedule"} instant nudge.`);
        } finally {
            setIsScheduling(false);
        }
    };

    const formatDisplayTime = (utcIsoString: string, customer?: Customer) => {
        const targetTz = customer?.timezone || businessProfile?.timezone || 'UTC';
        const date = parseISO(utcIsoString);
        const options: Intl.DateTimeFormatOptions = {
            weekday: 'short', month: 'short', day: 'numeric',
            hour: 'numeric', minute: 'numeric', hour12: true,
            timeZone: 'America/Denver', timeZoneName: 'short'
        };
        try { return new Intl.DateTimeFormat('en-US', options).format(date); } catch (e) { return date.toLocaleString(); }
    };
    
    const handleRoadmapEdit = (customerId: number, messageId: number, field: 'content' | 'time', value: string) => {
        setEditableRoadmaps(prev => {
            const newRoadmaps = { ...prev };
            const customerRoadmap = newRoadmaps[customerId].map(msg => {
                if (msg.id === messageId) {
                    if (field === 'content') return { ...msg, content: value };
                    if (field === 'time') return { ...msg, send_datetime_utc: new Date(value).toISOString() };
                }
                return msg;
            });
            newRoadmaps[customerId] = customerRoadmap;
            return newRoadmaps;
        });
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
            setExpandedCustomers(new Set());
        } catch (err: any) {
            setSchedulingError(err.response?.data?.detail || "A critical error occurred during scheduling.");
        } finally {
            setIsScheduling(false);
        }
    };

    const toggleCustomerExpansion = (customerId: number) => {
        setExpandedCustomers(prev => {
            const newSet = new Set(prev);
            if (newSet.has(customerId)) {
                newSet.delete(customerId);
            } else {
                newSet.add(customerId);
            }
            return newSet;
        });
    };


    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-[calc(100vh-150px)] text-white">
                <Loader2 className="w-10 h-10 animate-spin text-purple-400" />
                <p className="ml-4 mt-4 text-lg text-slate-300">Loading Composer Data...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-[calc(100vh-150px)] text-white">
                <div className="text-center p-8 bg-slate-800 border border-red-500/30 rounded-lg max-w-lg">
                    <AlertCircle className="w-12 h-12 mb-4 text-red-500 mx-auto" />
                    <h2 className="text-xl font-semibold text-red-400">Error Loading Composer</h2>
                    <p className="mt-2 text-slate-300">Could not fetch required data for the composer.</p>
                    <p className="mt-4 text-sm bg-red-900/50 p-3 rounded-md text-red-200 font-mono">{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
            <h1 className="text-4xl font-extrabold text-white mb-3">AI Nudge Composer</h1>
            <p className="text-lg text-slate-400 mb-10">Target customers, generate a personalized plan, and schedule it for delivery.</p>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
                {/* Left Column: Target Your Audience - This should be order-1 always */}
                <Card className="bg-slate-800 border-slate-700 text-white p-7 order-1 shadow-lg">
                    <CardHeader className="px-0 pt-0 pb-6">
                        <CardTitle className="flex items-center text-2xl font-bold text-purple-400">
                            <Users className="w-6 h-6 mr-3" /> Target Your Audience
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="px-0 py-0 space-y-8">
                        {/* Filter by Tags */}
                        {availableTags.length > 0 && (
                            <div>
                                <Label className="text-base font-semibold text-slate-200 flex items-center mb-4">
                                    <TagIcon className="w-5 h-5 mr-2 text-slate-400" /> Filter by Tags
                                </Label>
                                <div className="flex flex-wrap gap-3">
                                    {availableTags.map(tag => (
                                        <Button
                                            key={tag.id}
                                            onClick={() => handleTagToggle(tag)}
                                            className={cn(
                                                "transition-all duration-200 rounded-full px-5 py-2 text-base",
                                                nudgeBlock.selectedFilterTags.some(t => t.id === tag.id)
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

                        {/* Filter by Lifecycle Stage (Mock) */}
                        <div>
                            <Label className="text-base font-semibold text-slate-200 flex items-center mb-4 mt-6">
                                <CalendarClock className="w-5 h-5 mr-2 text-slate-400" /> Filter by Lifecycle Stage
                            </Label>
                            <div className="flex flex-wrap gap-3">
                                {lifecycleStages.map(stage => (
                                    <Button
                                        key={stage}
                                        onClick={() => handleLifecycleStageToggle(stage)}
                                        className={cn(
                                            "transition-all duration-200 rounded-full px-5 py-2 text-base",
                                            nudgeBlock.selectedLifecycleStage === stage
                                                ? 'bg-purple-600 hover:bg-purple-700 text-white shadow-md'
                                                : 'bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300'
                                        )}
                                    >
                                        {stage}
                                    </Button>
                                ))}
                            </div>
                        </div>

                        {/* Select Recipients */}
                        <div className="mt-8">
                            <Label className="text-base font-semibold text-slate-200 flex items-center mb-4">
                                Select Recipients <span className="ml-2 px-3 py-1 bg-purple-800/40 text-purple-300 rounded-full text-sm font-bold">
                                    {selectedCustomerIds.length}/{filteredCustomers.length}
                                </span>
                            </Label>
                            <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-h-64 overflow-y-auto custom-scrollbar shadow-inner">
                                <div className="flex items-center pb-4 mb-4 border-b border-slate-700/60">
                                    <input
                                        type="checkbox"
                                        id="selectAll"
                                        className="form-checkbox h-5 w-5 text-purple-500 bg-slate-700 border-slate-500 rounded focus:ring-purple-500 cursor-pointer"
                                        checked={selectedCustomerIds.length === filteredCustomers.length && filteredCustomers.length > 0}
                                        onChange={handleSelectAllFiltered}
                                    />
                                    <Label htmlFor="selectAll" className="ml-3 text-slate-200 font-medium text-lg cursor-pointer">
                                        Select All Filtered
                                    </Label>
                                </div>
                                <div className="space-y-3">
                                    {filteredCustomers.length === 0 && <p className="text-slate-400 text-base text-center py-4">No customers found matching filters.</p>}
                                    {filteredCustomers.map(customer => (
                                        <div key={customer.id} className="flex items-center py-1">
                                            <input
                                                type="checkbox"
                                                id={`customer-${customer.id}`}
                                                className="form-checkbox h-5 w-5 text-purple-500 bg-slate-700 border-slate-500 rounded focus:ring-purple-500 cursor-pointer"
                                                checked={selectedCustomerIds.includes(customer.id)}
                                                onChange={(e) => handleIndividualCustomerToggle(customer.id, e.target.checked)}
                                            />
                                            <Label htmlFor={`customer-${customer.id}`} className="ml-3 text-slate-300 text-base cursor-pointer">
                                                {customer.customer_name}
                                            </Label>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Right Column: Compose Your Nudge & Review - This should be order-2 always */}
                <div className="space-y-8 order-2">
                    <Card className="bg-slate-800 border-slate-700 text-white p-7 shadow-lg">
                        <CardHeader className="px-0 pt-0 pb-6">
                            <CardTitle className="flex items-center text-2xl font-bold text-purple-400">
                                <PencilLine className="w-6 h-6 mr-3" /> Create Instant Nudge
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="px-0 py-0 space-y-8">
                            {/* Action 1: Create Instant Nudge */}
                            <div className="space-y-5 pt-0 border-t-0">
                                <CardDescription className="text-slate-400 text-base leading-relaxed mb-4">
                                    This action is for immediate, one-off communications or for scheduling a single message for one or more contacts
                                </CardDescription>
                                {/* Topic / Goal input moved here */}
                                <div>
                                    <Label htmlFor="instant-nudge-topic" className="text-sm font-medium text-slate-300 mb-2 block">Topic / Goal</Label>
                                    <Input
                                        id="instant-nudge-topic"
                                        placeholder="welcome new contact"
                                        value={nudgeBlock.topic}
                                        onChange={(e) => updateTopic(e.target.value)}
                                        className="bg-slate-900 border-slate-600 text-slate-100 text-base py-2 px-3 h-auto placeholder-slate-500"
                                    />
                                </div>

                                <Textarea
                                    placeholder="AI draft for one-time message..."
                                    value={aiDraftMessage}
                                    onChange={(e) => setAiDraftMessage(e.target.value)}
                                    className="bg-slate-900 border-slate-600 text-slate-200 min-h-[120px] p-4 text-base placeholder-slate-500"
                                />
                                <div className="flex flex-col sm:flex-row items-center gap-3">
                                    <Button
                                        className="w-full sm:w-auto bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300 text-sm px-5 py-3 font-semibold shadow-sm"
                                        onClick={handleGenerateOneTimeDraft}
                                        disabled={isGeneratingRoadmaps || !nudgeBlock.topic}
                                    >
                                        {isGeneratingRoadmaps ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : "Draft"}
                                    </Button>
                                    <Button
                                        className="w-full sm:w-auto bg-purple-600 hover:bg-purple-700 text-white text-sm px-5 py-3 font-semibold shadow-md"
                                        onClick={() => handleSendInstantNudge(true)}
                                        disabled={!aiDraftMessage || selectedCustomerIds.length === 0 || isScheduling}
                                    >
                                        <Send className="h-4 w-4 mr-2"/>Send Nudge Now
                                    </Button>
                                </div>
                                <div className="flex flex-col sm:flex-row items-center gap-3 mt-4">
                                    <Input
                                        type="datetime-local"
                                        value={instantNudgeScheduleTime}
                                        onChange={(e) => setInstantNudgeScheduleTime(e.target.value)}
                                        className="w-full sm:w-auto bg-slate-900 border-slate-600 text-slate-200 p-3 text-base"
                                        disabled={isScheduling}
                                    />
                                    <Button
                                        className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white text-sm px-5 py-3 font-semibold shadow-md"
                                        onClick={() => handleSendInstantNudge(false)}
                                        disabled={!aiDraftMessage || selectedCustomerIds.length === 0 || isScheduling || !instantNudgeScheduleTime}
                                    >
                                        <CalendarClock className="h-4 w-4 mr-2"/>Schedule Nudge
                                    </Button>
                                </div>
                            </div>
                            {/* General success/error messages for instant nudge */}
                            {schedulingError && !schedulingSuccess && <p className="text-red-400 text-sm mt-3 text-center flex items-center justify-center"><XCircle className="mr-2"/>{schedulingError}</p>}
                            {schedulingSuccess && <p className="text-green-400 text-sm mt-3 text-center flex items-center justify-center"><CheckCircle className="mr-2"/>{schedulingSuccess}</p>}
                        </CardContent>
                    </Card>

                    {/* Combined Action 2: Personalized Nudge Plan Editor (Generate & Review) */}
                    <Card className="bg-slate-800 border-slate-700 text-white p-7 shadow-lg">
                        <CardHeader className="px-0 pt-0 pb-6">
                            <CardTitle className="flex items-center text-2xl font-bold text-purple-400">
                                <Sparkles className="w-6 h-6 mr-3" /> Personalized Nudge Plan Editor
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="px-0 py-0 space-y-6">
                            <CardDescription className="text-slate-400 text-base leading-relaxed mb-4">
                                Generate a personalized sequence of messages for each selected customer, crafting a multi-step journey. Review and fine-tune your roadmaps below.
                            </CardDescription>
                            <Button
                                size="lg"
                                className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold text-lg px-8 py-4 shadow-xl"
                                onClick={handleGenerateAiRoadmapBatch}
                                disabled={isGeneratingRoadmaps || selectedCustomerIds.length === 0}
                            >
                                {isGeneratingRoadmaps ? <Loader2 className="h-6 w-6 mr-3 animate-spin" /> : <Sparkles className="h-6 w-6 mr-3" />}
                                {isGeneratingRoadmaps ? 'Generating Roadmaps...' : `Generate Roadmaps for ${nudgeBlock.customerIds.length} Customers`}
                            </Button>
                            {roadmapError && <p className="text-red-400 text-sm mt-3 text-center">{roadmapError}</p>}

                            {/* --- Integrated Roadmap Review Section --- */}
                            {Object.keys(editableRoadmaps).length > 0 && (
                                <div className="mt-8 pt-6 border-t border-slate-700/60">
                                    <div className="text-center mb-6">
                                        <h3 className="text-2xl font-bold text-purple-300 flex items-center justify-center mb-2">
                                            <Edit className="w-6 h-6 mr-3" /> Review & Edit Roadmaps
                                        </h3>
                                        <p className="text-base text-slate-400">Fine-tune each message and its timing.</p>
                                    </div>
                                    <div className="space-y-6 max-h-[70vh] overflow-y-auto pr-3 custom-scrollbar">
                                        {Object.entries(editableRoadmaps).map(([customerId, messages]) => {
                                            const customer = allOptedInContacts.find(c => c.id === parseInt(customerId));
                                            const isExpanded = expandedCustomers.has(parseInt(customerId));
                                            return (
                                                <div key={customerId} className="bg-slate-700/60 rounded-xl border border-slate-600 shadow-inner overflow-hidden">
                                                    <button
                                                        className="w-full flex justify-between items-center p-5 cursor-pointer bg-slate-700 hover:bg-slate-600 transition-colors duration-200"
                                                        onClick={() => toggleCustomerExpansion(parseInt(customerId))}
                                                    >
                                                        <h3 className="font-bold text-xl text-slate-100 flex-grow text-left">{customer?.customer_name || 'Customer'}</h3>
                                                        <span className="text-slate-300 text-lg ml-4">({messages.length} messages)</span>
                                                        {isExpanded ? <ChevronUp className="w-6 h-6 text-purple-300 ml-4" /> : <ChevronDown className="w-6 h-6 text-purple-300 ml-4" />}
                                                    </button>

                                                    {isExpanded && (
                                                        <div className="p-6 pt-0 space-y-5">
                                                            {messages.map((msg) => {
                                                                const localDateTimeForInput = msg.send_datetime_utc ? format(parseISO(msg.send_datetime_utc), "yyyy-MM-dd'T'HH:mm") : "";
                                                                return (
                                                                    <div key={msg.id} className="p-5 bg-slate-800/70 rounded-lg border border-slate-700">
                                                                        <Label htmlFor={`content-${msg.id}`} className="text-sm font-medium text-slate-400 mb-2 block">Message Content</Label>
                                                                        <Textarea id={`content-${msg.id}`} value={msg.content} onChange={(e) => handleRoadmapEdit(parseInt(customerId), msg.id, 'content', e.target.value)} className="w-full bg-slate-900 border-slate-600 text-slate-200 text-base min-h-[80px] p-3" />
                                                                        
                                                                        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
                                                                            <div>
                                                                                <Label htmlFor={`time-${msg.id}`} className="text-sm font-medium text-slate-400 mb-2 block">Schedule Time</Label>
                                                                                <Input id={`time-${msg.id}`} type="datetime-local" value={localDateTimeForInput} onChange={(e) => handleRoadmapEdit(parseInt(customerId), msg.id, 'time', e.target.value)} className="w-full bg-slate-900 border-slate-600 text-slate-200 p-3 text-base" />
                                                                            </div>
                                                                            <div className="md:mt-0 text-base text-purple-300 bg-slate-900/50 p-3 rounded-md border border-slate-700">
                                                                                Scheduled: {formatDisplayTime(msg.send_datetime_utc, customer)}
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                    <div className="mt-8 text-center">
                                        {schedulingSuccess && <p className="text-green-400 mb-4 text-lg flex items-center justify-center"><CheckCircle className="mr-3 w-6 h-6"/>{schedulingSuccess}</p>}
                                        {schedulingError && <p className="text-red-400 mb-4 text-lg flex items-center justify-center"><XCircle className="mr-3 w-6 h-6"/>{schedulingError}</p>}
                                        <Button size="lg" className="bg-green-600 hover:bg-green-700 text-white font-bold text-xl px-10 py-5 shadow-xl" onClick={handleFinalizeAndSchedule} disabled={isScheduling}>
                                            {isScheduling ? <Loader2 className="h-6 w-6 mr-3 animate-spin"/> : <CalendarClock className="h-6 w-6 mr-3"/>}
                                            {isScheduling ? "Scheduling All Roadmaps..." : "Confirm & Schedule All Roadmaps"}
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div> {/* End of combined right column */}
            </div>
        </div>
    );
}