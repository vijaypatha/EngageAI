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

  return (
    <div className="min-h-screen bg-nudge-gradient text-white py-12 px-6">
      {step === 1 && (
        <div>
          <h1 className="text-2xl font-bold mb-4">Step 1: Business Info</h1>
          {Object.entries(businessProfile).map(([key, value]) => (
            <input
              key={key}
              className="block border border-neutral rounded p-2 mb-2 w-full text-black"
              placeholder={key.replace(/_/g, ' ')}
              value={value}
              onChange={e => setBusinessProfile({ ...businessProfile, [key]: e.target.value })}
            />
          ))}
          <button className="bg-primary text-white px-4 py-2 rounded" onClick={handleBusinessSubmit}>
            Save & Continue
          </button>
        </div>
      )}

      {step === 2 && (
        <div>
          <h1 className="text-2xl font-bold mb-4">Step 2: Add First Customer</h1>
          {Object.entries(customer).map(([key, value]) => (
            <input
              key={key}
              className="block border border-neutral rounded p-2 mb-2 w-full text-black"
              placeholder={key.replace(/_/g, ' ')}
              value={value}
              onChange={e => setCustomer({ ...customer, [key]: e.target.value })}
            />
          ))}
          <button className="bg-primary text-white px-4 py-2 rounded" onClick={handleCustomerSubmit}>
            Save & Continue
          </button>
        </div>
      )}

      {step === 3 && (
        <div>
          <h1 className="text-2xl font-bold mb-4">Step 3: Train AI Tone</h1>
          <p className="text-neutral mb-4">Answer a few quick questions so we can learn how you text your customers:</p>

          {loadingScenarios || scenarios.length === 0 ? (
            <div className="flex items-center space-x-4">
              <div className="h-2 w-40 bg-gradient-to-r from-yellow-400 to-red-500 rounded-full animate-pulse" />
              <p className="text-white text-lg font-medium animate-pulse">Teach Nudge AI your SMS style...</p>
            </div>
          ) : (
            <>
              {scenarios.map((s, i) => (
                <div key={i} className="mb-6">
                  <p className="text-white mb-2 font-semibold">{s}</p>
                  <textarea
                    className="block border border-neutral rounded p-2 w-full h-24 text-black"
                    value={responses[i] || ''}
                    onChange={(e) => {
                      const updated = [...responses];
                      updated[i] = e.target.value;
                      setResponses(updated);
                    }}
                  />
                </div>
              ))}
              <button className="bg-primary text-white px-4 py-2 rounded" onClick={handleSmsStyleSubmit}>
                Finish Onboarding
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}