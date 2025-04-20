import { useEffect, useState } from 'react'
import { apiClient } from '@/lib/api'

interface Business {
  id: number
  business_name: string
  representative_name: string
  industry: string
  business_goal?: string
  primary_services?: string
  twilio_number?: string
}

export function useBusiness(business_name: string) {
  const [business, setBusiness] = useState<Business | null>(null)
  const [businessId, setBusinessId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchBusiness() {
      try {
        const response = await apiClient.get(`/businesses/by-name/${business_name}`)
        setBusiness(response.data)
        setBusinessId(response.data.id)
        setLoading(false)
      } catch (err) {
        console.error('Failed to fetch business:', err)
        setError('Failed to load business data')
        setLoading(false)
      }
    }

    if (business_name) {
      fetchBusiness()
    }
  }, [business_name])

  return { business, businessId, loading, error }
}