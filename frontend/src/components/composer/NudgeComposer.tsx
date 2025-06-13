// frontend/src/components/composer/NudgeComposer.tsx
"use client";

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { CustomerSummarySchema } from '@/types';
import { Send, Clock, Sparkles, X, Users, MessageSquare, Calendar } from 'lucide-react';

interface NudgeComposerProps {
    businessId: number;
    onClose: () => void; // Function to close the composer (e.g., in a modal)
}

// A simple multi-select component for customers
const CustomerMultiSelect = ({ customers, selected, onSelect }: { customers: CustomerSummarySchema[], selected: number[], onSelect: (ids: number[]) => void }) => {
    const [searchTerm, setSearchTerm] = useState("");
    const filteredCustomers = customers.filter(c => 
        c.customer_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.phone?.includes(searchTerm)
    );

    const handleToggle = (id: number) => {
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
            />
            <div className="max-h-48 overflow-y-auto">
                {filteredCustomers.map(customer => (
                    <div key={customer.id} className="flex items-center p-2 rounded-md hover:bg-gray-700">
                        <input
                            type="checkbox"
                            checked={selected.includes(customer.id)}
                            onChange={() => handleToggle(customer.id)}
                            className="mr-3 h-4 w-4 rounded bg-gray-700 border-gray-500 text-blue-500 focus:ring-blue-600"
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
    // State management
    const [customers, setCustomers] = useState<CustomerSummarySchema[]>([]);
    const [selectedCustomerIds, setSelectedCustomerIds] = useState<number[]>([]);
    const [topic, setTopic] = useState("");
    const [message, setMessage] = useState("");
    const [isGenerating, setIsGenerating] = useState(false);
    const [scheduleOption, setScheduleOption] = useState<'now' | 'later'>('now');
    const [scheduleDate, setScheduleDate] = useState("");
    const [isSending, setIsSending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch customers on component mount
    useEffect(() => {
        const fetchCustomers = async () => {
            if (!businessId) return;
            try {
                console.log(`Fetching customers for business ID: ${businessId}`);
                const response = await apiClient.get<CustomerSummarySchema[]>(`/customers/by-business/${businessId}`);
                setCustomers(response.data);
                console.log(`Successfully fetched ${response.data.length} customers.`);
            } catch (err) {
                console.error("Failed to fetch customers", err);
                setError("Could not load customer list.");
            }
        };
        fetchCustomers();
    }, [businessId]);

    // Handler for generating message draft
    const handleGenerateDraft = async () => {
        if (!topic) return;
        setIsGenerating(true);
        setError(null);
        console.log(`Generating draft for topic: "${topic}"`);
        try {
            const response = await apiClient.post('/composer/generate-draft', { topic });
            setMessage(response.data.message_draft);
            console.log("Draft generated successfully.");
        } catch (err: any) {
            console.error("Draft generation failed:", err);
            setError(err.response?.data?.detail || "Failed to generate draft.");
        } finally {
            setIsGenerating(false);
        }
    };

    // Handler for sending the final message batch
    const handleSendNudge = async () => {
        if (selectedCustomerIds.length === 0 || !message) {
            setError("Please select at least one customer and provide a message.");
            return;
        }
        setIsSending(true);
        setError(null);

        const payload = {
            customer_ids: selectedCustomerIds,
            message: message,
            business_id: businessId,
            send_datetime_iso: scheduleOption === 'later' && scheduleDate ? new Date(scheduleDate).toISOString() : null
        };
        
        console.log("Sending nudge with payload:", payload);
        try {
            await apiClient.post('/instant-nudge/send-batch', payload);
            alert("Nudge sent/scheduled successfully!");
            onClose(); // Close the composer on success
        } catch (err: any) {
            console.error("Failed to send nudge:", err);
            setError(err.response?.data?.detail || "Failed to send nudge.");
        } finally {
            setIsSending(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
            <div className="bg-[#1A1D2D] text-white rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh]">
                <div className="flex justify-between items-center p-4 border-b border-gray-700">
                    <h2 className="text-xl font-bold text-white">Nudge Composer</h2>
                    <button onClick={onClose} className="p-1 rounded-full hover:bg-gray-700"><X size={20} /></button>
                </div>

                <div className="p-6 space-y-6 overflow-y-auto">
                    {error && <div className="bg-red-800 border border-red-600 text-white p-3 rounded-lg text-sm">{error}</div>}

                    {/* Step 1: To */}
                    <div>
                        <label className="flex items-center text-lg font-semibold mb-2 text-gray-200">
                            <Users size={20} className="mr-2 opacity-80" />To:
                        </label>
                        <CustomerMultiSelect customers={customers} selected={selectedCustomerIds} onSelect={setSelectedCustomerIds} />
                        <p className="text-xs text-gray-400 mt-1">{selectedCustomerIds.length} customer(s) selected.</p>
                    </div>

                    {/* Step 2: What */}
                    <div>
                         <label className="flex items-center text-lg font-semibold mb-2 text-gray-200">
                           <MessageSquare size={20} className="mr-2 opacity-80" />What:
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                placeholder="Enter a topic (e.g., 'holiday special', 'new product launch')"
                                value={topic}
                                onChange={e => setTopic(e.target.value)}
                                className="flex-grow bg-gray-800 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                            <button onClick={handleGenerateDraft} disabled={isGenerating || !topic} className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-bold p-3 rounded-lg flex items-center gap-2 transition-colors">
                                <Sparkles size={16} /> {isGenerating ? 'Generating...' : 'Generate'}
                            </button>
                        </div>
                        <textarea
                            placeholder="Your message will appear here..."
                            value={message}
                            onChange={e => setMessage(e.target.value)}
                            rows={5}
                            className="w-full bg-gray-900 p-3 mt-3 rounded-lg border border-gray-600 focus:ring-2 focus:ring-blue-500 outline-none resize-y"
                        />
                    </div>

                    {/* Step 3: When */}
                    <div>
                         <label className="flex items-center text-lg font-semibold mb-2 text-gray-200">
                           <Calendar size={20} className="mr-2 opacity-80" />When:
                        </label>
                        <div className="flex gap-4 p-2 bg-gray-800 rounded-lg">
                            <button onClick={() => setScheduleOption('now')} className={scheduleOption === 'now' ? 'bg-blue-600 text-white font-semibold px-4 py-2 rounded-md w-full' : 'bg-transparent text-gray-300 hover:bg-gray-700 px-4 py-2 rounded-md w-full'}>
                                Send Now
                            </button>
                            <button onClick={() => setScheduleOption('later')} className={scheduleOption === 'later' ? 'bg-blue-600 text-white font-semibold px-4 py-2 rounded-md w-full' : 'bg-transparent text-gray-300 hover:bg-gray-700 px-4 py-2 rounded-md w-full'}>
                                Schedule
                            </button>
                        </div>
                        {scheduleOption === 'later' && (
                            <input
                                type="datetime-local"
                                value={scheduleDate}
                                onChange={e => setScheduleDate(e.target.value)}
                                className="w-full bg-gray-800 p-3 mt-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                        )}
                    </div>
                </div>

                <div className="p-4 border-t border-gray-700 mt-auto">
                    <button onClick={handleSendNudge} disabled={isSending || selectedCustomerIds.length === 0 || !message} className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors">
                        <Send size={18} />
                        {isSending ? 'Sending...' : `Send Nudge to ${selectedCustomerIds.length} Customer(s)`}
                    </button>
                </div>
            </div>
        </div>
    );
}