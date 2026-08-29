import { useEffect, useMemo, useState } from 'react';

import api, {
  type ArtifactOverview,
  type ArtifactSource,
  type ArtifactSourceSummary,
  type ChatEpisodeState,
  type ConsolidatedFactArtifactSummary,
  type ConsolidatedFactDetail,
  type DreamRunArtifact,
  type DreamRunArtifactSummary,
  type EntityArtifactDetail,
  type EntityRecord,
  type EpisodeArtifact,
  type EpisodeArtifactSummary,
  type MemoryClaimArtifact,
  type MemoryClaimArtifactSummary,
  type OrganizationProposalArtifact,
  type ReconsolidationProposalArtifact,
  type StoredMemoryFile,
  type StoredMemoryFiles,
} from '../../lib/api';
import type { InspectorTab, SelectedFile } from './types';

function availableId<T>(current: string | null, items: T[], id: (item: T) => string) {
  return current && items.some((item) => id(item) === current) ? current : items[0] ? id(items[0]) : null;
}

export function useMemoryInspector(refreshKey: number) {
  const [activeTab, setActiveTab] = useState<InspectorTab>('overview');
  const [overview, setOverview] = useState<ArtifactOverview | null>(null);
  const [chatEpisodes, setChatEpisodes] = useState<ChatEpisodeState[]>([]);
  const [sources, setSources] = useState<ArtifactSourceSummary[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeArtifactSummary[]>([]);
  const [claims, setClaims] = useState<MemoryClaimArtifactSummary[]>([]);
  const [facts, setFacts] = useState<ConsolidatedFactArtifactSummary[]>([]);
  const [entities, setEntities] = useState<EntityRecord[]>([]);
  const [organizationProposals, setOrganizationProposals] = useState<OrganizationProposalArtifact[]>([]);
  const [proposals, setProposals] = useState<ReconsolidationProposalArtifact[]>([]);
  const [dreamRuns, setDreamRuns] = useState<DreamRunArtifactSummary[]>([]);
  const [files, setFiles] = useState<StoredMemoryFiles | null>(null);

  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedOrganizationProposalId, setSelectedOrganizationProposalId] = useState<string | null>(null);
  const [selectedDreamRunId, setSelectedDreamRunId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);

  const [selectedSource, setSelectedSource] = useState<ArtifactSource | null>(null);
  const [selectedEpisode, setSelectedEpisode] = useState<EpisodeArtifact | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<MemoryClaimArtifact | null>(null);
  const [selectedFact, setSelectedFact] = useState<ConsolidatedFactDetail | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<EntityArtifactDetail | null>(null);
  const [selectedDreamRun, setSelectedDreamRun] = useState<DreamRunArtifact | null>(null);
  const [selectedProposal, setSelectedProposal] = useState<ReconsolidationProposalArtifact | null>(null);
  const [proposalClaims, setProposalClaims] = useState<Record<string, MemoryClaimArtifact>>({});

  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [reviewNote, setReviewNote] = useState('');
  const [reviewing, setReviewing] = useState<'approve' | 'reject' | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        if (activeTab === 'overview') {
          const response = await api.get<ArtifactOverview>('/memory/artifacts/overview');
          if (!cancelled) setOverview(response.data);
        } else if (activeTab === 'chat') {
          const response = await api.get<ChatEpisodeState[]>('/memory/artifacts/chat-episodes');
          if (!cancelled) {
            setChatEpisodes(response.data);
            setSelectedChatId((value) => availableId(value, response.data, (item) => item.session_id));
          }
        } else if (activeTab === 'sources') {
          const response = await api.get<ArtifactSourceSummary[]>('/memory/artifacts/sources');
          const ordered = [...response.data].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
          if (!cancelled) {
            setSources(ordered);
            setSelectedSourceId((value) => availableId(value, ordered, (item) => item.source_id));
          }
        } else if (activeTab === 'episodes') {
          const response = await api.get<EpisodeArtifactSummary[]>('/memory/artifacts/episodes');
          if (!cancelled) {
            setEpisodes(response.data);
            setSelectedEpisodeId((value) => availableId(value, response.data, (item) => item.episode_id));
          }
        } else if (activeTab === 'claims') {
          const response = await api.get<MemoryClaimArtifactSummary[]>('/memory/artifacts/claims');
          if (!cancelled) {
            setClaims(response.data);
            setSelectedClaimId((value) => availableId(value, response.data, (item) => item.claim_id));
          }
        } else if (activeTab === 'facts') {
          const response = await api.get<ConsolidatedFactArtifactSummary[]>('/memory/artifacts/consolidated-facts');
          if (!cancelled) {
            setFacts(response.data);
            setSelectedFactId((value) => availableId(value, response.data, (item) => item.fact_id));
          }
        } else if (activeTab === 'entities') {
          const response = await api.get<EntityRecord[]>('/memory/artifacts/entities');
          if (!cancelled) {
            setEntities(response.data);
            setSelectedEntityId((value) => availableId(value, response.data, (item) => item.entity_id));
          }
        } else if (activeTab === 'organization') {
          const response = await api.get<OrganizationProposalArtifact[]>('/memory/artifacts/organization-proposals');
          const ordered = [...response.data].sort((a, b) => {
            if (a.status === 'pending' && b.status !== 'pending') return -1;
            if (b.status === 'pending' && a.status !== 'pending') return 1;
            return b.created_at.localeCompare(a.created_at);
          });
          if (!cancelled) {
            setOrganizationProposals(ordered);
            setSelectedOrganizationProposalId((value) => availableId(value, ordered, (item) => item.proposal_id));
          }
        } else if (activeTab === 'reconsolidation') {
          const response = await api.get<ReconsolidationProposalArtifact[]>('/memory/artifacts/reconsolidation-proposals');
          const ordered = [...response.data].sort((a, b) => {
            if (a.status === 'pending' && b.status !== 'pending') return -1;
            if (b.status === 'pending' && a.status !== 'pending') return 1;
            return b.created_at.localeCompare(a.created_at);
          });
          if (!cancelled) {
            setProposals(ordered);
            setSelectedProposalId((value) => availableId(value, ordered, (item) => item.proposal_id));
          }
        } else if (activeTab === 'dream-runs') {
          const response = await api.get<DreamRunArtifactSummary[]>('/memory/artifacts/dream-runs');
          if (!cancelled) {
            setDreamRuns(response.data);
            setSelectedDreamRunId((value) => availableId(value, response.data, (item) => item.run_id));
          }
        } else if (activeTab === 'files') {
          const response = await api.get<StoredMemoryFiles>('/memory/artifacts/files');
          if (!cancelled) {
            setFiles(response.data);
            const available: SelectedFile[] = [
              ...(response.data.wiki_index ? [{ ...response.data.wiki_index, group: 'index' as const }] : []),
              ...response.data.archived_pages.map((file) => ({ ...file, group: 'archive' as const })),
            ];
            setSelectedFile((value) => {
              const match = value && available.find((file) => file.group === value.group && file.filename === value.filename);
              return match ?? available[0] ?? null;
            });
          }
        }
      } catch (loadError) {
        console.error('Failed to load memory artifacts', loadError);
        if (!cancelled) setError(`The ${activeTab} artifacts could not be loaded.`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [activeTab, refreshKey, reloadKey]);

  useEffect(() => {
    const hasSelection =
      (activeTab === 'sources' && selectedSourceId) ||
      (activeTab === 'episodes' && selectedEpisodeId) ||
      (activeTab === 'claims' && selectedClaimId) ||
      (activeTab === 'facts' && selectedFactId) ||
      (activeTab === 'entities' && selectedEntityId) ||
      (activeTab === 'dream-runs' && selectedDreamRunId) ||
      (activeTab === 'reconsolidation' && selectedProposalId);
    if (!hasSelection) return;
    let cancelled = false;
    const load = async () => {
      setDetailLoading(true);
      try {
        if (activeTab === 'sources' && selectedSourceId) {
          setSelectedSource(null);
          const response = await api.get<ArtifactSource>(`/memory/artifacts/sources/${encodeURIComponent(selectedSourceId)}`);
          if (!cancelled) setSelectedSource(response.data);
        } else if (activeTab === 'episodes' && selectedEpisodeId) {
          setSelectedEpisode(null);
          const response = await api.get<EpisodeArtifact>(`/memory/artifacts/episodes/${encodeURIComponent(selectedEpisodeId)}`);
          if (!cancelled) setSelectedEpisode(response.data);
        } else if (activeTab === 'claims' && selectedClaimId) {
          setSelectedClaim(null);
          const response = await api.get<MemoryClaimArtifact>(`/memory/artifacts/claims/${encodeURIComponent(selectedClaimId)}`);
          if (!cancelled) setSelectedClaim(response.data);
        } else if (activeTab === 'facts' && selectedFactId) {
          setSelectedFact(null);
          const response = await api.get<ConsolidatedFactDetail>(`/memory/artifacts/consolidated-facts/${encodeURIComponent(selectedFactId)}`);
          if (!cancelled) setSelectedFact(response.data);
        } else if (activeTab === 'entities' && selectedEntityId) {
          setSelectedEntity(null);
          const response = await api.get<EntityArtifactDetail>(`/memory/artifacts/entities/${encodeURIComponent(selectedEntityId)}`);
          if (!cancelled) setSelectedEntity(response.data);
        } else if (activeTab === 'dream-runs' && selectedDreamRunId) {
          setSelectedDreamRun(null);
          const response = await api.get<DreamRunArtifact>(`/memory/artifacts/dream-runs/${encodeURIComponent(selectedDreamRunId)}`);
          if (!cancelled) setSelectedDreamRun(response.data);
        } else if (activeTab === 'reconsolidation' && selectedProposalId) {
          setSelectedProposal(null);
          const response = await api.get<ReconsolidationProposalArtifact>(`/memory/artifacts/reconsolidation-proposals/${encodeURIComponent(selectedProposalId)}`);
          if (!cancelled) setSelectedProposal(response.data);
        }
      } catch (detailError) {
        console.error('Failed to load artifact detail', detailError);
        if (!cancelled) setError('The selected artifact could not be loaded.');
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [activeTab, selectedSourceId, selectedEpisodeId, selectedClaimId, selectedFactId, selectedEntityId, selectedDreamRunId, selectedProposalId, reloadKey]);

  useEffect(() => {
    if (!selectedProposal) return;
    let cancelled = false;
    Promise.all([...selectedProposal.incoming_claim_ids, ...selectedProposal.target_claim_ids].map(async (claimId) => {
      const response = await api.get<MemoryClaimArtifact>(`/memory/artifacts/claims/${encodeURIComponent(claimId)}`);
      return [claimId, response.data] as const;
    })).then((values) => { if (!cancelled) setProposalClaims(Object.fromEntries(values)); });
    return () => { cancelled = true; };
  }, [selectedProposal]);

  useEffect(() => {
    if (activeTab !== 'files' || !selectedFile || selectedFile.content !== undefined) return;
    let cancelled = false;
    const load = async () => {
      setDetailLoading(true);
      try {
        const response = await api.get<StoredMemoryFile>(`/memory/artifacts/files/${selectedFile.group}/${encodeURIComponent(selectedFile.filename)}`);
        if (!cancelled) setSelectedFile((value) => value ? { ...value, content: response.data.content } : null);
      } catch (detailError) {
        console.error('Failed to load stored file', detailError);
        if (!cancelled) setError('The selected stored file could not be loaded.');
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [activeTab, selectedFile]);

  const query = search.trim().toLowerCase();
  const includes = (values: unknown[]) => values.some((value) => String(value ?? '').toLowerCase().includes(query));
  const filteredSources = sources.filter((item) => includes([item.source_id, item.source_type, item.session_id, ...item.participants]));
  const filteredChatEpisodes = chatEpisodes.filter((item) => includes([item.session_id, item.query]));
  const filteredEpisodes = episodes.filter((item) => includes([item.episode_id, item.source_id, item.source_type, item.extraction_status, ...item.participants]));
  const filteredClaims = claims.filter((item) => includes([item.claim_id, item.text, item.claim_type, item.dream_disposition, item.placement?.owner_entity_id]));
  const filteredFacts = facts.filter((item) => includes([item.fact_id, item.text, item.owner_entity_id, item.section_key]));
  const filteredEntities = entities.filter((item) => includes([item.entity_id, item.title, item.slug, item.entity_type, item.status, ...item.aliases]));
  const filteredOrganizationProposals = organizationProposals.filter((item) => includes([item.proposal_id, item.proposal_type, item.status, item.explanation, item.claim_id, item.source_entity_id, item.target_entity_id, item.proposed_owner_entity_id, item.proposed_new_entity_title]));
  const filteredDreamRuns = dreamRuns.filter((item) => includes([item.run_id, item.status]));
  const filteredProposals = proposals.filter((item) => includes([item.proposal_id, ...item.incoming_claim_ids, ...item.target_claim_ids, item.proposed_relation, item.status, item.explanation]));
  const allFiles = useMemo<SelectedFile[]>(() => files ? [
    ...(files.wiki_index ? [{ ...files.wiki_index, group: 'index' as const }] : []),
    ...files.archived_pages.map((file) => ({ ...file, group: 'archive' as const })),
  ] : [], [files]);
  const filteredFiles = allFiles.filter((item) => includes([item.group, item.filename]));

  const selectTab = (tab: InspectorTab) => { setSearch(''); setError(null); setActiveTab(tab); };
  const selectSource = (id: string) => { setSelectedSourceId(id); selectTab('sources'); };
  const selectClaim = (id: string) => { setSelectedClaimId(id); selectTab('claims'); };
  const selectFact = (id: string) => { setSelectedFactId(id); selectTab('facts'); };
  const selectEntity = (id: string) => { setSelectedEntityId(id); selectTab('entities'); };
  const selectReconciliation = (id: string) => { setSelectedProposalId(id); selectTab('reconsolidation'); };
  const reviewProposal = async (decision: 'approve' | 'reject') => {
    if (!selectedProposal) return;
    setReviewing(decision);
    try {
      await api.post(`/memory/reconsolidation/proposals/${encodeURIComponent(selectedProposal.proposal_id)}/${decision}`, { reviewer_note: reviewNote.trim() || null });
      setReviewNote('');
      setReloadKey((value) => value + 1);
    } catch (reviewError) {
      console.error('Failed to review reconciliation proposal', reviewError);
      setError('The reconciliation proposal review could not be applied.');
    } finally {
      setReviewing(null);
    }
  };
  const reviewOrganizationProposal = async (decision: 'approve' | 'reject') => {
    if (!selectedOrganizationProposalId) return;
    setReviewing(decision);
    try {
      await api.post(`/memory/organization/proposals/${encodeURIComponent(selectedOrganizationProposalId)}/${decision}`, { reviewer_note: reviewNote.trim() || null });
      setReviewNote('');
      setReloadKey((value) => value + 1);
    } catch (reviewError) {
      console.error('Failed to review organization proposal', reviewError);
      setError('The organization proposal review could not be applied.');
    } finally {
      setReviewing(null);
    }
  };

  return {
    activeTab, overview, filteredSources, filteredChatEpisodes, filteredEpisodes, filteredClaims,
    filteredFacts, filteredEntities, filteredOrganizationProposals, filteredDreamRuns, filteredProposals, filteredFiles,
    selectedSourceId, selectedChatId, selectedEpisodeId, selectedClaimId, selectedFactId,
    selectedEntityId, selectedOrganizationProposalId, selectedDreamRunId, selectedProposalId, selectedFile,
    selectedSource, selectedEpisode, selectedClaim, selectedFact, selectedEntity, selectedDreamRun,
    selectedProposal,
    proposalIncomingClaims: selectedProposal ? selectedProposal.incoming_claim_ids.map((id) => proposalClaims[id]).filter(Boolean) : [],
    proposalTargetClaims: selectedProposal ? selectedProposal.target_claim_ids.map((id) => proposalClaims[id]).filter(Boolean) : [],
    selectedOrganizationProposal: organizationProposals.find((item) => item.proposal_id === selectedOrganizationProposalId) ?? null,
    search, loading, detailLoading, error, reviewNote, reviewing,
    setSelectedSourceId, setSelectedChatId, setSelectedEpisodeId, setSelectedClaimId, setSelectedFactId,
    setSelectedEntityId, setSelectedOrganizationProposalId, setSelectedDreamRunId, setSelectedProposalId, setSelectedFile, setSearch,
    setReloadKey, setReviewNote, selectSource, selectClaim, selectFact, selectEntity, selectReconciliation, selectTab, reviewProposal, reviewOrganizationProposal,
    selectedChatEpisode: chatEpisodes.find((item) => item.session_id === selectedChatId) ?? null,
  };
}
