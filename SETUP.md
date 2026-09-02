# Setup — get this running with Claude Code

Your files are already in this folder: `job-intelligence-platform-overview.md`,
`build-prompt.md`, `Pradeep_Moorthy_Resume_Fixed.docx`, and the unzipped
`job_intel_scraper/` folder (already extracted for you). Claude Code is
already installed, so start here.

## 1. Install Python (skip if you already have 3.11+)

```powershell
python --version
```

If missing or older, get it from python.org (check "Add python.exe to PATH"
during install on Windows).

## 2. Open this folder as your project

```powershell
cd G:\CLAUDE\Jobs
git init
```

Running `git init` here matters — the platform design has a safety guard that
checks personal-data files aren't accidentally tracked by git, and that guard
needs an actual git repo to check. Create a `.gitignore` before your first
commit:

```
job_intel_scraper/jobs.db
job_intel_scraper/jobs.db-*
.env
*.pdf
Pradeep_Moorthy_Resume_Fixed.docx
__pycache__/
*.pyc
venv/
```

(Your resume and the scraped-jobs database are exactly the personal-data
files that should never end up in a public repo.)

## 3. Set up the Python environment

```powershell
cd G:\CLAUDE\Jobs\job_intel_scraper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Pick your LLM backend (for stage-2 scoring)

You don't need a paid API — pick one:

**Option A — Local, free, private (recommended to start):**
```powershell
# Install from https://ollama.com/download, then:
ollama pull qwen2.5:7b
```
No further setup — `main.py` defaults to this backend.

**Option B — Gemini free tier (faster, but Google may use your inputs for
training on the free tier):**
1. Get a free key at https://aistudio.google.com/apikey (no credit card).
2. Set it before running the scraper:
   ```powershell
   $env:JOB_INTEL_LLM_BACKEND = "gemini"
   $env:GEMINI_API_KEY = "your-key-here"
   ```

## 5. Test the scraper skeleton works

```powershell
cd G:\CLAUDE\Jobs\job_intel_scraper
python -m main --countries AU --limit 10
```

You'll see "no boards configured" messages until real Greenhouse/Lever/
Workable/Recruitee tokens are filled in `config.py` — that's expected right
now and is exactly what step 7 below hands to Claude Code.

## 6. Start Claude Code in this project folder

```powershell
cd G:\CLAUDE\Jobs
claude
```

Start it from `G:\CLAUDE\Jobs` specifically (not a subfolder) — that's where
both reference docs and the `job_intel_scraper/` package live, so Claude Code
can see everything in one session.

## 7. Hand it the build prompt

Once you're in the interactive session, paste this as your first message:

```
Read job-intelligence-platform-overview.md and build-prompt.md in this
folder, then look at the existing job_intel_scraper/ package (already
working — don't rewrite what's there, extend it). Start with:
1. The Flask local dashboard (scored jobs, both scoring layers, country
   filter, application-status tracking).
2. The resume data-contract check before any cover-letter generation.
3. The personal-data git-tracking guard described in the overview.
Ask me before adding any new external dependency or making architecture
choices not already decided in build-prompt.md.
```

Claude Code will read both docs and start working directly in this folder —
no copy-pasting code back and forth between this chat and your terminal.

## 8. What to do yourself, in parallel

These aren't code tasks — Claude Code can't look these up reliably on its own:
- Browse each target company's actual careers page and note whether the URL
  contains `greenhouse.io`, `lever.co`, `workable.com`, or `recruitee.com` —
  add confirmed ones to `job_intel_scraper/config.py`.
- Confirm your ANZSCO occupation code fit for Australia against the official
  Department of Home Affairs descriptions before trusting any AU posting's
  "visa-pathway eligible" flag.
- Re-check the Netherlands HSM salary threshold each hiring season — it's
  wage-indexed annually.

## If something breaks

Run `claude doctor` first — it catches most auth/config issues. For anything
Python-side, just describe the error to Claude Code inside the session; it
can see the file and the traceback directly, so there's no need to paste
tracebacks back into this chat.
