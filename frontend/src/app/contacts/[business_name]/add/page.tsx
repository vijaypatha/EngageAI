'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { useTimezone } from '@/hooks/useTimezone';
import { US_TIMEZONES, TIMEZONE_LABELS } from '@/lib/timezone';

export default function AddCustomerPage() {
  const { business_name } = useParams();
  const router = useRouter();
  const { businessTimezone } = useTimezone();
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [formData, setFormData] = useState({
    customer_name: '',
    phone: '',
    lifecycle_stage: '',
    pain_points: '',
    interaction_history: '',
    timezone: businessTimezone,
  });
  const [showTimezoneSelect, setShowTimezoneSelect] = useState(false);

  useEffect(() => {
    const fetchBusinessId = async () => {
      try {
        const res = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        setBusinessId(res.data.business_id);
      } catch (error) {
        console.error('Failed to fetch business ID:', error);
        router.push('/error');
      }
    };
    fetchBusinessId();
  }, [business_name, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiClient.post('/customers/', {
        ...formData,
        business_id: businessId,
      });
      router.push(`/contacts/${business_name}`);
    } catch (error) {
      console.error('Failed to add customer:', error);
    }
  };

  return (
    <div className="min-h-screen bg-[#0C0F1F] flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl">
        <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
          <h2 className="text-3xl font-bold text-center text-white">Add New Customer</h2>
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <input
                type="text"
                placeholder="Customer Name"
                value={formData.customer_name}
                onChange={e => setFormData({ ...formData, customer_name: e.target.value })}
                className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 bg-white"
                required
              />
            </div>

            <div>
              <input
                type="tel"
                placeholder="Phone Number"
                value={formData.phone}
                onChange={e => setFormData({ ...formData, phone: e.target.value })}
                className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 bg-white"
                required
              />
            </div>

            <div>
              <select
                value={formData.lifecycle_stage}
                onChange={e => setFormData({ ...formData, lifecycle_stage: e.target.value })}
                className="w-full border border-gray-300 rounded-md p-3 text-black bg-white"
                required
              >
                <option value="">Select Stage</option>
                <option value="🆕 Just Added">🆕 Just Added</option>
                <option value="👋 Reached Out">👋 Reached Out</option>
                <option value="✅ Interested">✅ Interested</option>
                <option value="✉️ Waiting on Their Reply">✉️ Waiting on Reply</option>
                <option value="🛠️ Getting Started">🛠️ Getting Started</option>
                <option value="🤝 Going Well">🤝 Going Well</option>
                <option value="📉 Lost Touch">📉 Lost Touch</option>
                <option value="🔙 Reconnecting">🔙 Reconnecting</option>
              </select>
            </div>

            <div>
              <textarea
                placeholder="Pain Points"
                value={formData.pain_points}
                onChange={e => setFormData({ ...formData, pain_points: e.target.value })}
                className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 bg-white"
                rows={3}
              />
            </div>

            <div>
              <textarea
                placeholder="Interaction History"
                value={formData.interaction_history}
                onChange={e => setFormData({ ...formData, interaction_history: e.target.value })}
                className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 bg-white"
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-300">Timezone: {TIMEZONE_LABELS[formData.timezone]}</span>
                <button
                  type="button"
                  onClick={() => setShowTimezoneSelect(!showTimezoneSelect)}
                  className="text-sm text-blue-400 hover:text-blue-300"
                >
                  {showTimezoneSelect ? 'Use Business Timezone' : 'Change Timezone'}
                </button>
              </div>
              
              {showTimezoneSelect && (
                <select
                  value={formData.timezone}
                  onChange={e => setFormData({ ...formData, timezone: e.target.value })}
                  className="w-full border border-white/10 rounded-lg p-3 text-black bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                >
                  {US_TIMEZONES.map(tz => (
                    <option key={tz} value={tz}>
                      {TIMEZONE_LABELS[tz]}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <button
              type="submit"
              className="w-full py-3 rounded-lg bg-gradient-to-r from-green-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg"
            >
              Add Customer
            </button>
          </form>
        </div>
      </div>
    </div>
  );
} 