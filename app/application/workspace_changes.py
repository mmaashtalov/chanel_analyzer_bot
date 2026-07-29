from pathlib import Path

from app.db.workspace_evolution_repository import WorkspaceEvolutionRepository
from app.db.evidence_repository import EvidenceRepository
from app.evidence.engine import attach_document_evidence, build_workspace_evolution_provenance
from app.db.document_evidence_repository import DocumentEvidenceRepository
from app.db.workspace_repository import WorkspaceRepository
from app.reports.workspace_evolution_pdf import build_workspace_evolution_pdf
from app.workspace_evolution.engine import compare_workspace_snapshots


class WorkspaceChangesUseCase:
    def __init__(
        self,
        workspace_repository: WorkspaceRepository,
        evolution_repository: WorkspaceEvolutionRepository,
        output_dir: Path,
        evidence_repository: EvidenceRepository | None = None,
        document_evidence_repository: DocumentEvidenceRepository | None = None,
    ) -> None:
        self._workspace_repository = workspace_repository
        self._evolution_repository = evolution_repository
        self._output_dir = output_dir
        self._evidence_repository = evidence_repository
        self._document_evidence_repository = document_evidence_repository

    async def execute(self, telegram_user_id: int, workspace_id: str, lookback_days: int = 30):
        workspace = await self._workspace_repository.get(telegram_user_id, workspace_id)
        if workspace is None:
            raise LookupError("Workspace не найден")
        pair = await self._evolution_repository.latest_pair(workspace.id, lookback_days)
        if pair is None:
            raise LookupError("Нужно минимум два Workspace snapshot в выбранном периоде")
        baseline, current = pair
        report = compare_workspace_snapshots(
            workspace_name=workspace.name,
            baseline_snapshot_id=baseline.id,
            current_snapshot_id=current.id,
            baseline=baseline.report_json,
            current=current.report_json,
        )
        provenance = build_workspace_evolution_provenance(report)
        if self._document_evidence_repository is not None:
            documents = await self._document_evidence_repository.list_for_workspace(
                workspace.id, report.baseline_generated_at, report.current_generated_at
            )
            provenance = attach_document_evidence(provenance, report, documents)
        path = build_workspace_evolution_pdf(report, self._output_dir, provenance)
        await self._evolution_repository.save(report, str(path))
        if self._evidence_repository is not None:
            await self._evidence_repository.save(provenance)
        return report, path
