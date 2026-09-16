import { useEffect, useMemo, useRef } from 'react';

export interface SelectionRequest {
  id: string;
  selection: number;
  version: number;
}

export function useSelectionRequests() {
  const state = useRef({ mounted: true, selectedId: null as string | null, selection: 0,
    listVersion: 0, versions: new Map<string, number>() });
  const scope = useMemo(() => {
    return {
      mount() { state.current.mounted = true; },
      dispose() { state.current.mounted = false; state.current.selection += 1; state.current.listVersion += 1; },
      select(id: string | null) { state.current.selectedId = id; state.current.selection += 1; },
      selection() { return state.current.selection; },
      selectedId() { return state.current.selectedId; },
      sameSelection(value: number) { return state.current.mounted && state.current.selection === value; },
      begin(id: string): SelectionRequest {
        const version = (state.current.versions.get(id) ?? 0) + 1;
        state.current.versions.set(id, version);
        return { id, selection: state.current.selection, version };
      },
      latest(ticket: SelectionRequest) { return state.current.mounted && state.current.versions.get(ticket.id) === ticket.version; },
      current(ticket: SelectionRequest) {
        return state.current.mounted && state.current.selectedId === ticket.id && state.current.selection === ticket.selection && state.current.versions.get(ticket.id) === ticket.version;
      },
      beginList() { return ++state.current.listVersion; },
      currentList(version: number) { return state.current.mounted && version === state.current.listVersion; },
      invalidateList() { state.current.listVersion += 1; },
      mounted() { return state.current.mounted; },
    };
  }, []);
  useEffect(() => { scope.mount(); return () => scope.dispose(); }, [scope]);
  return scope;
}
