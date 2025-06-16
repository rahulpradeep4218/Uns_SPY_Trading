'use client';

import Link from 'next/link';

export default function Sidebar() {
  return (
    <aside className="w-full md:w-64 bg-gray-800 text-white flex-none">
      <div className="p-4 font-bold text-xl border-b border-gray-700">
        TradeNav
      </div>
      <nav className="p-4 space-y-2">
        <Link href="/dashboard" className="block p-2 rounded hover:bg-gray-700">
          Dashboard
        </Link>
        <Link href="/dashboard/realtime" className="block p-2 rounded hover:bg-gray-700">
          Realtime
        </Link>
        <Link href="/dashboard/simulation" className="block p-2 rounded hover:bg-gray-700">
          Simulation
        </Link>
      </nav>
    </aside>
  );
}