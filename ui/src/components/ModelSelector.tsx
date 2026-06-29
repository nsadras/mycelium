import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Cpu, Loader2, RefreshCw, Save } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import api, { type LlmModelOption, type LlmPreset, type LlmSettings } from '../lib/api';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const providerOptions = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'vllm', label: 'vLLM' },
  { value: 'sglang', label: 'SGLang' },
  { value: 'llama-cpp', label: 'llama.cpp' },
  { value: 'openai-compatible', label: 'OpenAI API' },
];

export default function ModelSelector() {
  const [expanded, setExpanded] = useState(false);
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [draft, setDraft] = useState<LlmSettings | null>(null);
  const [presets, setPresets] = useState<LlmPreset[]>([]);
  const [models, setModels] = useState<LlmModelOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    void fetchSettings();
  }, []);

  const selectedPresetId = useMemo(() => {
    if (!draft) return 'custom';
    const match = presets.find((preset) =>
      preset.provider === draft.provider &&
      preset.url === draft.url &&
      preset.model === draft.model
    );
    return match?.id ?? 'custom';
  }, [draft, presets]);

  const isDirty = Boolean(draft && settings && (
    draft.provider !== settings.provider ||
    draft.model !== settings.model ||
    draft.url !== settings.url ||
    draft.temperature !== settings.temperature
  ));

  const fetchSettings = async () => {
    setIsLoading(true);
    setStatus(null);
    try {
      const res = await api.get('/settings/llm');
      setSettings(res.data.settings);
      setDraft(res.data.settings);
      setPresets(res.data.presets);
      setModels(res.data.models ?? []);
    } catch (err) {
      console.error('Failed to load model settings', err);
      setStatus('Unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchModels = async (provider: string, url: string) => {
    try {
      const res = await api.get('/settings/llm/models', { params: { provider, url } });
      setModels(res.data.models ?? []);
      if (res.data.error) {
        setStatus('No model list');
      } else {
        setStatus(null);
      }
    } catch (err) {
      console.error('Failed to load model list', err);
      setModels([]);
      setStatus('No model list');
    }
  };

  const updateDraft = (patch: Partial<LlmSettings>) => {
    setDraft(prev => prev ? { ...prev, ...patch } : prev);
  };

  const applyPreset = (id: string) => {
    const preset = presets.find(item => item.id === id);
    if (!preset || !draft) return;
    const next = {
      ...draft,
      provider: preset.provider,
      url: preset.url,
      model: preset.model,
    };
    setDraft(next);
    void fetchModels(next.provider, next.url);
  };

  const save = async () => {
    if (!draft || isSaving) return;
    setIsSaving(true);
    setStatus(null);
    try {
      const res = await api.put('/settings/llm', draft);
      setSettings(res.data.settings);
      setDraft(res.data.settings);
      setPresets(res.data.presets);
      setModels(res.data.models ?? []);
      setStatus('Saved');
      window.setTimeout(() => setStatus(null), 1800);
    } catch (err) {
      console.error('Failed to save model settings', err);
      setStatus('Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mb-3 rounded-md border border-emerald-500/15 bg-slate-950/30 p-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/70"
        title="Model settings"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Cpu size={15} className="text-emerald-400" />
        <span className="min-w-0 flex-1 truncate">{settings?.model ?? 'Model'}</span>
        {isLoading && <Loader2 size={13} className="animate-spin text-slate-400" />}
      </button>

      {expanded && draft && (
        <div className="mt-2 space-y-2">
          <select
            value={selectedPresetId}
            onChange={(e) => {
              if (e.target.value !== 'custom') applyPreset(e.target.value);
            }}
            className="h-8 w-full px-2 text-xs"
            title="Preset"
          >
            <option value="custom">Custom</option>
            {presets.map((preset) => (
              <option key={preset.id} value={preset.id}>{preset.label}</option>
            ))}
          </select>

          <div className="grid grid-cols-[82px_1fr] gap-2">
            <label className="self-center text-[10px] font-bold uppercase text-slate-500">Provider</label>
            <select
              value={draft.provider}
              onChange={(e) => {
                updateDraft({ provider: e.target.value });
                void fetchModels(e.target.value, draft.url);
              }}
              className="h-8 min-w-0 px-2 text-xs"
              title="Provider"
            >
              {providerOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>

            <label className="self-center text-[10px] font-bold uppercase text-slate-500">URL</label>
            <input
              value={draft.url}
              onChange={(e) => updateDraft({ url: e.target.value })}
              onBlur={() => fetchModels(draft.provider, draft.url)}
              className="h-8 min-w-0 px-2 text-xs"
              title="Runtime URL"
            />

            <label className="self-center text-[10px] font-bold uppercase text-slate-500">Model</label>
            {models.length > 0 ? (
              <select
                value={models.some(model => model.id === draft.model) ? draft.model : '__custom__'}
                onChange={(e) => {
                  if (e.target.value !== '__custom__') updateDraft({ model: e.target.value });
                }}
                className="h-8 min-w-0 px-2 text-xs"
                title="Installed model"
              >
                {!models.some(model => model.id === draft.model) && (
                  <option value="__custom__">{draft.model || 'Custom model'}</option>
                )}
                {models.map((model) => (
                  <option key={model.id} value={model.id}>{model.label}</option>
                ))}
              </select>
            ) : (
              <input
                value={draft.model}
                onChange={(e) => updateDraft({ model: e.target.value })}
                className="h-8 min-w-0 px-2 text-xs"
                title="Model"
              />
            )}

            <label className="self-center text-[10px] font-bold uppercase text-slate-500">Temp</label>
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={draft.temperature}
              onChange={(e) => updateDraft({ temperature: Number(e.target.value) })}
              className="h-8 min-w-0 px-2 text-xs"
              title="Temperature"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fetchModels(draft.provider, draft.url)}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-300 hover:bg-slate-800 hover:text-white"
              title="Refresh models"
            >
              <RefreshCw size={14} />
            </button>
            <button
              type="button"
              onClick={save}
              disabled={!isDirty || isSaving}
              className={cn(
                "flex h-8 flex-1 items-center justify-center gap-2 rounded-md text-xs font-semibold transition-colors",
                !isDirty || isSaving
                  ? "cursor-not-allowed bg-slate-800/40 text-slate-500"
                  : "bg-emerald-600 text-white hover:bg-emerald-700"
              )}
              title="Save model"
            >
              {isSaving ? <Loader2 size={14} className="animate-spin" /> : status === 'Saved' ? <Check size={14} /> : <Save size={14} />}
              {status === 'Saved' ? 'Saved' : 'Save'}
            </button>
          </div>

          {status && status !== 'Saved' && (
            <div className="truncate rounded bg-slate-950/60 px-2 py-1 text-[10px] font-semibold text-amber-300" title={status}>
              {status}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
