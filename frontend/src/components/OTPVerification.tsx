// frontend/src/components/OTPVerification.tsx

'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api';
// Import the new utility function
import { formatPhoneNumberForDisplay } from '@/lib/phoneUtils'; // Adjust path if needed

interface OTPVerificationProps {
  onVerified: (business_id: number, slug: string) => void;
  initialPhoneNumber?: string;
}

export default function OTPVerification({ onVerified, initialPhoneNumber = '' }: OTPVerificationProps) {
  // Initialize state with potentially pre-formatted number if provided
  const [phoneNumber, setPhoneNumber] = useState(initialPhoneNumber ? formatPhoneNumberForDisplay(initialPhoneNumber) : '');
  const [otp, setOTP] = useState('');
  const [isOTPSent, setIsOTPSent] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Removed the old formatPhoneNumberToE164 function

  const handleOTPRequest = async () => {
    setError('');
    setIsLoading(true);
    // The phoneNumber state should already be formatted by the input's onChange
    const numberToSend = phoneNumber;

    // Optional: Basic client-side check before sending (backend handles final validation)
    // This regex specifically checks for +1 and 10 digits.
    if (!/^\+1\d{10}$/.test(numberToSend)) {
         setError('Please enter a valid US phone number (e.g., +14155551212).');
         setIsLoading(false);
         return;
    }

    try {
      console.log(`Requesting OTP for: ${numberToSend}`);
      // Send the state variable which is formatted by onChange
      await apiClient.post('/auth/request-otp', { phone_number: numberToSend });
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
    // The phoneNumber state should already be formatted by the input's onChange
    const numberToSend = phoneNumber;

    // Optional: Add validation here too if desired

    try {
      console.log(`Verifying OTP for: ${numberToSend} with OTP: ${otp}`);
      // Send the state variable which is formatted by onChange
      const verifyResponse = await apiClient.post('/auth/verify-otp', {
          phone_number: numberToSend,
          otp
      });

      if (verifyResponse.data && verifyResponse.data.business_id && verifyResponse.data.slug) {
        const businessId = verifyResponse.data.business_id;
        const businessSlug = verifyResponse.data.slug;
        console.log(`OTP verified successfully for business_id: ${businessId}, slug: ${businessSlug}`);
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
         {/* Display the formatted phone number from state */}
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
            placeholder="Your Phone Number (e.g., 4155551212)" // Updated placeholder
            value={phoneNumber}
            // Use the formatter directly in onChange to update state
            onChange={(e) => setPhoneNumber(formatPhoneNumberForDisplay(e.target.value))}
            disabled={isLoading}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md disabled:opacity-50"
            onClick={handleOTPRequest}
            disabled={isLoading || !phoneNumber} // Keep basic check for non-empty
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
              onClick={() => { setIsOTPSent(false); setError(''); setOTP(''); /* Consider if phoneNumber should be reset */ }}
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