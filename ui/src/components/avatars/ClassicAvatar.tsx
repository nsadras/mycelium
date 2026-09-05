import { Book, FileText, Loader2, Mic, Hammer, Sparkles } from 'lucide-react';
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
  if (activity === 'building') {
    return <Hammer size={28} className="text-white animate-pulse" />;
  }
  if (activity === 'thinking' || activity === 'tool_calling' || activity === 'responding') {
    return <Loader2 size={28} className="text-white animate-spin" />;
  }
  return <Sparkles size={28} className="text-white" />;
}
