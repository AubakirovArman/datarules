import { SimpleFlow } from "@features/simple-flow/SimpleFlow";
import type { SimpleFlowProps as Props } from "@features/simple-flow/types";

export function FlowPage({
  selected,
  disabled,
  files,
  job,
  events,
  summaries,
  reviews,
  proposals,
  loadPlans,
  connections,
  tables,
  datasetId,
  onUpload,
  onDelete,
  onRefreshFiles,
  onStart,
  onRefreshSummaries,
  onRefreshReviews,
  onConfirmReview,
  onRefreshProposals,
  onApproveSchema,
  onSchemaChat,
  onCreateLoadPlan,
  onUpdateLoadPlanRows,
  onConfirmLoadPlan,
  onSearch,
  onAsk,
  t,
}: Props) {
  return (
    <SimpleFlow
      selected={selected}
      disabled={disabled}
      files={files}
      job={job}
      events={events}
      summaries={summaries}
      reviews={reviews}
      proposals={proposals}
      loadPlans={loadPlans}
      connections={connections}
      tables={tables}
      datasetId={datasetId}
      onUpload={onUpload}
      onDelete={onDelete}
      onRefreshFiles={onRefreshFiles}
      onStart={onStart}
      onRefreshSummaries={onRefreshSummaries}
      onRefreshReviews={onRefreshReviews}
      onConfirmReview={onConfirmReview}
      onRefreshProposals={onRefreshProposals}
      onApproveSchema={onApproveSchema}
      onSchemaChat={onSchemaChat}
      onCreateLoadPlan={onCreateLoadPlan}
      onUpdateLoadPlanRows={onUpdateLoadPlanRows}
      onConfirmLoadPlan={onConfirmLoadPlan}
      onSearch={onSearch}
      onAsk={onAsk}
      t={t}
    />
  );
}
