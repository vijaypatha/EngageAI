// frontend/src/app/auth/login/page.tsx

'use client';

import { useRouter } from 'next/navigation';
import confetti from 'canvas-confetti';
import OTPVerification from '@/components/OTPVerification';
import { apiClient } from '@/lib/api'; // Import apiClient for session creation

export default function LoginPage() {
  const router = useRouter();

  // Updated handleVerified function to accept slug
  const handleVerified = async (business_id: number, slug: string | undefined) => {
    // Store business_id
    localStorage.setItem('business_id', business_id.toString());

    if (slug) {
      localStorage.setItem('business_slug', slug); // Store slug
      console.log(`OTP Verified. Business ID: ${business_id}, Slug: ${slug}`);
    } else {
      // This case should ideally not happen if backend /verify-otp always returns a slug
      localStorage.removeItem('business_slug');
      console.warn("OTPVerification provided business_id but no slug.");
      // Handle error or redirect to a generic error page if slug is critical and missing
      // For now, we'll proceed, but navigation might fail if slug is required.
    }

    // After OTP is verified, create a session on the backend
    try {
      console.log(`Creating session for business_id: ${business_id}`);
      const sessionResponse = await apiClient.post('/auth/session', { business_id });
      if (sessionResponse.data && sessionResponse.data.slug) {
        // Optionally update localStorage slug again if /session returns a fresher one,
        // though /verify-otp should be the primary source for the initial redirect slug.
        if (slug !== sessionResponse.data.slug) {
            console.warn(`Slug from /session (${sessionResponse.data.slug}) differs from /verify-otp slug (${slug}). Using /session slug.`);
            localStorage.setItem('business_slug', sessionResponse.data.slug);
        }
        console.log("Session created successfully:", sessionResponse.data);
      } else {
        console.error("Session creation failed or response missing slug:", sessionResponse.data);
        // Handle session creation failure (e.g., show error message)
        // This might prevent redirection or cause issues later.
        // For now, we still attempt redirect based on OTP verification slug.
      }
    } catch (sessionError: any) {
      console.error("Error creating session:", sessionError);
      // Handle session creation error (e.g., show error message to user)
      // Depending on severity, you might not want to redirect.
    }

    confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });

    setTimeout(() => {
      if (slug) {
        // Redirect to the desired page using the slug
        router.push(`/contacts/${slug}`);
        console.log(`Redirecting to /contacts/${slug}`);
      } else {
        // Fallback if slug is somehow not available (should be addressed)
        console.error("Cannot redirect: Slug is not available. Redirecting to a default dashboard.");
        router.push(`/dashboard/${business_id}`); // Fallback, but ideally slug is always present
      }
    }, 700);
  };

  return (
    <div className="max-w-md mx-auto mt-20 p-6 bg-[#0C0F1F] rounded-xl shadow-2xl">
      {/* onVerified now expects (business_id: number, slug: string) */}
      <OTPVerification onVerified={handleVerified} />
    </div>
  );
}