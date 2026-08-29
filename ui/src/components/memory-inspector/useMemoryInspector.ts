import { useEffect, useMemo, useState } from 'react';

import api, {
  type ArtifactOverview,
  type ArtifactSource,
  type ArtifactSourceSummary,
  type ChatEpisodeState,
  type DreamRunArtifact,
  type EpisodeArtifact,
  type MemoryClaimArtifact,
  type ReconsolidationProposalArtifact,
  type StoredMemoryFiles,
} from '../../lib/api';
import type { InspectorTab, SelectedFile } from './types';

export function useMemoryInspector(refreshKey: number) {
  const [activeTab, setActiveTab] = useState<InspectorTab>('overview');
  const [overview, setOverview] = useState<ArtifactOverview | null>(null);
  const [chatEpisodes, setChatEpisodes] = useState<ChatEpisodeState[]>([]);
  const [sources, setSources] = useState<ArtifactSourceSummary[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeArtifact[]>([]);
  const [claims, setClaims] = useState<MemoryClaimArtifact[]>([]);
  const [proposals, setProposals] = useState<ReconsolidationProposalArtifact[]>([]);
  const [dreamRuns, setDreamRuns] = useState<DreamRunArtifact[]>([]);
  const [files, setFiles] = useState<StoredMemoryFiles | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<ArtifactSource | null>(null);
  const [failedSourceId, setFailedSourceId] = useState<string | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [selectedDreamRunId, setSelectedDreamRunId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [reviewNote, setReviewNote] = useState('');
  const [reviewing, setReviewing] = useState<'approve' | 'reject' | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [overviewResponse, chatResponse, sourceResponse, episodeResponse, claimResponse, proposalResponse, dreamRunResponse, fileResponse] = await Promise.all([
          api.get<ArtifactOverview>('/memory/artifacts/overview'),
          api.get<ChatEpisodeState[]>('/memory/artifacts/chat-episodes'),
          api.get<ArtifactSourceSummary[]>('/memory/artifacts/sources'),
          api.get<EpisodeArtifact[]>('/memory/artifacts/episodes'),
          api.get<MemoryClaimArtifact[]>('/memory/artifacts/claims'),
          api.get<ReconsolidationProposalArtifact[]>('/memory/artifacts/reconsolidation-proposals'),
          api.get<DreamRunArtifact[]>('/memory/artifacts/dream-runs'),
          api.get<StoredMemoryFiles>('/memory/artifacts/files'),
        ]);
        const orderedSources = [...sourceResponse.data].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
        setOverview(overviewResponse.data);
        setChatEpisodes(chatResponse.data);
        setSources(orderedSources);
        setEpisodes(episodeResponse.data);
        setClaims(claimResponse.data);
        const orderedProposals = [...proposalResponse.data].sort((a, b) => {
          if (a.status === 'pending' && b.status !== 'pending') return -1;
          if (b.status === 'pending' && a.status !== 'pending') return 1;
          return b.created_at.localeCompare(a.created_at);
        });
        setProposals(orderedProposals);
        setDreamRuns(dreamRunResponse.data);
        setFiles(fileResponse.data);
        setSelectedSourceId(orderedSources[0]?.source_id ?? null);
        setSelectedChatId(chatResponse.data[0]?.session_id ?? null);
        setSelectedEpisodeId(episodeResponse.data[0]?.episode_id ?? null);
        setSelectedClaimId(claimResponse.data[0]?.claim_id ?? null);
        setSelectedDreamRunId(dreamRunResponse.data[0]?.run_id ?? null);
        setSelectedProposalId(orderedProposals[0]?.proposal_id ?? null);
        const initialFile = fileResponse.data.wiki_index;
        setSelectedFile(initialFile ? { ...initialFile, group: 'index' } : null);
      } catch (loadError) {
        console.error('Failed to load memory artifacts', loadError);
        setError('The memory artifacts could not be loaded. Check the backend logs.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [refreshKey, reloadKey]);

  useEffect(() => {
    if (!selectedSourceId) {
      return;
    }
    let cancelled = false;
    api.get<ArtifactSource>(`/memory/artifacts/sources/${encodeURIComponent(selectedSourceId)}`)
      .then((response) => {
        if (!cancelled) {
          setSelectedSource(response.data);
          setFailedSourceId(null);
        }
      })
      .catch((sourceError) => {
        console.error('Failed to load source artifact', sourceError);
        if (!cancelled) setFailedSourceId(selectedSourceId);
      })
    return () => { cancelled = true; };
  }, [selectedSourceId]);

  const query = search.trim().toLowerCase();
  const filteredSources = sources.filter((source) =>
    [source.source_id, source.source_type, source.session_id, ...source.participants]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredChatEpisodes = chatEpisodes.filter((session) =>
    [session.session_id, session.query, JSON.stringify(session.active_episode), JSON.stringify(session.encoded_episodes)]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredEpisodes = episodes.filter((episode) =>
    [episode.episode_id, episode.source_id, episode.source_type, episode.extraction_status, ...episode.participants]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredClaims = claims.filter((claim) =>
    [claim.claim_id, claim.text, claim.claim_type, claim.dream_disposition, claim.predicate ?? '', claim.placement?.owner_entity_id ?? '']
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredDreamRuns = dreamRuns.filter((run) =>
    [run.run_id, run.status, ...run.source_ids, ...run.claim_decisions.flatMap((decision) => [decision.claim_id, decision.disposition, decision.reason])]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredProposals = proposals.filter((proposal) =>
    [proposal.proposal_id, proposal.incoming_claim_id, proposal.target_claim_id, proposal.proposed_relation, proposal.status, proposal.explanation]
      .some((value) => value.toLowerCase().includes(query))
  );
  const allFiles = useMemo<SelectedFile[]>(() => {
    if (!files) return [];
    return [
      ...(files.wiki_index ? [{ ...files.wiki_index, group: 'index' as const }] : []),
      ...files.archived_pages.map((file) => ({ ...file, group: 'archive' as const })),
    ];
  }, [files]);
  const filteredFiles = allFiles.filter((file) =>
    `${file.group} ${file.filename} ${file.content}`.toLowerCase().includes(query)
  );

  const selectedEpisode = episodes.find((episode) => episode.episode_id === selectedEpisodeId) ?? null;
  const selectedChatEpisode = chatEpisodes.find((session) => session.session_id === selectedChatId) ?? null;
  const selectedClaim = claims.find((claim) => claim.claim_id === selectedClaimId) ?? null;
  const selectedDreamRun = dreamRuns.find((run) => run.run_id === selectedDreamRunId) ?? null;
  const selectedProposal = proposals.find((proposal) => proposal.proposal_id === selectedProposalId) ?? null;
  const proposalIncomingClaim = claims.find((claim) => claim.claim_id === selectedProposal?.incoming_claim_id) ?? null;
  const proposalTargetClaim = claims.find((claim) => claim.claim_id === selectedProposal?.target_claim_id) ?? null;
  const claimedSegmentIds = useMemo(() => new Set(
    claims.flatMap((claim) => claim.provenance.flatMap((item) => item.segment_ids))
  ), [claims]);
  const ignoredSegmentIds = useMemo(() => new Set(
    episodes.flatMap((episode) => episode.ignored_segment_ids)
  ), [episodes]);

  const selectSource = (sourceId: string) => {
    setSelectedSourceId(sourceId);
    setSearch('');
    setActiveTab('sources');
  };
  const selectClaim = (claimId: string) => {
    setSelectedClaimId(claimId);
    setSearch('');
    setActiveTab('claims');
  };
  const selectTab = (tab: InspectorTab) => {
    setSearch('');
    setActiveTab(tab);
  };
  const reviewProposal = async (decision: 'approve' | 'reject') => {
    if (!selectedProposal) return;
    setReviewing(decision);
    try {
      await api.post(
        `/memory/reconsolidation/proposals/${encodeURIComponent(selectedProposal.proposal_id)}/${decision}`,
        { reviewer_note: reviewNote.trim() || null },
      );
      setReviewNote('');
      setReloadKey((current) => current + 1);
    } catch (reviewError) {
      console.error(`Failed to ${decision} reconsolidation proposal`, reviewError);
      alert(`The proposal could not be ${decision === 'approve' ? 'approved' : 'rejected'}. It may already have been reviewed or become stale.`);
    } finally {
      setReviewing(null);
    }
  };

  return {
    activeTab,
    overview,
    filteredSources,
    filteredChatEpisodes,
    filteredEpisodes,
    filteredClaims,
    filteredDreamRuns,
    filteredProposals,
    filteredFiles,
    selectedSourceId,
    selectedChatId,
    selectedSource,
    failedSourceId,
    selectedEpisodeId,
    selectedClaimId,
    selectedDreamRunId,
    selectedProposalId,
    selectedFile,
    selectedEpisode,
    selectedChatEpisode,
    selectedClaim,
    selectedDreamRun,
    selectedProposal,
    proposalIncomingClaim,
    proposalTargetClaim,
    claimedSegmentIds,
    ignoredSegmentIds,
    search,
    loading,
    error,
    reviewNote,
    reviewing,
    setSelectedSourceId,
    setSelectedChatId,
    setSelectedEpisodeId,
    setSelectedClaimId,
    setSelectedDreamRunId,
    setSelectedProposalId,
    setSelectedFile,
    setSearch,
    setReloadKey,
    setReviewNote,
    selectSource,
    selectClaim,
    selectTab,
    reviewProposal,
  };
}
