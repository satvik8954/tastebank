import { ClientDashboard } from "@/components/ClientDashboard";

export default async function ClientPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClientDashboard clientId={id} />;
}
