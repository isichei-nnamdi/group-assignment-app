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

# ========== Role-based View ==========
if st.session_state.user_role == "student":
    col1, col2, col3 = st.columns([1, 5, 1])

    with col2:
        st.subheader("🎓 Student Group Creator")

        # Clean fields
        df = st.session_state.students_df.copy()
        df['faculty'] = df['faculty'].str.strip().str.title()
        df['program'] = df['program'].str.strip().str.title()

        # ========== Group Creation (Student or Admin) ==========
        existing = pd.DataFrame()
        block_form = False  # flag to prevent group creation


        # === Step 1: Faculty & Department Selection ===
        faculty_list = sorted(df['faculty'].dropna().unique())
        faculty = st.selectbox("Select Faculty", faculty_list)

        dept_list = sorted(df[df['faculty'] == faculty]['program'].dropna().unique())
        department = st.selectbox("Select Department", dept_list)

        # === Step 2: Course Selection ===
        selected_course = st.selectbox("Select Course", st.session_state.course_list)


        # === Step 3: Prevent duplicate group creation by same student for same course ===
        if st.session_state.user_role == "student":
            if "created_by" in st.session_state.groups_df.columns and "course" in st.session_state.groups_df.columns:
                existing = st.session_state.groups_df[
                    (st.session_state.groups_df["created_by"].str.lower() == st.session_state.user_email.lower()) &
                    (st.session_state.groups_df["course"].str.lower() == selected_course.lower())
                ]
                if not existing.empty:
                    block_form = True # allow rendering but block action later
        # === Step 3: Prevent duplicate group creation by same student for same course ===
        # if st.session_state.user_role == "student":
        #     block_form = False  # Default state
        #     user_email = st.session_state.user_email.lower()
        
        #     # Prevent a user from creating more than one group per course
        #     if "created_by" in st.session_state.groups_df.columns and "course" in st.session_state.groups_df.columns:
        #         existing_group = st.session_state.groups_df[
        #             (st.session_state.groups_df["created_by"].str.lower() == user_email) &
        #             (st.session_state.groups_df["course"].str.lower() == selected_course.lower())
        #         ]
        #         if not existing_group.empty:
        #             st.warning("You have already created a group for this course.")
        #             block_form = True
        
        #     # Prevent any student from being added to more than one group per course
        #     if "members" in st.session_state.groups_df.columns and "course" in st.session_state.groups_df.columns:
        #         # Filter only the groups for the selected course
        #         course_groups = st.session_state.groups_df[
        #             st.session_state.groups_df["course"].str.lower() == selected_course.lower()
        #         ]
        
        #         # Flatten the list of all members for this course
        #         existing_members = set()
        #         for row in course_groups["members"].dropna():
        #             for matric in [m.strip().upper() for m in row.split(",")]:
        #                 existing_members.add(matric)
        
        #         # Check if any of the current inputs (matric numbers) are already in a group
        #         submitted_members = [m.strip().upper() for m in group_matric_list]  # your list from the form input
        
        #         duplicate_members = [m for m in submitted_members if m in existing_members]
        #         if duplicate_members:
        #             st.error(f"The following matric number(s) are already in another group for this course: {', '.join(duplicate_members)}")
        #             block_form = True



        # === Step 4: Remove already grouped students for the same course ===
        already_grouped = []
        if "members" in st.session_state.groups_df.columns and "course" in st.session_state.groups_df.columns:
            for _, row in st.session_state.groups_df.iterrows():
                if row["course"].strip().lower() == selected_course.strip().lower():
                    already_grouped.extend([m.strip().upper() for m in row["members"].split(",")])


        # Get current student's details
        if st.session_state.user_role == "student":
            current_student = st.session_state.current_student
            current_email = current_student['email'].strip().upper()
        else:
            current_student = None
            current_email = None



        # Filter: All students in selected dept, excluding already grouped (except current student)
        # filtered = df[
        #     (df['Faculty'] == faculty) &
        #     (df['Programme'] == department) &
        #     (~df['Matric Number'].astype(str).str.upper().isin(already_grouped) | (df['Matric Number'].astype(str).str.upper() == current_email))
        # ].copy()

        # # === Step 4: Clean names and emails ===
        # filtered["First Name"] = filtered["First Name"].str.strip().str.title()
        # filtered["Surname"] = filtered["Surname"].str.strip().str.title()
        # filtered["Matric Number"] = filtered["Matric Number"].astype(str).str.strip().str.upper()
        # filtered["MIVA Email"] = filtered["MIVA Email"].str.strip()

        # filtered["Display"] = filtered["First Name"] + " " + filtered["Surname"] + " (" + filtered["Matric Number"] + ")"

        # === Check if current student is already grouped ===
        if current_email in already_grouped:
            st.warning("You have already been added to a group for this course and cannot create another group.")
            st.markdown("---")
            if st.button("Logout"):
                st.session_state.clear()
                st.experimental_rerun()
        else:
            # === Filter: All students in selected dept, excluding already grouped (except current student) ===
            # filtered = df[
            #     (df['Faculty'] == faculty) &
            #     (df['Programme'] == department) &
            #     (~df['Matric Number'].astype(str).str.upper().isin(already_grouped) | (df['Matric Number'].astype(str).str.upper() == current_email))
            # ].copy()
            filtered = df[
                (~df['email'].astype(str).str.upper().isin(already_grouped) | (df['email'].astype(str).str.upper() == current_email))
            ].copy()
        
            # === Step 4: Clean names and emails ===
            filtered["first_name"] = filtered["first_name"].str.strip().str.title()
            filtered["last_name"] = filtered["last_name"].str.strip().str.title()
            filtered["email"] = filtered["email"].astype(str).str.strip().str.upper()
            filtered["email"] = filtered["email"].str.strip()
            filtered["Display"] = filtered["fullname"] + " (" + filtered["email"] + ")"

            # === Step 5: Add mappings for multiselect ===
            # display_to_matric = dict(zip(filtered["Display"], filtered["email"]))
            display_to_name = dict(zip(filtered["Display"], filtered["fullname"]))
            display_to_email = dict(zip(filtered["Display"], filtered["email"]))

            # === Step 6: Ensure current student is selected and shown ===
            if st.session_state.user_role == "student":
                current_student = st.session_state.current_student
                current_email = current_student['email'].strip().upper()
                current_display = f"{current_student['first_name'].strip().title()} {current_student['last_name'].strip().title()} ({current_email})"
                student_options = filtered["Display"].tolist()
    
                try:
                    # selected_display = st.multiselect(
                    #     "Choose 3–15 students",
                    #     student_options,
                    #     default=[current_display]
                    # )
                    selected_display = st.multiselect(
                        "Choose 3–15 students (you must be part of your own group)",
                        student_options,
                        default=[current_display]
                    )
                    
                    # Ensure current_display is always in the list
                    if current_display not in selected_display:
                        st.warning("You cannot remove yourself from the group. We've added you back.")
                        selected_display = [current_display] + [d for d in selected_display if d != current_display]
    
                except st.errors.StreamlitAPIException:
                    st.error(
                        f"""🚫 You must select your correct **Faculty** and **Programme** to proceed.
                    
            Your name {current_display} is not listed among the students in the selected department.
    
            Please go back and double-check your selection."""
                    )
                    st.stop()
    
    
            # selected_matrics = [display_to_matric[item] for item in selected_display if item in display_to_matric]
            selected_names = [display_to_name[item] for item in selected_display if item in display_to_name]
            selected_emails = [display_to_email[item] for item in selected_display if item in display_to_email]
    
            # === Step 7: Group name & submit ===
            group_name = st.text_input("Enter Group Name")
    
            existing_group_names = st.session_state.groups_df["group_name"].tolist() if not st.session_state.groups_df.empty else []
    
            # ========== Handle Group Creation with Block and Auto-Logout ==========
            if block_form:
                st.warning("🚫 You have already created a group for this programme.")
    
                # Optionally log them out immediately
                if st.button("🚪 Logout Now"):
                    for key in ["authenticated", "user_email", "user_role", "current_student"]:
                        st.session_state.pop(key, None)
                    st.rerun()
                else:
                    if st.button("Create Group"):
                        st.error("You have already created a group for this programme and are now being logged out.")
                        for key in ["authenticated", "user_email", "user_role", "current_student"]:
                            st.session_state.pop(key, None)
                        st.rerun()
            else:
                if st.button("Create Group"):
                    if len(selected_emails) < 3:
                        st.warning("You must select at least 3 students.")
                    elif len(selected_emails) > 15:
                        st.warning("You can't select more than 15 students.")
                    elif not group_name:
                        st.warning("Please provide a group name.")
                    elif group_name in existing_group_names:
                        st.error("Group name already exists.")
                    else:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_row = [
                            timestamp, group_name, faculty, department, selected_course,
                            ", ".join(selected_email), ", ".join(selected_names), st.session_state.user_email
                        ]
    
                        if not st.session_state.groups_ws.get_all_values():
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
    
                        # Clear group_df from cache and log out the student
                        del st.session_state.groups_df
                        for key in ["authenticated", "user_email", "user_role", "current_student"]:
                            st.session_state.pop(key, None)
                        st.rerun()


# ========== Admin Panel ==========
elif st.session_state.user_role == "admin":
    col1, col2, col3 = st.columns([1, 5, 1])

    with col2:
        st.subheader("👩‍💼 Admin Panel")
        admin_tabs = st.tabs(["📋 View Groups", "⬇️ Download", "❌ Delete Group", "👥 View & Assign"])

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
else:
    st.error("Unknown user role. Please contact administrator.")
    st.stop()



