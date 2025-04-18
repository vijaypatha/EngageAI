'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface BusinessProfile {
  business_name: string;
  industry: string;
  business_goal: string;
  primary_services: string;
  representative_name: string;
}

interface Customer {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
}

export default function OnboardingPage() {
  const router = useRouter();
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
  });

  const [customer, setCustomer] = useState<Customer>({
    customer_name: '',
    phone: '',
    lifecycle_stage: '',
    pain_points: '',
    interaction_history: '',
  });

  const [smsStyle, setSmsStyle] = useState('');
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [previewMessage, setPreviewMessage] = useState('');

  useEffect(() => {
    const fetchPreview = async () => {
      // Using correct preview API endpoint path as defined in backend routing
      if (businessProfile.business_name && businessProfile.business_goal) {
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
  }, [businessProfile.business_name, businessProfile.business_goal]);

  const handleBusinessSubmit = async () => {
    const res = await apiClient.post('/business-profile/', businessProfile);
    const id = res.data.id;
    setBusinessId(id);
    setStep(2);
  };

  const handleCustomerSubmit = async () => {
    setLoadingScenarios(true);
    await apiClient.post('/customers/', {
      business_id: businessId,
      ...customer,
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
    <div className="min-h-screen bg-nudge-gradient text-white py-12 px-6">
      {step === 1 && (
          <div className="max-w-2xl mx-auto rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-10 text-white space-y-8">
          <h1 className="text-3xl font-bold text-center text-primary">Let’s build first nudge plan</h1>
          <p className="text-center text-gray-300 text-lg md:text-xl font-medium">What’s the name of your business?</p>
          <input
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Business name"
            value={businessProfile.business_name}
            onChange={e => setBusinessProfile({ ...businessProfile, business_name: e.target.value })}
          />
 
          <p className="text-center text-gray-300 text-lg md:text-xl font-medium mt-4">What do you want to achieve with nudge messaging?</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
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
              className={`aspect-square rounded-xl flex items-center justify-center text-center transition-all duration-200 px-4 py-3 font-semibold text-lg ${
                  businessProfile.business_goal.split(', ').includes(goal.label)
                    ? 'bg-gradient-to-br from-green-400 to-blue-500 text-white shadow-lg scale-105'
                    : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B]'
              }`}
                onClick={() => toggleGoal(goal.label)}
              >
                <span className="text-xl md:text-2xl font-semibold leading-tight">{goal.label}</span>
              </button>
            ))}
          </div>

          {businessProfile.business_name && businessProfile.business_goal && (
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 mt-6">
              <p className="font-semibold text-sm text-gray-700">
                We’ll help <strong>{businessProfile.business_name}</strong> build meaningful nudge plan. Here is an example of a nudge:
              </p>
              <p className="italic text-sm mt-2">Here’s a preview:</p>
              <div className="bg-gray-100 mt-2 p-3 rounded text-sm text-black">
                {previewMessage || 'Loading preview...'}
              </div>
            </div>
          )}
 
          <button
            className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-green-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg"
            onClick={() => setStep(1.5)}
            disabled={!businessProfile.business_name || !businessProfile.business_goal}
          >
            Next: Personalize it for your business
          </button>
        </div>
      )}

      {step === 1.5 && (
        <div className="max-w-2xl mx-auto rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-10 text-white space-y-8">
          <h2 className="text-2xl font-bold text-center text-primary">Personalize your business profile</h2>
          <p className="text-center text-gray-400 mb-6">These details help us tailor your engagement messages perfectly.</p>

          <input
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Industry (e.g. Therapy, Real Estate)"
            value={businessProfile.industry}
            onChange={e => setBusinessProfile({ ...businessProfile, industry: e.target.value })}
          />
          <input
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Primary Services (e.g. Couples therapy)"
            value={businessProfile.primary_services}
            onChange={e => setBusinessProfile({ ...businessProfile, primary_services: e.target.value })}
          />
          <input
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Your Name (used in SMS)"
            value={businessProfile.representative_name}
            onChange={e => setBusinessProfile({ ...businessProfile, representative_name: e.target.value })}
          />

          <button
            className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-green-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg"
            onClick={handleBusinessSubmit}
            disabled={
              !businessProfile.industry ||
              !businessProfile.primary_services ||
              !businessProfile.representative_name
            }
          >
            Next: Add Your First Customer
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="max-w-2xl mx-auto rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-10 text-white space-y-8">
          <h2 className="text-3xl font-bold text-center text-primary">Who are you helping first?</h2>
          <p className="text-center text-gray-400 mb-6 text-lg">We’ll use this info to create a meaningful nudge plan tailored to them.</p>

          <input
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Full Name"
            value={customer.customer_name}
            onChange={e => setCustomer({ ...customer, customer_name: e.target.value })}
          />
          <input
            type="tel"
            autoComplete="off"
            inputMode="tel"
            name="customer_phone"
            className="appearance-none autofill:bg-transparent w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="Phone Number"
            value={customer.phone}
            onChange={e => setCustomer({ ...customer, phone: formatPhone(e.target.value) })}
          />

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
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                    customer.lifecycle_stage === label
                      ? 'bg-gradient-to-r from-green-400 to-blue-500 text-white shadow-md'
                      : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B]'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <textarea
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 mt-4"
            placeholder="What are they struggling with?"
            value={customer.pain_points}
            onChange={e => setCustomer({ ...customer, pain_points: e.target.value })}
          />
          <textarea
            className="w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500"
            placeholder="What have you talked about?"
            value={customer.interaction_history}
            onChange={e => setCustomer({ ...customer, interaction_history: e.target.value })}
          />

          <button
            className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-green-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg"
            onClick={handleCustomerSubmit}
            disabled={
              !customer.customer_name ||
              !customer.phone.match(/^\+\d{11,15}$/) ||
              !customer.lifecycle_stage
            }
          >
            Next: Teach Nudge Your Style
          </button>
        </div>
      )}

{step === 3 && (
  <div className="max-w-2xl mx-auto space-y-8">
    <h1 className="text-3xl font-bold text-center text-primary mb-4">Step 3: Teach Nudge Your Tone</h1>
    <p className="text-center text-gray-400 mb-8 text-lg">Reply to these common customer messages using your natural texting style.</p>

    {loadingScenarios || scenarios.length === 0 ? (
      <div className="flex items-center space-x-4 justify-center">
        <div className="h-2 w-40 bg-gradient-to-r from-yellow-400 to-red-500 rounded-full animate-pulse" />
        <p className="text-white text-lg font-medium animate-pulse">Generating tone questions…</p>
      </div>
    ) : (
      <>
        {scenarios.map((s, i) => (
          <div key={i} className="bg-[#111629] border border-white/10 rounded-xl p-6 space-y-4 shadow">
            <p className="text-sm font-medium text-white/70">📥 Customer Message</p>
            <div className="bg-[#1A1E2E] text-white p-4 rounded-lg text-sm border border-white/10">
              {s}
            </div>
            <label className="block text-sm font-medium text-white/70 mt-2 mb-1">💬 Your Typical Reply</label>
            <textarea
              className="block w-full border border-gray-300 rounded-md p-3 text-black placeholder-gray-500 h-28"
              value={responses[i] || ''}
              onChange={(e) => {
                const updated = [...responses];
                updated[i] = e.target.value;
                setResponses(updated);
              }}
              placeholder="Type how you’d normally respond..."
            />
          </div>
        ))}
        <button
          className="w-full mt-8 py-3 rounded-lg bg-gradient-to-r from-green-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg"
          onClick={handleSmsStyleSubmit}
        >
          Finish Onboarding
        </button>
      </>
    )}
  </div>
)}
    </div>
  );
}