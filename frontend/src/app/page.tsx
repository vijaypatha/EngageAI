"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <main
      className={`min-h-screen flex flex-col items-center justify-center px-6 transition-opacity duration-1000 ${
        mounted ? "opacity-100" : "opacity-0"
      } bg-gradient-to-b from-black via-gray-900 to-gray-800 text-white`}
    >
      <h1 className="text-5xl md:text-6xl font-extrabold mb-6 text-center tracking-tight">
        Welcome to <span className="text-green-400">AI Nudge 👋</span>
      </h1>

      <p className="text-xl text-gray-300 mb-10 text-center max-w-2xl leading-relaxed">
        Automatically send smart, human-like SMS messages to your contacts.
        AI Nudge helps you follow up, check in, and grow trust — while you sleep 🛌.
      </p>

      <Link href="/onboarding" passHref>
        <div className="px-8 py-4 bg-gradient-to-r from-green-400 to-blue-500 hover:from-green-500 hover:to-blue-600 text-white rounded-lg text-lg font-medium shadow-lg transition transform hover:scale-105 cursor-pointer">
          🚀 Try It Free — No Login Needed
        </div>
      </Link>

      <p className="mt-6 text-gray-400 text-sm">
        Already using AI Nudge?{" "}
        <Link href="/auth/login" passHref>
          <span className="underline text-blue-400 hover:text-blue-300 cursor-pointer">
            Log in here
          </span>
        </Link>
      </p>
    </main>
  );
}