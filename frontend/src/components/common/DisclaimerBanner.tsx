import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { DISCLAIMER_TEXT } from '../../types/uiTerms';

export const DisclaimerBanner: React.FC = () => {
  return (
    <div
      role="region"
      aria-label="National Water Supply and Drainage Board Regulatory Disclaimer"
      className="bg-amber-50/95 border-b border-amber-200/90 px-4 py-2 text-xs text-slate-800 sticky top-0 z-50 backdrop-blur-xs shadow-2xs transition-colors"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between sm:justify-center gap-2.5 text-center">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-200/80 text-amber-900 shrink-0">
            <ShieldAlert className="w-3 h-3 text-amber-700 inline" />
            Decision Support Notice
          </span>
          <p className="font-medium text-slate-700 leading-snug text-[11px] sm:text-xs">
            {DISCLAIMER_TEXT}
          </p>
        </div>
      </div>
    </div>
  );
};

export default DisclaimerBanner;
