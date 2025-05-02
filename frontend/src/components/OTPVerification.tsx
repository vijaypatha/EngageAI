'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api';

interface OTPVerificationProps {
  onVerified: (business_id: number, business_name: string) => void;
  initialPhoneNumber?: string;
}

export default function OTPVerification({ onVerified, initialPhoneNumber = '' }: OTPVerificationProps) {
  const [phoneNumber, setPhoneNumber] = useState(initialPhoneNumber);
  const [otp, setOTP] = useState('');
  const [isOTPSent, setIsOTPSent] = useState(false);
  const [error, setError] = useState('');

  const formatPhoneNumberToE164 = (raw: string): string => {
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 10) return `+1${digits}`;
    if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
    return raw; // fallback: let backend validate
  };

  const handleOTPRequest = async () => {
    try {
      await apiClient.post('/auth/request-otp', { phone_number: formatPhoneNumberToE164(phoneNumber) });
      setIsOTPSent(true);
      setError('');
    } catch (err) {
      setError('Failed to send OTP. Check the phone number.');
    }
  };

  const handleOTPVerify = async () => {
    try {
      await apiClient.post('/auth/verify-otp', { phone_number: formatPhoneNumberToE164(phoneNumber), otp });
      const res = await apiClient.get('/auth/me');
      onVerified(res.data.business_id, res.data.business_name);
    } catch (err) {
      setError('Invalid OTP. Please try again.');
    }
  };

  return (
    <div className="w-full max-w-md mx-auto rounded-xl bg-[#0C0F1F] shadow-2xl p-8 space-y-6 text-white">
      <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
        Log In to AI Nudge
      </h2>
      {!isOTPSent ? (
        <>
          <input
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
            placeholder="Enter your 10-digit phone number"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md"
            onClick={handleOTPRequest}
          >
            Send OTP
          </button>
        </>
      ) : (
        <>
          <input
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200 tracking-widest text-center"
            placeholder="Enter 6-digit OTP"
            maxLength={6}
            value={otp}
            onChange={(e) => setOTP(e.target.value)}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md"
            onClick={handleOTPVerify}
          >
            Verify OTP
          </button>
        </>
      )}
      {error && <p className="text-red-400 text-center text-sm">{error}</p>}
    </div>
  );
}