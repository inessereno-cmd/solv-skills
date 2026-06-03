---
name: setup-daily-assistant
description: Set up a personal daily AI assistant on a Mac that runs Claude CLI on a schedule via launchd, queries dbt/Redshift via MCP, and posts results to Slack. Use when a Solv employee wants to automate a recurring Claude task — daily reports, scheduled analyses, or any prompt that should run autonomously on a timer. Guides through installing prerequisites, creating the assistant infrastructure, configuring a custom daily prompt, and scheduling via launchd. Triggers on requests like "set up a daily assistant", "automate a Claude task", "schedule a recurring report", or "create a daily bot".
---

# Setup Daily Assistant

## Important: How This Guide Works

Before starting, ask the user which tool they are using:

_"Are you using **Claude Code** (the CLI tool in your terminal) or **Claude Chat** (the desktop/web chat app)?"_

The setup process is the same either way, but how you interact with the user is different depending on the tool.

---

### If the user is using Claude Code

First, ask: _"Do you already have Claude Code installed?"_

**If they don't have Claude Code installed yet**, walk them through the installation:

1. They need **Node.js** first. Tell them to open Terminal (Applications > Utilities > Terminal) and run:
   ```
   node --version
   ```
   - If it prints a version (like `v20.x.x`): Node is installed, move on.
   - If it says "command not found": They need to install Homebrew first, then Node:
     ```
     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
     ```
     After Homebrew installs, follow the "Next steps" it prints to add it to PATH, then:
     ```
     brew install node
     ```

2. Install Claude Code:
   ```
   npm install -g @anthropic-ai/claude-code
   ```
   If they get `EACCES` permission errors, they need to set up a user-local npm directory first:
   ```
   mkdir -p ~/.npm-global
   npm config set prefix '~/.npm-global'
   echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```
   Then retry the install command.

3. Verify it works:
   ```
   claude --version
   ```

4. Authenticate:
   ```
   claude login
   ```
   This opens a browser for login. After completing it, verify:
   ```
   claude -p "Say AUTH_OK"
   ```

Once Claude Code is installed and authenticated, they can proceed with the setup.

**If they already have Claude Code installed**, skip ahead to loading the skill below.

---

**Getting started with the setup in Claude Code:**

If the user hasn't already loaded this skill, they first need the skills repo cloned. Instruct them:

1. If they don't have the skills repo yet, run this in Terminal:
   ```
   git clone https://github.com/solvhealth/skills.git ~/skills
   ```
2. Then start Claude Code and reference this skill:
   ```
   claude
   ```
   Once in the Claude Code session, tell it:
   _"Use the skill at ~/skills/automation/setup-daily-assistant.md to set up my daily assistant."_

Or if they're already in a Claude Code session and asked you to set up a daily assistant, you're already running — proceed directly to Step 1.

---

**Behavior rules when running inside Claude Code:**

You **can** run commands and create files directly. You have full access to the user's terminal and filesystem. Follow these rules:

- **Run commands directly** using your Bash tool — do not ask the user to copy-paste commands unless you need their input (like credentials or schedule preferences).
- **Create files directly** using your write/edit tools — do not use `cat << EOF` syntax.
- **Go one step at a time** — verify each step succeeded before moving on.
- **Still ask the user for input** when the step requires it (MCP credentials from 1Password, schedule preferences, Slack channel ID, prompt customization, etc.).
- If something goes wrong, troubleshoot it directly — read log files, check command output, and fix issues before continuing.

Tell the user upfront: _"I'll handle most of the setup directly from here. I'll ask you for a few things along the way — like your MCP credentials and what time you want the assistant to run."_

---

### If the user is using Claude Chat

You **cannot** run commands or create files for them. Instead, you must:

- Give the user commands to **copy and paste into their Mac's Terminal app** (Applications > Utilities > Terminal, or search Spotlight for "Terminal")
- Ask them to **paste back the output** so you can verify each step succeeded
- When creating files, provide the **full file contents** and a **single copy-paste command** using `cat << 'EOF' > filepath` syntax so the user doesn't need a text editor
- **Go one step at a time** — don't dump the entire guide at once. Complete each step before moving to the next.
- If something goes wrong, **troubleshoot with the user** before continuing

Tell the user upfront: _"I'll walk you through this step by step. For each step, I'll give you a command to copy and paste into your Terminal. After you run it, paste the output back here so I can make sure it worked."_

---

## Overview

When complete, the user will have:

- A Claude CLI task that runs automatically every day at their chosen time
- MCP connections to dbt/Redshift (for SQL queries) and Slack (for posting results)
- A customizable prompt file they can edit anytime to change what the assistant does
- Automatic pulling of the latest skills from the shared skills repo before each run

Everything lives in `~/.solv-assistant/` and is easy to update, pause, or remove.

---

## Step 1: Prerequisites

> **Claude Code:** Run each check command directly. If something is missing, run the install command and verify. You can move through these quickly — only pause to ask the user if an install fails or needs their input (like Homebrew's initial setup prompts).
>
> **Claude Chat:** Walk through each prerequisite one at a time. Give the user the check command, ask them to paste back the output, then either move on or guide them through the install.

### 1a. Detect the user's shell

Tell the user to run:

```
echo $SHELL
```

**What to expect:**
- `/bin/zsh` — this is the default on modern Macs. They'll use `~/.zshrc` for PATH changes.
- `/bin/bash` — older setup. They'll use `~/.bashrc` or `~/.bash_profile`.

Remember which shell they have — you'll need it in step 1c.

### 1b. Homebrew

Tell the user to run:

```
which brew
```

**If it prints a path** (like `/opt/homebrew/bin/brew`): Homebrew is installed. Move on.

**If it prints nothing or "not found":** Tell the user to install it by running:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

This takes 1-2 minutes. After it finishes, Homebrew will print instructions about adding it to PATH — tell the user to **look for lines that say "Next steps"** and run those commands. Then verify by running:

```
brew --version
```

**What to expect:** Something like `Homebrew 4.x.x`. If they get "command not found", the PATH step was missed — ask them to paste what Homebrew printed after install.

### 1c. Node.js

Tell the user to run:

```
which node
```

**If it prints a path:** Node is installed. Move on.

**If not found:** Tell the user to run:

```
brew install node
```

Then verify:

```
node --version
```

**What to expect:** Something like `v20.x.x` or `v22.x.x`. Any version 18+ is fine.

### 1d. npm global directory

Tell the user to run:

```
npm config get prefix
```

**What to expect:**
- If it shows something under their home directory (like `/Users/theirname/.npm-global`): Good, move on.
- If it shows `/usr/local`: This requires sudo for global installs, which causes problems. Fix it by having them run these commands one at a time:

```
mkdir -p ~/.npm-global
```

```
npm config set prefix '~/.npm-global'
```

Then they need to add the new path to their shell. Based on the shell detected in step 1a:

**For zsh** (`~/.zshrc`):
```
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.zshrc
```

**For bash** (`~/.bashrc` or `~/.bash_profile`):
```
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
```

Then tell them to **close and reopen Terminal** (or run `source ~/.zshrc` / `source ~/.bashrc`), and verify:

```
npm config get prefix
```

**What to expect:** Should now show `/Users/<theirname>/.npm-global`.

**Common issue:** If they still see `/usr/local`, the source command didn't work. Tell them to fully quit Terminal (Cmd+Q) and reopen it, then try again.

### 1e. jq

Tell the user to run:

```
which jq
```

**If it prints a path:** Move on.

**If not found:**

```
brew install jq
```

Verify:

```
jq --version
```

**What to expect:** Something like `jq-1.7.1`.

### 1f. Claude CLI

Tell the user to run:

```
which claude
```

**If it prints a path:** Move on to auth check.

**If not found:**

```
npm install -g @anthropic-ai/claude-code
```

**Common issue:** If they get `EACCES` permission errors, the npm prefix from step 1d wasn't set up correctly. Go back and fix that first.

Verify:

```
claude --version
```

**What to expect:** A version string like `1.x.x`.

### 1g. Claude authentication

Tell the user to run:

```
claude -p "Say AUTH_OK"
```

**What to expect:**
- If it prints `AUTH_OK` (possibly with some extra text): Auth is working. Move on.
- If it opens a browser or says "not authenticated": Tell the user to run `claude login`, complete the browser login flow, then re-run the `AUTH_OK` test.

**Common issue:** If login says they need an API key or organization access, they should check with their team lead about Anthropic account access.

---

## Step 2: Create the assistant directory

> **Claude Code:** Run this command directly.
>
> **Claude Chat:** Tell the user to run:

```
mkdir -p ~/.solv-assistant/logs
```

This command produces no output on success. To verify, have them run:

```
ls -la ~/.solv-assistant/
```

**What to expect:** They should see the `logs` directory listed.

Explain the directory structure:

```
~/.solv-assistant/
  config.json          # schedule + model settings
  mcp-config.json      # MCP credentials (from 1Password)
  prompt.md            # your custom task prompt
  run.sh               # main execution script
  scheduler.sh         # time-gate wrapper
  .last-run            # lock file (auto-created at runtime)
  logs/
    assistant.log      # stdout from runs
    assistant-error.log # stderr from runs
```

---

## Step 3: MCP configuration

The MCP config connects Claude to dbt/Redshift and Slack. The credentials are stored in the team's 1Password vault.

Ask the user: _"Do you have access to 1Password? Look for an entry called 'Claude MCP Config' (or ask your team lead). It contains a JSON block you'll need for this step."_

Once they have the JSON content:

> **Claude Code:** Ask the user to paste the JSON into the chat. Then write it directly to `~/.solv-assistant/mcp-config.json` using your write tool. Validate it by running `jq . ~/.solv-assistant/mcp-config.json`.
>
> **Claude Chat:** Tell them to create the config file by running this command — but **replace the placeholder content** between the `EOF` markers with the actual JSON from 1Password:

```
cat << 'MCPEOF' > ~/.solv-assistant/mcp-config.json
PASTE_YOUR_1PASSWORD_JSON_HERE
MCPEOF
```

In practice, the JSON they paste should look like this structure (these are **placeholder values** — do NOT use them):

```json
{
  "mcpServers": {
    "dbt_remote_mcp": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://<your-dbt-instance>.us1.dbt.com/api/ai/v1/mcp/",
        "--header",
        "Authorization: token <YOUR_DBT_TOKEN>",
        "--header",
        "x-dbt-prod-environment-id: <PROD_ENV_ID>",
        "--header",
        "x-dbt-dev-environment-id: <DEV_ENV_ID>",
        "--header",
        "x-dbt-user-id: <YOUR_USER_ID>"
      ]
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "<YOUR_SLACK_BOT_TOKEN>",
        "SLACK_TEAM_ID": "T0PQQNE1G"
      }
    }
  }
}
```

Note: The Slack team ID `T0PQQNE1G` is the same for everyone at Solv.

After they create the file, verify the JSON is valid:

```
jq . ~/.solv-assistant/mcp-config.json
```

**What to expect:** The JSON printed back nicely formatted. If they see an error like `parse error`, the JSON is malformed — ask them to paste what they put in the file so you can help fix it.

**Common issue:** Sometimes copying from 1Password adds invisible characters or line breaks. If `jq` fails, have them try opening the file to inspect it:

```
cat ~/.solv-assistant/mcp-config.json
```

Ask them to paste the output so you can spot the issue.

---

## Step 4: Schedule configuration

Ask the user two questions:
1. _"What time do you want your assistant to run each day?"_ (e.g., 9:00 AM)
2. _"What timezone are you in?"_

Common timezones:
- `America/New_York` (Eastern)
- `America/Chicago` (Central)
- `America/Denver` (Mountain)
- `America/Los_Angeles` (Pacific)

Then create the config file with the values filled in based on their answers:

> **Claude Code:** Write the JSON directly to `~/.solv-assistant/config.json` using your write tool, substituting their preferred values.
>
> **Claude Chat:** Give them this command, with the values filled in. For example, for 9:00 AM Eastern:

```
cat << 'EOF' > ~/.solv-assistant/config.json
{
  "schedule_hour": 9,
  "schedule_minute": 0,
  "schedule_timezone": "America/New_York",
  "model": "opus",
  "skills_repo": "~/skills",
  "pull_skills_before_run": true
}
EOF
```

Adjust `schedule_hour` (0-23, 24-hour format), `schedule_minute` (0-59), and `schedule_timezone` to match what the user wants.

Verify:

```
jq . ~/.solv-assistant/config.json
```

**What to expect:** The JSON printed back. If they want to change the time later, they can re-run this command with new values — no restart needed.

---

## Step 5: Prompt template

This is the most important file — it tells the assistant what to do each day.

First, create a starter template with the content below.

> **Claude Code:** Write this content directly to `~/.solv-assistant/prompt.md` using your write tool.
>
> **Claude Chat:** Give the user this command:

```
cat << 'PROMPTEOF' > ~/.solv-assistant/prompt.md
# Daily Assistant Prompt

## Available MCP Tools

You have access to the following tools via MCP:

- **dbt_remote_mcp** — `execute_sql` tool for running Redshift SQL queries against Solv's dbt models
- **slack** — `slack_send_message` tool for posting messages to Slack channels

## Task

<!-- REPLACE THIS SECTION with your specific daily task. Examples:

1. Query yesterday's key metrics from dbt and post a summary to #your-channel
2. Run a daily health check on a set of SQL queries and alert on anomalies
3. Generate a daily digest of data from multiple tables and post to Slack

Be specific about:
- What SQL queries to run (tables, filters, date ranges)
- How to interpret/format the results
- Which Slack channel to post to (use channel ID, e.g., C0ADW386TT8)
- What the message should look like
-->

Describe your task here. Be as specific as possible about what data to query, how to analyze it, and where to post the results.

## Slack Channel

Post results to channel ID: `CXXXXXXXXXX`

<!-- Find your channel ID: open Slack in a browser, navigate to the channel,
     and the ID is the last segment of the URL (starts with C). -->

## Skill Reference (Optional)

<!-- If your task uses a skill from the skills repo, uncomment the line below
     and update the path. The assistant will read the skill file and include
     it as context for the run.

Use the skill at: ~/skills/analytics/analysis-skills/your-skill.md
-->

## Output Format

Format the Slack message using Slack mrkdwn syntax:
- Use `*bold*` for headers and key metrics
- Use ``` for code blocks and booking IDs
- Use bullet points for lists
- Keep the message concise but actionable

## Important Notes

- Use the `dbt_remote_mcp` `execute_sql` tool for all SQL queries (Redshift dialect)
- Use the `slack_send_message` tool to post the report
- If any query fails, still post whatever data you have with a note about the failure
- Do NOT ask for user confirmation — this runs autonomously
PROMPTEOF
```

Tell the user: _"This created a template prompt. You'll customize it in Step 9 after we finish the setup and verify everything works. For now, we'll use a simple test prompt."_

**How to find a Slack channel ID:** Tell the user to open Slack in their web browser, navigate to the channel they want to post to, and look at the URL — the channel ID is the last segment (starts with `C`, like `C0ADW386TT8`).

---

## Step 6: Create `run.sh`

Create the main execution script with the content below, then make it executable with `chmod +x ~/.solv-assistant/run.sh`.

> **Claude Code:** Write this content directly to `~/.solv-assistant/run.sh` using your write tool, then run `chmod +x ~/.solv-assistant/run.sh`.
>
> **Claude Chat:** Tell the user to run this command to create the script:

```
cat << 'RUNEOF' > ~/.solv-assistant/run.sh
#!/bin/bash
# ==============================================================================
# Solv Daily Assistant - Main Execution Script
# Reads prompt.md, optionally loads a referenced skill, and runs Claude CLI.
# ==============================================================================

set -euo pipefail

# Ensure PATH includes claude and npx for headless execution
export PATH="${HOME}/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

ASSISTANT_DIR="${HOME}/.solv-assistant"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "${LOG_PREFIX} Starting daily assistant..."

# ---------- Read configuration ----------
CONFIG_FILE="${ASSISTANT_DIR}/config.json"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "${LOG_PREFIX} ERROR: Config file not found at ${CONFIG_FILE}"
  exit 1
fi

MODEL=$(jq -r '.model // "opus"' "${CONFIG_FILE}")
SKILLS_REPO=$(jq -r '.skills_repo // "~/skills"' "${CONFIG_FILE}")
SKILLS_REPO="${SKILLS_REPO/#\~/$HOME}"
PULL_SKILLS=$(jq -r '.pull_skills_before_run // true' "${CONFIG_FILE}")

# ---------- MCP config ----------
MCP_CONFIG="${ASSISTANT_DIR}/mcp-config.json"

if [[ ! -f "${MCP_CONFIG}" ]]; then
  echo "${LOG_PREFIX} ERROR: MCP config not found at ${MCP_CONFIG}"
  exit 1
fi

# ---------- Optionally pull latest skills ----------
if [[ "${PULL_SKILLS}" == "true" ]] && [[ -d "${SKILLS_REPO}/.git" ]]; then
  echo "${LOG_PREFIX} Pulling latest skills..."
  git -C "${SKILLS_REPO}" pull --ff-only origin main 2>&1 || echo "${LOG_PREFIX} WARNING: git pull failed, using local copy"
fi

# ---------- Read prompt ----------
PROMPT_FILE="${ASSISTANT_DIR}/prompt.md"

if [[ ! -f "${PROMPT_FILE}" ]]; then
  echo "${LOG_PREFIX} ERROR: Prompt file not found at ${PROMPT_FILE}"
  exit 1
fi

PROMPT_CONTENT=$(cat "${PROMPT_FILE}")

# ---------- Load referenced skill (if any) ----------
SKILL_PATH=$(echo "${PROMPT_CONTENT}" | sed -n 's/^Use the skill at: *//p' | head -1)

if [[ -n "${SKILL_PATH}" ]]; then
  SKILL_PATH="${SKILL_PATH/#\~/$HOME}"
  if [[ -f "${SKILL_PATH}" ]]; then
    echo "${LOG_PREFIX} Loading skill from ${SKILL_PATH}..."
    SKILL_CONTENT=$(cat "${SKILL_PATH}")
    PROMPT_CONTENT="${PROMPT_CONTENT}

<skill-reference>
${SKILL_CONTENT}
</skill-reference>"
  else
    echo "${LOG_PREFIX} WARNING: Referenced skill not found at ${SKILL_PATH}, continuing without it"
  fi
fi

# ---------- Execute ----------
echo "${LOG_PREFIX} Running Claude CLI with model=${MODEL}..."

claude -p \
  --model "${MODEL}" \
  --mcp-config "${MCP_CONFIG}" \
  --permission-mode bypassPermissions \
  "${PROMPT_CONTENT}"

EXIT_CODE=$?

echo "${LOG_PREFIX} Claude CLI exited with code ${EXIT_CODE}"
exit ${EXIT_CODE}
RUNEOF
```

Then make it executable:

```
chmod +x ~/.solv-assistant/run.sh
```

Verify:

```
ls -la ~/.solv-assistant/run.sh
```

**What to expect:** The file should show `-rwxr-xr-x` permissions (the `x` means executable).

---

## Step 7: Create `scheduler.sh`

Create the scheduler script with the content below, then make it executable with `chmod +x ~/.solv-assistant/scheduler.sh`.

> **Claude Code:** Write this content directly to `~/.solv-assistant/scheduler.sh` using your write tool, then run `chmod +x ~/.solv-assistant/scheduler.sh`.
>
> **Claude Chat:** Tell the user to run:

```
cat << 'SCHEDEOF' > ~/.solv-assistant/scheduler.sh
#!/bin/bash
# ==============================================================================
# Solv Daily Assistant - Scheduler
# Checks if it's time to run the daily assistant, then runs it.
# Designed for use with launchd StartInterval since StartCalendarInterval
# is unreliable on macOS 15.
#
# Uses a lock file to ensure the assistant only runs once per day.
# ==============================================================================

ASSISTANT_DIR="${HOME}/.solv-assistant"
CONFIG_FILE="${ASSISTANT_DIR}/config.json"
LOCK_FILE="${ASSISTANT_DIR}/.last-run"

# Ensure PATH includes jq for headless execution
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Config file not found at ${CONFIG_FILE}"
  exit 1
fi

# Read schedule from config
SCHEDULE_HOUR=$(jq -r '.schedule_hour // 9' "${CONFIG_FILE}")
SCHEDULE_MIN=$(jq -r '.schedule_minute // 0' "${CONFIG_FILE}")
SCHEDULE_TZ=$(jq -r '.schedule_timezone // "America/New_York"' "${CONFIG_FILE}")

# Get current time in the target timezone
CURRENT_HOUR=$(TZ="${SCHEDULE_TZ}" date "+%H")
CURRENT_MIN=$(TZ="${SCHEDULE_TZ}" date "+%M")
TODAY=$(TZ="${SCHEDULE_TZ}" date "+%Y-%m-%d")

# Check if we already ran today
if [[ -f "${LOCK_FILE}" ]] && [[ "$(cat "${LOCK_FILE}")" == "${TODAY}" ]]; then
  exit 0
fi

# Check if it's time (allow a 5-minute window)
if [[ "${CURRENT_HOUR#0}" -eq "${SCHEDULE_HOUR}" ]] && \
   [[ "${CURRENT_MIN#0}" -ge "${SCHEDULE_MIN}" ]] && \
   [[ "${CURRENT_MIN#0}" -lt $((SCHEDULE_MIN + 5)) ]]; then

  # Mark as run for today
  echo "${TODAY}" > "${LOCK_FILE}"

  # Run the actual assistant
  exec "${ASSISTANT_DIR}/run.sh"
fi
SCHEDEOF
```

Then make it executable:

```
chmod +x ~/.solv-assistant/scheduler.sh
```

Verify both scripts exist and are executable:

```
ls -la ~/.solv-assistant/*.sh
```

**What to expect:** Both `run.sh` and `scheduler.sh` should show `-rwxr-xr-x` permissions.

---

## Step 8: Create launchd plist and load

> **Claude Code:** Run `whoami` and `echo $HOME` to get the username and home path, then write the plist file directly and run the `launchctl load` command. No need to ask the user for these values.
>
> **Claude Chat:** Walk through the commands below one at a time.

First, get the username. Tell the user to run:

```
whoami
```

**What to expect:** Their macOS username (e.g., `jsmith`). You'll need this for the next command.

Then get their home directory:

```
echo $HOME
```

**What to expect:** Something like `/Users/jsmith`.

Now give them the plist creation command, with `<username>` replaced by their actual username and `<HOME>` replaced by their actual home directory path. For example, if username is `jsmith` and home is `/Users/jsmith`:

```
cat << 'PLISTEOF' > ~/Library/LaunchAgents/com.solv.assistant.jsmith.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.solv.assistant.jsmith</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/jsmith/.solv-assistant/scheduler.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>/Users/jsmith/.solv-assistant/logs/assistant.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jsmith/.solv-assistant/logs/assistant-error.log</string>
</dict>
</plist>
PLISTEOF
```

**IMPORTANT:** You must substitute the actual username and home path into this command before giving it to the user. Do NOT give them the version with `<username>` and `<HOME>` placeholders — that will create a broken plist.

Load the agent:

```
launchctl load ~/Library/LaunchAgents/com.solv.assistant.<username>.plist
```

(Again, replace `<username>` with their actual username in the command you give them.)

Verify it's loaded:

```
launchctl list | grep com.solv.assistant
```

**What to expect:** A line showing the agent with a PID or `-` and an exit status. Something like:

```
-    0    com.solv.assistant.jsmith
```

The `-` means it's not currently running (which is normal — it runs every 5 minutes briefly). The `0` means no errors.

**Common issues:**
- `"service already loaded"` — They may have loaded it before. Run `launchctl unload ~/Library/LaunchAgents/com.solv.assistant.<username>.plist` first, then load again.
- `"Could not find specified service"` — The plist file path or label has a typo. Have them run `cat ~/Library/LaunchAgents/com.solv.assistant.*.plist` to check the contents.
- Non-zero exit status (like `78`) — Usually means the scheduler script has an error. Check with `~/.solv-assistant/logs/assistant-error.log`.

---

## Step 9: Test run

Before relying on the scheduler, do a manual test. Ask the user for a Slack channel ID to test with, then overwrite the prompt with a simple test.

> **Claude Code:** Write the test prompt directly to `~/.solv-assistant/prompt.md` (substituting the real channel ID), then run `~/.solv-assistant/run.sh` and check the output.
>
> **Claude Chat:** Give the user this command (with the real channel ID substituted):

```
cat << 'TESTEOF' > ~/.solv-assistant/prompt.md
# Test Prompt

Send a test message to Slack channel CXXXXXXXXXX saying:
"Daily assistant test — setup complete! This message was sent automatically by the Solv daily assistant."

Do NOT ask for user confirmation — this runs autonomously.
TESTEOF
```

(Replace `CXXXXXXXXXX` with the user's actual channel ID before giving them this command.)

Now run the test:

```
~/.solv-assistant/run.sh
```

**What to expect:** Output like:

```
[2025-01-15 09:00:00] Starting daily assistant...
[2025-01-15 09:00:00] Running Claude CLI with model=opus...
... (Claude's response about sending the Slack message) ...
[2025-01-15 09:00:15] Claude CLI exited with code 0
```

Ask the user to check the Slack channel for the test message.

**If it works:** Tell them to now customize their prompt. They can re-run the Step 5 command with their real prompt content, or edit the file manually with any text editor:

```
open -e ~/.solv-assistant/prompt.md
```

(This opens the file in TextEdit.)

Then delete the lock file so the scheduler can run today:

```
rm -f ~/.solv-assistant/.last-run
```

**If the test fails**, troubleshoot based on the error:

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `command not found: claude` | PATH issue in run.sh | Have them run `which claude` and verify the path is included in run.sh's PATH export |
| `command not found: jq` | PATH issue | Have them run `which jq` and check it's in `/opt/homebrew/bin/` or `/usr/local/bin/` |
| `ERROR: Config file not found` | File wasn't created in an earlier step | Go back to the relevant step and recreate the file |
| `ERROR: MCP config not found` | mcp-config.json missing | Go back to Step 3 |
| `parse error` in output | JSON syntax error in a config file | Have them run `jq . ~/.solv-assistant/config.json` and `jq . ~/.solv-assistant/mcp-config.json` to find which file is broken |
| Claude auth error | Token expired | Run `claude login` and re-authenticate |
| MCP/Slack connection error | Bad Slack token or expired dbt token | Re-check credentials from 1Password, recreate mcp-config.json |
| `Permission denied` | Script not executable | Run `chmod +x ~/.solv-assistant/run.sh` |

If the user gets an error not listed here, ask them to paste the **full output** so you can diagnose it.

---

## Step 10: Customizing the prompt

Once the test works, help the user write their real daily prompt. Ask them:

1. _"What do you want the assistant to do each day?"_ (e.g., pull metrics, run a report, check data quality)
2. _"What SQL queries or dbt models are involved?"_
3. _"Which Slack channel should it post to?"_
4. _"What should the message format look like?"_

Then construct a customized version of the prompt template:

- **Claude Code:** Write the file directly to `~/.solv-assistant/prompt.md` using your write tool.
- **Claude Chat:** Give them the `cat << 'PROMPTEOF' > ~/.solv-assistant/prompt.md` command with their specific content.

### Editing the prompt later

- **Claude Code users:** They can start a Claude Code session and say _"help me update my daily assistant prompt at ~/.solv-assistant/prompt.md"_ — Claude Code will read and edit the file directly.
- **Claude Chat users:** They can edit the file with TextEdit (`open -e ~/.solv-assistant/prompt.md`), or come back to Claude Chat and say _"help me update my daily assistant prompt"_ — you can generate a new `cat` command for them.

### Using a skill from the skills repo

If the user's task matches an existing skill, they can reference it in their prompt by adding this line (uncommented) in the prompt file:

```
Use the skill at: ~/skills/analytics/analysis-skills/your-skill.md
```

To see available skills:

```
ls ~/skills/analytics/analysis-skills/
```

---

## Step 11: Managing the assistant

Give the user these commands as reference for common management tasks. Present them as needed, not all at once.

### Change the schedule

Edit the config — have them run a new `cat` command with updated values (reuse the Step 4 command format with new hour/minute/timezone). No restart needed since the scheduler re-reads config on every check.

### Force a re-run today

```
rm ~/.solv-assistant/.last-run
```

The scheduler will trigger the assistant within 5 minutes.

### Check if it ran today

```
cat ~/.solv-assistant/.last-run
```

If it shows today's date, it already ran.

### View recent logs

```
cat ~/.solv-assistant/logs/assistant.log
```

For errors:

```
cat ~/.solv-assistant/logs/assistant-error.log
```

### Stop the assistant

Tell the user to run (with their actual username):

```
launchctl unload ~/Library/LaunchAgents/com.solv.assistant.<username>.plist
```

### Restart the assistant

```
launchctl load ~/Library/LaunchAgents/com.solv.assistant.<username>.plist
```

### Uninstall completely

```
launchctl unload ~/Library/LaunchAgents/com.solv.assistant.$(whoami).plist
rm ~/Library/LaunchAgents/com.solv.assistant.$(whoami).plist
rm -rf ~/.solv-assistant
```

---

## Step 12: Troubleshooting Reference

Use this section to help users diagnose issues. Don't dump this all at once — use it reactively when the user reports a problem.

### "The assistant didn't run this morning"

Walk through these checks one at a time:

1. **Is launchd loaded?**
   ```
   launchctl list | grep com.solv.assistant
   ```
   If nothing shows up, the agent isn't loaded. Reload it (Step 8).

2. **Did it already run today?**
   ```
   cat ~/.solv-assistant/.last-run
   ```
   If it shows today's date, it ran (or tried to). Check the logs.

3. **Check the logs for errors:**
   ```
   cat ~/.solv-assistant/logs/assistant-error.log
   ```
   Ask the user to paste the output.

4. **Was the computer asleep at the scheduled time?**
   launchd will catch up when the Mac wakes, but only if the 5-minute window hasn't passed in the target timezone. If the user's Mac is frequently asleep at run time, suggest they adjust the schedule to a time when the Mac is typically awake and open.

### "Claude auth expired"

```
claude -p "Say AUTH_OK"
```

If it fails:

```
claude login
```

Complete the browser flow, then re-test.

### "MCP connection errors"

Ask the user to:
1. Check if their credentials in 1Password have been rotated
2. Recreate the mcp-config.json with fresh credentials (repeat Step 3)
3. Verify the JSON is valid: `jq . ~/.solv-assistant/mcp-config.json`

### "I see an error about permissions"

Scripts need to be executable:

```
chmod +x ~/.solv-assistant/run.sh ~/.solv-assistant/scheduler.sh
```

### "The Slack message didn't post"

1. Verify the channel ID is correct (starts with `C`, not `#channel-name`)
2. Check that the Slack bot has been added to the target channel
3. Test the Slack token: have them check 1Password for a fresh token

### "jq: command not found" in logs

The PATH in the scripts may not include Homebrew's bin directory. Have the user check:

```
which jq
```

If it's at an unexpected path, they may need to update the PATH export line in `scheduler.sh` and `run.sh` to include that directory.
