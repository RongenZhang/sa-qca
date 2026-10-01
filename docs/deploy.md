# Deploying the public demo (free tier)

The public demo is a **scripted** version of the tool: demo project and scripted responses only, no uploads, no API keys, no language model calls. It runs as one Docker container (built frontend + backend + R with QCA).

Two free-tier options are prepared. **Render** is the one to use if Hugging Face does not offer you free Docker/CPU Spaces (some accounts see Docker marked "Paid").

## Option A: Render (free web service)

Measured peak memory for one full demo run is about 230 MB (Python server 78 MB + R 151 MB), which fits Render's 512 MB free plan if only one run happens at a time; `render.yaml` sets that.

1. Sign up at render.com (GitHub login is simplest).
2. Dashboard › New + › **Blueprint** › pick the `sa-qca` repository (or paste its public URL) › **Apply**. Render reads `render.yaml` and builds the Dockerfile (first build takes several minutes).
3. When it shows **Live**, open the `https://sa-qca-demo-xxxx.onrender.com` address it gives you.
4. Check it: `bash deploy/smoke.sh https://sa-qca-demo-xxxx.onrender.com`

It redeploys automatically on every push to `main`. Free services sleep after about 15 minutes idle and take about a minute to wake.

## Option B: Hugging Face Spaces (Docker SDK, free CPU where available)

Setup (about 10 minutes, done by you):

1. Create a free account at huggingface.co.
2. Create a **Space**: New Space › name it (for example `sa-qca-demo`) › SDK **Docker** › hardware **CPU basic (free)** › visibility **Public**.
3. Create an access token: Settings › Access Tokens › New token with **Write** permission. Copy it once; do not paste it anywhere except step 4.
4. In the GitHub repository: Settings › Secrets and variables › Actions
   - **Secrets** › New repository secret: name `HF_TOKEN`, value = the token.
   - **Variables** › New repository variable: name `HF_SPACE`, value = `your-hf-username/sa-qca-demo`.
5. Run the workflow: Actions › "Deploy public demo to Hugging Face Spaces" › Run workflow. It also runs on every push to `main` once the variable is set.
6. The Space builds the image (about 10 minutes the first time). The live site is at `https://<username>-<space-name>.hf.space`.

Afterwards, run the smoke test against the live URL from any terminal:
```bash
bash deploy/smoke.sh https://<username>-<space-name>.hf.space
```

## What protects the demo

- **No visitor data to protect:** uploads, other projects and real model providers are refused by the server, not just hidden in the page; keys and workspace IDs sent to it are ignored.
- **Visitor isolation:** each browser gets a random token; runs are visible only to the browser that started them (others get 404).
- **Abuse limits:** at most 5 repetitions and 6 roles per run, one run at a time per visitor, 2 runs at once overall (HTTP 429 beyond that).
- **Retention:** runs and role approvals are deleted after 24 hours (`SA_QCA_RETENTION_HOURS`), and the database lives in the container's temporary storage, so a restart also clears it.
- Environment variables: `SA_QCA_MODE=demo` (set in the Dockerfile), `SA_QCA_MAX_REPS`, `SA_QCA_MAX_ROLES`, `SA_QCA_MAX_CONCURRENT`, `SA_QCA_RETENTION_HOURS`.

## Free-tier behaviour to expect

The site sleeps after inactivity and takes a minute to wake; the first run after a cold start is slower. The mechanical source makes about 30 separate R calls, so a full demo run takes around a minute.

## Not yet supported on the public site

Uploading your own data and bring-your-own-key runs. Those need per-visitor data isolation, expiry and a privacy notice before they can be offered to strangers; until then, run the tool locally (see the README).
