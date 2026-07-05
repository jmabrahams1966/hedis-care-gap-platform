export default function StepIndicator({ step, total }: { step: number; total: number }) {
  return (
    <div className="step-indicator" role="progressbar" aria-valuenow={step} aria-valuemin={1} aria-valuemax={total}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`step-indicator__dot${i < step ? " done" : i === step ? " active" : ""}`} />
      ))}
    </div>
  );
}
