import RealtimeConfig from "@/app/dashboard/realtime/config";

export default function RealtimeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
    <RealtimeConfig />
      {children}
    </>
  );
}