'use client';

import { usePathname } from 'next/navigation';
import { TimezoneProvider } from '@/context/TimezoneContext';
import { Navigation } from '@/components/Navigation';
import { PageWrapper } from '@/components/PageWrapper';

export default function ClientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isLandingPage = pathname === "/";
  const isOnboardingPage = pathname === "/onboarding";
  const isAuthPage = pathname.startsWith("/auth");
  const shouldShowNavigation = !isLandingPage && !isOnboardingPage && !isAuthPage;

  return (
    <TimezoneProvider>
      {shouldShowNavigation && <Navigation />}
      <PageWrapper>
        {children}
      </PageWrapper>
    </TimezoneProvider>
  );
} 