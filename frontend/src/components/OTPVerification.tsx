// frontend/src/components/OTPVerification.tsx

'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api';
// Import AxiosError if you need more specific error handling
// import { AxiosError } from 'axios'; 

interface OTPVerificationProps {
  onVerified: (business_id: number, business_name?: string) => void; // Make business_name optional for now
  initialPhoneNumber?: string;
}

export default function OTPVerification({ onVerified, initialPhoneNumber = '' }: OTPVerificationProps) {
  const [phoneNumber, setPhoneNumber] = useState(initialPhoneNumber);
  const [otp, setOTP] = useState('');
  const [isOTPSent, setIsOTPSent] = useState(false);
  const [isLoading, setIsLoading] = useState(false); // Add loading state
  const [error, setError] = useState('');

  const formatPhoneNumberToE164 = (raw: string): string => {
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 10) return `+1${digits}`;
    if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
    // Allow potentially invalid formats through? Or handle better?
    // Consider adding + if missing and length > 10?
    return raw.startsWith('+') ? raw : `+${raw}`; 
  };

  const handleOTPRequest = async () => {
    setError(''); // Clear previous errors
    setIsLoading(true);
    const formattedNumber = formatPhoneNumberToE164(phoneNumber);
    // Basic frontend check - adjust regex/logic as needed
    if (!/^\+1\d{10}$/.test(formattedNumber)) {
         setError('Please enter a valid 10-digit US phone number.');
         setIsLoading(false);
         return;
    }

    try {
      console.log(`Requesting OTP for: ${formattedNumber}`); // Log formatted number
      await apiClient.post('/auth/request-otp', { phone_number: formattedNumber });
      setIsOTPSent(true);
      setError('');
    } catch (err: any) { // Use any or AxiosError
      console.error("OTP Request Error:", err);
      const errorDetail = err.response?.data?.detail || 'Failed to send OTP. Please check the phone number and try again.';
      setError(errorDetail);
      setIsOTPSent(false); // Stay on phone input if request fails
    } finally {
        setIsLoading(false);
    }
  };

  const handleOTPVerify = async () => {
    setError(''); // Clear previous errors
    setIsLoading(true);
    const formattedNumber = formatPhoneNumberToE164(phoneNumber);

    try {
      // 1. Call verify-otp and get the response
      console.log(`Verifying OTP for: ${formattedNumber} with OTP: ${otp}`); // Log what's being sent
      const verifyResponse = await apiClient.post('/auth/verify-otp', { 
          phone_number: formattedNumber, 
          otp 
      });

      // 2. Check if the response contains the expected business_id
      if (verifyResponse.data && verifyResponse.data.business_id) {
        const businessId = verifyResponse.data.business_id;
        console.log(`OTP verified successfully for business_id: ${businessId}`);
        
        // 3. Call the onVerified callback with the business_id
        //    We don't have business_name here, pass undefined or modify parent
        onVerified(businessId); // <<< PASS businessId back

      } else {
        // This case shouldn't happen if backend returns 200 OK with the correct structure
        console.error("Verification succeeded (200 OK) but response missing business_id:", verifyResponse.data);
        setError('Verification failed. Unexpected response.');
      }

    } catch (err: any) { // Use any or AxiosError
        console.error("OTP Verify Error:", err);
        // Extract error detail from backend response if available (like "Invalid OTP")
        const errorDetail = err.response?.data?.detail || 'Invalid OTP or verification failed. Please try again.';
        setError(errorDetail);
    } finally {
        setIsLoading(false);
    }
  };

  return (
    // --- Keep existing JSX structure ---
    <div className="w-full max-w-md mx-auto rounded-xl bg-[#0C0F1F] shadow-2xl p-8 space-y-6 text-white">
      <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
        {/* Conditional Title based on Login/Onboarding context could be added */}
        Secure your account 
      </h2>
      <p className="text-center text-gray-300 text-sm">
         {isOTPSent ? `Enter the code sent to ${phoneNumber}` : 'Verify your phone number to continue'}
      </p>

      {!isOTPSent ? (
        // --- Phone Number Input Stage ---
        <div className="space-y-4">
          <label htmlFor="phone-number" className="sr-only">Phone Number</label>
          <input
            id="phone-number"
            type="tel" // Use type="tel" for better mobile experience
            autoComplete="tel" // Help browsers autofill
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
            placeholder="Your Phone Number (e.g., +14155551212)"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            // Optional: Add formatting on blur? Be careful not to interfere with typing.
            // onBlur={(e) => setPhoneNumber(formatPhoneNumberToE164(e.target.value))} 
            disabled={isLoading}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md disabled:opacity-50"
            onClick={handleOTPRequest}
            disabled={isLoading || !phoneNumber} // Disable if loading or no phone number
          >
            {isLoading ? 'Sending...' : 'Send Verification Code'}
          </button>
        </div>
      ) : (
        // --- OTP Input Stage ---
        <div className="space-y-4">
          <label htmlFor="otp-code" className="sr-only">OTP Code</label>
          <input
            id="otp-code"
            type="text" // Use text, but add inputMode="numeric"
            inputMode="numeric" 
            pattern="[0-9]*" // Helps mobile keyboards
            autoComplete="one-time-code" // Helps autofill from SMS
            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/90 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200 tracking-widest text-center text-lg font-mono"
            placeholder="Enter 6-digit code"
            maxLength={6}
            value={otp}
            onChange={(e) => setOTP(e.target.value.replace(/\D/g,''))} // Allow only digits
            disabled={isLoading}
          />
          <button
            className="w-full bg-gradient-to-r from-emerald-400 to-blue-500 text-white font-semibold py-3 rounded-lg hover:opacity-90 transition-all shadow-md disabled:opacity-50"
            onClick={handleOTPVerify}
            disabled={isLoading || otp.length !== 6} // Disable if loading or OTP length isn't 6
          >
            {isLoading ? 'Verifying...' : 'Verify Code'}
          </button>
            {/* Optional: Add a "Resend OTP" button here */}
           <button 
              onClick={() => { setIsOTPSent(false); setError(''); setOTP(''); }} // Go back to phone input
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