# Operator Rebuild Guide — the machine-local layer (F90)

**What this is.** The repo survives the laptop; a pile of setup on the laptop does not. Nothing
outside this file records that setup. If the machine dies, is wiped, or is handed to someone
else, `git clone` gets you the code and the store — and none of the things below. This file
lists every one of them: what it is, where it lives, how to put it back, and what breaks
*silently* if you skip it.

"Silently" is the operative word. Almost nothing here fails loudly. The daily job just stops
running; the web-reach tools just return nothing; the guard hook just stops guarding. No error
lands in the repo, so a rebuilt machine can look healthy while the desk has quietly gone blind.

Scope note: this covers the operator's machine only. Human continuity (who knows what, and why
the desk makes the calls it makes) is the F81–F86 preamble's job, not this file's.

- **Inventoried by inspection on:** 2026-08-04, machine `Daniel` / Windows 11 Home 26200.
- **Backlog F90 called this file `docs/operator-machine.md`;** the lane brief called it
  `docs/operator-rebuild.md`. Same document, one name — this one. Mechanical choice, recorded
  here rather than question-stopped.
- **Everything below was read from the live machine**, not remembered. Where something could
  not be established by looking, it is in OPEN QUESTIONS at the bottom instead of guessed.

---

## Rebuild order (do these in sequence)

1. Clone the repo.
2. Python and the shared virtual environment (§4).
3. Claude Code itself, plus the personal settings and hooks (§3, §5).
4. The coordination skills (§2).
5. The web-reach tools (§6).
6. The scheduled daily job (§1) — last, because it depends on all of the above.
7. Verify (§8).

Repo clone target on this machine: `C:\Users\danie\random_for_fun`, remote
`https://github.com/daniel-wong-tsmc/ai-market-digital-twin.git`. Several paths below are
hard-coded to that exact location; a different folder means editing them.

---

## 1. The daily scheduled job

### 1a. The Windows Task Scheduler registration

**What it is.** A Windows scheduled task that starts the merchant-gpu daily cycle by itself,
once a day, whether or not anyone opens a terminal. It is the only thing that makes the desk
"daily" rather than "whenever the operator remembers".

**Where it lives.** Windows Task Scheduler, task name `Claude GPU Daily Cycle`, at the root
task path (`\`). Not a file in the repo. As registered 2026-08-20 (F83 scheduler fix,
user-approved): enabled, state Ready, daily trigger stored as the absolute moment
2026-07-05T07:57:00+07:00 (displays as the local equivalent when the machine's time zone
moves — user-decided 2026-08-20: leave it), **repeats every 2 hours for 12 hours** so a missed
or failed morning retries until one run succeeds that day (the script's ALREADY-DONE check
makes repeats free after success), runs as user `Daniel` with an interactive token and normal
(non-admin) privileges, three-hour time limit, **starts on battery and keeps running on
battery** (the pre-2026-08-20 "AC only" rules silently lost most unplugged days),
`StartWhenAvailable` on so a missed day runs late rather than never, and `IgnoreNew` so a
second copy never overlaps the first — which also stops a repetition fire from overlapping a
run still in flight.

**How to rebuild.** Recreate the task pointing at the script in §1b:

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -File "C:\Users\danie\.claude\jobs\gpu-daily-cycle.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 08:57
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 08:57 `
  -RepetitionInterval (New-TimeSpan -Hours 2) `
  -RepetitionDuration (New-TimeSpan -Hours 12)).Repetition
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName 'Claude GPU Daily Cycle' -Action $action `
  -Trigger $trigger -Settings $set -RunLevel Limited `
  -Description 'Headless Claude Code run of the merchant-gpu daily cycle (user-authorized 2026-07-05). Logs: ~\.claude\jobs\logs. 2026-08-20 (user-approved, F83 fix): battery starts allowed, repeats every 2h until one run succeeds that day.'
```

Do NOT re-add the battery restrictions and do NOT enable `WakeToRun` — the laptop must never
wake itself (user-decided 2026-08-20).

**What breaks silently.** Everything about "daily". No task means no cycles, no new findings,
no scorecards — and no error anywhere, because nothing ran to produce one. The first symptom is
a gap in the cycle log that someone notices weeks later.

**Live health note (2026-08-04).** Last run 2026-07-29 08:57, exit code 0 (success), next run
2026-08-05 08:57 — but **6 missed runs** since. The task is fine; the machine was off or on
battery at 08:57 on those days. This is exactly the silent failure mode above, happening right
now: the desk lost six days and nothing flagged it. Worth a periodic look at
`Get-ScheduledTaskInfo -TaskName 'Claude GPU Daily Cycle'`.

**Live health note (2026-08-20).** The pattern above repeated (7 no-run days since 08-09, two
dead runs) and was diagnosed end to end — memo:
`.superpowers/handoffs/f83-scheduler-diagnosis-QUESTIONS.md`. The task settings, script, and
watchdog described in this section are the user-approved fixes, applied 2026-08-20; the
pre-change task XML and script are preserved in
`.superpowers/handoffs/f83-scheduler-fix-BACKUP/`.

### 1b. The job script — `~/.claude/jobs/gpu-daily-cycle.ps1`

**What it is.** The PowerShell script the task runs. Rewritten 2026-08-20 (F83 scheduler fix,
user-approved). It opens a dated log, exits fast if today's cycle already completed (so the
2-hour repeats are free), checks the safety interlock, launches Claude Code headlessly with a
fixed instruction — and then **judges success itself**: the run only counts if the repo's
`store/cycle-log.json` shows a completed cycle for today. Anything else exits 1 and fires a
Windows toast, with a distinct toast for an expired login. Deliberately **not** in the repo
(per F83, the live copy stays machine-local); its content is mirrored below so it can be
rebuilt from the repo alone.

**Where it lives.** `C:\Users\danie\.claude\jobs\gpu-daily-cycle.ps1` (rewritten 2026-08-20).
Logs go to `C:\Users\danie\.claude\jobs\logs\gpu-daily-<date>.log`. Two sibling helpers, both
new 2026-08-20: `gpu-cycle-toast.ps1` (shows a toast, message as parameter) and
`gpu-cycle-watchdog.ps1` (§1c). A sibling `pins.json` exists and is an empty list `[]` — no
pinning in effect.

**The safety interlock, in plain words.** Before launching, the script reads
`~/.claude/settings.json` and looks for the text `git push`. If the git/venv permission
allowlist has been removed, it writes "SKIPPED" to the log, fires a toast, and exits 1 rather
than launching a headless session that would freeze forever on a permission prompt nobody is
there to answer. Note the coupling: **§5's allowlist is load-bearing for §1.** Remove it and
the job stops running — and since 2026-08-20 it says so out loud, not just in the log.

**The four silent-death classes this script now catches (diagnosed 2026-08-20, memo
`.superpowers/handoffs/f83-scheduler-diagnosis-QUESTIONS.md`).** (1) Machine asleep or on
battery at trigger time — fixed by the task's battery settings + repetition (§1a). (2) The
session hits a blocker and politely asks a question nobody is there to answer, exiting 0
(08-12) — caught by the success judge: no cycle-log entry for today means FAILED, toast,
exit 1. (3) Headless mode kills background work after 600 seconds (08-19, killed the thesis
brain) — fixed by `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` in the script. (4) **Expired
login (08-14): the run dies in ~30 seconds with "Failed to authenticate". The script detects
that string and toasts "Claude login expired". The operator remedy is simply to open Claude
Code interactively and sign in; the task then retries by itself at the next 2-hour mark. No
credentials are stored or refreshed anywhere in this job — do not try.**

**How to rebuild.** Write this file verbatim to
`C:\Users\danie\.claude\jobs\gpu-daily-cycle.ps1`:

```powershell
# Daily merchant-gpu live cycle, run headless via Windows Task Scheduler.
# User-authorized fully-autonomous run (2026-07-05): commits and pushes on success.
# 2026-07-12 (user-approved, F83): runs with --dangerously-skip-permissions — ALL tools
# granted to this scheduled session only (resolves the 07-09/07-11/07-12 blocked dailies).
# 2026-08-20 (user-approved, F83 scheduler fix):
#   - CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 (headless mode killed the 08-19 thesis step
#     after its 600s background-wait cap; the CLI's own log printed this fix).
#   - The script, not the session, judges success: a run only counts if store/cycle-log.json
#     shows a completed cycle for today. Anything else exits 1 and fires a toast
#     (catches "polite stop" deaths like 08-12 and auth deaths like 08-14).
#   - Distinct toast for auth failure (08-14 class): sign in, the task retries.
#   - The task now repeats every 2h for 12h; ALREADY-DONE below makes repeats free
#     once a cycle has completed, so a missed/failed morning retries until success.
# Logs to ~\.claude\jobs\logs\gpu-daily-<date>.log
$ErrorActionPreference = 'Continue'

$repo = 'C:\Users\danie\random_for_fun'
$logDir = Join-Path $env:USERPROFILE '.claude\jobs\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$today = Get-Date -Format 'yyyy-MM-dd'
$log = Join-Path $logDir ("gpu-daily-" + $today + ".log")

function Get-CycleState {
  # Newest completed-cycle marker from the repo's cycle log:
  # capturedAt date (completion day) + newest entry status.
  try {
    $cl = Get-Content (Join-Path $repo 'store\cycle-log.json') -Raw | ConvertFrom-Json
    $cap = ''
    if ($cl.capturedAt) { $cap = ([string]$cl.capturedAt).Substring(0, 10) }
    $status = ''
    if ($cl.entries -and $cl.entries.Count -gt 0) { $status = [string]$cl.entries[0].status }
    return New-Object PSObject -Property @{ CapturedDate = $cap; Status = $status }
  } catch {
    return New-Object PSObject -Property @{ CapturedDate = ''; Status = '' }
  }
}

function Send-CycleToast([string]$Message) {
  try { & powershell.exe -NoProfile -File (Join-Path $env:USERPROFILE '.claude\jobs\gpu-cycle-toast.ps1') -Message $Message } catch {}
}

"=== gpu-daily-cycle start $(Get-Date -Format o) ===" | Out-File $log -Append -Encoding utf8

# Fast exit for the repetition trigger: once today's cycle completed, later fires are no-ops.
$pre = Get-CycleState
if ($pre.CapturedDate -eq $today -and $pre.Status -eq 'done') {
  "ALREADY-DONE: cycle log shows a completed cycle for $today; nothing to do." | Out-File $log -Append -Encoding utf8
  exit 0
}

# Safety interlock: headless runs need the git/venv permission allowlist in ~\.claude\settings.json.
# If it is ever removed, skip cleanly instead of stalling mid-run on permission prompts.
$settings = Get-Content (Join-Path $env:USERPROFILE '.claude\settings.json') -Raw
if ($settings -notmatch 'git push') {
  "SKIPPED: git/venv permission allowlist not present in settings.json; headless run would stall." | Out-File $log -Append -Encoding utf8
  Send-CycleToast "Daily cycle SKIPPED: the git/venv permission allowlist is missing from ~\.claude\settings.json."
  exit 1
}

Set-Location $repo

# F83 fix (user-approved 2026-08-20): print mode terminates background tasks after 600s
# by default — this killed the 08-19 thesis brain. 0 = wait indefinitely (the CLI's own
# suggested fix, printed in gpu-daily-2026-08-19.log). The task's 3h limit stays the backstop.
$env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS = '0'

$prompt = @'
Use the run-gpu-market skill to run the daily cycle for category:chips.merchant-gpu (mode: daily, live gather). Follow CLAUDE.md and the skill exactly. Orient first: if git status shows another instance mid-run (fresh uncommitted store/ artifacts appearing), or git pull --ff-only fails, STOP and append the blocker to docs/superpowers/HANDOFF.md instead of improvising. After a successful cycle: commit and push store/ artifacts and the cycle log, then append a one-line run summary (scorecard path, DMI/SMI) to the newest-state section of docs/superpowers/HANDOFF.md and push that too. This is a scheduled headless run: record any judgment calls as "AFK-default" in HANDOFF.md. Nobody is watching this session: if you hit a blocking condition or an unanswerable question, do NOT end your turn with a question — save all work, append the blocker and where you stopped to docs/superpowers/HANDOFF.md, and end your turn with the single line CYCLE FAILED so the wrapper script can alert.
'@

& "C:\Users\danie\.local\bin\claude.exe" -p $prompt --dangerously-skip-permissions *>> $log
$claudeExit = $LASTEXITCODE
"=== gpu-daily-cycle claude done $(Get-Date -Format o) exit=$claudeExit ===" | Out-File $log -Append -Encoding utf8

# Success judge: the ONLY success signal is a completed cycle logged for today.
# Exit 0 + friendly words is not success (the 08-12 lesson).
$post = Get-CycleState
if ($post.CapturedDate -eq $today -and $post.Status -eq 'done') {
  "SUCCESS: cycle log shows a completed cycle for $today (claude exit=$claudeExit)." | Out-File $log -Append -Encoding utf8
  "=== gpu-daily-cycle end $(Get-Date -Format o) exit=0 ===" | Out-File $log -Append -Encoding utf8
  exit 0
}

# Failure: classify this attempt's log slice (from this invocation's start marker on).
$content = ''
try { $content = Get-Content $log -Raw } catch {}
$idx = $content.LastIndexOf('=== gpu-daily-cycle start')
$slice = if ($idx -ge 0) { $content.Substring($idx) } else { $content }
# PS 5.1's *>> appends claude's output as UTF-16 while our markers are UTF-8; strip the
# interleaved NUL bytes so string matching sees the CLI's words.
$slice = $slice -replace [string][char]0, ''

if ($slice -match 'Failed to authenticate|OAuth (session|token) expired') {
  "FAILED-AUTH: Claude login expired; run died before doing anything (claude exit=$claudeExit)." | Out-File $log -Append -Encoding utf8
  Send-CycleToast "Daily cycle FAILED: Claude login expired. Open Claude Code and sign in; the task retries every 2h until 19:57."
} else {
  "FAILED: no completed cycle recorded for $today (claude exit=$claudeExit). See this log." | Out-File $log -Append -Encoding utf8
  Send-CycleToast "Daily cycle FAILED today: no completed cycle recorded. Log: ~\.claude\jobs\logs\gpu-daily-$today.log"
}
"=== gpu-daily-cycle end $(Get-Date -Format o) exit=1 ===" | Out-File $log -Append -Encoding utf8
exit 1
```

Three things in that script are machine-specific and must be checked on a rebuild: the repo
path, the path to `claude.exe` (`C:\Users\danie\.local\bin\claude.exe`, present, native
install), and the `--dangerously-skip-permissions` flag — which grants that scheduled session
every tool with no prompts. That flag is user-approved for this job only (2026-07-12, F83) and
is documented in `docs/threat-model-unattended.md` as "Stage 0". Do not copy it onto anything
else.

**What breaks silently.** Much less than before 2026-08-20: a failed or absent run now exits 1,
toasts, and is caught again by the watchdog (§1c) and the session-start gap banner
(`scripts/session-orient` → `scripts/cycle_gap.py`). Still silent: the machine being asleep or
off all day (nothing can run, and the toast waits for the next logon), and a corrupted script
that Task Scheduler cannot even start.

### 1c. The missed-run watchdog — `~/.claude/jobs/gpu-cycle-watchdog.ps1` + toast helper

**What it is.** Two small machine-local scripts plus a second scheduled task, added 2026-08-20
(F83 fix, user-approved). `gpu-cycle-toast.ps1` shows a Windows toast, taking the message as a
parameter (a standalone copy of the `~\.claude\hooks\claude-toast.ps1` logic). The scheduled
task **`Claude GPU Cycle Watchdog`** (triggers: at logon of `Daniel`, and daily 20:30; battery
allowed; StartWhenAvailable; 5-minute limit) runs `gpu-cycle-watchdog.ps1`, which reads
`store/cycle-log.json` (read-only, never starts a cycle) and toasts when a scheduled day
produced no run: "last completed cycle was N days ago" when 2+ days stale, or "no completed
cycle today" when it is 20:00+ and today is still empty. Silent when healthy and silent on any
read error.

**How to rebuild.** Copy both scripts from the backup
(`.superpowers/handoffs/f83-scheduler-fix-BACKUP/` holds the task XMLs; the scripts' logic is
described above and the toast body matches `~\.claude\hooks\claude-toast.ps1`), then:

```powershell
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -WindowStyle Hidden -File "C:\Users\danie\.claude\jobs\gpu-cycle-watchdog.ps1"'
$t1 = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$t2 = New-ScheduledTaskTrigger -Daily -At 20:30
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'Claude GPU Cycle Watchdog' -Action $action `
  -Trigger $t1,$t2 -Settings $set -RunLevel Limited `
  -Description 'Missed-run alert for the GPU daily cycle (F83 fix, user-approved 2026-08-20). Toasts when a scheduled day produced no run. Read-only.'
```

**What breaks silently.** The watchdog itself: if it is deleted, nothing alerts about missed
days again and nothing alerts about the watchdog. The session-start gap banner in the repo
(`scripts/cycle_gap.py`) is the independent backstop.

---

## 2. The coordination skills in `~/.claude/skills`

**What they are.** Six short instruction files that live in the user's home folder, not the
repo, so they work from *any* Claude Code session — including one opened outside the project.
They are how a session knows to orient before acting, how to launch the market, how to run
evals without re-deriving the failure protocol, and how two concurrent sessions avoid trampling
each other.

**Where they live.** `C:\Users\danie\.claude\skills\<name>\SKILL.md`. All six named in F90 are
present, each a single `SKILL.md` with no extra files:

| Skill | Lines | What it does |
|---|---|---|
| `run-gpu-market` | 61 | Launcher — refreshes the repo, then hands off to the repo's `run-cycle` skill. The daily job depends on this one. |
| `resume-desk` | 24 | Session start — orient from live git state, not from memory. |
| `eval-driver` | 38 | Eval runs and the rejected-answer protocol; defers to the repo's `run-eval` skill for the step sequence. |
| `instance-sync` | 32 | Proactive lane/branch/worktree claim protocol for concurrent sessions. |
| `concurrent-edit-guard` | 92 | Reactive companion — what to do when you find a file someone else is editing. Paired with the hook in §3. |
| `desk-handoff` | 30 | Session end — writes the handoff from live state. |

Three further skills sit alongside them and are unrelated to this project's core loop but are
part of the working setup: `agent-reach` (with a `references/` folder of six routing docs),
`last30days` (scripts + assets), and `stop-slop`. The first two are covered in §6.

**How to rebuild.** These are hand-written and have no upstream source — **there is no install
command.** If they are lost, they are lost. The repo's own `.claude/skills/` (about 20 skills,
tracked in git) survives a clone; these six do not. Rebuild means writing them again from the
repo's CLAUDE.md and the handoff docs, which is a real afternoon of work and will not reproduce
them faithfully.

**Recommended, cheap, not yet done:** copy the six files into the repo as reference (they
contain no secrets), the same way §1b's script content is mirrored here. See OPEN QUESTIONS.

**What breaks silently.** The worst class of failure in this document. A session with no
`resume-desk` skill does not error — it just starts work without orienting. No `instance-sync`
means two sessions quietly collide (the F69 mixup precedent). No `eval-driver` means the eval
failure protocol gets improvised, expensively, every time. No `run-gpu-market` means the daily
job's prompt names a skill that does not exist, and the headless session improvises a market
run with no supervision.

---

## 3. The repo's local hook settings — `.claude/settings.local.json`

**What it is.** A small settings file that wires the concurrent-edit guard into every file edit
in this repo: before and after each Edit or Write, Claude Code runs a Python script that checks
whether another session is mid-edit on the same file.

**Where it lives.** `C:\Users\danie\random_for_fun\.claude\settings.local.json`. It is **not**
tracked by git and **not** in `.gitignore` — it is excluded through `.git/info/exclude`, which
is itself a machine-local file inside `.git/` that no clone ever receives. So a fresh clone
loses both the settings file and the rule that hides it.

**Two files, both needed:**

- `.claude/settings.local.json` — the hook wiring (PreToolUse and PostToolUse, matcher
  `Edit|Write`, 15-second timeout, run through bash).
- `C:\Users\danie\.claude\hooks\concurrent-edit-guard.py` — the script itself, 3653 bytes, home
  folder, not in the repo. A sibling `claude-toast.ps1` (1658 bytes) powers the desktop
  notification hook in §5.

**How to rebuild.** Recreate the exclusion line, then the settings file:

```bash
printf '\n# Claude Code personal local settings (concurrent-edit-guard hook)\n.claude/settings.local.json\n' \
  >> C:/Users/danie/random_for_fun/.git/info/exclude
```

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [ { "type": "command", "shell": "bash",
          "command": "py -3 \"C:/Users/danie/.claude/hooks/concurrent-edit-guard.py\" pre",
          "timeout": 15, "statusMessage": "concurrent-edit guard" } ] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [ { "type": "command", "shell": "bash",
          "command": "py -3 \"C:/Users/danie/.claude/hooks/concurrent-edit-guard.py\" post",
          "timeout": 15 } ] }
    ]
  }
}
```

The guard script `concurrent-edit-guard.py` has no upstream and is not mirrored anywhere. Same
problem as §2 — see OPEN QUESTIONS.

**What breaks silently.** Edits stop being checked. Nothing announces it; the guard's whole
value was catching the collision you did not know was happening. Note the hook also calls
`py -3`, so it fails the moment the Python launcher is missing (§4).

---

## 4. The shared Python environment — root `.venv`

**What it is.** One virtual environment at the repo root that every session and every worktree
uses. `.gitignore` line 1 excludes it, so a clone never has one. CLAUDE.md is explicit: one
shared root venv, never per-worktree copies; from a worktree the path is `../../.venv/...`.

**Where it lives.** `C:\Users\danie\random_for_fun\.venv`. Interpreter: **Python 3.13.7**
(64-bit, Windows). `pyproject.toml` requires 3.11 or newer, so 3.11+ works; 3.13.7 is what is
installed and what the tests have been green on.

**What is in it** (full list as inspected — it is deliberately small): the project itself
(`gpu_agent 0.1.0`, editable/installed), `pydantic 2.13.4` + `pydantic_core` +
`annotated-types` + `typing_extensions` + `typing-inspection`, `pytest 9.1.1` + `pluggy` +
`iniconfig` + `packaging` + `Pygments` + `colorama`, `PyYAML 6.0.3`, `pip 25.2`.

There is no `requirements.txt`. `pyproject.toml` is the authoritative source: runtime dependency
`pydantic>=2,<3`; optional group `dev = pytest>=8`; optional group `llm = anthropic>=0.40,
claude-agent-sdk>=0.1` (**not installed** — the desk uses Claude Code itself as the brain, no
API/SDK path). `PyYAML` is installed but is not declared in `pyproject.toml` — see OPEN
QUESTIONS.

**How to rebuild.**

```powershell
cd C:\Users\danie\random_for_fun
py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pip install pyyaml
.venv\Scripts\python -c "import gpu_agent; print('ok')"
.venv\Scripts\python -m pytest
```

The suite must be green, with 3–4 skips expected.

Caution carried from the user's environment notes: `python3` on this machine resolves to a
Windows Store stub and must never be called. Use `py -3` or `.venv\Scripts\python`.

**What breaks silently.** Less silently than the rest — imports fail loudly. But the *headless*
job is the problem: it fails inside a log file nobody reads, on a schedule, at 08:57.

---

## 5. Personal Claude Code settings — `~/.claude/settings.json`

**What it is.** The user-level Claude Code configuration. Three parts matter operationally:

1. **The permission allowlist** — 29 entries pre-approving read-only git commands plus
   `git add/commit/push/pull/switch/worktree/stash`, `.venv/Scripts/python`, and `pytest`,
   under both the Bash and PowerShell tools. **This is what the §1b interlock checks for.**
2. **The notification hook** — runs `~/.claude/hooks/claude-toast.ps1` to raise a Windows toast
   when a session wants attention.
3. **Assorted preferences** — model `opus[1m]`, `effortLevel: medium`, theme auto, auto-memory
   off, the `superpowers@claude-plugins-official` plugin enabled.

**Where it lives.** `C:\Users\danie\.claude\settings.json`. Home folder, never in any repo.

**How to rebuild.** Retype it. The allowlist is the load-bearing half; the exact 29 entries are
readable from the live file today and follow an obvious pattern (`Bash(git status:*)`,
`PowerShell(git status:*)`, and so on for status/log/diff/show/branch/fetch/rev-parse/add/
commit/push/pull/switch/worktree/stash, plus `.venv/Scripts/python` and `pytest`). Also
re-enable the superpowers plugin, which several dispatch workflows assume:
`/plugin` inside Claude Code, or the `enabledPlugins` key.

Related but separate: `~/.claude.json` holds per-project state and the MCP server list. One MCP
server is configured — `headroom`, a stdio server run from
`c:\users\danie\appdata\roaming\python\python313\scripts\headroom.EXE mcp serve`. It is not
part of the daily cycle, but a rebuilt machine will not have it.

**What breaks silently.** Remove the allowlist and §1b skips the run *cleanly* — a log line, no
alarm, no cycle. Lose the notification hook and sessions wait for an operator who was never
told.

---

## 6. The web-reach tools

**What they are.** External command-line tools that fetch material from the open web during a
gather cycle, alongside Claude Code's built-in search. Doctrine is charter Part 37; the
authoritative list is data in `registry/web-reach-tools.json` (in the repo, four tools); the
operator how-to is `docs/web-reach.md` (in the repo). Only the *installs* are machine-local.

**Where they live.** Installed via `pipx` into `C:\Users\danie\pipx\venvs`, exposed on PATH at
`C:\Users\danie\.local\bin`. Verified present today:

- **agent-reach 1.5.0** (installed with Python 3.13.7) — the router. Config folder
  `~/.agent-reach/` exists with an empty `tools/` subfolder.
- **crawl4ai 0.9.0** (installed with Python 3.13.7) — headless-browser crawler; exposes `crwl`,
  `crawl4ai-setup`, `crawl4ai-doctor`, and two more. `crwl --help` works.
- **Playwright's Chromium** — present at `C:\Users\danie\AppData\Local\ms-playwright`:
  `chromium-1228`, `chromium_headless_shell-1228`, `ffmpeg-1011`, `winldd-1007`. Roughly a
  gigabyte, downloaded by `crawl4ai-setup`, never in any repo.
- **last30days** — a skill, not a binary. Present in **two** places:
  `~/.claude/skills/last30days` (with `scripts/`, `references/`, `agents/openai.yaml`, and
  assets) and `~/.agents/skills/last30days`. The registry's health check looks only at
  `~/.agents/skills/last30days`.
- **huggingnews** — nothing to install; a public JSON API. Its optional key is a machine-local
  file: `.superpowers/secrets/HUGGINGNEWS_API_KEY` (35 bytes, present) — inside `.superpowers/`,
  which `.gitignore` excludes. Never committed, never logged.

**How to rebuild.** The repo already automates this. From the repo root:

```
scripts\web-reach-ensure.cmd --json
```

That wrapper finds a Python (prefers `.venv\Scripts\python.exe`, falls back to `py -3`, then
`python`) and runs `gpu_agent.web_reach_ensure`, which reads the registry and reports or
performs the per-OS installs recorded there. The registry's Windows recipes, for reference:

```
py -3 -m pip install --user pipx
py -3 -m pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
py -3 -m pipx ensurepath
agent-reach install --env=auto

py -3 -m pipx install crawl4ai==0.9.0
crawl4ai-setup                          # downloads the Chromium browser

npx -y skills add mvanhorn/last30days-skill -g
```

The API key must be recreated by hand — see OPEN QUESTIONS.

**Live health, checked read-only today** (`agent-reach doctor --json`, 15 channels):

| Working now | Warning (backend missing) | Off |
|---|---|---|
| web (Jina Reader), rss (feedparser), bilibili, v2ex | github (`gh` CLI not installed), twitter (`twitter-cli` not installed), xueqiu | youtube (`yt-dlp`), reddit, facebook, instagram, xiaohongshu, linkedin, xiaoyuzhou, exa_search |

Read that as: the two channels the desk actually leans on for open-web reading — plain web
pages and RSS — are live. The social and video channels are not configured on this machine and
would need per-channel logins or extra CLIs. That is a standing state, not a regression, and it
matches the registry note that the Exa search path fails clean until `mcporter` and the Exa MCP
are configured.

**What breaks silently.** This is the subtlest one. A gather cycle with no web-reach tools does
not crash — it just gathers less, from fewer places, and the cycle log looks normal. Findings
get thinner over weeks before anyone connects it to a missing install. Same for the Chromium
download: without it, `crwl` fails on every JavaScript-heavy page while everything else keeps
working.

---

## 7. One-time acceptance state

Claude Code stores some "you already agreed to this" flags per machine, outside any repo, in
`C:\Users\danie\.claude.json`. What inspection found:

- **The bypass-permissions acceptance:** F90 assumed a stored one-time acceptance exists. It is
  **not present** in `~/.claude.json` — no key containing `bypassPermissions`, `dangerously`,
  `accept`, or `acknowledge`. The daily job passes `--dangerously-skip-permissions` directly on
  the command line for that one headless session, which is what actually grants the bypass. So
  on this machine there is no acceptance flag to rebuild. A future Claude Code version could
  reintroduce an interactive confirmation that a headless run cannot answer; if the daily job
  ever starts hanging at launch after an update, look here first.
- **Trust dialog:** the project entry for `C:/Users/danie/random_for_fun` records
  `hasTrustDialogAccepted: false`, with an empty `allowedTools` list. Trust and permissions for
  this repo come from the home-level allowlist in §5, not from a per-project acceptance.
- **Onboarding flags** (`hasCompletedOnboarding`, marketplace auto-install, Chrome-extension
  onboarding, and similar) are set and would be re-answered naturally on a fresh machine. No
  rebuild action needed.
- **Git worktrees** are machine-local by construction. Nine exist today (root plus eight lane
  worktrees under `.worktrees/`). A clone has none; branches come back with the clone, and
  worktrees are recreated on demand with `git worktree add`. Nothing to preserve.

---

## 8. Verify a rebuild

Run all of these; every one should pass before calling the machine restored.

```powershell
cd C:\Users\danie\random_for_fun
.venv\Scripts\python -c "import gpu_agent; print('venv ok')"
.venv\Scripts\python -m pytest                       # green, 3-4 skips expected
agent-reach doctor --json                            # web + rss at least 'ok'
crwl --help                                          # crawl4ai present
scripts\web-reach-ensure.cmd --json                  # registry vs installed
Get-ScheduledTaskInfo -TaskName 'Claude GPU Daily Cycle'
Get-Content $env:USERPROFILE\.claude\settings.json | Select-String 'git push'
Test-Path $env:USERPROFILE\.claude\jobs\gpu-daily-cycle.ps1
Test-Path $env:USERPROFILE\.claude\hooks\concurrent-edit-guard.py
Get-ChildItem $env:USERPROFILE\.claude\skills         # expect the six coordination skills
Test-Path $env:USERPROFILE\AppData\Local\ms-playwright\chromium-1228
```

**Quarterly check (10 minutes, calendar it).** Re-run the block above and confirm four things:
the scheduled task's `LastRunTime` is recent and `NumberOfMissedRuns` is not climbing; the six
skills are still present; `agent-reach doctor` has not lost a channel that used to work; the
test suite is still green. Then re-read this file against reality and fix anything that drifted
— a rebuild guide that has quietly gone stale is worse than none, because it will be trusted.

---

## OPEN QUESTIONS

Things inspection cannot settle. These are gaps in the record, not blockers.

1. **The six coordination skills and the guard hook have no backup.** `~/.claude/skills/*` (six
   files) and `~/.claude/hooks/concurrent-edit-guard.py` are hand-written, have no upstream, and
   exist in exactly one place on one laptop. F90's own lean mirrors only the *job script* into
   the repo. Recommendation: mirror these seven files into the repo too (a
   `docs/machine-local/` reference folder), since they contain no secrets. Needs the user's yes,
   and it is a real change to what the repo carries — not this lane's to decide.
2. **`HUGGINGNEWS_API_KEY` cannot be rebuilt from anything on this machine.** The file exists
   and is correctly excluded from git. Where the key came from, and how to get another, is only
   in the user's head or the vendor's account. Needed: where it is re-obtainable from, and
   whether it is stored anywhere else (password manager?).
3. **`PyYAML` is installed in the venv but not declared in `pyproject.toml`.** A clean rebuild
   following only `pyproject.toml` would omit it. Either something imports it (and the
   declaration is missing) or it is a leftover. Needs a look — code change, out of scope here.
4. **The `last30days` skill is installed in two places** (`~/.claude/skills/` and
   `~/.agents/skills/`) and the registry health check only looks at the second. Whether that is
   intentional belt-and-braces or accidental drift is unknown.
5. **Which web-reach channels are *supposed* to work.** Eight channels are off and three warn.
   Some of those need a browser login (Reddit, Facebook, Instagram, Xiaohongshu via OpenCLI),
   which only the user can perform, and some need extra CLIs (`gh`, `yt-dlp`, `twitter-cli`).
   Nobody has written down the intended target state, so a rebuilder cannot tell "restored" from
   "still degraded". Recommendation: record the intended set in `docs/web-reach.md`.
6. **The Exa search path** (`mcporter` + Exa MCP) is registered but not configured; the registry
   says it fails clean. Is configuring it wanted, or is it deliberately parked?
7. **No account-level items are inventoried here** — the Claude Code login, the GitHub
   credentials that let the headless job push, and any Cloudflare Pages access for the published
   site. All are credentials only the user holds. A rebuild needs them and this file cannot
   supply them.
8. **The `~/.agent-reach/tools/` folder is empty.** Whether agent-reach is supposed to populate
   it (and something is unconfigured) or empty is normal for v1.5.0 could not be determined by
   inspection.
9. **The name.** F90 in the backlog specifies `docs/operator-machine.md`; this file is
   `docs/operator-rebuild.md` per the lane brief. Worth aligning the backlog entry when F90 is
   closed so future readers do not hunt for a file that never existed.
