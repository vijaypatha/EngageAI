export default function PrivacyPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-20 text-gray-200">
      <h1 className="text-4xl font-bold mb-6 text-white">Privacy Policy</h1>
      <p className="mb-4">Your privacy is important to us. Here’s what we collect and how we use it:</p>
      <ul className="list-disc list-inside space-y-2 mb-8">
        <li>We collect your name, business info, and communication history to personalize your messages.</li>
        <li>We do not sell your data. Ever.</li>
        <li>Message logs are encrypted and stored securely to ensure compliance and auditability.</li>
        <li>You can request deletion of your account and data at any time.</li>
      </ul>
      <p className="text-sm text-gray-400">Last updated April 2025.</p>
    </main>
  );
}
