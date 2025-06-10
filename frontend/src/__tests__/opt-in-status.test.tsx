import { render, screen, waitFor } from '@testing-library/react';
import * as api from '@/lib/api'; // Changed import
import ContactsPage from '@/app/contacts/[business_name]/page';
import AllEngagementPlansPage from '@/app/all-engagement-plans/[business_name]/page';
import InboxPage from '@/app/inbox/[business_name]/page';

// Mock the API client
jest.mock('@/lib/api'); // Auto-mock (or can use the factory if specific structure needed)
// Let's stick to the factory to be explicit for now, matching previous structure
// jest.mock('@/lib/api', () => ({
//   apiClient: {
//     get: jest.fn(),
//   },
//   getCustomersByBusiness: jest.fn(),
// }));
// For auto-mock to work well, the actual module should export functions directly.
// If it exports a default object, then the mock needs to reflect that.
// Given the previous mock, it implies named exports. So auto-mock should work.

// The mock for 'next/navigation' is now expected to be solely in jest.setup.js
// Ensure jest.setup.js has a comprehensive mock like:
// jest.mock('next/navigation', () => ({
//   useParams: jest.fn(() => ({ business_name: 'test-business' })),
//   useRouter: jest.fn(() => ({ push: jest.fn() })),
//   usePathname: jest.fn(() => '/mock-path'), // Provide a default mock value
//   useSearchParams: jest.fn(() => ({ get: jest.fn((param) => `mockValue-${param}`) })), // Provide a default mock value
// }));

describe('Opt-in Status Consistency', () => {
  const mockBusinessId = 123;
  const mockCustomerId = 456;
  const mockCustomer = {
    id: mockCustomerId,
    customer_name: 'Test Customer',
    opted_in: true,
    phone: '+1234567890',
    latest_consent_status: "opted_in" // Added this field
  };

  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks(); // This clears all mocks, including their implementations.
    
    // Set a default, basic mock for apiClient.get in beforeEach.
    // Tests should override this with specific mockResolvedValueOnce or mockImplementation as needed.
    (api.apiClient.get as jest.Mock).mockResolvedValue({ data: {} });
  });

  describe('Contacts Page', () => {
    it('should display correct opt-in status from customers endpoint', async () => {
      // Mock business ID lookup specifically for this test's setup phase in ContactsPage
      (api.apiClient.get as jest.Mock).mockResolvedValueOnce({ data: { business_id: mockBusinessId } });
      // Mock customers endpoint
      (api.getCustomersByBusiness as jest.Mock).mockResolvedValue([mockCustomer]);

      render(<ContactsPage />);
      
      await waitFor(() => {
        const optInBadge = screen.getByText('Messages On');
        expect(optInBadge).toBeInTheDocument();
      });
    });
  });

  describe('All Engagement Plans Page', () => {
    it('should display correct opt-in status from engagements endpoint', async () => {
      // Mock business ID lookup for AllEngagementPlansPage
      (api.apiClient.get as jest.Mock).mockResolvedValueOnce({ data: { business_id: mockBusinessId } });
      // Mock engagements endpoint (uses api.apiClient.get)
      (api.apiClient.get as jest.Mock).mockResolvedValueOnce({
        data: [{
          customer_id: mockCustomerId,
          customer_name: 'Test Customer',
          opted_in: true,
          latest_consent_status: 'opted_in', // ensure this is included as page uses it
          messages: [{
            id: 1,
            status: 'pending',
            smsContent: 'Test message',
            send_datetime_utc: new Date().toISOString()
          }]
        }]
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
      // Mock for the first apiClient.get call (business ID)
      (api.apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: { business_id: mockBusinessId } })
        // Mock for the second apiClient.get call (customer history)
        .mockResolvedValueOnce({
           data: [{ // This needs to match CustomerSummary[] structure
            customer_id: mockCustomerId,
            customer_name: 'Test Customer',
          opted_in: true,
          consent_status: 'opted_in', // ensure this is included
          messages: []
        }]
      });

      render(<InboxPage />);
      
      await waitFor(() => {
        // InboxPage uses "Opted-In" text directly, not the "Messages On" from OptInStatusBadge
        const optInText = screen.getByText('Opted-In');
        expect(optInText).toBeInTheDocument();
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
          latest_consent_status: "opted_in", // Added this field
          messages: [{
            id: 1,
            status: 'pending',
            smsContent: 'Test message',
            send_datetime_utc: new Date().toISOString()
          }]
        }
      };

      // Mock for ContactsPage
      (api.apiClient.get as jest.Mock).mockResolvedValueOnce({ data: { business_id: mockBusinessId } }); // Business ID
      (api.getCustomersByBusiness as jest.Mock).mockResolvedValueOnce([mockData.customer]); // Customers

      const { rerender } = render(<ContactsPage />);
      await waitFor(() => {
        expect(screen.getByText('Messages On')).toBeInTheDocument();
      });

      // Mock for AllEngagementPlansPage
      // No mockReset() here, rely on beforeEach's clearAllMocks and the default mock.
      // Chain the specific responses needed for this page.
      (api.apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: { business_id: mockBusinessId } }) // For business ID
        .mockResolvedValueOnce({ data: [mockData.engagement] });          // For all engagements

      rerender(<AllEngagementPlansPage />);
      await waitFor(() => {
        expect(screen.getByText('Messages On')).toBeInTheDocument();
      });

      // Mock for InboxPage
      // Chain the specific responses needed for this page.
      (api.apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: { business_id: mockBusinessId } }) // For business ID
        .mockResolvedValueOnce({ data: [mockData.engagement] }); // Full history

      rerender(<InboxPage />);
      await waitFor(() => {
        // InboxPage uses "Opted-In" text directly, not the "Messages On" from OptInStatusBadge
        expect(screen.getByText('Opted-In')).toBeInTheDocument();
      });
    });
  });
}); 