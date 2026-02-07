🤖 TeamPulse – AI Stand-up & Progress Reporter

An AI-powered team productivity assistant that automates daily stand-ups, summarizes updates, detects risks, and delivers clean reports to Slack.

Built using Python, FastAPI, SQLModel, and AI-based text processing, this project focuses on workflow automation and team visibility.

🚀 Project Overview

TeamPulse simplifies the daily stand-up process for teams by automating update collection and reporting.

Instead of manual meetings or long message threads, team members submit their daily progress through an API or chat interface. The system intelligently processes these updates, identifies blockers or delays, and sends structured reports to Slack — both instantly and on a scheduled basis.

This project showcases AI-driven automation, backend development, NLP summarization, and scheduling systems.

✨ Key Features
Feature	Description
🤖 Intelligent Summary Generator	Converts multiple team updates into clear, concise summaries
⏰ Scheduled Reporting	Automatically sends a daily stand-up report every morning
🧍 Individual Update Tracking	Posts each team member’s update instantly
⚠️ Progress Risk Analysis	Identifies missing updates, repeated blockers, or stalled tasks
💬 Slack Notifications	Sends formatted messages directly to Slack channels
🧠 Data Storage	Stores all stand-up data securely using SQLite
🛠️ Scalable Design	Easy to extend with dashboards, analytics, or follow-up reminders
🏗️ System Architecture
User submits daily update
        ↓
FastAPI receives and validates input
        ↓
Data stored in database (SQLModel + SQLite)
        ↓
AI engine processes and summarizes updates
        ↓
Risk analysis checks for blockers or delays
        ↓
Formatted report sent to Slack (instant / scheduled)

🧰 Tech Stack

Backend: Python, FastAPI

AI / NLP: Large Language Models for text summarization

Database: SQLModel, SQLite

Automation: APScheduler

Messaging: Slack Webhooks

Environment Management: Python Virtual Environment

⚙️ Installation & Setup
1️⃣ Clone the Repository
git clone https://github.com/khushi-kukkar/teampulse-standup-reporter.git
cd teampulse-standup-reporter

2️⃣ Create a Virtual Environment
python -m venv venv


Activate it:

Windows

venv\Scripts\activate


macOS / Linux

source venv/bin/activate

3️⃣ Install Dependencies
pip install -r requirements.txt

4️⃣ Configure Environment Variables

Create a .env file in the root directory:

AI_API_KEY=your_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXXX/YYYY/ZZZZ


You can also copy from the example file:

cp .env.example .env

5️⃣ Run the Application
uvicorn main:app --reload


The server will start at:

http://127.0.0.1:8000

📌 Use Cases

Daily team stand-ups

Remote team progress tracking

Internship or academic project demonstrations

Productivity automation tools

🔮 Future Enhancements

Web dashboard for analytics

User authentication & roles

Reminder notifications for missing updates

Integration with tools like Notion or Email

👩‍💻 Author

Khushi Kukkar
Computer Science Student | Software Development Enthusiast
