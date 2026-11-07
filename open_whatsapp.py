import urllib.parse
import subprocess
import webbrowser

phone = "917807221279"
text = (
    "☀️ *LeetCode Problem of the Day*\n"
    "📅 2026-11-07\n\n"
    "📌 *1882. Process Tasks Using Servers* (🟡 *Medium*)\n"
    "🔗 https://leetcode.com/problems/process-tasks-using-servers/\n\n"
    "📝 *Summary:*\nAssign tasks to servers with minimum weight/index using two priority queues.\n\n"
    "💡 *Approach:* Maintain free servers (weight, idx) & busy servers (available_time, weight, idx).\n\n"
    "📊 *Complexity:* Time: O((m+n) log n) | Space: O(n+m)\n\n"
    "🛡️ *Status:* ✅ Verified with Example Tests"
)

url = f"https://api.whatsapp.com/send?phone={phone}&text={urllib.parse.quote(text)}"
print(f"Opening WhatsApp URL for {phone}...")
webbrowser.open(url)
print("WhatsApp Web/Desktop opened successfully!")
