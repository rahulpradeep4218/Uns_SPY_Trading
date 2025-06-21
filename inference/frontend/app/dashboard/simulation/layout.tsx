import SimulationConfig from "@/app/dashboard/simulation/config";

export default function SimulationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
    <SimulationConfig />
      {children}
    </>
  );
}