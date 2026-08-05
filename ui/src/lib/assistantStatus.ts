export type AssistantActivity =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'tool_calling'
  | 'responding'
  | 'flushing'
  | 'dreaming'
  | 'error'
  | 'clicked'
  | 'clicked-left'
  | 'clicked-right'
  | 'wiki'
  | 'memory'
  | 'logs'
  | 'engram'
  | 'chat';

export interface AssistantStatus {
  activity: AssistantActivity;
  label?: string;
  detail?: string;
}

export const idleStatus: AssistantStatus = {
  activity: 'idle',
  label: 'Idle',
};
