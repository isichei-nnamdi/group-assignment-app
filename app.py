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

# ---- 1. single helper that returns an *already‑authorised* client ---
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    return gspread.service_account_from_dict(
        st.secrets["google_service_account"], scopes=scopes
    )

try:
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
        # eligible_df["Display"] = eligible_df["fullname"] + " (" + eligible_df["email"] + ")"
        # display_to_name = dict(zip(eligible_df["Display"], eligible_df["fullname"]))
        # display_to_email = dict(zip(eligible_df["Display"], eligible_df["email"]))
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



        # current_display = eligible_df[eligible_df["email"] == current_email]["Display"].values[0]
        # student_options = eligible_df["Display"].tolist()
        # if current_display not in student_options:
        #     student_options.insert(0, current_display)

        # def format_option(option):
        #     return f"✅ {option} (You)" if option == current_display else option

        # selected_display = st.multiselect(
        #     "Choose 3–15 students (you must be part of your own group)",
        #     options=student_options,
        #     default=[current_display],
        #     format_func=format_option
        # )

        # if current_display not in selected_display:
        #     st.warning("You must be part of your group. We've re-added you.")
        #     selected_display = [current_display] + [opt for opt in selected_display if opt != current_display]

        # Filter eligible_df to only those in valid_emails
        valid_df = eligible_df[eligible_df["email"].isin(valid_emails)].copy()
        
        # Get selected names and emails
        selected_names = valid_df["fullname"].tolist()
        selected_emails = valid_df["email"].tolist()

        # selected_names = [display_to_name[item] for item in selected_display]
        # selected_emails = [display_to_email[item] for item in selected_display]

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

            # Reload latest group data before final validation
            try:
                latest_data = st.session_state.groups_ws.get_all_values()
            except Exception as e:
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
    col1, col2, col3 = st.columns([1, 5, 1])

    with col2:
        st.subheader("👩‍💼 Admin Panel")
        admin_tabs = st.tabs(["📋 View Groups", "⬇️ Download", "❌ Delete Group", "📝 Grade Submissions"]) #"👥 View & Assign",

        with admin_tabs[0]:
            st.markdown("### 🔍 Filter and View Groups")

            if st.session_state.groups_df.empty:
                st.info("No groups created yet.")
            else:
                # Extract unique values for filters
                faculty_options = st.session_state.groups_df["faculty"].dropna().unique().tolist()
                selected_faculty = st.selectbox("Select Faculty", faculty_options)

                dept_options = st.session_state.groups_df[
                    st.session_state.groups_df["faculty"] == selected_faculty
                ]["department"].dropna().unique().tolist()
                selected_department = st.selectbox("Select Department", dept_options)

                course_options = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department)
                ]["course"].dropna().unique().tolist()
                selected_course = st.selectbox("Select Course", course_options)

                # Filter groups based on selections
                filtered_groups = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department) &
                    (st.session_state.groups_df["course"] == selected_course)
                ]

                if filtered_groups.empty:
                    st.warning("No groups found for this selection.")
                else:
                    st.success(f"Displaying groups for: {selected_faculty} > {selected_department} > {selected_course}")
                    st.dataframe(filtered_groups)

        with admin_tabs[1]:
            st.markdown("### ⬇️ Download Groups")

            if st.session_state.groups_df.empty:
                st.info("No groups created yet.")
            else:
                # Filter dropdowns
                faculty_options = st.session_state.groups_df["faculty"].dropna().unique().tolist()
                selected_faculty = st.selectbox("Select Faculty", faculty_options, key="dl_faculty")

                dept_options = st.session_state.groups_df[
                    st.session_state.groups_df["faculty"] == selected_faculty
                ]["department"].dropna().unique().tolist()
                selected_department = st.selectbox("Select Department", dept_options, key="dl_department")

                course_options = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department)
                ]["course"].dropna().unique().tolist()
                selected_course = st.selectbox("Select Course", course_options, key="dl_course")

                # Apply filtering
                filtered_groups = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department) &
                    (st.session_state.groups_df["course"] == selected_course)
                ]

                if filtered_groups.empty:
                    st.warning("No data available for download.")
                else:
                    csv = filtered_groups.to_csv(index=False).encode('utf-8')
                    st.success("Filtered group data ready for download.")
                    st.download_button("Download Filtered CSV", data=csv, file_name="filtered_groups.csv", mime="text/csv")


        with admin_tabs[2]:
            st.markdown("### ❌ Delete a Group")

            if st.session_state.groups_df.empty:
                st.info("No groups created yet.")
            else:
                faculty_options = st.session_state.groups_df["faculty"].dropna().unique().tolist()
                selected_faculty = st.selectbox("Select Faculty", faculty_options, key="del_faculty")

                dept_options = st.session_state.groups_df[
                    st.session_state.groups_df["faculty"] == selected_faculty
                ]["department"].dropna().unique().tolist()
                selected_department = st.selectbox("Select Department", dept_options, key="del_department")

                course_options = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department)
                ]["course"].dropna().unique().tolist()
                selected_course = st.selectbox("Select Course", course_options, key="del_course")

                filtered_df = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department) &
                    (st.session_state.groups_df["course"] == selected_course)
                ]

                if filtered_df.empty:
                    st.warning("No groups found for this selection.")
                else:
                    group_names = filtered_df["group_name"].unique().tolist()
                    group_to_delete = st.selectbox("Select group to delete", group_names)

                    if st.button("Confirm Delete"):
                        # Clear and re-upload Google Sheet with group removed
                        all_rows = st.session_state.groups_ws.get_all_values()
                        headers = all_rows[0]
                        updated_rows = [row for row in all_rows if row[1] != group_to_delete]

                        st.session_state.groups_ws.clear()
                        st.session_state.groups_ws.append_row(headers)
                        for row in updated_rows[1:]:
                            st.session_state.groups_ws.append_row(row)

                        # Update local dataframe
                        st.session_state.groups_df = st.session_state.groups_df[
                            st.session_state.groups_df["group_name"] != group_to_delete
                        ]

                        st.success(f"✅ Group '{group_to_delete}' deleted successfully.")
                        st.rerun()

            
        # with admin_tabs[3]:
        #     st.markdown("### 👥 View Group Members & Assign Students")

        #     if st.session_state.groups_df.empty:
        #         st.info("No groups created yet.")
        #     else:
        #         # Filters for Faculty, Department, Course
        #         faculty_options = st.session_state.groups_df["faculty"].dropna().unique().tolist()
        #         selected_faculty = st.selectbox("Select Faculty", faculty_options, key="assign_faculty")

        #         dept_options = st.session_state.groups_df[
        #             st.session_state.groups_df["faculty"] == selected_faculty
        #         ]["department"].dropna().unique().tolist()
        #         selected_department = st.selectbox("Select Department", dept_options, key="assign_department")

        #         course_options = st.session_state.groups_df[
        #             (st.session_state.groups_df["faculty"] == selected_faculty) &
        #             (st.session_state.groups_df["department"] == selected_department)
        #         ]["course"].dropna().unique().tolist()
        #         selected_course = st.selectbox("Select Course", course_options, key="assign_course")

        #         # Filtered groups
        #         filtered_groups = st.session_state.groups_df[
        #             (st.session_state.groups_df["faculty"] == selected_faculty) &
        #             (st.session_state.groups_df["department"] == selected_department) &
        #             (st.session_state.groups_df["course"] == selected_course)
        #         ]

        #         group_names = filtered_groups["group_name"].unique().tolist()
        #         selected_group = st.selectbox("Select Group to View Members", group_names)

        #         group_members = filtered_groups[filtered_groups["group_name"] == selected_group]

        #         st.markdown(f"#### Members of **{selected_group}**")
        #         st.write(group_members)  # or process as a list if needed


                # # Load students_df to identify ungrouped students
                # students_df = st.session_state.students_df.copy()
                # grouped_matrics = st.session_state.groups_df["members"].unique().tolist()
                # ungrouped_df = students_df[~students_df["members"].isin(grouped_matrics)]

                # ungrouped_filtered = ungrouped_df[
                #     (ungrouped_df["faculty"] == selected_faculty) &
                #     (ungrouped_df["department"] == selected_department) &
                #     (ungrouped_df["course"] == selected_course)
                # ]

                # st.markdown("#### ➕ Assign Ungrouped Student to Selected Group")

                # # Always define selected_display first
                # selected_display = []

                # if ungrouped_filtered.empty:
                #     st.info("No ungrouped students available.")
                # else:
                #     # Mapping display name to matric number
                #     display_to_matric = {
                #         f"{row['First Name'].strip().title()} {row['Surname'].strip().title()} ({row['matric_no']})": row["matric_no"]
                #         for _, row in ungrouped_filtered.iterrows()
                #     }

                #     selected_display = st.multiselect("Select students to assign", list(display_to_matric.keys()))

                #     if selected_display:
                #         selected_matrics = [display_to_matric[item] for item in selected_display if item in display_to_matric]

                #         if st.button("Assign Selected Students to Group"):
                #             assigned = False
                #             for matric in selected_matrics:
                #                 student_row = ungrouped_filtered[ungrouped_filtered["matric_no"] == matric].iloc[0]

                #                 new_row = [
                #                     "",  # serial number
                #                     selected_group,
                #                     student_row["matric_no"],
                #                     student_row["First Name"],
                #                     student_row["Surname"],
                #                     student_row["email"],
                #                     student_row["faculty"],
                #                     student_row["department"],
                #                     student_row["course"]
                #                 ]

                #                 # Append to Google Sheet
                #                 st.session_state.groups_ws.append_row(new_row)

                #                 # Update local DataFrame
                #                 st.session_state.groups_df = pd.concat([st.session_state.groups_df, pd.DataFrame([{
                #                     "group_name": selected_group,
                #                     "matric_no": student_row["matric_no"],
                #                     "First Name": student_row["First Name"],
                #                     "Surname": student_row["Surname"],
                #                     "email": student_row["email"],
                #                     "faculty": student_row["faculty"],
                #                     "department": student_row["department"],
                #                     "course": student_row["course"]
                #                 }])], ignore_index=True)

                #                 assigned = True

                #             if assigned:
                #                 st.success("✅ Selected students have been added to the group.")
                #                 st.rerun()
        with admin_tabs[3]:
            st.markdown("### 📝 Grade Lab Submissions")

            try:
                # Load Labs sheet
                labs_ws = client.open_by_key(group_log_sheet_id).worksheet("Labs")
                labs_data = labs_ws.get_all_values()
        
                if len(labs_data) <= 1:
                    st.warning("⚠️ No labs found.")
                else:
                    labs_df = pd.DataFrame(labs_data[1:], columns=[col.strip() for col in labs_data[0]])
                    labs_df.columns = [
                        "Lab Name" if "lab" in c.lower() else "Course" if "course" in c.lower() else c
                        for c in labs_df.columns
                    ]
                    course_options = sorted(labs_df["Course"].dropna().unique())
                    selected_course = st.selectbox("Select Course", course_options, key="grade_admin_course")
        
                    lab_options = sorted(labs_df[labs_df["Course"].str.lower() == selected_course.lower()]["Lab Name"].dropna().unique())
                    if not lab_options:
                        st.warning("No labs available for this course.")
                    else:
                        selected_lab = st.selectbox("Select Lab", lab_options, key="grade_admin_lab")
        
                       # Load Submissions sheet
                        submissions_ws = client.open_by_key(group_log_sheet_id).worksheet("Submissions")
                        submissions_data = submissions_ws.get_all_values()
                        
                        # Create DataFrame with header row
                        group_df = pd.DataFrame(submissions_data[1:], columns=[col.strip() for col in submissions_data[0]])
                        
                        # Get list of unique group names from the 'group_name' column
                        if "group_name" in group_df.columns:
                            group_options = sorted(group_df[group_df["lab"] == selected_lab]["group_name"].unique())
                            selected_submission_group = st.selectbox("Select A Group to Grade", group_options, key="grade_admin_group")
                        else:
                            st.error("⚠️ 'group_name' column not found in the Submissions sheet.")

        
                        if len(submissions_data) <= 1:
                            st.info("No submissions found.")
                        else:
                            submissions_df = pd.DataFrame(submissions_data[1:], columns=submissions_data[0])
                            
                            filtered = submissions_df[
                                (submissions_df["course"].str.lower() == selected_course.lower()) &
                                (submissions_df["lab"].str.lower() == selected_lab.lower()) &
                                (submissions_df["group_name"].str.lower() == selected_submission_group.lower())
                            ]
        
                            if filtered.empty:
                                st.info("No submissions found for this lab.")
                            else:
                                for idx, row in filtered.iterrows():
                                    st.markdown("---")
                                    st.markdown(f"### 👥 Group: **{row['group_name']}**")
                                    st.markdown(f"👤 Submitted by: {row['submitted_by']}")
                                    st.markdown(f"📎 File: [{row['file_name']}]({row['file_link']})")
        
                                    file_ext = row['file_name'].split('.')[-1].lower()
                                    file_link = row['file_link']
        
                                    with st.expander("🔍 Preview File"):
                                        try:
                                            if file_ext == "pdf":
                                                st.components.v1.iframe(file_link.replace("/view?usp=sharing", "/preview"), height=600)
                                            elif file_ext in ["doc", "docx", "ppt", "pptx", "xls", "xlsx"]:
                                                try:
                                                    # Extract the file ID from the Drive link
                                                    file_id = file_link.split("/d/")[1].split("/")[0]
                                                    preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
                                                    st.components.v1.iframe(preview_url, height=600)
                                                except Exception as e:
                                                    st.warning(f"⚠️ Unable to preview the document: {e}")
                                            elif file_ext == "ipynb":
                                                try:
                                                    # Extract file ID from the drive link
                                                    file_id = file_link.split("/d/")[1].split("/")[0]
                                            
                                                    # Use Drive API to fetch file content
                                                    drive_service = build("drive", "v3", credentials=creds)
                                                    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
                                                    file_buffer = BytesIO()
                                                    downloader = MediaIoBaseDownload(file_buffer, request)
                                            
                                                    done = False
                                                    while not done:
                                                        _, done = downloader.next_chunk()
                                            
                                                    file_buffer.seek(0)
                                                    notebook_json = json.load(file_buffer)
                                            
                                                    st.markdown("#### 📘 Notebook Preview")
                                            
                                                    for cell in notebook_json.get("cells", []):
                                                        if cell["cell_type"] == "markdown":
                                                            st.markdown("".join(cell["source"]), unsafe_allow_html=True)
                                                        elif cell["cell_type"] == "code":
                                                            st.code("".join(cell["source"]), language="python")
                                                            if "outputs" in cell:
                                                                for output in cell["outputs"]:
                                                                    if output.get("output_type") == "stream":
                                                                        st.text("".join(output.get("text", "")))
                                                                    elif output.get("output_type") == "execute_result":
                                                                        text = output.get("data", {}).get("text/plain", "")
                                                                        if isinstance(text, list):
                                                                            text = "".join(text)
                                                                        st.text(text)
                                                except Exception as e:
                                                    st.error(f"⚠️ Notebook preview failed: {e}")
                        
                                                # file_id = file_link.split("/d/")[1].split("/")[0]
                                                # st.components.v1.iframe(f"https://drive.google.com/file/d/{file_id}/preview", height=600)
                                            elif file_ext == "py":
                                                import requests
                                                from google.auth.transport.requests import Request
                                            
                                                try:
                                                    # ➊ refresh token if needed
                                                    if not creds.valid:
                                                        creds.refresh(Request())
                                            
                                                    # ➋ extract file‑id
                                                    file_id = file_link.split("/d/")[1].split("/")[0]
                                            
                                                    # ➌ build download URL – note supportsAllDrives
                                                    download_url = (
                                                        f"https://www.googleapis.com/drive/v3/files/{file_id}"
                                                        "?alt=media&supportsAllDrives=true"
                                                    )
                                            
                                                    # ➍ authenticated GET
                                                    headers = {"Authorization": f"Bearer {creds.token}"}
                                                    r = requests.get(download_url, headers=headers, timeout=20)
                                            
                                                    if r.ok:
                                                        st.code(r.text, language="python")
                                                    else:
                                                        st.warning(
                                                            f"⚠️ Drive returned {r.status_code}. "
                                                            "Check that the file is shared with the service‑account "
                                                            "and that the ID is correct."
                                                        )
                                            
                                                except Exception as e:
                                                    st.error(f"⚠️ Error displaying .py file: {e}")
                                        except Exception as e:
                                            st.error(f"Error previewing file: {e}")
        
                                    score = st.text_input(f"Enter grade for {row['group_name']}", key=f"score_{idx}")
                                    if st.button(f"✅ Submit Grade for {row['group_name']}", key=f"submit_{idx}"):
                                        try:
                                            row_idx = idx + 2  # Adjust for header + 0-based index
                                            submissions_ws.update_cell(row_idx, submissions_df.columns.get_loc("graded") + 1, "Yes")
                                            submissions_ws.update_cell(row_idx, submissions_df.columns.get_loc("grade") + 1, score)
        
                                            grade_sheet_name = f"{selected_course}_{selected_lab}".replace(" ", "_")
                                            try:
                                                grade_ws = client.open_by_key(group_log_sheet_id).worksheet(grade_sheet_name)
                                            except:
                                                grade_ws = client.open_by_key(group_log_sheet_id).add_worksheet(grade_sheet_name, rows="1000", cols="10")
                                                grade_ws.append_row(["timestamp", "course", "lab", "group_name", "name", "email", "score"])
        
                                            group_students = st.session_state.groups_df[st.session_state.groups_df["group_name"] == row["group_name"]]

                                            # Check if group_students has multiple rows or just one with comma-separated names
                                            if group_students.shape[0] == 1 and "member_names" in group_students.columns and "," in group_students.iloc[0]["member_names"]:
                                                # Split comma-separated names and emails into lists
                                                names = [n.strip() for n in group_students.iloc[0]["member_names"].split(",")]
                                                emails = [e.strip() for e in group_students.iloc[0]["members"].split(",")]

                                                for name, email in zip(names, emails):
                                                    grade_ws.append_row([
                                                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                        selected_course,
                                                        selected_lab,
                                                        row['group_name'],
                                                        name,
                                                        email,
                                                        score
                                                    ])
                                                
                                            for _, student in group_students.iterrows():
                                                grade_ws.append_row([
                                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                    selected_course,
                                                    selected_lab,
                                                    row['group_name'],
                                                    student['member_names'],
                                                    student['members'],
                                                    score
                                                ])
        
                                            st.success(f"✅ Grade saved for {row['group_name']}")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Failed to grade: {e}")
        
            except Exception as e:
                st.error(f"🚫 Failed to load Labs or Submissions: {e}")

else:
    st.error("Unknown user role. Please contact administrator.")
    st.stop()



