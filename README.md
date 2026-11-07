# 🚀 LeetCode Daily WhatsApp Bot

An automated Python assistant that delivers LeetCode's **Problem of the Day (POTD)** directly to your WhatsApp twice daily:
1. **Morning (10:30 AM IST):** Full problem statement, short summary, LLM-generated & verified optimal Python 3 solution, approach explanation, and Big-O time/space complexity.
2. **Evening (6:30 PM IST):** Gentle reminder with direct problem link, difficulty badge, and an LLM-generated conceptual hint (without spoiling the full solution).

---

## 📋 Features

- **Automated POTD Extraction:** Queries `https://leetcode.com/graphql` for active daily challenge, extracts example test cases and Python 3 starter code, and cleans HTML formatting.
- **LLM Solution Generator & Verifier:** Generates clean, commented Python 3 code using Google Gemini (or Claude) and executes it against extracted test cases. Automatically retries up to 3 times feeding execution errors back to the LLM if an assertion or runtime error occurs.
- **Official Twilio WhatsApp API:** Built with the official `twilio` library using a swappable interface (`BaseWhatsAppSender`) to easily migrate to Meta WhatsApp Cloud API in the future.
- **Smart Message Splitting:** Automatically breaks long solutions into clean chunks (respecting WhatsApp's 1600-character limit) at line breaks so code snippets remain intact.
- **Duplicate Protection & Evening Reuse:** Persists daily status to `state.json` so the evening run reuses the morning data without re-fetching or re-billing LLM API calls.
- **Dual Triggering:** Automated GitHub Actions workflows with dual cron triggers (`0 5 * * *` and `0 13 * * *`), manual `workflow_dispatch`, and local CLI execution with `--dry-run`.

---

## 🏗️ Project Structure

```
leetcode-whatsapp-bot/
├── .github/
│   └── workflows/
│       └── daily.yml          # GitHub Actions dual cron workflow
├── .env.example               # Template for environment secrets
├── .gitignore                 # Excludes .env, caches, and venvs
├── requirements.txt           # Python package dependencies
├── leetcode.py                # LeetCode GraphQL fetcher & HTML cleaner
├── solver.py                  # LLM solver & testcase verification engine
├── whatsapp.py                # Official Twilio WhatsApp sender & message splitter
├── state.py                   # State persistence (state.json) & deduplication
├── main.py                    # CLI runner (--mode morning|evening, --dry-run)
└── README.md                  # Comprehensive setup & scheduling guide
```

---

## ⚙️ Step-by-Step Setup Guide

### 1. Join the Twilio WhatsApp Sandbox (Testing)

The official Twilio WhatsApp Sandbox lets you send and receive messages without waiting for business verification:

1. Sign up for a free account at [twilio.com](https://www.twilio.com/).
2. In the Twilio Console, navigate to **Messaging** ➔ **Try it out** ➔ **Send a WhatsApp message**.
3. You will see a Twilio Sandbox WhatsApp number (usually `+1 415 523 8886`) and a unique code (e.g., `join silver-wolf`).
4. Open WhatsApp on your phone (`+917807221279`) and send the message `join <your-code>` to `+1 415 523 8886`.
5. Twilio will reply with a confirmation message: *"You are all set! The sandbox is ready to use."*
6. Copy your **Account SID** and **Auth Token** from your [Twilio Console Dashboard](https://console.twilio.com/).

> [!NOTE]
> The sandbox session stays active for 72 hours and automatically renews whenever you send any message back to the sandbox number.

---

### 2. Obtain Your LLM API Key

- **Google Gemini (Default & Recommended):**
  1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
  2. Click **Create API Key**.
  3. Copy your key into `GEMINI_API_KEY`.
- **Optional - Anthropic Claude:**
  1. Obtain an API key from [Anthropic Console](https://console.anthropic.com/).
  2. Set `LLM_PROVIDER=claude` and `ANTHROPIC_API_KEY=your_key`.

---

### 3. Local Installation & Configuration

1. Clone or navigate to the project directory:
   ```bash
   cd leetcode-whatsapp-bot
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. Create your `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your credentials:
   ```env
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL=gemini-2.5-flash
   LLM_PROVIDER=gemini

   TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   TO_WHATSAPP_NUMBER=whatsapp:+917807221279
   ```

---

## 🧪 Local Dry-Run Testing

The `--dry-run` flag prints the exact formatted WhatsApp messages directly to your terminal without calling the Twilio API or incurring charges:

```bash
# Test Morning Mode (Problem + Explanation + Complexity + Verified Code)
python main.py --mode morning --dry-run

# Test Evening Mode (Reminder + Link + Conceptual Hint)
python main.py --mode evening --dry-run

# Bypass duplicate protection during testing:
python main.py --mode morning --dry-run --force
```

---

## ☁️ GitHub Actions Automated Scheduling

The repository includes a production-ready workflow at [`.github/workflows/daily.yml`](.github/workflows/daily.yml) configured with two cron schedules.

### Configure GitHub Repository Secrets

Go to your GitHub repository ➔ **Settings** ➔ **Secrets and variables** ➔ **Actions** ➔ **New repository secret**, and add:

| Secret Name | Description | Example Value |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `4a8f...` |
| `TWILIO_WHATSAPP_NUMBER` | Sandbox sender number | `whatsapp:+14155238886` |
| `TO_WHATSAPP_NUMBER` | Your personal phone | `whatsapp:+917807221279` |

### Enable Repository Write Permissions

To allow GitHub Actions to commit `state.json` back to the repository so the evening job can reuse morning data:
1. Go to **Settings** ➔ **Actions** ➔ **General**.
2. Under **Workflow permissions**, select **Read and write permissions**.
3. Click **Save**.

---

## ⏰ Schedule & Time Conversion Reference

GitHub Actions runs on **UTC (Coordinated Universal Time)**.
Indian Standard Time (IST) is **UTC + 5 hours 30 minutes**.

$$\text{UTC Time} = \text{IST Time} - 5:30$$

| Event | Time in IST | Time in UTC | GitHub Actions Cron |
| :--- | :--- | :--- | :--- |
| **Morning Solution** | **10:30 AM IST** | **05:00 UTC** | `0 5 * * *` |
| **Evening Reminder** | **06:30 PM IST** | **13:00 UTC** | `0 13 * * *` |
| Alternate Morning | 08:00 AM IST | 02:30 UTC | `30 2 * * *` |
| Alternate Morning | 09:00 AM IST | 03:30 UTC | `30 3 * * *` |
| Alternate Evening | 08:00 PM IST | 14:30 UTC | `30 14 * * *` |
| Alternate Evening | 09:30 PM IST | 16:00 UTC | `0 16 * * *` |

---

## 💻 Local Scheduling Alternatives

If you prefer to run the bot locally on your own machine rather than GitHub Actions:

### Option A: Windows Task Scheduler

You can schedule both times in Windows using PowerShell or the Task Scheduler UI:

```powershell
# 1. Schedule Morning Job at 10:30 AM IST
$ActionMorning = New-ScheduledTaskAction -Execute "python.exe" -Argument "main.py --mode morning" -WorkingDirectory "C:\path\to\leetcode-whatsapp-bot"
$TriggerMorning = New-ScheduledTaskTrigger -Daily -At 10:30AM
Register-ScheduledTask -TaskName "LeetCodeMorningWhatsApp" -Action $ActionMorning -Trigger $TriggerMorning -Description "Daily LeetCode Morning Solution"

# 2. Schedule Evening Job at 6:30 PM IST
$ActionEvening = New-ScheduledTaskAction -Execute "python.exe" -Argument "main.py --mode evening" -WorkingDirectory "C:\path\to\leetcode-whatsapp-bot"
$TriggerEvening = New-ScheduledTaskTrigger -Daily -At 6:30PM
Register-ScheduledTask -TaskName "LeetCodeEveningWhatsApp" -Action $ActionEvening -Trigger $TriggerEvening -Description "Daily LeetCode Evening Reminder"
```

### Option B: Linux / macOS Crontab

On Linux or macOS (assuming system timezone is set to IST):

```bash
crontab -e
```

Add these entries:
```cron
# Morning at 10:30 AM IST
30 10 * * * cd /path/to/leetcode-whatsapp-bot && /path/to/venv/bin/python main.py --mode morning >> /path/to/cron.log 2>&1

# Evening at 6:30 PM IST
30 18 * * * cd /path/to/leetcode-whatsapp-bot && /path/to/venv/bin/python main.py --mode evening >> /path/to/cron.log 2>&1
```

---

## 🛡️ Error Handling & Fallbacks

- **LeetCode Outages / Premium Problems:** If LeetCode is down or today's problem is locked behind a paywall, the bot logs the error and sends a short WhatsApp alert notification.
- **Code Verification Retries:** If the LLM generates a solution that fails the example test cases, the exact error is fed back to the LLM to self-heal and re-solve up to 3 times.
- **Evening Resiliency:** If the morning job failed or `state.json` is missing, the evening job automatically falls back to re-fetching the question and sends the reminder link and hint without crashing.
