'use client';

// Removed NEXT_PUBLIC_BACKEND_URL fallback as per previous discussion and api.ts update
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
import React, { useState, useEffect, useCallback, useMemo, use, FC } from 'react';
import {
  StarIcon,
  AlertTriangleIcon,
  Loader2,
  UserCircle2,
  ChevronDownIcon,
  ChevronUpIcon,
  XCircle,
  CheckCircle2Icon,
  Send,
  SparklesIcon,
  CalendarClockIcon,
  LightbulbIcon,
  TrendingUpIcon,
  ArrowRight,
  MessageSquare,
  XIcon,
} from 'lucide-react';
import { useRouter } from 'next/navigation';

// Card Components
import SentimentSpotlightCard, { CoPilotNudge } from '@/components/SentimentSpotlightCard';
import PotentialTimedCommitmentCard from '@/components/PotentialTimedCommitmentCard';
import EngagementPlanCard from '@/components/EngagementPlanCard';
import GrowthOpportunityCard from '@/components/GrowthOpportunityCard';

// --- Interface Definitions ---
interface ResolvedPageParams {
  business_name: string;
}
interface CoPilotPageProps {
  params: Promise<ResolvedPageParams>;
}
interface CustomerSentimentGroup {
  customer_name: string | null | undefined;
  customer_id: number | null | undefined;
  nudges: CoPilotNudge[];
  positive_count: number;
  negative_count: number;
}
interface GroupedNudgesMap {
  [customerIdKey: string]: CustomerSentimentGroup;
}
type NotificationInfo = {
  id: number;
  type: 'success' | 'error';
  title: string;
  message: string;
  linkAction?: () => void;
  linkText?: string;
}

// Props for Sub-Components
type NotificationBannersProps = { notifications: NotificationInfo[], onDismiss: (id: number) => void };
type PageHeaderProps = { businessName: string };
type ErrorMessageProps = { message: string };
type ActionCenterProps = {
  nudges: CoPilotNudge[];
  isLoading: boolean;
  setAllActiveNudges: React.Dispatch<React.SetStateAction<CoPilotNudge[]>>;
  setIsActionLoading: React.Dispatch<React.SetStateAction<number | string | null>>;
  addNotification: (notif: Omit<NotificationInfo, 'id'>) => void;
  businessSlug: string;
  businessId: number | null; // Pass businessId down
};
type SentimentSectionProps = Omit<ActionCenterProps, 'isLoading' | 'nudges'> & { groupedNudges: GroupedNudgesMap };
type GrowthSectionProps = Omit<ActionCenterProps, 'businessSlug'> & {
  isActionLoading: number | string | null;
  businessSlug: string;
  businessId: number | null; // Pass businessId down
};
// --- End Interface Definitions ---

const CoPilotPage: FC<CoPilotPageProps> = ({ params: paramsProp }) => {
  const resolvedParams = use(paramsProp);

  if (!resolvedParams || typeof resolvedParams.business_name !== 'string') {
    return <PageLoader />;
  }

  const { business_name: businessSlug } = resolvedParams;
  const router = useRouter();

  // --- State Management ---
  const [allActiveNudges, setAllActiveNudges] = useState<CoPilotNudge[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState<number | string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeBusinessDisplayName, setActiveBusinessDisplayName] = useState<string>('');
  const [businessId, setBusinessId] = useState<number | null>(null); // New state for business ID
  const [notifications, setNotifications] = useState<NotificationInfo[]>([]);

  // --- Utility Functions ---
  const addNotification = useCallback((notif: Omit<NotificationInfo, 'id'>) => {
    const newNotif = { ...notif, id: Date.now() };
    setNotifications(prev => [...prev, newNotif]);
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== newNotif.id));
    }, 8000);
  }, []);

  // --- Data Fetching and Effects ---

  // Effect to fetch business_id and display name first
  useEffect(() => {
    const fetchBusinessDetails = async () => {
      setIsLoading(true); // Start loading when fetching business details
      try {
        const res = await fetch(`${API_BASE_URL}/business-profile/business-id/slug/${businessSlug}`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          setBusinessId(data.business_id); // Set the business ID
          // Fetch navigation profile for display name, but don't block
          fetch(`${API_BASE_URL}/business-profile/navigation-profile/slug/${businessSlug}`, { credentials: 'include' })
            .then(navRes => navRes.json())
            .then(navData => setActiveBusinessDisplayName(navData.business_name || decodeURIComponent(businessSlug)))
            .catch(navErr => {
              console.warn("Could not fetch business name by slug (navigation profile)", navErr);
              setActiveBusinessDisplayName(decodeURIComponent(businessSlug));
            });
        } else {
          // If business ID not found, set error and default display name
          setError('Business not found or invalid slug.');
          setActiveBusinessDisplayName(decodeURIComponent(businessSlug));
          setBusinessId(null); // Ensure businessId is null on error
          addNotification({ type: 'error', title: 'Business Not Found', message: 'The specified business could not be loaded.' });
        }
      } catch (e) {
        console.error("Error fetching business ID by slug", e);
        setError('Failed to load business details. Please try again.');
        setActiveBusinessDisplayName(decodeURIComponent(businessSlug));
        setBusinessId(null);
        addNotification({ type: 'error', title: 'Loading Error', message: 'Could not fetch business details.' });
      } finally {
        // Keep loading true until nudges are fetched or initial error is final
      }
    };
    if (businessSlug) {
      fetchBusinessDetails();
    }
  }, [businessSlug, addNotification]);


  // fetchNudges now depends on businessId
  const fetchNudges = useCallback(async (id: number, showLoadingIndicator = true) => {
    if (showLoadingIndicator) setIsLoading(true); // Only show loading if explicitly requested
    setError(null); // Clear previous errors
    try {
      // MODIFIED: Added business_id as a query parameter
      const response = await fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges?business_id=${id}`, { credentials: 'include' });
      if (!response.ok) {
        throw new Error((await response.json()).detail || `Failed to fetch nudges for business ID ${id}`);
      }
      const data: CoPilotNudge[] = await response.json();
      setAllActiveNudges(data.filter(nudge => nudge.status === 'active'));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred.';
      setError(errorMessage);
      addNotification({ type: 'error', title: 'Failed to Load', message: errorMessage });
      setAllActiveNudges([]);
    } finally {
      if (showLoadingIndicator) setIsLoading(false);
    }
  }, [addNotification]);

  // Effect to fetch nudges once businessId is available
  useEffect(() => {
    if (businessId !== null) { // Only fetch nudges if businessId has been successfully resolved
      fetchNudges(businessId);
    } else if (!isLoading && !error && businessSlug) {
      // If businessId is null and not loading (meaning initial business details fetch failed),
      // ensure loading is false and error is shown.
      setIsLoading(false);
    }
  }, [businessId, fetchNudges, isLoading, error, businessSlug]);


  // --- Memoized Grouping Logic ---
  const { actionableNudges, growthNudges, groupedSentimentNudges, noActiveNudgesOfAnyType } = useMemo(() => {
    const actionable = allActiveNudges.filter(n => n.nudge_type === 'potential_targeted_event' || n.nudge_type === 'strategic_engagement_opportunity');
    const sentiment = allActiveNudges.filter(n => n.nudge_type === 'sentiment_positive' || n.nudge_type === 'sentiment_negative');
    const growth = allActiveNudges.filter(n => n.nudge_type === 'goal_opportunity');
    const groupedSentiment = sentiment.reduce((acc, nudge) => {
      const key = String(nudge.customer_id);
      if (!acc[key]) {
        acc[key] = { customer_id: nudge.customer_id, customer_name: nudge.customer_name, nudges: [], positive_count: 0, negative_count: 0 };
      }
      acc[key].nudges.push(nudge);
      if (nudge.nudge_type === 'sentiment_positive') acc[key].positive_count += 1;
      if (nudge.nudge_type === 'sentiment_negative') acc[key].negative_count += 1;
      return acc;
    }, {} as GroupedNudgesMap);

    // Consider all types of nudges for "no nudges" message
    const noNudges = !isLoading && actionable.length === 0 && sentiment.length === 0 && growth.length === 0;

    return { actionableNudges: actionable, growthNudges: growth, groupedSentimentNudges: groupedSentiment, noActiveNudgesOfAnyType: noNudges };
  }, [allActiveNudges, isLoading]);

  // Render a loader if businessId is still null and we're in the initial loading phase for it
  if (businessId === null && isLoading && !error) {
    return <PageLoader />;
  }
  // Render an error message if businessId is null and there was an error
  if (error && businessId === null) {
    return (
        <div className="flex-1 bg-slate-900 text-slate-100 min-h-screen font-sans flex items-center justify-center p-4">
            <ErrorMessage message={error} />
        </div>
    );
  }


  return (
    <div className="flex-1 bg-slate-900 text-slate-100 min-h-screen font-sans">
      <NotificationBanners notifications={notifications} onDismiss={id => setNotifications(p => p.filter(n => n.id !== id))} />
      <div className="max-w-screen-2xl mx-auto p-4 sm:p-6 md:p-8">
        <PageHeader businessName={activeBusinessDisplayName} />
        {error && <ErrorMessage message={error} />}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
          <main className="lg:col-span-2 space-y-12">
            <ActionCenter
              nudges={actionableNudges}
              isLoading={isLoading && actionableNudges.length === 0}
              setAllActiveNudges={setAllActiveNudges}
              setIsActionLoading={setIsActionLoading}
              addNotification={addNotification}
              businessSlug={businessSlug}
              businessId={businessId} // Pass businessId down
            />
          </main>
          <aside className="lg:col-span-1 space-y-12">
            <SentimentSection
              groupedNudges={groupedSentimentNudges}
              setAllActiveNudges={setAllActiveNudges}
              setIsActionLoading={setIsActionLoading}
              addNotification={addNotification}
              businessSlug={businessSlug}
              businessId={businessId} // Pass businessId down
            />
            <GrowthSection
              nudges={growthNudges}
              isLoading={isLoading && growthNudges.length === 0}
              isActionLoading={isActionLoading}
              setAllActiveNudges={setAllActiveNudges}
              setIsActionLoading={setIsActionLoading}
              addNotification={addNotification}
              businessSlug={businessSlug}
              businessId={businessId} // Pass businessId down
            />
          </aside>
        </div>

        {noActiveNudgesOfAnyType && <AllClearMessage />}
      </div>
    </div>
  );
};

// --- Sub-Components ---

const PageLoader: FC = () => (
  <div className="flex-1 bg-slate-900 text-slate-100 min-h-screen font-sans flex items-center justify-center p-4">
    <div className="text-center">
      <Loader2 className="animate-spin h-10 w-10 text-purple-400 mx-auto mb-4" />
      <h1 className="text-xl sm:text-2xl font-bold text-slate-300">Loading Page Data...</h1>
    </div>
  </div>
);

const NotificationBanners: FC<NotificationBannersProps> = ({ notifications, onDismiss }) => (
  <div className="fixed top-4 right-4 z-50 w-full max-w-sm space-y-3">
    {notifications.map(notif => {
      const isSuccess = notif.type === 'success';
      const bgColor = isSuccess ? 'bg-green-600/95' : 'bg-red-600/95';
      const iconColor = 'text-white';
      return (
        <div key={notif.id} className={`relative text-white p-4 rounded-lg shadow-xl flex items-start backdrop-blur-sm transition-all duration-300 animate-in fade-in slide-in-from-top-4 ${bgColor}`}>
          <div className={`flex-shrink-0 w-6 h-6 mr-3 mt-0.5 ${iconColor}`}>
            {isSuccess ? <CheckCircle2Icon /> : <AlertTriangleIcon />}
          </div>
          <div className="text-sm flex-grow">
            <p className="font-bold">{notif.title}</p>
            <p className="text-white/80">
              {notif.message}{' '}
              {notif.linkAction && (
                <button onClick={notif.linkAction} className="font-semibold underline hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-white/50 rounded">
                  {notif.linkText}
                </button>
              )}
            </p>
          </div>
          <button onClick={() => onDismiss(notif.id)} className="absolute top-1 right-1 p-1 rounded-full hover:bg-black/20 transition-colors">
            <XIcon className="w-4 h-4" />
          </button>
        </div>
      );
    })}
  </div>
);

const PageHeader: FC<PageHeaderProps> = ({ businessName }) => (
  <header className="mb-8 sm:mb-10">
    <h1 className="text-4xl md:text-5xl font-bold mb-1 text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500">
      AI Nudge Co-Pilot
    </h1>
    <p className="text-base text-slate-400">
      {businessName ? `Insights for ${businessName}` : 'Your intelligent partner for growth.'}
    </p>
  </header>
);

const ErrorMessage: FC<ErrorMessageProps> = ({ message }) => (
  <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-4 rounded-lg mb-8 flex items-center gap-3">
    <AlertTriangleIcon className="w-6 h-6 flex-shrink-0" />
    <div>
      <h3 className="font-bold">Error Loading Data</h3>
      <p className="text-sm">{message}</p>
    </div>
  </div>
);

const ActionCenter: FC<ActionCenterProps> = ({ nudges, isLoading, setAllActiveNudges, setIsActionLoading, addNotification, businessSlug, businessId }) => {
  const router = useRouter();
  const [expandedActionItems, setExpandedActionItems] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (nudges.length > 0 && !expandedActionItems[nudges[0].id]) {
      setExpandedActionItems(prev => ({ ...prev, [nudges[0].id]: true }));
    }
  }, [nudges, expandedActionItems]);

  const handleToggleActionItemExpansion = (nudgeId: number) => {
    setExpandedActionItems(prev => ({ ...prev, [nudgeId]: !prev[nudgeId] }));
  };

  const handleDismiss = useCallback(async (nudgeId: number) => {
    if (businessId === null) {
      addNotification({ type: 'error', title: 'Action Failed', message: 'Business ID not available for this action.' });
      return;
    }
    setIsActionLoading(nudgeId);
    try {
      // NOTE: Dismiss still requires authentication and business_id on backend
      const res = await fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}), credentials: 'include' });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed to dismiss');
      setAllActiveNudges(prev => prev.filter(n => n.id !== nudgeId));
      addNotification({ type: 'success', title: 'Dismissed', message: 'The suggestion has been dismissed.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Dismissal Failed', message: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsActionLoading(null);
    }
  }, [setIsActionLoading, setAllActiveNudges, addNotification, businessId]);

  const handleActivatePlan = useCallback(async (nudgeId: number, customerId: number, finalMessages: any[]) => {
    if (businessId === null) {
      addNotification({ type: 'error', title: 'Action Failed', message: 'Business ID not available for this action.' });
      return;
    }
    setIsActionLoading(nudgeId);
    try {
      // NOTE: Activate Plan still requires authentication
      const response = await fetch(`${API_BASE_URL}/follow-up-plans/activate-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: customerId, messages: finalMessages }), credentials: 'include' });
      if (!response.ok) throw new Error((await response.json()).detail || 'Failed to activate plan');
      const nudge = nudges.find(n => n.id === nudgeId);
      addNotification({ type: 'success', title: `Plan for ${nudge?.customer_name || 'customer'} activated!`, message: 'You can view the messages on your Nudge Plans page.', linkAction: () => router.push(`/${businessSlug}/nudge-plans`), linkText: 'View Plans' });
      setAllActiveNudges(prev => prev.filter(n => n.id !== nudgeId));
    } catch (err) {
      addNotification({ type: 'error', title: 'Activation Failed', message: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsActionLoading(null);
    }
  }, [setIsActionLoading, setAllActiveNudges, addNotification, nudges, router, businessSlug, businessId]);

  const handleConfirmEvent = useCallback(async (nudgeId: number, confirmedDatetimeUtc: string, confirmedPurpose: string) => {
    if (businessId === null) {
      addNotification({ type: 'error', title: 'Action Failed', message: 'Business ID not available for this action.' });
      return;
    }
    setIsActionLoading(nudgeId);
    try {
      // NOTE: Confirm Event still requires authentication
      const response = await fetch(`${API_BASE_URL}/targeted-events/confirm-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed_datetime_utc: confirmedDatetimeUtc, confirmed_purpose: confirmedPurpose }), credentials: 'include' });
      if (!response.ok) throw new Error((await response.json()).detail || 'Failed to confirm event');
      const nudge = nudges.find(n => n.id === nudgeId);
      addNotification({ type: 'success', title: `Event for ${nudge?.customer_name || 'customer'} confirmed!`, message: 'Reminders will be sent automatically.' });
      setAllActiveNudges(prev => prev.filter(n => n.id !== nudgeId));
    } catch (err) {
      addNotification({ type: 'error', title: 'Confirmation Failed', message: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsActionLoading(null);
    }
  }, [setIsActionLoading, setAllActiveNudges, addNotification, nudges, businessId]);

  const handleViewConversation = useCallback((nudge: CoPilotNudge) => {
    if (nudge.customer_id && businessSlug) {
      router.push(`/inbox/${businessSlug}?activeCustomer=${nudge.customer_id}&engagementId=${nudge.id}`);
    } else {
      addNotification({ type: 'error', title: 'Cannot View Conversation', message: 'Nudge is not associated with a specific customer.' });
    }
  }, [router, businessSlug, addNotification]);

  return (
    <section>
      <h2 className="text-3xl font-semibold mb-5 text-slate-100 flex items-center">
        <SparklesIcon className="w-8 h-8 mr-3 text-yellow-400 opacity-90" />
        Action Center
        {nudges.length > 0 &&
          <span className="ml-4 bg-yellow-500/20 text-yellow-300 text-sm font-semibold px-3 py-1 rounded-full">
            {nudges.length}
          </span>
        }
      </h2>
      {isLoading && <div className="text-center py-10"><Loader2 className="animate-spin h-8 w-8 text-purple-400 mx-auto" /></div>}
      {!isLoading && nudges.length === 0 && (
        <div className="text-center py-12 bg-slate-800/50 rounded-lg border border-slate-700/60">
          <CheckCircle2Icon className="h-14 w-14 text-green-400/90 mx-auto mb-4" />
          <p className="text-slate-200 text-lg font-semibold">No immediate actions needed!</p>
          <p className="text-slate-400">Co-Pilot is monitoring for new opportunities.</p>
        </div>
      )}

      <div className="space-y-6">
        {nudges.map((nudge) => {
          const isEvent = nudge.nudge_type === 'potential_targeted_event';
          const isExpanded = expandedActionItems[nudge.id] || false;
          const accentGradient = isEvent ? "from-sky-500/60 to-blue-600/60" : "from-purple-500/60 to-pink-600/60";
          const iconToShow = isEvent ? <CalendarClockIcon className="w-8 h-8" /> : <LightbulbIcon className="w-8 h-8" />;

          return (
            <div key={nudge.id} className={`bg-slate-800/70 backdrop-blur-sm border border-slate-700 rounded-2xl shadow-2xl overflow-hidden transition-all duration-300 ${isExpanded ? 'ring-2 ring-purple-500' : 'ring-0 ring-transparent'}`}>
              <div className="p-5">
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className={`w-16 h-16 rounded-xl flex-shrink-0 flex items-center justify-center text-white bg-gradient-to-br ${accentGradient} shadow-lg`}>{iconToShow}</div>
                    <div className="min-w-0">
                      <p className="text-xs uppercase tracking-wider font-semibold text-purple-300">{isEvent ? "Potential Appointment" : "Follow-up Plan"}</p>
                      <h3 className="text-2xl font-bold text-slate-50 truncate">{nudge.customer_name}</h3>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button onClick={() => handleViewConversation(nudge)} className="p-2 text-slate-400 rounded-full hover:bg-slate-700 hover:text-white transition-colors" title="View Conversation"><MessageSquare className="w-5 h-5" /></button>
                    <button onClick={() => handleDismiss(nudge.id)} className="p-2 text-slate-400 rounded-full hover:bg-slate-700 hover:text-red-400 transition-colors" title="Dismiss Nudge"><XCircle className="w-5 h-5" /></button>
                  </div>
                </div>
                <div className="mt-5 flex flex-col sm:flex-row items-center justify-between gap-4 p-4 bg-slate-900/50 rounded-lg">
                  <p className="text-slate-300 text-sm italic text-center sm:text-left">"{nudge.message_snippet}"</p>
                  <button onClick={() => handleToggleActionItemExpansion(nudge.id)} className="flex-shrink-0 w-full sm:w-auto bg-gradient-to-r from-purple-500 to-pink-500 text-white font-semibold px-6 py-3 rounded-lg shadow-lg hover:scale-105 transition-transform duration-200 flex items-center justify-center">
                    {isEvent ? "Confirm Appointment" : "Review Plan"}
                    <ArrowRight className="w-5 h-5 ml-2" />
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="bg-slate-900/70 p-4 sm:p-6 border-t border-slate-700/50">
                  {isEvent ? (
                    <PotentialTimedCommitmentCard nudge={nudge} onConfirm={handleConfirmEvent} onDismiss={() => handleDismiss(nudge.id)} onViewConversation={handleViewConversation} />
                  ) : (
                    <EngagementPlanCard nudge={nudge} onActivatePlan={handleActivatePlan} onDismiss={() => handleDismiss(nudge.id)} onViewConversation={handleViewConversation} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};

const SentimentSection: FC<SentimentSectionProps> = ({ groupedNudges, setAllActiveNudges, setIsActionLoading, addNotification, businessSlug, businessId }) => {
  const router = useRouter();
  const [expandedSentimentCustomers, setExpandedSentimentCustomers] = useState<Record<string, boolean>>({});

  const handleDismiss = useCallback(async (nudgeId: number) => {
    if (businessId === null) {
      addNotification({ type: 'error', title: 'Action Failed', message: 'Business ID not available for this action.' });
      return;
    }
    setIsActionLoading(nudgeId);
    try {
      // NOTE: Dismiss still requires authentication
      const res = await fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}), credentials: 'include' });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed to dismiss');
      setAllActiveNudges(prev => prev.filter(n => n.id !== nudgeId));
      addNotification({ type: 'success', title: 'Dismissed', message: 'The sentiment insight has been dismissed.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Dismissal Failed', message: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsActionLoading(null);
    }
  }, [setIsActionLoading, setAllActiveNudges, addNotification, businessId]);

  const handleViewConversation = useCallback((nudge: CoPilotNudge) => {
    if (nudge.customer_id && businessSlug) {
      router.push(`/inbox/${businessSlug}?activeCustomer=${nudge.customer_id}&engagementId=${nudge.id}`);
    } else {
      addNotification({ type: 'error', title: 'Cannot View Conversation', message: 'Nudge is not associated with a specific customer.' });
    }
  }, [router, businessSlug, addNotification]);

  return (
    <section>
      <h2 className="text-2xl font-semibold mb-4 text-slate-100 border-b-2 border-slate-700 pb-2 flex items-center">
        Customer Sentiment
      </h2>
      <div className="space-y-4">
        {Object.entries(groupedNudges).map(([customerIdKey, group]: [string, CustomerSentimentGroup]) => {
          const isExpanded = expandedSentimentCustomers[customerIdKey] || false;
          const tileBorderColor = group.negative_count > 0 ? 'border-red-500/40' : (group.positive_count > 0 ? 'border-yellow-500/40' : 'border-slate-700/50');
          return (
            <div key={customerIdKey} className={`bg-slate-800/50 rounded-lg border ${tileBorderColor} transition-all duration-300`}>
              <div onClick={() => setExpandedSentimentCustomers(p => ({ ...p, [customerIdKey]: !p[customerIdKey] }))} className="p-3 cursor-pointer hover:bg-slate-700/30 flex justify-between items-center">
                <div className="flex items-center min-w-0">
                  <UserCircle2 className="w-7 h-7 text-purple-400 mr-3 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-slate-100 truncate">{group.customer_name}</h3>
                    <div className="flex items-center flex-wrap gap-x-2 text-xs text-slate-400 mt-0.5">
                      {group.positive_count > 0 && (<span className="flex items-center text-yellow-400"> <StarIcon className="w-3 h-3 mr-1" /> {group.positive_count}</span>)}
                      {group.negative_count > 0 && (<span className="flex items-center text-red-400"> <AlertTriangleIcon className="w-3 h-3 mr-1" /> {group.negative_count}</span>)}
                    </div>
                  </div>
                </div>
                {isExpanded ? <ChevronUpIcon className="w-5 h-5 text-slate-400" /> : <ChevronDownIcon className="w-5 h-5 text-slate-400" />}
              </div>
              {isExpanded && (
                <div className="p-3 border-t border-slate-700/50 space-y-3">
                  {group.nudges.map(nudge => (
                    <SentimentSpotlightCard key={nudge.id} nudge={nudge} onDismiss={() => handleDismiss(nudge.id)} onRequestReview={() => addNotification({ type: 'error', title: 'Not Implemented', message: 'Requesting reviews is not yet available.' })} onViewConversation={handleViewConversation} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  )
};

const GrowthSection: FC<GrowthSectionProps> = ({ nudges, isLoading, isActionLoading, addNotification, setAllActiveNudges, setIsActionLoading, businessSlug, businessId }) => {
  const router = useRouter();

  const handleLaunchGrowthCampaign = useCallback(async (nudgeId: number) => {
    if (businessId === null) {
      addNotification({ type: 'error', title: 'Action Failed', message: 'Business ID not available for this action.' });
      return;
    }
    setIsActionLoading(nudgeId);
    try {
      // NOTE: Launch Growth Campaign still requires authentication
      const res = await fetch(`${API_BASE_URL}/copilot-growth/nudges/${nudgeId}/launch-campaign`, { method: 'POST', credentials: 'include' });
      
      if (!res.ok) {
        // Provide more detailed error feedback from the backend
        const errorData = await res.json().catch(() => ({ detail: 'Failed to create campaign drafts.' }));
        throw new Error(errorData.detail || `Request failed with status ${res.status}`);
      }
      
      const resultData = await res.json();
      
      addNotification({ 
        type: 'success', 
        title: 'Drafts Created!', 
        message: `${resultData.drafts_created || 0} drafts are ready for your review. Redirecting...` 
      });

      setAllActiveNudges(prev => prev.filter(n => n.id !== nudgeId));
      router.push(`/all-engagement-plans/${businessSlug}`);

    } catch (err) {
      addNotification({ type: 'error', title: 'Draft Creation Failed', message: err instanceof Error ? err.message : 'Unknown error' });
      setIsActionLoading(null);
    }
  }, [setIsActionLoading, setAllActiveNudges, addNotification, router, businessSlug, businessId]);

  return (
    <section>
      <h2 className="text-2xl font-semibold mb-4 text-slate-100 border-b-2 border-slate-700 pb-2 flex items-center">
        <TrendingUpIcon className="w-7 h-7 mr-3 text-purple-400" />
        Unlock Growth
        {nudges.length > 0 &&
          <span className="ml-4 bg-purple-500/20 text-purple-300 text-sm font-semibold px-3 py-1 rounded-full">
            {nudges.length}
          </span>
        }
      </h2>
      <div className="space-y-4">
        {isLoading && <div className="text-center py-8 px-4 bg-slate-800/40 rounded-lg border border-slate-700/60"><Loader2 className="h-8 w-8 text-slate-500 mx-auto animate-spin" /></div>}
        {!isLoading && nudges.length === 0 && (
          <div className="text-center py-8 px-4 bg-slate-800/40 rounded-lg border border-slate-700/60">
            <CheckCircle2Icon className="h-10 w-10 text-green-500/70 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No new growth strategies</p>
            <p className="text-slate-400 text-sm">Co-Pilot is analyzing your data for opportunities.</p>
          </div>
        )}

        {nudges.map(nudge => (
          <GrowthOpportunityCard
            key={nudge.id}
            nudge={nudge}
            onLaunchCampaign={handleLaunchGrowthCampaign}
            isLoading={isActionLoading === nudge.id}
          />
        ))}
      </div>
    </section>
  );
};

const AllClearMessage: FC = () => (
  <section className="text-center py-16 bg-slate-800/40 rounded-lg mt-12 border border-slate-700/60">
    <CheckCircle2Icon className="h-20 w-20 text-green-400/80 mx-auto mb-4" />
    <h3 className="text-3xl font-semibold text-slate-100 mb-2">All Co-Pilot Insights Clear!</h3>
    <p className="text-slate-400 text-lg">No active suggestions to review right now. Great job!</p>
  </section>
);

export default CoPilotPage;