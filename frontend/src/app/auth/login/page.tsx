'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import confetti from 'canvas-confetti';

export default function LoginPage() {
  const router = useRouter();
  const [businessName, setBusinessName] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const saved = localStorage.getItem('business_name');
    if (saved) setBusinessName(saved);
  }, []);

  const handleLogin = async () => {
    try {
      const res = await apiClient.get(`/business-profile/business-id/slug/${businessName}`);
      const businessId = res.data.business_id;

      localStorage.setItem('business_id', businessId.toString());
      localStorage.setItem('business_name', businessName);

      confetti({
        particleCount: 100,
        spread: 80,
        origin: { y: 0.6 },
      });

      setTimeout(() => {
        router.push(`/dashboard/${res.data.business_id}`);
      }, 700);
    } catch (err) {
      setError('Business not found. Please try again.');
    }
  };

  return (
    <div className="max-w-md mx-auto mt-20 px-4">
      <h1 className="text-3xl font-bold mb-6 text-white">Login to AI Nudge</h1>

      <input
        type="text"
        placeholder="Enter your business name"
        value={businessName}
        onChange={(e) => setBusinessName(e.target.value)}
        className="w-full p-3 rounded mb-4 border border-gray-300"
      />

      {error && <p className="text-red-500 mb-4">{error}</p>}

      <button
        onClick={handleLogin}
        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 rounded"
      >
        Log In
      </button>

      <p className="text-sm text-gray-400 mt-4 text-center">
        Don’t have an account?{' '}
        <a href="/onboarding" className="underline text-blue-300 hover:text-blue-200">
          Create one
        </a>
      </p>
    </div>
  );
}