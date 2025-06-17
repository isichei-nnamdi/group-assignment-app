# 🎓 MIVA Group Assignment App

This is a Streamlit web application designed for **students and admins** at Miva Open University to manage group assignments, view student data, and facilitate collaboration through an intuitive interface.

---

## 🚀 Features

- 🔐 Secure login for **Students** and **Admins**
- 📄 Google Sheets integration (Live database)
- 👨‍🎓 Student group creation and preview
- 🧑‍💼 Admin access for group management
- 🔍 Real-time filtering by faculty, department, and course
- 💾 Auto-saving to Google Sheets

---

## 🛠 Tech Stack

- [Streamlit](https://streamlit.io) – Python web UI
- [GSpread](https://gspread.readthedocs.io) – Google Sheets API
- [Pandas](https://pandas.pydata.org/) – Data handling
- [Google Service Account](https://cloud.google.com/iam/docs/service-accounts) – Authentication

---

## 📂 Setup Instructions

### 🔑 1. Add Google API Credentials

- Create a **Google Service Account** and download the JSON key (e.g., `my-miva-project-xxxx.json`).
- Share your Google Sheet with the service account email (`xxxxx@xxxxx.iam.gserviceaccount.com`) as **Editor**.

### 🧪 2. Create `.streamlit/secrets.toml`

```toml
student_sheet_id = "your_student_sheet_id"
group_log_sheet_id = "your_group_log_sheet_id"
