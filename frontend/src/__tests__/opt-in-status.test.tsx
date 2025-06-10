import { render, screen, waitFor } from '@testing-library/react';
import { apiClient } from '@/lib/api';
import ContactsPage from '@/app/contacts/[business_name]/page';
import AllEngagementPlansPage from '@/app/all-engagement-plans/[business_name]/page';
import InboxPage from '@/app/inbox/[business_name]/page';

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn()
  }
}));

// Mock useParams
jest.mock('next/navigation', () => ({
  useParams: () => ({ business_name: 'test-business' }),
  useRouter: () => ({ push: jest.fn() })
}));

describe('Opt-in Status Consistency', () => {
  const mockBusinessId = 123;
  const mockCustomerId = 456;
  const mockCustomer = {
    id: mockCustomerId,
    customer_name: 'Test Customer',
    opted_in: true,
    phone: '+1234567890'
  };

  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks();
    
    // Mock business ID lookup
    (apiClient.get as jest.Mock).mockImplementation((url) => {
      if (url.includes('/business-profile/business-id')) {
        return Promise.resolve({ data: { business_id: mockBusinessId } });
      }
      return Promise.resolve({ data: [] });
    });
  });

  describe('Contacts Page', () => {
    it('should display correct opt-in status from customers endpoint', async () => {
      // Mock customers endpoint
      (apiClient.get as jest.Mock).mockImplementation((url) => {
        if (url === `/customers/by-business/${mockBusinessId}`) {
          return Promise.resolve({ data: [mockCustomer] });
        }
        return Promise.resolve({ data: { business_id: mockBusinessId } });
      });

      render(<ContactsPage />);
      
      await waitFor(() => {
        const optInBadge = screen.getByText('Messages On');
        expect(optInBadge).toBeInTheDocument();
      });
    });
  });

  describe('All Engagement Plans Page', () => {
    it('should display correct opt-in status from engagements endpoint', async () => {
      // Mock engagements endpoint
      (apiClient.get as jest.Mock).mockImplementation((url) => {
        if (url === `/review/all-engagements?business_id=${mockBusinessId}`) {
          return Promise.resolve({
            data: [{
              customer_id: mockCustomerId,
              customer_name: 'Test Customer',
              opted_in: true,
              messages: [{
                id: 1,
                status: 'pending',
                smsContent: 'Test message',
                send_datetime_utc: new Date().toISOString()
              }]
            }]
          });
        }
        return Promise.resolve({ data: { business_id: mockBusinessId } });
      });

      render(<AllEngagementPlansPage />);
      
      await waitFor(() => {
        const optInBadge = screen.getByText('Messages On');
        expect(optInBadge).toBeInTheDocument();
      });
    });
  });

  describe('Inbox Page', () => {
    it('should display correct opt-in status from engagement plan endpoint', async () => {
      // Mock engagement plan endpoint
      (apiClient.get as jest.Mock).mockImplementation((url) => {
        if (url === `/review/engagement-plan/${mockBusinessId}`) {
          return Promise.resolve({
            data: [{
              customer_id: mockCustomerId,
              customer_name: 'Test Customer',
              opted_in: true,
              messages: []
            }]
          });
        }
        return Promise.resolve({ data: { business_id: mockBusinessId } });
      });

      render(<InboxPage />);
      
      await waitFor(() => {
        const optInBadge = screen.getByText('Messages On');
        expect(optInBadge).toBeInTheDocument();
      });
    });
  });

  describe('Cross-page Consistency', () => {
    it('should show same opt-in status across all pages for the same customer', async () => {
      // Setup consistent mock data across all endpoints
      const mockData = {
        customer: mockCustomer,
        engagement: {
          customer_id: mockCustomerId,
          customer_name: 'Test Customer',
          opted_in: true,
          messages: [{
            id: 1,
            status: 'pending',
            smsContent: 'Test message',
            send_datetime_utc: new Date().toISOString()
          }]
        }
      };

      (apiClient.get as jest.Mock).mockImplementation((url) => {
        if (url === `/customers/by-business/${mockBusinessId}`) {
          return Promise.resolve({ data: [mockData.customer] });
        }
        if (url === `/review/all-engagements?business_id=${mockBusinessId}`) {
          return Promise.resolve({ data: [mockData.engagement] });
        }
        if (url === `/review/engagement-plan/${mockBusinessId}`) {
          return Promise.resolve({ data: [mockData.engagement] });
        }
        return Promise.resolve({ data: { business_id: mockBusinessId } });
      });

      // Render all pages
      const { rerender } = render(<ContactsPage />);
      await waitFor(() => {
        expect(screen.getByText('Messages On')).toBeInTheDocument();
      });

      rerender(<AllEngagementPlansPage />);
      await waitFor(() => {
        expect(screen.getByText('Messages On')).toBeInTheDocument();
      });

      rerender(<InboxPage />);
      await waitFor(() => {
        expect(screen.getByText('Messages On')).toBeInTheDocument();
      });
    });
  });
}); 