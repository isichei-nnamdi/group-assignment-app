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
# from student_submission_page import student_submission_page



st.set_page_config(
    page_title="CreateGroup",
    page_icon="favicon_io/favicon-16x16.png",
    # layout="wide"
)

try:
    # ========== Google Sheets Auth ==========
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Load credentials from secrets
    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=scope
    )
    
    client = gspread.authorize(creds)
    
    # Now safely access sheet IDs
    sheet_id = st.secrets["google_service_account"]["student_sheet_id"]
    
    # Access sheet IDs from secrets
    student_sheet_id = st.secrets["google_service_account"]["student_sheet_id"]
    group_log_sheet_id = st.secrets["google_service_account"]["group_log_sheet_id"]
    developer_email = st.secrets["google_service_account"]["developer_email"]
    developer_password = st.secrets["google_service_account"]["developer_password"]
    # folder_id = st.secrets["google_service_account"]["folder_id"]

    # ========== Load Data & Cache ==========
    def load_students_df():
        # ws = client.open_by_key(student_sheet_id).worksheet("UNDERGRADUATE")
        ws = client.open_by_key(student_sheet_id).worksheet("Enrolled Students")
        df = pd.DataFrame(ws.get_all_records())
        df["email"] = df["email"].str.strip().str.lower()
        df["student_id"] = df["student_id"].astype(str).str.strip()
        return df

    def load_login_df():
        ws = client.open_by_key(group_log_sheet_id).worksheet("Login_details")
        df = pd.DataFrame(ws.get_all_records())
        df["Email"] = df["Email"].str.strip().str.lower()
        df["Password"] = df["Password"].astype(str).str.strip()
        return df

    def load_groups_df():
        sheet = client.open_by_key(group_log_sheet_id)
        try:
            ws = sheet.worksheet("groups")
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title="groups", rows="1000", cols="10")
        df = pd.DataFrame(ws.get_all_records())
        return ws, df

    if "students_df" not in st.session_state:
        st.session_state.students_df = load_students_df()

    if "login_df" not in st.session_state:
        st.session_state.login_df = load_login_df()

    if "groups_ws" not in st.session_state or "groups_df" not in st.session_state:
        st.session_state.groups_ws, st.session_state.groups_df = load_groups_df()

    def load_course_list():
        course_ws = client.open_by_key(group_log_sheet_id).worksheet("course_list")
        return sorted(pd.Series(course_ws.col_values(1)).dropna().unique())

    if "course_list" not in st.session_state:
        st.session_state.course_list = load_course_list()
    
except (gspread.exceptions.APIError, socket.gaierror, TransportError, Exception) as e:
    st.error(
        f"""
    🚫 **Connection Error**

    We couldn't connect to the database or load required data. Please check your internet connection or try again later.

    **Details:** `{str(e)}`

    If the issue persists, contact the app administrator.
    """)
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
            # if st.button("🚪 Logout Now"):
            #     for key in ["authenticated", "user_email", "user_role", "current_student"]:
            #         st.session_state.pop(key, None)
            #     st.rerun()
            # st.stop()

        # Get all already grouped students
        already_grouped = []
        for _, row in st.session_state.groups_df.iterrows():
            if row["course"].strip().lower() == selected_course.strip().lower():
                already_grouped.extend([e.strip().lower() for e in row["members"].split(",")])

        if current_email in already_grouped:
            # st.warning("You have already been added to a group for this course and cannot create another.")
            # if st.button("Logout"):
            #     st.session_state.clear()
            #     st.rerun()
            # st.stop()
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
        eligible_df["Display"] = eligible_df["fullname"] + " (" + eligible_df["email"] + ")"
        display_to_name = dict(zip(eligible_df["Display"], eligible_df["fullname"]))
        display_to_email = dict(zip(eligible_df["Display"], eligible_df["email"]))

        current_display = eligible_df[eligible_df["email"] == current_email]["Display"].values[0]
        student_options = eligible_df["Display"].tolist()
        if current_display not in student_options:
            student_options.insert(0, current_display)

        def format_option(option):
            return f"✅ {option} (You)" if option == current_display else option

        selected_display = st.multiselect(
            "Choose 3–15 students (you must be part of your own group)",
            options=student_options,
            default=[current_display],
            format_func=format_option
        )

        if current_display not in selected_display:
            st.warning("You must be part of your group. We've re-added you.")
            selected_display = [current_display] + [opt for opt in selected_display if opt != current_display]

        selected_names = [display_to_name[item] for item in selected_display]
        selected_emails = [display_to_email[item] for item in selected_display]

        group_name = st.text_input("Enter Group Name")

        if st.button("Create Group"):
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
            latest_data = st.session_state.groups_ws.get_all_values()
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
            
            st.stop()  # prevent rerun since we're showing the submission page now
            # Clear group_df from cache and log out the student
            # del st.session_state.groups_df
            # for key in ["authenticated", "user_email", "user_role", "current_student"]:
            #     st.session_state.pop(key, None)
            # st.rerun()


# ========== Admin Panel ==========
elif st.session_state.user_role == "admin":
    col1, col2, col3 = st.columns([1, 5, 1])

    with col2:
        st.subheader("👩‍💼 Admin Panel")
        admin_tabs = st.tabs(["📋 View Groups", "⬇️ Download", "❌ Delete Group", "👥 View & Assign", "📝 Grade Submissions"])

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

            
        with admin_tabs[3]:
            st.markdown("### 👥 View Group Members & Assign Students")

            if st.session_state.groups_df.empty:
                st.info("No groups created yet.")
            else:
                # Filters for Faculty, Department, Course
                faculty_options = st.session_state.groups_df["faculty"].dropna().unique().tolist()
                selected_faculty = st.selectbox("Select Faculty", faculty_options, key="assign_faculty")

                dept_options = st.session_state.groups_df[
                    st.session_state.groups_df["faculty"] == selected_faculty
                ]["department"].dropna().unique().tolist()
                selected_department = st.selectbox("Select Department", dept_options, key="assign_department")

                course_options = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department)
                ]["course"].dropna().unique().tolist()
                selected_course = st.selectbox("Select Course", course_options, key="assign_course")

                # Filtered groups
                filtered_groups = st.session_state.groups_df[
                    (st.session_state.groups_df["faculty"] == selected_faculty) &
                    (st.session_state.groups_df["department"] == selected_department) &
                    (st.session_state.groups_df["course"] == selected_course)
                ]

                group_names = filtered_groups["group_name"].unique().tolist()
                selected_group = st.selectbox("Select Group to View Members", group_names)

                group_members = filtered_groups[filtered_groups["group_name"] == selected_group]

                st.markdown(f"#### Members of **{selected_group}**")
                # st.write("Group Members:")
                st.write(group_members)  # or process as a list if needed


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

        with admin_tabs[4]:
            st.markdown("### 📝 Grade Lab Submissions")

            # Load submission records
            try:
                submissions_ws = client.open_by_key(sheet_id).worksheet("Submissions")
                records = submissions_ws.get_all_values()
                submissions_df = pd.DataFrame(records[1:], columns=records[0])
            except:
                st.error("❌ Unable to load Submissions sheet.")
                # return

            # Load Labs sheet for course-lab relationship
            try:
                labs_ws = client.open_by_key(sheet_id).worksheet("Labs")
                labs_data = labs_ws.get_all_values()
                labs_df = pd.DataFrame(labs_data[1:], columns=labs_data[0])
                course_options = sorted(labs_df["Course"].dropna().unique())
            except:
                st.error("❌ Unable to load Labs sheet.")
                # return

            selected_course = st.selectbox("Select Course", course_options, key="grade_course")

            filtered_labs = labs_df[labs_df["Course"].str.lower() == selected_course.lower()]
            lab_options = sorted(filtered_labs["Lab Name"].dropna().unique())

            selected_lab = st.selectbox("Select Lab to Grade", lab_options, key="grade_lab")

            # Filter submissions for course & lab
            filtered_submissions = submissions_df[
                (submissions_df["course"].str.lower() == selected_course.lower()) &
                (submissions_df["lab"].str.lower() == selected_lab.lower())
            ]

            if filtered_submissions.empty:
                st.info("No submissions found for this course and lab.")
            else:
                for idx, row in filtered_submissions.iterrows():
                    st.markdown("---")
                    st.markdown(f"### Group: **{row['group_name']}**")
                    st.markdown(f"👤 Submitted by: {row['submitted_by']}")
                    st.markdown(f"📎 File: [{row['file_name']}]({row['file_link']})")

                    # Preview logic based on file extension
                    file_link = row['file_link']
                    file_ext = row['file_name'].lower().split('.')[-1]

                    if file_ext == "pdf":
                        preview_url = file_link.replace("/view?usp=sharing", "/preview")
                        st.components.v1.iframe(preview_url, height=600)
                    elif file_ext in ["doc", "docx", "ppt", "pptx", "xls", "xlsx"]:
                        st.components.v1.iframe(f"https://docs.google.com/gview?url={file_link}&embedded=true", height=600)
                    elif file_ext == "ipynb":
                        try:
                            import requests
                            response = requests.get(file_link)
                            notebook_content = response.json()
                            st.json(notebook_content)  # Basic display, can be enhanced
                        except:
                            st.error("Unable to fetch notebook content from Google Drive.")
                    elif file_ext == "py":
                        try:
                            import requests
                            content = requests.get(file_link).text
                            st.code(content, language="python")
                        except:
                            st.warning("Unable to preview .py file")
                    elif file_ext in ["png", "jpg", "jpeg", "gif"]:
                        st.image(file_link, caption=row['file_name'], use_column_width=True)
                    else:
                        st.info("⚠️ No preview available for this file type.")

                    # Grade input
                    score = st.text_input(f"Enter grade for {row['group_name']}", key=f"grade_{idx}")
                    if st.button(f"Submit Grade for {row['group_name']}", key=f"btn_grade_{idx}"):
                        try:
                            # Update the original Submissions sheet
                            submissions_ws.update_cell(idx + 2, submissions_df.columns.get_loc("graded") + 1, "Yes")
                            submissions_ws.update_cell(idx + 2, submissions_df.columns.get_loc("grade") + 1, score)

                            # Log the graded info in a new sheet
                            sheet_title = f"{selected_course}_{selected_lab}".replace(" ", "_")
                            try:
                                grade_ws = client.open_by_key(sheet_id).worksheet(sheet_title)
                            except:
                                grade_ws = client.open_by_key(sheet_id).add_worksheet(title=sheet_title, rows="1000", cols="10")
                                grade_ws.append_row(["timestamp", "course", "lab", "group_name", "name", "email", "score"])

                            group_students = st.session_state.groups_df[
                                st.session_state.groups_df["group_name"] == row['group_name']
                            ]
                            for _, student in group_students.iterrows():
                                grade_ws.append_row([
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    selected_course,
                                    selected_lab,
                                    row['group_name'],
                                    student["name"],
                                    student["email"],
                                    score
                                ])

                            st.success(f"✅ Grade saved for group {row['group_name']}.")
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error grading submission: {e}")
else:
    st.error("Unknown user role. Please contact administrator.")
    st.stop()



