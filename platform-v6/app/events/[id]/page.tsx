import { EventDetailView } from "@/features/event-detail/event-detail-view";

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EventDetailView id={id} />;
}
