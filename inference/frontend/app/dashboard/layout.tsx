import Sidebar from '@/components/Sidebar';
import { PageContextProvider } from '@/context/PageContext';

export default function DashboardLayout({
  children,
  sidebarConfig,
}: {
  children: React.ReactNode;
  sidebarConfig?: React.ReactNode;
}) {
  return (
    <PageContextProvider>
      <div className="flex h-screen flex-col md:flex-row md:overflow-hidden">
        <div className="w-full flex-none md:w-64">
          <Sidebar>{sidebarConfig}</Sidebar>
        </div>
        <div className="flex-grow p-6 md:overflow-y-auto md:p-12">{children}</div>
      </div>
    </PageContextProvider>
  );
}
