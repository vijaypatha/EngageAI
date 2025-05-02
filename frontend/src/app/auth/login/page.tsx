'use client';

import { useRouter } from 'next/navigation';
import confetti from 'canvas-confetti';
import OTPVerification from '@/components/OTPVerification';

export default function LoginPage() {
  const router = useRouter();

  const handleVerified = (business_id: number, business_name: string) => {
    localStorage.setItem('business_id', business_id.toString());
    localStorage.setItem('business_name', business_name);

    confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });

    setTimeout(() => {
      router.push(`/dashboard/${business_id}`);
    }, 700);
  };

  return (
    <div className="max-w-md mx-auto mt-20 p-6 bg-[#0C0F1F] rounded-xl shadow-2xl">
      <OTPVerification onVerified={handleVerified} />
    </div>
  );
}