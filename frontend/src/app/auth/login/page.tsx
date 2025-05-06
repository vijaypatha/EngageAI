'use client';

import { useRouter } from 'next/navigation';
import confetti from 'canvas-confetti';
import OTPVerification from '@/components/OTPVerification'; // Assuming this path is correct

export default function LoginPage() {
  const router = useRouter();

  // --- CORRECTED handleVerified function signature ---
  const handleVerified = (business_id: number, business_name: string | undefined) => {
    // Store business_id (always available)
    localStorage.setItem('business_id', business_id.toString());

    // Conditionally store business_name if it's provided
    if (business_name) {
      localStorage.setItem('business_name', business_name);
    } else {
      // If business_name is undefined, you might want to remove any old one
      localStorage.removeItem('business_name');
      console.warn("OTPVerification provided business_id but no business_name.");
    }

    confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });

    setTimeout(() => {
      // Navigate based on business_id. The dashboard can fetch name if needed.
      // Or, if you have a slug and it's part of business_name (e.g., business_name is the slug),
      // you'd still want to handle the undefined case.
      // For now, let's assume the dashboard URL uses the business_id as it's more robust
      // if the name might be missing from the OTP callback.
      router.push(`/dashboard/${business_id}`); // Or your preferred redirect path
    }, 700);
  };
  // --- END CORRECTION ---

  return (
    <div className="max-w-md mx-auto mt-20 p-6 bg-[#0C0F1F] rounded-xl shadow-2xl">
      {/* This line should no longer cause a type error */}
      <OTPVerification onVerified={handleVerified} />
    </div>
  );
}