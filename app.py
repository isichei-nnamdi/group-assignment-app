import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.exceptions import TransportError
import socket
import json
import time
from googleapiclient.discovery import build
import requests
from io import BytesIO
import logging
from datetime import timedelta
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request


st.set_page_config(
    page_title="CreateGroup",
    page_icon="favicon_io/favicon-16x16.png",
)

try:
    @st.cache_resource
    def get_gspread_client():
        return gspread.service_account_from_dict(st.secrets["google_service_account"])
    
    # Usage
    gc = get_gspread_client()
    client = gc

    creds = Credentials.from_service_account_info(
    st.secrets["google_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        ]
    )
    
    # ---- 2. grab the sheet ids once, keep them in session_state -------
    if "student_sheet_id" not in st.session_state:
        ss = st.secrets["google_service_account"]
        st.session_state.student_sheet_id   = ss["student_sheet_id"]
        st.session_state.group_log_sheet_id = ss["group_log_sheet_id"]
        st.session_state.dev_email          = ss["developer_email"]
        st.session_state.dev_password       = ss["developer_password"]

    student_sheet_id   = st.session_state.student_sheet_id
    group_log_sheet_id = st.session_state.group_log_sheet_id
    developer_email = st.session_state.dev_email
    developer_password = st.session_state.dev_password

    # ---- 3. cached loaders (10 min) -----------------------------------
    @st.cache_data(ttl=600)
    def load_df(key: str, worksheet: str) -> pd.DataFrame:
        """Generic helper – returns an empty DF if worksheet is empty."""
        ws   = gc.open_by_key(key).worksheet(worksheet)
        data = ws.get_all_values()
        if len(data) <= 1:      # header row only
            return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=[c.strip() for c in data[0]])
        return df

    @st.cache_data(ttl=600)
    def load_groups_ws_and_df():
        sht  = gc.open_by_key(group_log_sheet_id)
        try:
            ws = sht.worksheet("groups")
        except gspread.exceptions.WorksheetNotFound:
            ws = sht.add_worksheet("groups", rows=1000, cols=12)
        df = load_df(group_log_sheet_id, "groups")
        return ws, df

    # ---- 4. put every table you need into session_state ---------------
    if "students_df" not in st.session_state:
        df = load_df(student_sheet_id, "Enrolled Students")
        if not df.empty:
            df["email"]      = df["email"].str.strip().str.lower()
            df["student_id"] = df["student_id"].astype(str).str.strip()
        st.session_state.students_df = df

    if "login_df" not in st.session_state:
        df = load_df(group_log_sheet_id, "Login_details")
        if not df.empty:
            df["Email"]    = df["Email"].str.strip().str.lower()
            df["Password"] = df["Password"].astype(str).str.strip()
        st.session_state.login_df = df

    if "groups_ws" not in st.session_state or "groups_df" not in st.session_state:
        ws, df = load_groups_ws_and_df()
        st.session_state.groups_ws  = ws
        st.session_state.groups_df  = df

    if "course_list" not in st.session_state:
        course_df = load_df(group_log_sheet_id, "course_list")
        st.session_state.course_list = sorted(course_df.iloc[:, 0].dropna().unique())

except (gspread.exceptions.APIError,
        socket.gaierror,
        TransportError,
        Exception) as e:
    st.error(
        f"""
🚫 **Connection Error**

We couldn't connect to Google Sheets / Drive.  
Please check your internet connection or try again later.

**Details:** `{e}`

If the issue persists, contact the app administrator.
"""
    )
    st.stop()

# ========== Session Defaults ==========
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.user_role = None

# ========== Authentication ==========
def authenticate(email, password):
    email = email.strip().lower()
    password = str(password).strip()
    student_match = st.session_state.students_df[
        (st.session_state.students_df["email"] == email) &
        (st.session_state.students_df["student_id"] == password)
    ]
    admin_match = st.session_state.login_df[
        (st.session_state.login_df["Email"] == email) &
        (st.session_state.login_df["Password"] == password)
    ]

    if not student_match.empty:
        st.session_state.authenticated = True
        st.session_state.user_email = email
        st.session_state.user_role = "student"
        st.session_state.current_student = student_match.iloc[0]
        return True
    elif not admin_match.empty:
        st.session_state.authenticated = True
        st.session_state.user_email = email
        st.session_state.user_role = "admin"
        return True
    return False

# ========== Login ==========
col1, col2, col3 = st.columns([1, 5, 1])

with col2:
    if not st.session_state.authenticated:
        st.subheader("🔐 Login Required")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password (Student ID for students)", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            if authenticate(email, password):
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials")
        st.stop()

# ========== Logout Button ==========
st.sidebar.markdown(f"👤 Logged in as: **{st.session_state.user_email}**")
if st.sidebar.button("🚪 Logout"):
    for key in ["authenticated", "user_email", "user_role", "current_student"]:
        st.session_state.pop(key, None)
    st.rerun()

if st.session_state.user_role == "student":
    col1, col2, col3 = st.columns([1, 5, 1])
    with col2:
        st.subheader("🎓 Student Group Creator")

        df = st.session_state.students_df.copy()
        df['faculty'] = df['faculty'].str.strip().str.title()
        df['program'] = df['program'].str.strip().str.title()
        df["email"] = df["email"].astype(str).str.strip().str.lower()
        df["fullname"] = df["first_name"].str.strip().str.title() + " " + df["last_name"].str.strip().str.title()

        faculty = st.selectbox("Select Faculty", sorted(df['faculty'].dropna().unique()))
        department = st.selectbox("Select Department", sorted(df[df['faculty'] == faculty]['program'].dropna().unique()))
        selected_course = st.selectbox("Select Course", st.session_state.course_list)

        current_email = st.session_state.user_email.strip().lower()

        # Check if student has already created a group for the course
        existing = st.session_state.groups_df[
            (st.session_state.groups_df["created_by"].str.lower() == current_email) &
            (st.session_state.groups_df["course"].str.lower() == selected_course.lower())
        ] if not st.session_state.groups_df.empty else pd.DataFrame()

        if not existing.empty:
            st.warning("🚫 You have already created a group for this course.")
            # 🔍 Find your group info
            group_row = st.session_state.groups_df[
                (st.session_state.groups_df["course"].str.lower() == selected_course.lower()) &
                (st.session_state.groups_df["members"].str.lower().str.contains(current_email))
            ]
        
            if not group_row.empty:
                group_info = group_row.iloc[0].to_dict()
        
                from student_submission_page import student_submission_page

                student_submission_page(group_info, selected_course, current_email, client, group_log_sheet_id, creds)
        
                st.stop()
            else:
                st.warning("You are grouped, but group info couldn't be found.")
                st.stop()

        # Get all already grouped students
        already_grouped = []
        for _, row in st.session_state.groups_df.iterrows():
            if row["course"].strip().lower() == selected_course.strip().lower():
                already_grouped.extend([e.strip().lower() for e in row["members"].split(",")])

        if current_email in already_grouped:
            st.success("🎉 You are already in a group for this course.")
    
            # 🔍 Find your group info
            group_row = st.session_state.groups_df[
                (st.session_state.groups_df["course"].str.lower() == selected_course.lower()) &
                (st.session_state.groups_df["members"].str.lower().str.contains(current_email))
            ]
        
            if not group_row.empty:
                group_info = group_row.iloc[0].to_dict()
        
                from student_submission_page import student_submission_page
                student_submission_page(group_info, selected_course, current_email, client, group_log_sheet_id, creds)
        
                st.stop()
            else:
                st.warning("You are grouped, but group info couldn't be found.")
                st.stop()

        # Filter eligible students
        eligible_df = df[~df["email"].isin(already_grouped) | (df["email"] == current_email)].copy()
        eligible_emails_set = set(eligible_df["email"])
        current_fullname = eligible_df[eligible_df["email"] == current_email]["fullname"].values[0]
        
        st.write(f"Your email `{current_email}` has been added automatically.")

        # Let the user input a comma-separated list of emails
        email_input = st.text_area("Enter the emails of students to add to your group (comma-separated):")
        
        # Process the input
        input_emails = [email.strip().lower() for email in email_input.split(",") if email.strip()]
        input_emails = list(set(input_emails))  # Remove duplicates if any
        
        # Ensure current user's email is always included
        if current_email not in input_emails:
            input_emails.append(current_email)

        # Split valid and invalid emails
        valid_emails = [email for email in input_emails if email in eligible_emails_set]
        invalid_emails = [email for email in input_emails if email not in eligible_emails_set]
        
        # Inform user about invalid emails
        if invalid_emails:
            st.warning(f"The following emails are invalid or not eligible: {', '.join(invalid_emails)}")
            st.info(f"Valid emails so far: {', '.join(valid_emails)}")

        # Filter eligible_df to only those in valid_emails
        valid_df = eligible_df[eligible_df["email"].isin(valid_emails)].copy()
        
        # Get selected names and emails
        selected_names = valid_df["fullname"].tolist()
        selected_emails = valid_df["email"].tolist()

        group_name = st.text_input("Enter Group Name")

        if st.button("Create Group"):
            if current_email not in valid_emails:
                st.warning("You must be part of your own group. Your email has been re-added.")
                valid_emails.append(current_email)
                
            if len(selected_emails) < 3:
                st.warning("You must select at least 3 students.")
                st.stop()
            elif len(selected_emails) > 15:
                st.warning("You can't select more than 15 students.")
                st.stop()
            elif not group_name.strip():
                st.warning("Please provide a group name.")
                st.stop()

            def safe_get_all_values(ws, retries=3, delay=2):
                for attempt in range(retries):
                    try:
                        return ws.get_all_values()
                    except Exception as e:
                        if attempt < retries - 1:
                            time.sleep(delay)
                        else:
                            raise e
            # Reload latest group data before final validation
            try:
                latest_data = st.session_state.groups_ws.get_all_values()
            except Exception as e:
                # st.error("An unexpected error occurred.")
                # st.text(str(e))  # Optional: debug output for dev
                # logging.exception("Error while fetching data from Google Sheets.")
                # st.stop()
                logging.exception("Error while fetching data from Google Sheets.")
                st.error("We’re experiencing high activity right now. Please try again in a few minutes as multiple users are making requests at the same time.")
                st.stop()
            st.session_state.groups_df = pd.DataFrame(latest_data[1:], columns=latest_data[0]) if len(latest_data) > 1 else pd.DataFrame(columns=latest_data[0])
            existing_group_names = st.session_state.groups_df["group_name"].str.lower().tolist()

            if group_name.strip().lower() in existing_group_names:
                st.error("Group name already exists.")
                st.stop()


            # Recheck grouped members to ensure selected_emails are not in
            already_grouped = []
            for _, row in st.session_state.groups_df.iterrows():
                if row["course"].strip().lower() == selected_course.strip().lower():
                    already_grouped.extend([e.strip().lower() for e in row["members"].split(",")])

            duplicate_students = [email for email in selected_emails if email.lower() in already_grouped]
            if duplicate_students:
                st.error("🚫 One or more selected students are already in a group:\n" + "\n".join(f"- {e}" for e in duplicate_students))
                st.stop()

            # === Save group ===
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [
                timestamp, group_name, faculty, department, selected_course,
                ", ".join(selected_emails), ", ".join(selected_names), st.session_state.user_email
            ]

            if not latest_data:
                st.session_state.groups_ws.append_row(["timestamp", "group_name", "faculty", "department", "course", "members", "member_names", "created_by"])

            st.session_state.groups_ws.append_row(new_row)
    
            # Email each member
            for email, name in zip(selected_emails, selected_names):
                subject = f"[{selected_course}] You've been added to '{group_name}'"
                body = f"""
            Dear {name},
    
            You have been added to the group '{group_name}' for the course {selected_course}, created by {st.session_state.user_email}.
    
            Group Members:
            {chr(10).join(f"- {n} ({e})" for n, e in zip(selected_names, selected_emails))}
    
            Please collaborate with your teammates.
    
            Best regards,  
            
            Group Formation Support,
            School of Computing,
            Miva Open University
            """
                msg = MIMEMultipart()
                msg['From'] = "Group Formation Support"
                msg['To'] = email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))

                try:
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(developer_email, developer_password)
                    server.send_message(msg)
                    server.quit()
                except Exception as e:
                    st.warning(f"Failed to send email to {email}. Reason: {e}")

            st.success(f"✅ Group '{group_name}' created and notifications sent!")

            # 🔁 Load the latest group info for submission
            group_info = {
                "group_name": group_name,
                "members": ", ".join(selected_emails),
                "member_names": ", ".join(selected_names),
            }
            
            # ✅ Call the submission page
            from student_submission_page import student_submission_page
            student_submission_page(group_info, selected_course, current_email, client, group_log_sheet_id, creds)
            
            st.stop()

# ========== Admin Panel ==========
elif st.session_state.user_role == "admin":
    elif st.session_state.user_role == "admin":
    st.subheader("🛠 Admin Group Creation")

    df = st.session_state.students_df.copy()
    df['faculty'] = df['faculty'].str.strip().str.title()
    df['program'] = df['program'].str.strip().str.title()
    df["email"] = df["email"].astype(str).str.strip().str.lower()
    df["fullname"] = df["first_name"].str.strip().str.title() + " " + df["last_name"].str.strip().str.title()

    faculty = st.selectbox("Select Faculty", sorted(df['faculty'].dropna().unique()))
    department = st.selectbox("Select Department", sorted(df[df['faculty'] == faculty]['program'].dropna().unique()))
    selected_course = st.selectbox("Select Course", st.session_state.course_list)

    # Already grouped students for this course
    already_grouped = []
    for _, row in st.session_state.groups_df.iterrows():
        if row["course"].strip().lower() == selected_course.strip().lower():
            already_grouped.extend([e.strip().lower() for e in row["members"].split(",")])

    eligible_df = df.copy()  # Admin can pick anyone, but still highlight already grouped
    st.info(f"⚠ Students already grouped for this course will be flagged in red below.")

    email_input = st.multiselect(
        "Select students to add to the group",
        options=eligible_df["email"].tolist(),
        format_func=lambda x: f"{eligible_df.loc[eligible_df['email'] == x, 'fullname'].values[0]} ({x})"
                              + (" ❌" if x in already_grouped else "")
    )

    selected_names = [eligible_df.loc[eligible_df["email"] == email, "fullname"].values[0] for email in email_input]
    group_name = st.text_input("Enter Group Name")

    if st.button("✅ Create Group as Admin"):
        if len(email_input) < 3:
            st.warning("You must select at least 3 students.")
            st.stop()
        elif len(email_input) > 15:
            st.warning("You can't select more than 15 students.")
            st.stop()
        elif not group_name.strip():
            st.warning("Please provide a group name.")
            st.stop()

        # Reload sheet to prevent name conflicts
        latest_data = st.session_state.groups_ws.get_all_values()
        st.session_state.groups_df = pd.DataFrame(latest_data[1:], columns=latest_data[0]) if len(latest_data) > 1 else pd.DataFrame(columns=latest_data[0])
        existing_group_names = st.session_state.groups_df["group_name"].str.lower().tolist()

        if group_name.strip().lower() in existing_group_names:
            st.error("Group name already exists.")
            st.stop()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = [
            timestamp, group_name, faculty, department, selected_course,
            ", ".join(email_input), ", ".join(selected_names), st.session_state.user_email
        ]

        # Write to sheet
        if not latest_data:
            st.session_state.groups_ws.append_row(["timestamp", "group_name", "faculty", "department", "course", "members", "member_names", "created_by"])
        st.session_state.groups_ws.append_row(new_row)

        # Email notifications
        for email, name in zip(email_input, selected_names):
            subject = f"[{selected_course}] You've been added to '{group_name}'"
            body = f"""
        Dear {name},

        You have been added to the group '{group_name}' for the course {selected_course}, created by the Admin.

        Group Members:
        {chr(10).join(f"- {n} ({e})" for n, e in zip(selected_names, email_input))}

        Please collaborate with your teammates.

        Best regards,  
        Group Formation Support,
        School of Computing,
        Miva Open University
        """
            msg = MIMEMultipart()
            msg['From'] = "Group Formation Support"
            msg['To'] = email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            try:
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(st.session_state.dev_email, st.session_state.dev_password)
                server.send_message(msg)
                server.quit()
            except Exception as e:
                st.warning(f"Failed to send email to {email}. Reason: {e}")

        st.success(f"✅ Group '{group_name}' created successfully by Admin!")
else:
    st.error("Unknown user role. Please contact administrator.")
    st.stop()



