// frontend/src/app/inbox/[business_name]/page.tsx

"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { MessageSquare, AlertCircle, MessageCircle, UserPlus, User, X } from "lucide-react";
import clsx from "clsx";

import { InboxSkeleton } from "@/components/inbox/InboxSkeleton";
import CustomerListItem from "@/components/inbox/CustomerListItem";
import TimelineItem from "@/components/inbox/TimelineItem";
import MessageBox from "@/components/inbox/MessageBox";
import CustomerIntelligencePane from "@/components/inbox/CustomerIntelligencePane";
import InboxFilterBar, { InboxFilterType } from "@/components/inbox/InboxFilterBar";

const processTimelineEntry = (msg: any): any | null => {
  if (!msg.type || typeof msg.id === 'undefined') return null;
  let content: string = "[No Content]";
  try {
    const parsed = JSON.parse(msg.content);
    content = parsed.text || msg.content;
  } catch (e) {
    content = msg.content || "[No Content]";
  }
  return { ...msg, content, timestamp: msg.timestamp || msg.sent_time || msg.scheduled_time || null };
};

export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  // State Management
  const [customerSummaries, setCustomerSummaries] =useState<any[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<any | null>(null);
  const [isNewMessageMode, setIsNewMessageMode] = useState(false);
  const [newlyCreatedCustomerId, setNewlyCreatedCustomerId] = useState<number | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<any[]>([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  
  const [activeFilter, setActiveFilter] = useState<InboxFilterType>('all');
  const [inboxStats, setInboxStats] = useState({ unread: 0, drafts: 0, opportunities: 0 });
  const [isIntelligencePanelOpen, setIntelligencePanelOpen] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  
  // Memoized data fetching functions
  const fetchInboxSummaries = useCallback(async (bId: number) => {
    try {
      const res = await apiClient.get(`/review/inbox/summaries?business_id=${bId}`);
      setCustomerSummaries(res.data.items || []);
      setInboxStats({ unread: res.data.total_unread, drafts: res.data.total_drafts, opportunities: res.data.total_opportunities });
      return res.data.items || [];
    } catch (error) {
      console.error("Failed to fetch inbox summaries:", error);
      setFetchError("Failed to load conversation list.");
    }
  }, []);

  const fetchActiveCustomerHistory = useCallback(async (custId: number) => {
    try {
      const res = await apiClient.get(`/conversations/customer/${custId}`);
      setTimelineEntries(res.data.messages
          .map((msg: any) => processTimelineEntry(msg))
          .filter((entry: any): entry is any => entry !== null)
      );
    } catch (error) {
      console.error(`Failed to fetch history for customer ${custId}:`, error);
      setFetchError("Failed to load conversation history.");
    }
  }, []);

  // --- FIX: Logic to load a customer's data is now in its own function ---
  // This function is the single authority for changing the active conversation state.
  const loadCustomer = useCallback(async (customerId: number) => {
    if (!businessId) return;
    
    // Perform state updates
    setIsNewMessageMode(false);
    setActiveCustomerId(customerId);
    setNewlyCreatedCustomerId(null); 
    setSelectedDraft(null);

    // Optimistically update the UI to show the unread count as 0 immediately
    setCustomerSummaries(prevSummaries => 
      prevSummaries.map(summary => 
        summary.customer_id === customerId 
          ? { ...summary, unread_message_count: 0 } 
          : summary
      )
    );
    
    // Fetch new data in the background
    await fetchActiveCustomerHistory(customerId);
    
    // Mark as read on the server
    apiClient.put(`/conversations/customers/${customerId}/mark-as-read`).catch(err => {
      console.error("Failed to mark as read on server:", err);
    });
    
  }, [businessId, fetchActiveCustomerHistory]);


  // Effect 1: Get the business ID from the URL slug. Runs once.
  useEffect(() => {
    const getBusinessId = async () => {
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        setBusinessId(bizRes.data?.business_id);
      } catch (error) {
        setFetchError("Failed to retrieve business ID.");
      }
    };
    if (business_name) {
      getBusinessId();
    }
  }, [business_name]);

  // Effect 2: Fetch the main conversation list once the business ID is available.
  useEffect(() => {
    if (businessId) {
      setIsLoading(true);
      fetchInboxSummaries(businessId).finally(() => setIsLoading(false));
    }
  }, [businessId, fetchInboxSummaries]);

  // --- FIX: This master useEffect is now the single source of truth for reacting to the URL ---
  // It ensures the application state is always synchronized with the activeCustomer in the URL.
  useEffect(() => {
    const urlCustomerIdStr = searchParams.get('activeCustomer');
    const urlCustomerId = urlCustomerIdStr ? parseInt(urlCustomerIdStr, 10) : null;

    if (urlCustomerId && urlCustomerId !== activeCustomerId) {
      // The URL has changed to a new customer, so we load their data.
      loadCustomer(urlCustomerId);
    } else if (!urlCustomerId && !isNewMessageMode) {
      // The URL has no active customer, so we clear the view.
      setActiveCustomerId(null);
      setTimelineEntries([]);
    }
  }, [searchParams, activeCustomerId, loadCustomer, isNewMessageMode]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries]);
  
  const handleNewMessageClick = () => {
    router.push(`/inbox/${business_name}?new=true`);
    setIsNewMessageMode(true);
    setActiveCustomerId(null);
    setSelectedDraft(null);
    setNewlyCreatedCustomerId(null); 
    setIntelligencePanelOpen(false);
    setTimelineEntries([]);
  };
  
  const handleSendMessage = async (message: string, recipientPhone?: string) => {
    if (!businessId) return;
    
    if (isNewMessageMode) {
      const res = await apiClient.post(`/customers/find-or-create-by-phone`, { phone_number: recipientPhone, business_id: businessId });
      const customerId = res.data.id;
      await apiClient.post(`/conversations/customer/${customerId}/send-message`, { message });
      
      await fetchInboxSummaries(businessId);
      router.push(`/inbox/${business_name}?activeCustomer=${customerId}`);
      setNewlyCreatedCustomerId(customerId);
      setIntelligencePanelOpen(true);
    } else {
      if (!activeCustomerId) return;
      const endpoint = selectedDraft?.ai_draft_id ? `/engagement-workflow/reply/${selectedDraft.ai_draft_id}/send` : `/conversations/customer/${activeCustomerId}/send-message`;
      const payload = selectedDraft?.ai_draft_id ? { updated_content: message } : { message };
      const method = selectedDraft?.ai_draft_id ? 'put' : 'post';

      await apiClient[method](endpoint, payload);
      await fetchInboxSummaries(businessId);
      await fetchActiveCustomerHistory(activeCustomerId);
      setSelectedDraft(null);
    }
  };

  const filteredCustomerSummaries = useMemo(() => {
    if (activeFilter === 'all') return customerSummaries;
    if (activeFilter === 'unread') return customerSummaries.filter(c => c.unread_message_count > 0);
    if (activeFilter === 'drafts') return customerSummaries.filter(c => c.has_draft);
    if (activeFilter === 'opportunities') return customerSummaries.filter(c => c.has_opportunity);
    return customerSummaries;
  }, [customerSummaries, activeFilter]);

  const activeCustomerHeaderDetails = useMemo(() => {
    return customerSummaries.find(cs => cs.customer_id === activeCustomerId);
  }, [customerSummaries, activeCustomerId]);

  if (isLoading) return <InboxSkeleton />;
  if (fetchError) return (
    <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
      <AlertCircle className="w-12 h-12 mb-3 text-red-500" />
      <p className="text-xl font-semibold">Oops! Something went wrong.</p>
      <p className="text-sm mt-1">{fetchError}</p>
    </div>
  );
  
  return (
    <div className="h-screen flex bg-[#0B0E1C] overflow-hidden">
      <aside className="w-80 lg:w-96 bg-[#1A1D2D] border-r border-[#2A2F45] flex flex-col h-full">
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
          <h2 className="text-xl font-semibold text-white">Inbox</h2>
          <button onClick={handleNewMessageClick} className="p-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
            <UserPlus className="w-5 h-5" />
          </button>
        </div>
        <InboxFilterBar stats={inboxStats} activeFilter={activeFilter} onFilterChange={setActiveFilter} totalConversations={customerSummaries.length} />
        <div className="flex-1 overflow-y-auto">
          {filteredCustomerSummaries.map((cs) => (
            <CustomerListItem 
              key={cs.customer_id} 
              summary={cs} 
              isActive={cs.customer_id === activeCustomerId && !isNewMessageMode} 
              // --- FIX: onClick now only changes the URL ---
              onClick={(customerId) => router.push(`/inbox/${business_name}?activeCustomer=${customerId}`)}
            />
          ))}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-[#0F1221] h-full">
        {activeCustomerId && activeCustomerHeaderDetails ? (
          <>
            <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-white">{activeCustomerHeaderDetails.customer_name}</h3>
                <p className="text-xs text-gray-400">{activeCustomerHeaderDetails.phone} - 
                  <span className={clsx("ml-1", activeCustomerHeaderDetails.opted_in ? "text-green-400" : "text-red-400")}>{activeCustomerHeaderDetails.consent_status.replace(/_/g, ' ')}</span>
                </p>
              </div>
              <button onClick={() => setIntelligencePanelOpen(prev => !prev)} className="p-2 rounded-full hover:bg-gray-700">
                {isIntelligencePanelOpen ? <X size={20} /> : <User size={20} />}
              </button>
            </div>
            
            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {timelineEntries.map((entry) => (
                <TimelineItem key={entry.id} entry={entry} onEditDraft={setSelectedDraft} onDeleteDraft={() => {}} onActionClick={() => {}} />
              ))}
            </div>

            <MessageBox
              key={activeCustomerId}
              customer={activeCustomerHeaderDetails}
              onSendMessage={handleSendMessage}
              initialMessage={selectedDraft?.content ?? ""}
              selectedDraftId={selectedDraft?.id ?? null}
              onCancelEdit={() => setSelectedDraft(null)}
            />
          </>
        ) : isNewMessageMode ? (
            <>
              <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0"><h3 className="text-lg font-semibold text-white">New Message</h3></div>
              <div className="flex-1 flex flex-col justify-between"><div className="p-4 text-center text-gray-400">Enter a phone number to start a new conversation.</div>
                <MessageBox onSendMessage={handleSendMessage} selectedDraftId={null} onCancelEdit={() => {}} isNewMessageMode={true} />
              </div>
            </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
            <MessageCircle className="w-16 h-16 mb-4 text-gray-500" /><p className="text-lg">Select a conversation</p><p className="text-sm">Choose a customer from the list to start messaging.</p>
          </div>
        )}
      </main>

      <aside className={clsx("transition-all duration-300 ease-in-out bg-gray-800 h-full overflow-y-auto", isIntelligencePanelOpen && activeCustomerId ? "w-96" : "w-0")}>
        {isIntelligencePanelOpen && activeCustomerId && (
          <CustomerIntelligencePane 
            customerId={activeCustomerId}
            isNewlyCreated={newlyCreatedCustomerId === activeCustomerId}
            key={activeCustomerId}
          />
        )}
      </aside>
    </div>
  );
}