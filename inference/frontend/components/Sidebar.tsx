'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';
import { usePageContext } from '@/context/PageContext';

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebar_fields } = usePageContext();
  const navItems = [
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/dashboard/realtime', label: 'Realtime' },
    { href: '/dashboard/simulation', label: 'Simulation' },
  ]
  return (
    <aside className="w-full md:w-64 bg-gray-800 text-white flex-none">
      <div className="p-4 font-bold text-xl border-b border-gray-700">
        Rahuls Trading System
      </div>
      <nav className="p-4 space-y-2">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              'block p-2 rounded hover:bg-indigo-700',
              {
                'font-semibold ring-2 ring-[#2f639d] bg-[#000000]': pathname === item.href,
                'bg-[#525151]': pathname !== item.href
              }
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Configuration Section */}
      <div className="p-4 space-y-2">
        {sidebar_fields}
      </div>
    </aside>
  );
}