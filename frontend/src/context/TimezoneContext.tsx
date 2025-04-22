'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { getUserTimezone } from '@/lib/timezone';
import { apiClient } from '@/lib/api';

export interface TimezoneContextType {
  businessTimezone: string;
  updateBusinessTimezone: (timezone: string) => Promise<void>;
  isLoading: boolean;
}

export const TimezoneContext = createContext<TimezoneContextType | undefined>(undefined);

export function TimezoneProvider({ children }: { children: React.ReactNode }) {
  const [businessTimezone, setBusinessTimezone] = useState<string>(getUserTimezone());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const initializeTimezone = async () => {
      try {
        const businessId = localStorage.getItem('business_id');
        if (businessId) {
          // Try to fetch business timezone from API
          const response = await apiClient.get(`/business-profile/${businessId}/timezone`);
          if (response.status === 200) {
            const data = response.data;
            setBusinessTimezone(data.timezone || getUserTimezone());
          } else {
            setBusinessTimezone(getUserTimezone());
          }
        } else {
          setBusinessTimezone(getUserTimezone());
        }
      } catch (error) {
        console.error('Error fetching timezone:', error);
        setBusinessTimezone(getUserTimezone());
      } finally {
        setIsLoading(false);
      }
    };

    initializeTimezone();
  }, []);

  const updateBusinessTimezone = async (timezone: string) => {
    try {
      const businessId = localStorage.getItem('business_id');
      if (businessId) {
        // Update timezone in API
        await apiClient.put(`/business-profile/${businessId}/timezone`, {
          timezone,
        });
      }
      setBusinessTimezone(timezone);
    } catch (error) {
      console.error('Error updating timezone:', error);
    }
  };

  const value: TimezoneContextType = {
    businessTimezone,
    updateBusinessTimezone,
    isLoading,
  };

  return (
    <TimezoneContext.Provider value={value}>
      {children}
    </TimezoneContext.Provider>
  );
}

export function useTimezone(): TimezoneContextType {
  const context = useContext(TimezoneContext);
  if (!context) {
    throw new Error('useTimezone must be used within a TimezoneProvider');
  }
  return context;
} 