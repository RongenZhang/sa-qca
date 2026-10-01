# SA-QCA live demo script (about 10 minutes)

Use **localhost** for the talk (fast, full features) and keep the live site as a backup and a link to share.

## Before you go on stage

1. Start everything with one command, from any folder:
   ```bash
   "/Users/rongenzhang/Dropbox/Research/Current Projects/QCA_LLM/sa-qca/scripts/start-local.sh"
   ```
   It checks prerequisites and ports, starts the backend and frontend, and prints the address (http://localhost:5173). Ctrl+C stops both. Use `--check` to test without starting.
2. Do one **rehearsal run** with the exact settings below and leave its results page open in a second tab. If anything stalls on stage, switch to that tab.
3. Download that run's replication bundle and open its report, so both are ready as files.
4. Open https://sa-qca-demo.onrender.com once, a few minutes early, so it is awake if you need it.
5. Use **Scripted test responses**. Only use a real Anthropic key on stage if you have already had a successful real run.

**Settings for the demo run:** roles = the three suggested ones; repetitions = 3; Generic ticked; Mechanical ticked; provider = "Scripted test responses". A full run takes about 25 seconds.

## What to say about the results (read this once)
The demo's answers are **scripted stand-ins** that show how the tool works. They are not findings, and a real model would answer differently. The report says so on purpose.

## The flow

**1. Open with the question (1 min).** Click **About this tool**.
> "In fsQCA the analyst sets the calibration anchors, and results can depend on them. Usual robustness checks nudge the analyst's own numbers. This tool asks a different question: across the range of calibration decisions that stakeholders with different interpretations would defensibly make, which findings survive?"

**2. Step 1, data (1 min).** Show a condition's definition, instrument and histogram with the dashed original anchors.
> "Agents read the phenomenon description, each definition and instrument, and summary statistics. They never see rows."

**3. Step 2, roles (1.5 min).** Click **Suggest roles (AI)**, type your name, click **Approve roles**.
> "Roles come from the cases, not from us, and nothing runs until the researcher approves them. (The suggestions here are scripted examples.)"

**4. Step 3, run design (1.5 min).** Tick the three roles, Generic and Mechanical. Open the prompt preview for a role. Click **Estimate cost and calls**, tick the confirmation box, click **Start run**.
> "This is the exact text an agent receives. Conditions and outcome are sets; the prompt asks for anchors with substantive rationales, not a percentile rule. The researcher confirms exactly what is sent and what it costs."

**5. Step 4, run (1 min).** Watch the progress and the validation table.
> "Some first answers fail structural checks, such as anchors out of order. The agent gets one retry with the error appended; a second failure is recorded as invalid, never repaired, and the invalid rate is itself a finding."
Expected: Generic and the IT consultant each show about 33% first-attempt failures, all recovered on retry, so 0% invalid.

**6. Step 5, results (3 min).** Click **View results**, then:
- **Similarity** (the chart): "1 means the run found the analyst's solution, 0 means nothing in common. Two of the three roles and the generic reading agree exactly; the independent IT consultant does not."
- **Robustness:** with the scripted data, `SUPPORT*TRUST` survives under every reading, while `RESOURCES*~TRUST` survives under three readings but not the consultant's. Mechanical perturbation matches the analyst in 27 of 29 runs.
  > "That is the contrast: a mechanical nudge says the finding is stable, while one defensible reading of the measure changes it."
- **Anchors:** "Here is where the readings differ on the real distribution."
- **Rationales:** open one, then click **Prompt & raw response**. "Every number traces to the exact prompt and raw answer."

**7. Export and verify (1 min).** Click **Verify bundle**; open **Open report (HTML)**.
> "The bundle has the data, every prompt, every raw response and the R code. Verify re-runs the QCA computation from scratch with no LLM and checks every result matches."
Point to the AI-use statement. Note the warning that it is a scripted run.

**Close (30 s).**
> "It is a candidate protocol for discussion. It does not say which anchors are right. The model's answer is one reading, not evidence about real stakeholders."

## If something goes wrong
- **Anything stalls:** switch to the rehearsal tab.
- **Page blank or backend error:** run the launcher again; it tells you what is missing.
- **Laptop fails:** use https://sa-qca-demo.onrender.com (demo project only; untick Mechanical and use 1 repetition for a quick run; the first visit after idle takes about a minute).

## Likely questions
- **Is this a real LLM?** Today's demo is scripted. The tool supports Anthropic with a key; real answers will differ and may be invalid more often.
- **Why not let the LLM run the QCA?** Judgment and computation are kept separate on purpose: the model only proposes anchors and cutoffs, and identical R code does all calculation.
- **Isn't the model just guessing?** It is one structured reading of a measure, with a written rationale you can read and challenge. Its value is the spread across readings, not any single answer.
- **Can I use my own data?** Yes, locally (Step 1 › Upload my own data). The public site is demo-only for now.
