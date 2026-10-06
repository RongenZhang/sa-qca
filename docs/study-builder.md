# The guided study flow

The tool walks a researcher from their own question to an interpretation of the results, in eight steps. Each step saves automatically (the bundled demo study is read-only).

| Step | What you do | Help available |
|---|---|---|
| 1 Question | Describe the phenomenon and context, and the outcome of interest (name, meaning, how it is measured, how it will be calibrated) | guidance and an example |
| 2 Stakeholders | List groups who would defensibly read your measures differently; approve the set | **Suggest stakeholders** (AI or scripted), or write your own |
| 3 Conditions | List the conditions (factors that may bring about the outcome), each with a definition, how it is measured, and how it will be calibrated | **Suggest conditions** (AI), or write your own; download a blank data template |
| 4 Data | Attach your file and map its columns to your plan; add original anchors, breakpoints and cutoffs if you have them | columns whose names match your plan are pre-ticked and pre-filled |
| 5 Calibration | Choose the sources to compare (each approved stakeholder, a generic reading, a mechanical perturbation) | exact prompt preview and a cost and call estimate |
| 6 Analysis | The same R code analyses every proposal; invalid answers are counted | live validation report |
| 7 Results | Compare solutions across sources, with robustness, similarity, anchors, rationales and exports | |
| 8 Interpretation | Read what the solutions mean from each stakeholder's perspective; edit and save your own version | computed facts; rule-based summary; optional model draft |

## AI settings
Open **AI settings** in the top bar. *Scripted* needs no model: for the bundled demo it returns the demo's own suggestions; for any other topic it returns generic prompts to think with (clearly labelled) and cannot suggest conditions. *Anthropic* needs your API key (and workspace ID if your key is not scoped to one), kept only in the browser tab's memory.

## What a model sees
- The planning helpers send **only the text you wrote** in the steps (phenomenon, outcome, stakeholders, conditions): never your data. Before any call, **What will be sent** shows the exact prompt.
- The calibration runs send each variable's definition, instrument and summary statistics, never rows.
- Everything a model returns is shown as a proposal you review, edit and explicitly add, labelled *AI-generated · editable*.
- Each helper answer must match a schema; an answer that does not gets one further attempt with the errors appended, then is rejected. Strict JSON only; nothing a model returns is edited.
- Every helper call (scripted or model) is logged with its prompt and raw answer, exported in the replication bundle (`assist/helper_calls.jsonl`) with the plan (`study/study.json`), and, when a model gave suggestions, named in the report's AI-use statement.

## Public demo
The public demo shows the demo study read-only, uses scripted helpers only, and creates no studies.

## The interpretation (step 8)
Two layers, kept apart on purpose.

**Facts, computed from the stored runs, never by a model.** For the chosen solution type: which paths of the solution hold under every stakeholder reading (a path counts as present in a reading when it appears in at least half of that reading's valid runs), which depend on the reading, which appear under only one stakeholder, which exist only in your own solution, and which alternative routes appear under some readings. For each stakeholder: its typical solution, how stable that reading is across repetitions, its invalid-answer rate, and whether it set a stricter or more lenient bar than you on each variable (a mean shift of its anchors or breakpoints relative to yours, as a share of the scale; under 2% is called similar). For a path that some readings lose, the tool also compares the calibration of those that lose it with those that keep it. That comparison is descriptive: with a handful of readings it cannot show cause.

**A narrative.** By default the facts are put into words by fixed rules (so it is always available, including on the public demo). Optionally a model drafts the narrative from your study text and these facts only. Its answer must match a schema and is checked against the facts: every path must exist and be classified as it says (robust findings only robust paths), and every stakeholder must be one that was run. A draft that invents a path or stakeholder is rejected, with one retry, like any other model answer. You can edit every sentence, add notes, and save: the saved version (with a label saying whether it was rule-based, model-drafted or edited by you) goes into the report and the replication bundle (`interpretation/interpretation.json`, with the facts).

What the interpretation cannot do: it cannot say which stakeholder is right, and when the calibrations come from a language model it is one structured reading of each perspective, not evidence about what real stakeholders think. The text says so.
