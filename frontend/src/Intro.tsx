export function Intro({ onClose }: { onClose: () => void }) {
  return (
    <section className="card" aria-labelledby="intro-h">
      <h2 id="intro-h">What this tool does</h2>
      <p>In fsQCA, the analyst sets the calibration anchors, and results can depend on those choices. Usual robustness checks nudge the analyst's own numbers. SA-QCA enables us to ask a different question: across the range of calibration decisions based on stakeholders' different interpretations of conditions and outcomes, which findings survive?</p>
      <h3>How it works</h3>
      <ol>
        <li>You describe the phenomenon and define each condition and outcome, then approve a set of stakeholder roles drawn from your own cases.</li>
        <li>Each role (and a role-free "generic" LLM calibration) proposes anchors and truth-table cutoffs, with a written rationale.</li>
        <li>The same QCA (R) code analyses every proposal, to make sure of separation of judgement and calculation.</li>
        <li>Structurally invalid answers are rejected, and the invalid rate is counted as a finding.</li>
        <li>You compare solutions across roles, the generic LLM calibration, a mechanical perturbation of your own anchors (Skaaning-style), and your original solution.</li>
      </ol>
      <h3>What it does not do</h3>
      <p>It does not say which anchors are right. A model's answer is one reading of a measure, not evidence about what real stakeholders think. This is a candidate protocol for discussion, not a finished standard.</p>
      <h3>Privacy of Information</h3>
      <p>Only variable definitions and summary statistics go to the model provider, never your rows. The API key stays in browser memory.</p>
      <p className="muted">New here? Try the demo project first: it needs no API key.</p>
      <details>
        <summary>Glossary</summary>
        <dl>
          <dt><b>Calibration</b></dt><dd>Turning raw values into set-membership scores between 0 and 1.</dd>
          <dt><b>Anchors</b></dt><dd>Three raw values that fix the calibration: full non-membership (membership about 0.05), crossover (0.5, maximum ambiguity) and full membership (about 0.95).</dd>
          <dt><b>Truth table</b></dt><dd>Every combination of conditions, with the cases that fit it and how consistently they show the outcome.</dd>
          <dt><b>Consistency cutoff</b></dt><dd>The minimum consistency for a combination to count as sufficient for the outcome.</dd>
          <dt><b>Frequency cutoff</b></dt><dd>The minimum number of cases for a combination to be considered.</dd>
          <dt><b>PRI</b></dt><dd>Proportional reduction in inconsistency: guards against combinations that look sufficient for both the outcome and its absence.</dd>
          <dt><b>Complex, parsimonious, intermediate solution</b></dt><dd>The minimized result using no, all, or only plausible logical remainders (combinations with no cases). The intermediate solution needs your directional expectations.</dd>
          <dt><b>Invalid judgment</b></dt><dd>An answer that failed structural validation twice (for example anchors out of order or outside the observed range). It is recorded, never repaired, and never sent to R.</dd>
          <dt><b>Anchor source</b></dt><dd>Where a set of anchors comes from: a stakeholder role, the generic reading, the mechanical perturbation, or your original specification.</dd>
        </dl>
      </details>
      <div className="actions"><span /><button onClick={onClose}>Got it</button></div>
    </section>
  )
}
