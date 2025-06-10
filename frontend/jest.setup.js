import '@testing-library/jest-dom';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: jest.fn() })),
  usePathname: jest.fn(() => '/mock-path'),
  useSearchParams: jest.fn(() => ({
    get: jest.fn((param) => `mockValue-${param}`),
  })),
  useParams: jest.fn(() => ({ business_name: 'test-business' })),
}));
