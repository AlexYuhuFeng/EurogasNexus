import { contractChain, type ContractChainFacts, type ContractChainStepId } from "@/app/model/contractChainModel";

/**
 * Where the selected contract stands in its work chain and the next step (#32): terms, route
 * economics, pool allocation, review. A blocked step names the rule that blocks it.
 */
export function ContractChainStrip({
  facts,
  t,
  onOpen,
}: {
  facts: ContractChainFacts;
  t: (key: string) => string;
  onOpen: (step: ContractChainStepId) => void;
}) {
  const steps = contractChain(facts);
  return (
    <nav className="contract-chain" aria-label={t("chain.title")}>
      <ol>
        {steps.map((step, index) => (
          <li key={step.id} className={`contract-chain-step chain-${step.state}`} data-chain-step={step.id}>
            <button
              type="button"
              disabled={step.state === "blocked" || step.id === "terms"}
              aria-current={step.state === "next" && steps.findIndex((item) => item.state === "next") === index ? "step" : undefined}
              onClick={() => onOpen(step.id)}
            >
              <span className="contract-chain-index" aria-hidden="true">
                {step.state === "done" ? "✓" : index + 1}
              </span>
              <span className="contract-chain-label">{t(`chain.step.${step.id}`)}</span>
            </button>
            <span className="contract-chain-reason">{t(step.reasonKey)}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
