'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { format, isThisWeek, addWeeks, isBefore, parseISO } from 'date-fns';
import { OptInStatusBadge } from '@/components/OptInStatus';
import type { OptInStatus } from "@/components/OptInStatus";

interface EngagementPlan {
  id: number;
  customer_name: string;
  status: string;
  smsContent: string;
  smsTiming: string;
  send_datetime_utc: string;
  source: string;
  latest_consent_status: OptInStatus;
}

export default function AllEngagementPlansPage() {
  const { business_name } = useParams();
  const [plans, setPlans] = useState<EngagementPlan[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);

  useEffect(() => {
    const fetchPlans = async () => {
      try {
        // First get the business ID
        const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const businessId = businessRes.data.business_id;
        setBusinessId(businessId);

        // Then fetch all engagements
        const response = await apiClient.get(`/review/all-engagements?business_id=${businessId}`);
        setPlans(response.data.engagements);
      } catch (error) {
        console.error('Error fetching plans:', error);
      }
    };
    fetchPlans();
  }, [business_name]);

  // Group messages by timing
  const groupedPlans = plans.reduce((acc, plan) => {
    const date = parseISO(plan.send_datetime_utc);
    const nextWeekStart = addWeeks(new Date(), 1);
    let group = 'Later';
    
    if (isThisWeek(date)) {
      group = 'This Week';
    } else if (isBefore(date, nextWeekStart)) {
      group = 'Next Week';
    }

    if (!acc[group]) {
      acc[group] = [];
    }
    acc[group].push(plan);
    return acc;
  }, {} as Record<string, EngagementPlan[]>);

  return (
    <div className="flex-1 p-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">📬 Engagement Plans</h1>
        <p className="text-gray-400 mb-8">Grouped SMS plans across all customers</p>

        {['This Week', 'Next Week', 'Later'].map(group => (
          <div key={group} className="mb-12 last:mb-6">
            <h2 className="text-2xl font-semibold mb-6">{group}</h2>
            <div className="space-y-4">
              {groupedPlans[group]?.map(plan => (
                <div key={plan.id} className="relative">
                  {/* Timeline line */}
                  <div className="absolute left-6 w-1 h-full bg-green-500 rounded-full"></div>
                  
                  {/* Date circle */}
                  <div className="absolute left-6 -translate-x-1/2 w-14 h-14 rounded-full bg-[#2C2F3E] border-2 border-green-500 flex items-center justify-center text-sm shadow-lg shadow-green-500/20">
                    <div className="text-green-400">{format(parseISO(plan.send_datetime_utc), 'MMM d')}</div>
                  </div>

                  {/* Content card */}
                  <div className="ml-20 bg-[#1C1F2E] rounded-lg p-6 relative">
                    <div className="flex justify-between items-start mb-6">
                      <div className="flex-1 pr-24"> {/* Added padding to prevent text overlap with status badge */}
                        <div className="text-lg mb-2">{format(parseISO(plan.send_datetime_utc), 'EEEE, h:mm a')}</div>
                        <div className="text-gray-300 mb-4">{plan.smsContent}</div>
                        <div className="flex items-center gap-3">
                          <span className="text-gray-400">👤</span>
                          <span className="mr-2">{plan.customer_name}</span>
                          <OptInStatusBadge status={plan.latest_consent_status as OptInStatus} size="sm" />
                        </div>
                      </div>
                      
                      {/* Status badge - positioned absolutely to avoid layout issues */}
                      <div className="absolute top-6 right-6 px-3 py-1 bg-yellow-500/20 text-yellow-300 rounded-full text-sm font-medium">
                        {plan.status.toUpperCase()}
                      </div>
                    </div>

                    {/* Action buttons - now in a separate row below content */}
                    <div className="flex justify-end gap-2 mt-4">
                      <button className="px-4 py-2 bg-red-500 hover:bg-red-600 rounded-lg transition-colors">
                        Remove
                      </button>
                      <button className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors">
                        Edit
                      </button>
                      <button className="px-4 py-2 bg-green-500 hover:bg-green-600 rounded-lg transition-colors">
                        Schedule
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
