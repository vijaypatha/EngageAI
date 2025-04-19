export default function TermsPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-20 text-gray-200">
      <h1 className="text-4xl font-bold mb-6 text-white">Terms of Service</h1>
      <p className="mb-4">Welcome to AI Nudge. By using our platform, you agree to the following terms:</p>
      <ul className="list-disc list-inside space-y-2 mb-8">
        <li>You must be 18 or older to use the service.</li>
        <li>You are responsible for the content of messages sent via your account.</li>
        <li>AI Nudge reserves the right to suspend accounts for spam, abuse, or carrier non-compliance.</li>
        <li>You agree to receive transactional emails or SMS communications from us.</li>
      </ul>
      <p className="text-sm text-gray-400">Last updated April 2025.</p>
    </main>
  );
}
