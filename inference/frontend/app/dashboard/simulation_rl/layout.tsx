import SimulationRLConfig from "@/app/dashboard/simulation_rl/config";

export default function SimulationRLLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
    <SimulationRLConfig />
      {children}
    </>
  );
}