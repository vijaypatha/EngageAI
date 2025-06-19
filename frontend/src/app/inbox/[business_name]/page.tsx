// frontend/src/app/inbox/[business_name]/page.tsx
"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, AlertCircle, User, X, Loader2, Menu, UserPlus } from "lucide-react";
import clsx from 'clsx';

// Layout and Component Imports
import { Navigation } from "@/components/Navigation";
import { InboxSkeleton } from "@/components/inbox/InboxSkeleton";
import CustomerListItem from "@/components/inbox/CustomerListItem";
import TimelineItem from "@/components/inbox/TimelineItem";
import MessageBox from "@/components/inbox/MessageBox";
import { CustomerIntelligencePane } from "@/components/inbox/CustomerIntelligencePane";
import InboxFilterBar, { InboxFilterType } from "@/components/inbox/InboxFilterBar";
import { StartConversationFlow } from "@/components/inbox/StartConversationFlow";
import { TimelineEntry } from "@/types";

// --- Type Definitions ---
interface BusinessProfile {
  id: number;
  business_name: string;
  representative_name: string;
}

// --- Helper Functions ---
// FIX: Using the exact function you provided.
const processTimelineEntry = (msg: any): TimelineEntry | null => {
    if (!msg || typeof msg.id === 'undefined') return null;
    let content = msg.content || "[No Content]";
    if (typeof content === 'string' && content.startsWith('{')) {
        try { const parsed = JSON.parse(content); content = parsed.text || content; } catch (e) {}
    }
    return {
        id: msg.id, type: msg.type || msg.message_type, content: content,
        customer_id: msg.customer_id,
        timestamp: msg.timestamp || msg.created_at, status: msg.status,
        ai_response: msg.ai_response, ai_draft_id: msg.ai_draft_id,
        contextual_action: msg.contextual_action, is_faq_answer: msg.is_faq_answer || false,
        appended_opt_in_prompt: msg.appended_opt_in_prompt || false,
    };
};

// --- Main Inbox Page Component ---
export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  // --- State Management ---
  const [customerSummaries, setCustomerSummaries] = useState<any[]>([]);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<InboxFilterType>('all');
  const [inboxStats, setInboxStats] = useState({ unread: 0, drafts: 0, opportunities: 0 });
  const [isIntelligencePanelOpen, setIntelligencePanelOpen] = useState(false);
  const [isNewlyCreatedCustomer, setIsNewlyCreatedCustomer] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isStartFlowOpen, setIsStartFlowOpen] = useState(false); // State to control the visibility of the "Start Conversation Flow" modal

  const chatContainerRef = useRef<HTMLDivElement>(null);

  // --- Data Fetching & Actions ---
  const fetchInboxSummaries = useCallback(async (bId: number) => {
    try {
      const res = await apiClient.get(`/review/inbox/summaries?business_id=${bId}`);
      setCustomerSummaries(res.data.items || []);
      setInboxStats({ unread: res.data.total_unread, drafts: res.data.total_drafts, opportunities: res.data.total_opportunities });
    } catch (error) { console.error("Failed to fetch inbox summaries:", error); setFetchError("Failed to load conversation list."); }
  }, []);

  const fetchActiveCustomerHistory = useCallback(async (custId: number) => {
    setIsHistoryLoading(true);
    try {
      const res = await apiClient.get(`/conversations/customer/${custId}`);
      const processedEntries = res.data.messages.map(processTimelineEntry).filter((entry: TimelineEntry | null): entry is TimelineEntry => entry !== null);
      setTimelineEntries(processedEntries);
    } catch (error) {
      console.error(`Failed to fetch history for customer ${custId}:`, error);
      setFetchError("Failed to load conversation history.");
      setTimelineEntries([]);
    } finally { setIsHistoryLoading(false); }
  }, []);

  const loadCustomer = useCallback(async (customerId: number, isNew: boolean = false) => {
    if (!businessProfile?.id) return;
    setActiveCustomerId(customerId);
    setIsNewlyCreatedCustomer(isNew);
    setIsSidebarOpen(false); 
    if (isNew) setIntelligencePanelOpen(true);
    setCustomerSummaries(prev => prev.map(s => s.customer_id === customerId ? { ...s, unread_message_count: 0 } : s));
    await fetchActiveCustomerHistory(customerId);
    apiClient.put(`/conversations/customers/${customerId}/mark-as-read`).catch(err => console.error("Mark as read failed:", err));
  }, [businessProfile?.id, fetchActiveCustomerHistory]);

  // --- Lifecycle Effects ---
  useEffect(() => {
    if (business_name) {
      apiClient.get(`/business-profile/navigation-profile/slug/${business_name}`)
        .then(res => setBusinessProfile(res.data))
        .catch(err => { console.error("Business profile fetch error:", err); setFetchError("Failed to retrieve business profile."); });
    }
  }, [business_name]);

  useEffect(() => {
    if (businessProfile?.id) {
      setIsLoading(true);
      fetchInboxSummaries(businessProfile.id).finally(() => setIsLoading(false));
    }
  }, [businessProfile, fetchInboxSummaries]);

  useEffect(() => {
    const urlCustomerIdStr = searchParams.get('activeCustomer');
    const newCustomerFlag = searchParams.get('newContact');
    const urlCustomerId = urlCustomerIdStr ? parseInt(urlCustomerIdStr, 10) : null;
    if (urlCustomerId && urlCustomerId !== activeCustomerId) {
      loadCustomer(urlCustomerId, newCustomerFlag === 'true');
    }
  }, [searchParams, activeCustomerId, loadCustomer]);
  
  useEffect(() => {
    if (chatContainerRef.current) chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
  }, [timelineEntries]);

  // --- Event Handlers ---
  const handleSendMessage = async (message: string) => {
    if (!businessProfile?.id || !activeCustomerId) return;
    const endpoint = selectedDraft?.ai_draft_id ? `/engagement-workflow/reply/${selectedDraft.ai_draft_id}/send` : `/conversations/customer/${activeCustomerId}/send-message`;
    const payload = selectedDraft?.ai_draft_id ? { updated_content: message } : { message };
    const method = selectedDraft?.ai_draft_id ? 'put' : 'post';
    await apiClient[method](endpoint, payload);
  };
  
  const handleMessageSent = () => {
    if (businessProfile?.id && activeCustomerId) {
        fetchInboxSummaries(businessProfile.id);
        fetchActiveCustomerHistory(activeCustomerId);
        setSelectedDraft(null);
    }
  };

  const handleNewConversationClick = () => {
    setIsStartFlowOpen(true);
    setActiveCustomerId(null);
    setIntelligencePanelOpen(false);
    router.push(`/inbox/${business_name}`);
  }

  const activeCustomerHeaderDetails = useMemo(() => customerSummaries.find(cs => cs.customer_id === activeCustomerId), [customerSummaries, activeCustomerId]);

  if (isLoading) return <InboxSkeleton />;
  if (fetchError) return <div className="h-screen flex items-center justify-center bg-slate-900 text-red-400"><AlertCircle className="w-8 h-8 mr-2" />{fetchError}</div>;

  return (
    // FIX: The main layout is now structured correctly. Navigation is a sibling to the main content area.
    <div className="h-screen w-full bg-slate-900 text-slate-200">
        <Navigation />
        
        {/* FIX: The md:pl-64 class is applied to the container of the inbox content, not the root. */}
        <div className="h-full md:pl-2"> {/* padding from 64 to 2 */}
          <div className="flex h-full">
            {isSidebarOpen && <div className="fixed inset-0 bg-black/60 z-30 md:hidden" onClick={() => setIsSidebarOpen(false)}></div>}

            {/* Conversation List Sidebar */}
            <aside className={clsx(
                "fixed md:static top-0 bottom-0 z-40 w-full max-w-xs md:w-80 lg:w-96 bg-slate-800 border-r border-slate-700 flex flex-col h-full transition-transform duration-300 ease-in-out",
                isSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
            )}>
                <div className="flex justify-between items-center p-4 border-b border-slate-700 shrink-0">
                    <h2 className="text-xl font-semibold text-white">Inbox</h2>
                    <div className="flex items-center gap-2">
                        <button onClick={handleNewConversationClick} className="p-2 rounded-full hover:bg-slate-700 text-slate-300" title="New Conversation">
                            <UserPlus size={20} />
                        </button>
                        <button className="md:hidden text-slate-300" onClick={() => setIsSidebarOpen(false)}><X size={24} /></button>
                    </div>
                </div>
                <InboxFilterBar stats={inboxStats} activeFilter={activeFilter} onFilterChange={setActiveFilter} totalConversations={customerSummaries.length} />
                <div className="flex-1 overflow-y-auto aai-scrollbars-dark">
                    {customerSummaries.map((cs) => (
                        <CustomerListItem key={cs.customer_id} summary={cs} isActive={cs.customer_id === activeCustomerId} onClick={(id) => router.push(`/inbox/${business_name}?activeCustomer=${id}`)} />
                    ))}
                </div>
            </aside>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col h-full">
                {activeCustomerId && activeCustomerHeaderDetails ? (
                    <div className="flex flex-1 min-h-0">
                        <main className="flex-1 flex flex-col h-full">
                            <header className="p-3 bg-slate-800 border-b border-slate-700 shrink-0 flex justify-between items-center">
                                <div className="flex items-center gap-2">
                                    <button className="md:hidden text-slate-300" onClick={() => setIsSidebarOpen(true)}><Menu size={24} /></button>
                                    <div>
                                        <h3 className="text-md font-semibold text-white">{activeCustomerHeaderDetails.customer_name}</h3>
                                        <p className="text-xs text-slate-400">{activeCustomerHeaderDetails.phone}</p>
                                    </div>
                                </div>
                                <button onClick={() => setIntelligencePanelOpen(p => !p)} className="p-2 rounded-full hover:bg-slate-700 text-slate-300" title="Customer Intelligence">
                                    {isIntelligencePanelOpen ? <X size={20} /> : <User size={20} />}
                                </button>
                            </header>
                            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-slate-900">
                                {isHistoryLoading ? <div className="flex-1 flex items-center justify-center"><Loader2 className="animate-spin text-cyan-400" /></div> : timelineEntries.map((entry) => (
                                    <TimelineItem key={`${entry.id}-${entry.timestamp}`} entry={entry} onEditDraft={setSelectedDraft} onDeleteDraft={() => {}} onActionClick={() => {}} />
                                ))}
                            </div>
                            <MessageBox
                                key={activeCustomerId} customer={activeCustomerHeaderDetails}
                                onSendMessage={handleSendMessage} initialMessage={selectedDraft?.ai_response ?? ""}
                                selectedDraftId={selectedDraft?.ai_draft_id ?? null} onCancelEdit={() => setSelectedDraft(null)}
                                onMessageSent={handleMessageSent}
                            />
                        </main>

                        {/* Allow CustomerIntelligencePane to manage its own "No customer selected" state */}
                        <aside className={clsx("transition-all duration-300 ease-in-out bg-slate-800/80 backdrop-blur-sm h-full overflow-y-auto shrink-0 border-l border-slate-700", isIntelligencePanelOpen ? "w-full md:w-80 lg:w-96 absolute right-0 top-0 md:static z-20" : "w-0 hidden")}></aside>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-500 p-4 text-center">
                        <button className="md:hidden text-slate-300 absolute top-4 left-4" onClick={() => setIsSidebarOpen(true)}><Menu size={24} /></button>
                        <MessageSquare className="w-16 h-16 mb-4" />
                        <h3 className="text-lg font-semibold text-slate-300">Select a conversation</h3>
                        <p className="text-sm max-w-xs">Choose a customer from the list to view your message history.</p>
                    </div>
                )}
            </div>
          </div>
        </div>
        
        {/* Floating Action Button (FAB) for Add Customer */}
        <button
            onClick={() => setIsStartFlowOpen(true)} // Toggles the visibility of the StartConversationFlow modal
            className="fixed bottom-6 right-6 bg-blue-600 hover:bg-blue-700 text-white p-4 rounded-full shadow-lg flex items-center justify-center transition-colors z-50"
            title="Add New Customer"
        >
            <UserPlus size={24} />
        </button>

        {isStartFlowOpen && businessProfile && (
            <StartConversationFlow
                businessId={businessProfile.id}
                businessName={businessProfile.business_name}
                representativeName={businessProfile.representative_name}
                onClose={() => setIsStartFlowOpen(false)}
                onConversationStarted={(id) => router.push(`/inbox/${business_name}?activeCustomer=${id}&newContact=true`)}
            />
        )}
    </div>
  );
}