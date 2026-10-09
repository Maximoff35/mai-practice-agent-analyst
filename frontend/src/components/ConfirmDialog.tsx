"use client";

type ConfirmDialogProps = {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onCancel}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md rounded-xl border border-accent/40 bg-panel p-6 shadow-xl"
      >
        <h2 className="text-base font-semibold text-foreground/90">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-foreground/60">
          {message}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-foreground/25 px-4 py-2 text-sm text-foreground/70 transition-colors duration-300 hover:border-foreground/50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg border border-accent/60 bg-accent/15 px-4 py-2 text-sm text-accent transition-colors duration-300 hover:bg-accent/25"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}