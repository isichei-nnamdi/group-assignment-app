import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.exceptions import TransportError
import socket
import json


try:
    # ========== Google Sheets Auth ==========
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Convert AttrDict to a regular dict
    secrets_dict = dict(st.secrets["google_service_account"])

    with open("temp_credentials.json", "w") as f:
    json.dump(secrets_dict, f)

    # Then use it like this:
    creds = Credentials.from_service_account_file("temp_credentials.json")
    
    # service_account_info = st.secrets["google_service_account"]
    # creds = ServiceAccountCredentials.from_json_keyfile_dict(
    #     json.loads(json.dumps(service_account_info)), scope
    # )
    client = gspread.authorize(creds)
    # creds = ServiceAccountCredentials.from_json_keyfile_name("my-miva-project-e7d820ea62bf.json", scope)
    # client = gspread.authorize(creds)

    # ========== Load Data & Cache ==========
    def load_students_df():
        ws = client.open_by_key(st.secrets["student_sheet_id"]).worksheet("UNDERGRADUATE")
        df = pd.DataFrame(ws.get_all_records())
        df["Email"] = df["Email"].str.strip().str.lower()
        df["Student ID"] = df["Student ID"].astype(str).str.strip()
        return df

    def load_login_df():
        ws = client.open_by_key(st.secrets["group_log_sheet_id"]).worksheet("Login_details")
        df = pd.DataFrame(ws.get_all_records())
        df["Email"] = df["Email"].str.strip().str.lower()
        df["Password"] = df["Password"].astype(str).str.strip()
        return df

    def load_groups_df():
        sheet = client.open_by_key(st.secrets["group_log_sheet_id"])
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
        course_ws = client.open_by_key(st.secrets["group_log_sheet_id"]).worksheet("course_list")
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
        (st.session_state.students_df["MIVA Email"] == email) &
        (st.session_state.students_df["Student ID"] == password)
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
        df['Faculty'] = df['Faculty'].str.strip().str.title()
        df['Programme'] = df['Programme'].str.strip().str.title()

        # ========== Group Creation (Student or Admin) ==========
        existing = pd.DataFrame()
        block_form = False  # flag to prevent group creation


        # === Step 1: Faculty & Department Selection ===
        faculty_list = sorted(df['Faculty'].dropna().unique())
        faculty = st.selectbox("Select Faculty", faculty_list)

        dept_list = sorted(df[df['Faculty'] == faculty]['Programme'].dropna().unique())
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


        # === Step 4: Remove already grouped students for the same course ===
        already_grouped = []
        if "members" in st.session_state.groups_df.columns and "course" in st.session_state.groups_df.columns:
            for _, row in st.session_state.groups_df.iterrows():
                if row["course"].strip().lower() == selected_course.strip().lower():
                    already_grouped.extend([m.strip().upper() for m in row["members"].split(",")])


        # Get current student's details
        if st.session_state.user_role == "student":
            current_student = st.session_state.current_student
            current_matric = current_student['Matric Number'].strip().upper()
        else:
            current_student = None
            current_matric = None



        # Filter: All students in selected dept, excluding already grouped (except current student)
        filtered = df[
            (df['Faculty'] == faculty) &
            (df['Programme'] == department) &
            (~df['Matric Number'].astype(str).str.upper().isin(already_grouped) | (df['Matric Number'].astype(str).str.upper() == current_matric))
        ].copy()

        # === Step 4: Clean names and emails ===
        filtered["First Name"] = filtered["First Name"].str.strip().str.title()
        filtered["Surname"] = filtered["Surname"].str.strip().str.title()
        filtered["Matric Number"] = filtered["Matric Number"].astype(str).str.strip().str.upper()
        filtered["MIVA Email"] = filtered["MIVA Email"].str.strip()

        filtered["Display"] = filtered["First Name"] + " " + filtered["Surname"] + " (" + filtered["Matric Number"] + ")"

        # === Step 5: Add mappings for multiselect ===
        display_to_matric = dict(zip(filtered["Display"], filtered["Matric Number"]))
        display_to_name = dict(zip(filtered["Display"], filtered["First Name"] + " " + filtered["Surname"]))
        display_to_email = dict(zip(filtered["Display"], filtered["MIVA Email"]))

        # === Step 6: Ensure current student is selected and shown ===
        if st.session_state.user_role == "student":
            current_student = st.session_state.current_student
            current_matric = current_student['Matric Number'].strip().upper()
            current_display = f"{current_student['First Name'].strip().title()} {current_student['Surname'].strip().title()} ({current_matric})"
            student_options = filtered["Display"].tolist()

            try:
                selected_display = st.multiselect(
                    "Choose 3–15 students",
                    student_options,
                    default=[current_display]
                )
            except st.errors.StreamlitAPIException:
                st.error(
                    f"""🚫 You must select your correct **Faculty** and **Programme** to proceed.
                
        Your name (**{current_display}**) is not listed among the students in the selected department.

        Please go back and double-check your selection."""
                )
                st.stop()


        selected_matrics = [display_to_matric[item] for item in selected_display if item in display_to_matric]
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
                if len(selected_matrics) < 3:
                    st.warning("You must select at least 3 students.")
                elif len(selected_matrics) > 15:
                    st.warning("You can't select more than 15 students.")
                elif not group_name:
                    st.warning("Please provide a group name.")
                elif group_name in existing_group_names:
                    st.error("Group name already exists.")
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    new_row = [
                        timestamp, group_name, faculty, department, selected_course,
                        ", ".join(selected_matrics), ", ".join(selected_names), st.session_state.user_email
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
        Group Formation App
        """
                        msg = MIMEMultipart()
                        msg['From'] = "Group App"
                        msg['To'] = email
                        msg['Subject'] = subject
                        msg.attach(MIMEText(body, 'plain'))

                        try:
                            server = smtplib.SMTP('smtp.gmail.com', 587)
                            server.starttls()
                            server.login("isichei.nnamdi@gmail.com", "yjmkwwrokhxlbske")
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



