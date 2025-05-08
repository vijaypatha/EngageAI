// frontend/src/components/OTPVerification.tsx

'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api';
// Import AxiosError if you need more specific error handling
// import { AxiosError } from 'axios';

interface OTPVerificationProps {
  // Update the onVerified prop to expect business_id and slug
  onVerified: (business_id: number, slug: string) => void;
  initialPhoneNumber?: string;
}

export default function OTPVerification({ onVerified, initialPhoneNumber = '' }: OTPVerificationProps) {
  const [phoneNumber, setPhoneNumber] = useState(initialPhoneNumber);
  const [otp, setOTP] = useState('');
  const [isOTPSent, setIsOTPSent] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const formatPhoneNumberToE164 = (raw: string): string => {
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 10) return `+1${digits}`;
    if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
    return raw.startsWith('+') ? raw : `+${raw}`;
  };

  const handleOTPRequest = async () => {
    setError('');
    setIsLoading(true);
    const formattedNumber = formatPhoneNumberToE164(phoneNumber);
    if (!/^\+1\d{10}$/.test(formattedNumber)) {
         setError('Please enter a valid 10-digit US phone number.');
         setIsLoading(false);
         return;
    }

    try {
      console.log(`Requesting OTP for: ${formattedNumber}`);
      await apiClient.post('/auth/request-otp', { phone_number: formattedNumber });
      setIsOTPSent(true);
      setError('');
    } catch (err: any) {
      console.error("OTP Request Error:", err);
      const errorDetail = err.response?.data?.detail || 'Failed to send OTP. Please check the phone number and try again.';
      setError(errorDetail);
      setIsOTPSent(false);
    } finally {
        setIsLoading(false);
    }
  };

  const handleOTPVerify = async () => {
    setError('');
    setIsLoading(true);
    const formattedNumber = formatPhoneNumberToE164(phoneNumber);

    try {
      console.log(`Verifying OTP for: ${formattedNumber} with OTP: ${otp}`);
      const verifyResponse = await apiClient.post('/auth/verify-otp', {
          phone_number: formattedNumber,
          otp
      });

      // Expect 'business_id' and 'slug' in the response
      if (verifyResponse.data && verifyResponse.data.business_id && verifyResponse.data.slug) {
        const businessId = verifyResponse.data.business_id;
        const businessSlug = verifyResponse.data.slug; // Get the slug
        console.log(`OTP verified successfully for business_id: ${businessId}, slug: ${businessSlug}`);

        // Call onVerified with both businessId and businessSlug
        onVerified(businessId, businessSlug);

      } else {
        console.error("Verification succeeded but response missing business_id or slug:", verifyResponse.data);
        setError('Verification failed. Unexpected response from server.');
      }

    } catch (err: any) {
        console.error("OTP Verify Error:", err);
        const errorDetail = err.response?.data?.detail || 'Invalid OTP or verification failed. Please try again.';
        setError(errorDetail);
    } finally {
        setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto rounded-xl bg-[#0C0F1F] shadow-2xl p-8 space-y-6 text-white">
      <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
        Secure your account
      </h2>
      <p className="text-center text-gray-300 text-sm">
         {isOTPSent ? `Enter the code sent to ${phoneNumber}` : 'Verify your phone number to continue'}
      </p>

      {!isOTPSent ? (
        <div className="space-y-4">
          <label htmlFor="phone-number" className="sr-only">Phone Number</label>
          <input
            id="phone-number"
            type="tel"
            autoComplete="tel"
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
            placeholder="Your Phone Number (e.g., +14155551212)"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            disabled={isLoading}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md disabled:opacity-50"
            onClick={handleOTPRequest}
            disabled={isLoading || !phoneNumber}
          >
            {isLoading ? 'Sending...' : 'Send Verification Code'}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <label htmlFor="otp-code" className="sr-only">OTP Code</label>
          <input
            id="otp-code"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete="one-time-code"
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200 tracking-widest text-center text-lg font-mono"
            placeholder="Enter 6-digit code"
            maxLength={6}
            value={otp}
            onChange={(e) => setOTP(e.target.value.replace(/\D/g,''))}
            disabled={isLoading}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md disabled:opacity-50"
            onClick={handleOTPVerify}
            disabled={isLoading || otp.length !== 6}
          >
            {isLoading ? 'Verifying...' : 'Verify Code'}
          </button>
           <button
              onClick={() => { setIsOTPSent(false); setError(''); setOTP(''); }}
              className="text-sm text-gray-400 hover:text-white text-center w-full mt-2 disabled:opacity-50"
              disabled={isLoading}
           >
               Change phone number
           </button>
        </div>
      )}
      {error && <p className="text-red-400 text-center text-sm pt-2">{error}</p>}
    </div>
  );
}