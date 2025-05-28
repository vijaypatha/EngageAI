// frontend/src/app/page.tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Target, Users, ListChecks, CalendarCheck, Smile, Zap, Heart, MapPin, Route, CheckSquare, Bot, MessageCircleHeart  } from "lucide-react"; // Added Heart

// Define a type for your testimonial data for better structure
interface Testimonial {
  name: string;
  title: string;
  img: string;
  quote: string;
}

// Define a type for "How it works" steps
interface HowItWorksStep {
  icon: React.ElementType;
  title: string;
  description: string;
}

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const howItWorksSteps: HowItWorksStep[] = [
    { icon: Target, title: "1. Define Your Goals", description: "Clearly set what you want to achieve with client communication." },
    { icon: Users, title: "2. Add Your Contacts", description: "Easily import or manually add your client information and key notes." },
    { icon: ListChecks, title: "3. Create Nudge Plans", description: "Our AI helps craft personalized, multi-step message sequences." },
    { icon: CalendarCheck, title: "4. Review & Schedule", description: "Approve AI-drafted messages and let the autopilot take over." },
    { icon: Smile, title: "5. Build Connections", description: "Forge lasting relationships with timely, thoughtful, and personal nudges." },
    { icon: Zap, title: "6. Send Instant Nudges", description: "Quickly send targeted one-off messages for announcements or offers." },
  ];

  const testimonials: Testimonial[] = [
    {
      name: "Dr. Eliza Stone",
      title: "CareBridge Therapy",
      img: "https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=300&h=300&q=80",
      quote: "AI Nudge lets me stay in touch with clients in a way that feels authentic and saves me so much time. It's a game-changer for my practice."
    },
    {
      name: "Marcus Bell",
      title: "Bell Financial Planning",
      img: "https://images.unsplash.com/photo-1552058544-f2b08422138a?auto=format&fit=crop&w=300&h=300&q=80",
      quote: "The reminders and check-ins are so personalized, they look like I wrote them myself. It builds incredible trust and keeps clients engaged."
    },
    {
      name: "Sofia Tran",
      title: "Red Rose Yoga Studio",
      img: "https://images.unsplash.com/photo-1607746882042-944635dfe10e?auto=format&fit=crop&w=300&h=300&q=80",
      quote: "I can focus on teaching and providing care to my students. AI Nudge handles the follow-ups with kindness and clarity, keeping everyone informed."
    },
    {
      name: "Reggie Scott",
      title: "Scott & Co. Realty",
      img: "https://images.unsplash.com/photo-1573497491208-6b1acb260507?auto=format&fit=crop&w=300&h=300&q=80",
      quote: "While I'm focused on closing deals for one client, AI Nudge is effortlessly connecting with all my other prospects and past clients. That's real ROI."
    }
  ];

  return (
    <main
      className={`min-h-screen w-full flex flex-col justify-start transition-opacity duration-1000 ${
        mounted ? "opacity-100" : "opacity-0"
      } bg-gradient-to-b from-black via-gray-900 to-gray-800 text-gray-200`}
    >
      {/* Hero Section */}
      <section className="w-full bg-nudge-gradient flex flex-col items-center justify-center py-28 md:py-36 lg:py-48 text-center min-h-[75vh] md:min-h-[65vh] px-4">
        <div className="max-w-4xl mx-auto">
        <div className="flex justify-center mb-10 md:mb-12">
            <div className="relative overflow-hidden group rounded-lg">
              <Image
                src="/AI Nudge Logo.png"
                alt="AI Nudge Logo"
                width={800}
                height={160}
                priority
                className="block drop-shadow-2xl max-w-full h-auto"
              />
              <div
                className="absolute inset-0 w-full h-full
                           animate-logo-shine
                           bg-gradient-to-r from-transparent via-white/5 to-transparent group-hover:via-pink-400/10 transition-all duration-500" // Subtle pink hint on hover in shine
              ></div>
            </div>
          </div>
          <h2 className="text-2xl md:text-3xl lg:text-4xl text-gray-100 mb-4 leading-tight max-w-3xl mx-auto font-semibold">
            Client Engagement, Back to Basics. <span className="whitespace-nowrap">Powered by AI.</span>
          </h2>

          <p className="text-lg md:text-xl lg:text-2xl text-gray-400 mb-12 leading-relaxed max-w-2xl mx-auto">
          We help your customers remember you with timely, personal SMS messages, automatically and in <span className="text-gradient-accent font-medium">your authentic style</span>. {/* Used pink/purple accent here */}
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-5">
            <Link href="/onboarding" passHref>
              <button className="btn-primary text-lg md:text-xl px-10 py-4 transform transition-all duration-300 ease-in-out hover:scale-105 hover:shadow-glow focus:outline-none focus:ring-4 focus:ring-emerald-500/60 w-full sm:w-auto font-semibold">
                🚀 Try It Free — No Login Needed
              </button>
            </Link>
            {/* Example for a secondary button - uncomment and style if needed
            <Link href="#how-it-works" passHref>
              <button className="text-gray-300 hover:text-white font-medium py-4 px-10 rounded-lg transition-colors border-2 border-gray-700 hover:border-gray-500 w-full sm:w-auto flex items-center justify-center text-lg md:text-xl">
                Learn How <ArrowRight className="inline-block ml-2 w-5 h-5" />
              </button>
            </Link>
            */}
          </div>
          <p className="mt-12 text-gray-400 text-base">
            Already using AI Nudge?{" "}
            <Link href="/auth/login" passHref>
              <span className="underline text-blue-400 hover:text-purple-400 transition-colors cursor-pointer font-medium"> {/* Purple hover for login */}
                Log in here
              </span>
            </Link>
          </p>
        </div>
      </section>

      {/* AI Nudge is Your GPS Section */}
      <section id="how-it-works-gps" className="py-16 md:py-28 bg-gray-900">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14 md:mb-20">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white">
              AI Nudge is your GPS for <span className="text-gradient">Staying Top-of-Mind</span> {/* Assuming text-gradient is your main teal/blue */}
            </h2>
            <p className="mt-5 text-lg md:text-xl text-gray-400 max-w-2xl mx-auto">
              Navigate client engagement effortlessly. We guide you every step of the way.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-10">
            {/* Step 1: Set Destination */}
            <div className="card p-6 md:p-8 rounded-xl text-center flex flex-col items-center transform transition-all duration-300 hover:scale-105 hover:shadow-xl hover:border-pink-500/50"> {/* Example pink hover border */}
              <div className="p-4 bg-gradient-to-br from-red-500/10 via-pink-500/10 to-orange-500/10 rounded-full mb-6">
                <MapPin className="w-10 h-10 text-red-400" />
              </div>
              <h3 className="text-xl font-semibold text-white mb-3">Step 1: Set Destination</h3>
              <p className="text-base text-gray-400 flex-grow leading-relaxed">
                Define your client engagement goals, teach AI Nudge your unique communication style, and add your contacts.
              </p>
            </div>

            {/* Step 2: See The Route - Applying Pink/Purple Accent */}
            <div className="card p-6 md:p-8 rounded-xl text-center flex flex-col items-center transform transition-all duration-300 hover:scale-105 hover:shadow-xl hover:border-purple-500/50">
              <div className="p-4 bg-gradient-to-br from-purple-500/10 via-pink-500/10 to-fuchsia-500/10 rounded-full mb-6"> {/* Pink/Purple icon background */}
                <Route className="w-10 h-10 text-purple-400" /> {/* Purple icon */}
              </div>
              <h3 className="text-xl font-semibold text-white mb-3">Step 2: See The Route</h3>
              <p className="text-base text-gray-400 flex-grow leading-relaxed">
                Our AI drafts personalized nudges in your voice, precisely mapped to achieve your engagement goals.
              </p>
            </div>

            {/* Step 3: Follow or Adjust */}
            <div className="card p-6 md:p-8 rounded-xl text-center flex flex-col items-center transform transition-all duration-300 hover:scale-105 hover:shadow-xl hover:border-emerald-500/50">
              <div className="p-4 bg-gradient-to-br from-emerald-500/10 via-green-500/10 to-teal-500/10 rounded-full mb-6">
                <CheckSquare className="w-10 h-10 text-emerald-400" />
              </div>
              <h3 className="text-xl font-semibold text-white mb-3">Step 3: Follow or Adjust</h3>
              <p className="text-base text-gray-400 flex-grow leading-relaxed">
                Review the AI-generated engagement plan. Let it run automatically, or easily make adjustments as needed.
              </p>
            </div>
          </div>

          <p className="mt-16 md:mt-20 text-xl md:text-2xl text-center text-gray-300 font-medium max-w-3xl mx-auto leading-relaxed">
            AI Nudge <span className="text-gradient">learns your style</span>,
            sounds like <span className="text-gradient-accent">you</span>, {/* Pink/Purple for "you" */}
            and connects with your <span className="text-gradient">customers</span>.
          </p>
        </div>
      </section>

      {/* Testimonials Section - THIS IS THE SECTION THAT WAS MISSING */}
      <section className="py-16 md:py-28 bg-gray-800"> {/* Consistent background with main theme */}
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14 md:mb-20">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-4 text-white">
              Small Businesses <Heart className="inline-block w-10 h-10 text-red-500 animate-pulse fill-current" /> AI Nudge
            </h2>
            <p className="mt-5 text-lg md:text-xl text-gray-400 max-w-2xl mx-auto">
              See how professionals like you build stronger, more personal client connections.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-10">
            {testimonials.map((person, i) => (
              <div key={i} className="card p-6 md:p-8 text-center group hover:shadow-glow-purple transition-all duration-300 flex flex-col items-center rounded-xl"> {/* Applied hover:shadow-glow-purple */}
                <Image src={person.img} alt={person.name} width={100} height={100} className="rounded-full mx-auto mb-6 object-cover border-4 border-white/20 shadow-lg" />
                <h3 className="font-semibold text-xl text-white mb-1">{person.name}</h3>
                <p className="text-sm text-gray-400 mb-5">{person.title}</p>
                <p className="text-md italic text-gray-300 leading-relaxed">"{person.quote}"</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="text-base text-center space-y-8 border-t border-white/10 pt-16 pb-12 bg-black">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-center mb-6">
            <Image
              src="/AI Nudge Logo.png"
              alt="AI Nudge Footer Logo"
              width={220} // Slightly larger footer logo
              height={44}
            />
          </div>
          <p className="text-gray-400">Small Nudges. Smart Guidance. Stronger Connections.</p>
          <p className="text-gray-400">Lovingly crafted in St. George, UT</p>
          <a href="mailto:support@ainudge.app" className="block text-blue-400 hover:text-purple-300 underline transition-colors text-lg"> {/* Purple hover */}
            support@ainudge.app
          </a>
          <p className="text-gray-400 mt-2">
            Nudge us with questions like "what is AI Nudge?" or "How will AI Nudge help my business grow?" @ <a href="sms:+14352721987" className="text-blue-400 hover:text-purple-300 underline transition-colors">435-272-1987</a> {/* Purple hover */}
          </p>

          <div className="mt-10 space-x-6 font-medium">
            <Link href="/terms" className="text-gray-400 hover:text-white underline transition-colors">Terms of Service</Link>
            <Link href="/privacy" className="text-gray-400 hover:text-white underline transition-colors">Privacy Policy</Link>
          </div>

          <div className="mt-10 space-y-2 text-gray-500 text-xs max-w-2xl mx-auto">
            <p className="italic">Registered A2P 10DLC Messaging Provider (USA) · Fully compliant with carrier guidelines.</p>
            <p className="italic">All messages include opt-out language. Reply STOP to unsubscribe. Standard message rates may apply. Message frequency varies.</p>
            <p className="mt-3">Message and data rates may apply. Carriers are not liable for delayed or undelivered messages.</p>
            <p className="mt-8 text-gray-400">&copy; {new Date().getFullYear()} AI Nudge. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </main>
  );
}