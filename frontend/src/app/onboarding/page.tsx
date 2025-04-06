"use client";

import { useRouter } from 'next/navigation';
import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { motion } from 'framer-motion';
import { useSearchParams } from 'next/navigation';


const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function OnboardingFlow() {
  const router = useRouter();
  const stepsText = ['Step 1 of 3: Business Profile', 'Step 2 of 3: Add Customer', 'Step 3 of 3: Train AI'];

  const searchParams = useSearchParams();
  const initialStep = Number(searchParams.get('step')) || 1;
  const [step, setStep] = useState(initialStep);

  useEffect(() => {
    setStep(initialStep);
  }, [initialStep]);


  const [businessData, setBusinessData] = useState({
    business_name: '', industry: '', business_goal: '', primary_services: '', representative_name: ''
  });

  const [customerData, setCustomerData] = useState({
    customer_name: '', phone: '', lifecycle_stage: '', pain_points: '', interaction_history: ''
  });

  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loadingQuestions, setLoadingQuestions] = useState(true);

  useEffect(() => {
    const fetchPrompts = async () => {
      try {
        const businessId = localStorage.getItem('business_id');
        if (!businessId) throw new Error('Missing business ID');

        const response = await fetch(`${API_BASE_URL}/sms-style/scenarios/${businessId}`);
        if (!response.ok) throw new Error('Failed to fetch tone questions');
        const data = await response.json();
        setQuestions(data.scenarios || []);
      } catch (err) {
        console.error('Error fetching questions:', err);
        alert('Failed to load AI training questions. Please refresh and try again.');
      } finally {
        setLoadingQuestions(false);
      }
    };

    if (step === 3) {
      fetchPrompts();
    }
  }, [step]);

  const handleBusinessSubmit = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/business-profile/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(businessData)
      });
      if (!response.ok) throw new Error('Failed to create business profile.');
      const data = await response.json();
      localStorage.setItem('business_id', data.id);
      setStep(2);
    } catch (error) {
      console.error('Error creating business profile:', error);
      alert('There was an error setting up your business profile. Please try again.');
    }
  };

  const handleCustomerSubmit = async () => {
    try {
      const businessId = localStorage.getItem('business_id');
      if (!businessId) throw new Error('Business ID not found in localStorage.');

      const response = await fetch(`${API_BASE_URL}/customers/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'business-Id': businessId
        },
        body: JSON.stringify(customerData)
      });

      const rawText = await response.text();

      if (!response.ok) {
        console.error("❌ Backend error response:", rawText);
        throw new Error('Failed to add customer.');
      }

      let data;
      try {
        data = JSON.parse(rawText);
      } catch (err) {
        console.error("❌ Failed to parse JSON:", rawText);
        throw new Error('Invalid JSON response from backend.');
      }

      console.log("✅ Customer added:", data);
      setStep(3);
    } catch (error) {
      console.error('Error submitting customer data:', error);
      alert('There was an error adding the customer. Please try again.');
    }
  };

  const handleToneSubmit = async () => {
    try {
      const businessId = localStorage.getItem('business_id');
      if (!businessId) throw new Error('Missing business ID');
  
      const payload = questions.map((scenario, i) => ({
        scenario,
        response: answers[i] || '',
        business_id: Number(businessId),
      }));
      
  
      const response = await fetch(`${API_BASE_URL}/sms-style`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
  
      if (!response.ok) throw new Error('Submission failed');
  
      // ✅ Redirect to dashboard
      router.push('/dashboard');
    } catch (err) {
      console.error('Submit error:', err);
      alert('There was a problem saving your tone. Please try again.');
    }
  };
  
  

  const renderStepOne = () => (
    <Card className="p-10 max-w-xl mx-auto mt-10 shadow-2xl rounded-3xl bg-white text-gray-800 border border-gray-100">
      <CardContent>
        <h2 className="text-4xl font-extrabold mb-6 text-gray-900 leading-tight">Let's start with your business ✨</h2>
        <p className="text-lg text-gray-600 mb-8">Tell us about your business so we can tailor your SMS engagement style.</p>
        <Input placeholder="Business Name" onChange={e => setBusinessData({ ...businessData, business_name: e.target.value })} />
        <Input placeholder="Industry" onChange={e => setBusinessData({ ...businessData, industry: e.target.value })} className="mt-4" />
        <Input placeholder="Business Goal" onChange={e => setBusinessData({ ...businessData, business_goal: e.target.value })} className="mt-4" />
        <Textarea placeholder="Primary Services" onChange={e => setBusinessData({ ...businessData, primary_services: e.target.value })} className="mt-4" />
        <Input placeholder="Representative Name" onChange={e => setBusinessData({ ...businessData, representative_name: e.target.value })} className="mt-4" />
        <Button className="mt-6 w-full" onClick={handleBusinessSubmit}>Next: Add a Customer</Button>
      </CardContent>
    </Card>
  );

  const renderStepTwo = () => (
    <Card className="p-10 max-w-xl mx-auto mt-10 shadow-2xl rounded-3xl bg-white text-gray-800 border border-gray-100">
      <CardContent>
        <h2 className="text-4xl font-extrabold mb-6 text-gray-900 leading-tight">Add your first customer 👤</h2>
        <p className="text-lg text-gray-600 mb-8">Just one customer to help personalize the AI follow-ups for your business.</p>
        <Input placeholder="Customer Name" onChange={e => setCustomerData({ ...customerData, customer_name: e.target.value })} />
        <Input placeholder="Phone Number" onChange={e => setCustomerData({ ...customerData, phone: e.target.value })} className="mt-4" />
        <Input placeholder="Lifecycle Stage" onChange={e => setCustomerData({ ...customerData, lifecycle_stage: e.target.value })} className="mt-4" />
        <Textarea placeholder="Pain Points" onChange={e => setCustomerData({ ...customerData, pain_points: e.target.value })} className="mt-4" />
        <Textarea placeholder="Interaction History" onChange={e => setCustomerData({ ...customerData, interaction_history: e.target.value })} className="mt-4" />
        <Button className="mt-6 w-full" onClick={handleCustomerSubmit}>Next: Teach the AI</Button>
      </CardContent>
    </Card>
  );

  const renderStepThree = () => (
    <motion.div
      initial={{ opacity: 0, y: 50 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="p-4 max-w-xl mx-auto mt-10"
    >
      <Card className="p-10 shadow-2xl rounded-3xl bg-white text-gray-800 border border-gray-100">
        <CardContent>
          <h2 className="text-4xl font-extrabold mb-6 text-gray-900 leading-tight">Train EngageAI on your tone ✍️</h2>
          <p className="text-lg text-gray-600 mb-8">These are real questions customers might ask. Respond in your voice so EngageAI can match your tone.</p>
          {loadingQuestions ? (
            <p className="text-center text-gray-500">Loading questions...</p>
          ) : (
            <>
              {questions.map((q, i) => (
                <div key={i} className="mb-6">
                  <p className="font-semibold mb-2 text-gray-800">{q}</p>
                  <Textarea
                    className="text-base min-h-[100px] px-4 py-2 rounded-lg border border-gray-300"
                    placeholder="Your natural response..."
                    value={answers[i] || ''}
                    onChange={e => setAnswers(prev => ({ ...prev, [i]: e.target.value }))}
                  />
                </div>
              ))}
              <Button className="mt-6 w-full" onClick={handleToneSubmit}>Finish Setup 🚀</Button>
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );

  const renderStep = () => (
    <motion.div
      key={step}
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="text-center text-2xl font-bold text-white drop-shadow-sm mt-6 mb-4 tracking-wide">{stepsText[step - 1]}</div>
      {step === 1 && renderStepOne()}
      {step === 2 && renderStepTwo()}
      {step === 3 && renderStepThree()}
    </motion.div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#a148f1] to-[#ff68b4] p-4">
      {renderStep()}
    </div>
  );
}
