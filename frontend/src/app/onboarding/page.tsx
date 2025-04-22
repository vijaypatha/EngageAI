'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { useTimezone } from '@/hooks/useTimezone';
import { getUserTimezone, US_TIMEZONES, TIMEZONE_LABELS } from '@/lib/timezone';

interface BusinessProfile {
  business_name: string;
  industry: string;
  business_goal: string;
  primary_services: string;
  representative_name: string;
  timezone: string;
}

interface Customer {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
}

export default function OnboardingPage() {
  const router = useRouter();
  const { businessTimezone, updateBusinessTimezone } = useTimezone();
  const formatPhone = (input: string) => {
    const trimmed = input.trim().replace(/[^\d+]/g, '');
    if (trimmed.startsWith('+') && trimmed.length <= 16) return trimmed;
    if (/^\d{10}$/.test(trimmed)) return `+1${trimmed}`;
    return trimmed;
  };
  const [step, setStep] = useState(1);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [responses, setResponses] = useState<string[]>([]);
  const [loadingScenarios, setLoadingScenarios] = useState(false);

  const [businessProfile, setBusinessProfile] = useState<BusinessProfile>({
    business_name: '',
    industry: '',
    business_goal: '',
    primary_services: '',
    representative_name: '',
    timezone: getUserTimezone(),
  });

  const [customer, setCustomer] = useState<Customer>({
    customer_name: '',
    phone: '',
    lifecycle_stage: '',
    pain_points: '',
    interaction_history: '',
    timezone: businessProfile.timezone,
  });

  const [smsStyle, setSmsStyle] = useState('');
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [previewMessage, setPreviewMessage] = useState('');

  useEffect(() => {
    const fetchPreview = async () => {
      // Using correct preview API endpoint path as defined in backend routing
      if (businessProfile.business_name && businessProfile.business_goal && businessProfile.industry) {
        const res = await apiClient.post('/onboarding-preview/preview-message', {
          business_name: businessProfile.business_name,
          business_goal: businessProfile.business_goal,
          industry: businessProfile.industry,
          customer_name: 'Jane Doe'
        });
        setPreviewMessage(res.data.preview);
      }
    };
    fetchPreview();
  }, [businessProfile.business_name, businessProfile.business_goal, businessProfile.industry]);

  useEffect(() => {
    // Update business timezone when form data changes
    if (businessProfile.timezone) {
      updateBusinessTimezone(businessProfile.timezone);
    }
  }, [businessProfile.timezone, updateBusinessTimezone]);

  useEffect(() => {
    setCustomer(prev => ({ ...prev, timezone: businessProfile.timezone }));
  }, [businessProfile.timezone]);

  const handleBusinessSubmit = async () => {
    const res = await apiClient.post('/business-profile/', businessProfile);
    const id = res.data.id;
    setBusinessId(id);
    await updateBusinessTimezone(businessProfile.timezone);
    setStep(2);
  };

  const handleCustomerSubmit = async () => {
    setLoadingScenarios(true);
    await apiClient.post('/customers/', {
      ...customer,
      business_id: businessId,
      timezone: customer.timezone || businessProfile.timezone,
    });
    const res = await apiClient.get(`/sms-style/scenarios/${businessId}`);
    setScenarios(res.data.scenarios || []);
    setLoadingScenarios(false);
    setStep(3);
  };

  const handleSmsStyleSubmit = async () => {
    const payload = scenarios.map((scenario, i) => ({
      business_id: businessId,
      scenario,
      response: responses[i],
    }));

    await apiClient.post('/sms-style', payload);
    const res = await apiClient.get(`/business-profile/${businessId}`);
    const slug = res.data.slug;
    router.push(`/dashboard/${slug}`);
  };

  const toggleGoal = (goal: string) => {
    const goals = businessProfile.business_goal.split(', ').filter(Boolean);
    const updated = goals.includes(goal)
      ? goals.filter(g => g !== goal)
      : [...goals, goal];
    setBusinessProfile({ ...businessProfile, business_goal: updated.join(', ') });
  };

  return (
    <div className="min-h-screen bg-[#0C0F1F] flex items-center justify-center py-8 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl space-y-6">
        {step === 1 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 text-white space-y-8 backdrop-blur-sm">
            <h1 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Let's build your first nudge plan</h1>
            <p className="text-center text-gray-300 text-lg md:text-xl font-medium">What's the name of your business?</p>

            <div className="space-y-6">
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Business name"
                value={businessProfile.business_name}
                onChange={e => setBusinessProfile({ ...businessProfile, business_name: e.target.value })}
              />

              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Industry (e.g. Therapy, Real Estate)"
                value={businessProfile.industry}
                onChange={e => setBusinessProfile({ ...businessProfile, industry: e.target.value })}
              />

              <div className="space-y-4">
                <p className="text-center text-gray-300 text-lg font-medium">What's your business timezone?</p>
                <select
                  className="w-full border border-white/10 rounded-lg p-3 text-black bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                  value={businessProfile.timezone}
                  onChange={e => setBusinessProfile({ ...businessProfile, timezone: e.target.value })}
                >
                  {US_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {TIMEZONE_LABELS[tz]}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-gray-400 text-center">This helps us schedule messages at the right time for your business</p>
              </div>

              <div className="space-y-4">
                <p className="text-center text-gray-300 text-lg font-medium">What do you want to achieve with nudge messaging?</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {[
                    { key: 'stay_in_touch', label: '💬 Stay in touch' },
                    { key: 'build_trust', label: '🤝 Build trust' },
                    { key: 'grow_sales', label: '📈 Grow sales' },
                    { key: 'repeat_engagement', label: '🔁 Get repeat business' },
                    { key: 'automate_followups', label: '⏱️ Save time with follow-ups' },
                    { key: 'get_referrals', label: '📣 Get more referrals' },
                  ].map(goal => (
                    <button
                      key={goal.key}
                      className={`aspect-square rounded-xl flex items-center justify-center text-center transition-all duration-300 p-4 hover:scale-105 ${
                        businessProfile.business_goal.split(', ').includes(goal.label)
                          ? 'bg-gradient-to-br from-emerald-400 to-blue-500 text-white shadow-lg scale-105'
                          : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B] hover:shadow-lg'
                      }`}
                      onClick={() => toggleGoal(goal.label)}
                    >
                      <span className="text-sm md:text-base font-semibold leading-tight">{goal.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {businessProfile.business_name && businessProfile.business_goal && businessProfile.industry && (
              <div className="bg-[#1A1E2E]/80 backdrop-blur-sm p-4 rounded-lg border border-white/10 shadow-lg">
                <p className="font-semibold text-sm text-white/80">
                  Here's a sample nudge {businessProfile.business_name} could use to start a thoughtful conversation:
                </p>
                <div className="bg-[#111629]/90 mt-2 p-3 rounded-lg text-sm text-white/90 shadow-inner">
                  <p>{previewMessage || 'Loading preview...'}</p>
                  <p className="text-xs text-white/60 pt-2">
                    Reply STOP to unsubscribe. Standard message rates may apply.
                  </p>
                </div>
              </div>
            )}

            <button
              className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
              onClick={() => setStep(1.5)}
              disabled={!businessProfile.business_name || !businessProfile.business_goal || !businessProfile.industry}
            >
              Next: Personalize it for your business
            </button>
          </div>
        )}

        {step === 1.5 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm">
            <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Personalize your business profile</h2>
            <p className="text-center text-gray-400 mb-6">These details help us tailor your engagement messages perfectly.</p>

            <div className="space-y-6">
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Primary services (The more details, the smarter your nudges!)"
                value={businessProfile.primary_services}
                onChange={e => setBusinessProfile({ ...businessProfile, primary_services: e.target.value })}
              />
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Your Name (used in SMS)"
                value={businessProfile.representative_name}
                onChange={e => setBusinessProfile({ ...businessProfile, representative_name: e.target.value })}
              />

              <button
                className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                onClick={handleBusinessSubmit}
                disabled={!businessProfile.primary_services || !businessProfile.representative_name}
              >
                Next: Add Your First Customer
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm">
            <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Who are you helping first?</h2>
            <p className="text-center text-gray-400 mb-6 text-lg">We'll use this info to create a meaningful nudge plan tailored to them.</p>

            <div className="space-y-6">
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Customer Name"
                value={customer.customer_name}
                onChange={e => setCustomer({ ...customer, customer_name: e.target.value })}
              />

              <input
                type="tel"
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Phone Number"
                value={customer.phone}
                onChange={e => setCustomer({ ...customer, phone: formatPhone(e.target.value) })}
              />

              <div className="space-y-2">
                <label className="block text-sm font-medium text-white">
                  Customer's Timezone
                </label>
                <select
                  value={customer.timezone}
                  onChange={e => setCustomer({ ...customer, timezone: e.target.value })}
                  className="w-full border border-white/10 rounded-lg p-3 text-black bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                >
                  {US_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {TIMEZONE_LABELS[tz]}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-gray-400">
                  This helps us send messages at appropriate times for your customer
                </p>
              </div>

              <div>
                <p className="text-white font-semibold mb-2">Where are they in the relationship?</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: "🆕 Just Added" },
                    { label: "👋 Reached Out" },
                    { label: "✅ Interested" },
                    { label: "✉️ Waiting on Their Reply" },
                    { label: "🛠️ Getting Started" },
                    { label: "🤝 Going Well" },
                    { label: "📉 Lost Touch" },
                    { label: "🔙 Reconnecting" },
                  ].map(({ label }) => (
                    <button
                      key={label}
                      onClick={() => setCustomer({ ...customer, lifecycle_stage: label })}
                      className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-300 hover:scale-105 ${
                        customer.lifecycle_stage === label
                          ? 'bg-gradient-to-r from-emerald-400 to-blue-500 text-white shadow-lg'
                          : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B] hover:shadow-lg'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="What are they struggling with?"
                value={customer.pain_points}
                onChange={e => setCustomer({ ...customer, pain_points: e.target.value })}
              />
              <textarea
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Any past interactions with this contact?"
                value={customer.interaction_history}
                onChange={e => setCustomer({ ...customer, interaction_history: e.target.value })}
              />

              <button
                className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                onClick={handleCustomerSubmit}
                disabled={!customer.customer_name || !customer.phone.match(/^\+\d{11,15}$/) || !customer.lifecycle_stage}
              >
                Next: Teach Nudge Your Style
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm">
            <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">How would you respond?</h2>
            <p className="text-center text-gray-400 mb-6">Help us understand your communication style by responding to these scenarios.</p>

            {loadingScenarios ? (
              <div className="text-center text-white">
                <div className="animate-pulse space-y-4">
                  <div className="h-4 bg-[#1A1E2E] rounded w-3/4 mx-auto"></div>
                  <div className="h-4 bg-[#1A1E2E] rounded w-1/2 mx-auto"></div>
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {scenarios.map((scenario, index) => (
                  <div key={index} className="space-y-4">
                    <div className="bg-[#1A1E2E]/80 backdrop-blur-sm p-4 rounded-lg border border-white/10 shadow-lg">
                      <p className="text-white">{scenario}</p>
                    </div>
                    <textarea
                      className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                      placeholder="Your response..."
                      value={responses[index] || ''}
                      onChange={e => {
                        const newResponses = [...responses];
                        newResponses[index] = e.target.value;
                        setResponses(newResponses);
                      }}
                      rows={3}
                    />
                  </div>
                ))}

                <button
                  className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                  onClick={handleSmsStyleSubmit}
                  disabled={responses.length !== scenarios.length || responses.some(r => !r)}
                >
                  Complete Setup
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}