import { Book, BrainCircuit, FileText, Loader2, Mic, Moon, Sparkles, Waves } from 'lucide-react';
import type { AvatarProps } from './index';

export default function ClassicAvatar({ activity }: AvatarProps) {
  if (activity === 'wiki') {
    return <Book size={28} className="text-emerald-400 opacity-90 animate-pulse" />;
  }
  if (activity === 'logs') {
    return <FileText size={28} className="text-emerald-400 opacity-90 animate-pulse" />;
  }
  if (activity === 'engram') {
    return <Mic size={28} className="text-emerald-400 opacity-90 animate-pulse" />;
  }
  if (activity === 'dreaming') {
    return <Moon size={28} className="text-white animate-pulse" />;
  }
  if (activity === 'flushing') {
    return <Waves size={28} className="text-white animate-pulse" />;
  }
  if (activity === 'reconsolidating') {
    return <BrainCircuit size={28} className="text-white animate-pulse" />;
  }
  if (activity === 'thinking' || activity === 'tool_calling' || activity === 'responding') {
    return <Loader2 size={28} className="text-white animate-spin" />;
  }
  return <Sparkles size={28} className="text-white" />;
}
