import React from 'react';
import { cn } from './utils';

interface BadgeProps {
  variant?: 'normal' | 'warning' | 'danger' | 'info';
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'normal', children, className }) => {
  const styles = {
    normal: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    danger: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    info: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border',
        styles[variant],
        className
      )}
    >
      {children}
    </span>
  );
};

export * from './utils';
