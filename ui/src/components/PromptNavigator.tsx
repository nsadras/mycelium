import { useState } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface PromptNavigatorProps {
  userPrompts: Array<{ content: string; originalIndex: number }>;
  activePromptIndex: number | null;
  onJumpToPrompt: (originalIndex: number) => void;
}

export default function PromptNavigator({
  userPrompts,
  activePromptIndex,
  onJumpToPrompt,
}: PromptNavigatorProps) {
  const [isHovered, setIsHovered] = useState(false);

  const getPromptSnippet = (content: string) => {
    const maxLength = 35;
    const cleaned = content.replace(/[\n\r]+/g, ' ').trim();
    if (cleaned.length <= maxLength) return cleaned;
    return cleaned.slice(0, maxLength).trim() + '...';
  };

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        "absolute right-4 top-1/2 -translate-y-1/2 z-30 flex flex-col items-end transition-all duration-300 ease-in-out py-3 px-2 rounded-xl border border-transparent select-none",
        isHovered
          ? "w-72 bg-slate-900/90 backdrop-blur-md border-[rgba(16,185,129,0.2)] shadow-2xl"
          : "w-10 bg-transparent"
      )}
      style={{
        boxShadow: isHovered ? "0 8px 32px 0 rgba(0, 0, 0, 0.45), 0 0 15px rgba(16, 185, 129, 0.1)" : "none"
      }}
    >
      {/* Title block when hovered */}
      <div
        className={cn(
          "w-full text-left mb-3 px-2 transition-opacity duration-200 overflow-hidden whitespace-nowrap",
          isHovered ? "opacity-100 h-auto" : "opacity-0 h-0 pointer-events-none"
        )}
      >
        <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">
          Thread Navigation
        </span>
      </div>

      {/* Stack of Bars Container */}
      <div
        className="w-full flex flex-col space-y-1 overflow-y-auto overflow-x-hidden pr-1"
        style={{
          maxHeight: '320px', // Capped at exactly 10 items (each item is h-8 = 32px)
        }}
      >
        {userPrompts.map((prompt) => {
          const isActive = activePromptIndex === prompt.originalIndex;
          const snippet = getPromptSnippet(prompt.content);
          
          return (
            <button
              key={prompt.originalIndex}
              onClick={() => onJumpToPrompt(prompt.originalIndex)}
              className={cn(
                "h-8 w-full flex items-center justify-end gap-3 rounded-md transition-all duration-200 hover:bg-emerald-500/10 group px-2 text-left cursor-pointer border-none outline-none",
                isActive && "bg-emerald-500/5"
              )}
            >
              {/* Prompt snippet visible when hovered */}
              <span
                className={cn(
                  "text-xs font-medium text-right flex-1 transition-all duration-200 truncate select-none",
                  isActive
                    ? "text-emerald-400 font-bold"
                    : "text-slate-400 group-hover:text-white",
                  isHovered ? "opacity-100 max-w-[200px]" : "opacity-0 max-w-0 pointer-events-none"
                )}
              >
                {snippet}
              </span>

              {/* The horizontal bar itself */}
              <div
                className={cn(
                  "h-1 rounded transition-all duration-200 shrink-0",
                  isActive
                    ? "w-6 bg-emerald-400 shadow-[0_0_8px_#34d399]"
                    : "w-4 bg-slate-600 group-hover:bg-emerald-500/60 group-hover:w-5"
                )}
                title={!isHovered ? snippet : undefined}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
