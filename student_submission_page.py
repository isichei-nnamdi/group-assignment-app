import streamlit as st
import pandas as pd
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials

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
    def load_lab_list():
    labs_ws = client.open_by_key(group_log_sheet_id).worksheet("Labs")
    return sorted(pd.Series(labs_ws.col_values(2)).dropna().unique())  # Assumes column 2 has lab names

    if "lab_list" not in st.session_state:
        st.session_state.lab_list = load_lab_list()
    
except (gspread.exceptions.APIError, socket.gaierror, TransportError, Exception) as e:
    st.error(
        f"""
    🚫 **Connection Error**

    We couldn't connect to the database or load required data. Please check your internet connection or try again later.

    **Details:** `{str(e)}`

    If the issue persists, contact the app administrator.
    """)
    st.stop()

# def load_labs_sheet():
#     return pd.DataFrame(st.session_state.labs_ws.get_all_records())

# labs_df = load_labs_sheet()
# @st.cache_data



# === You will also need to define this function externally ===
def save_file_to_drive(uploaded_file, destination_path):
    with open(destination_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return destination_path

def student_submission_page():
    st.subheader("📤 Group Lab Submission Portal")

    # Initial checks
    if "groups_df" not in st.session_state or st.session_state.groups_df.empty:
        st.warning("Group data not found. Please try again later.")
        return

    student_email = st.session_state.user_email.strip().lower()

    # Get all courses where the student is part of a group
    grouped_courses = []
    student_group_info = []

    for _, row in st.session_state.groups_df.iterrows():
        group_emails = [e.strip().lower() for e in row["members"].split(",")]
        if student_email in group_emails:
            grouped_courses.append(row["course"])
            student_group_info.append(row)

    if not grouped_courses:
        st.info("You're not yet added to a group for any course.")
        return

    selected_course = st.selectbox("Select Course to Submit Lab For", sorted(set(grouped_courses)))

    # Retrieve student group data
    student_group = None
    for row in student_group_info:
        if row["course"] == selected_course:
            student_group = row
            break

    if not student_group:
        st.error("Group information could not be retrieved. Contact your admin.")
        return

    group_name = student_group["group_name"]

    # === Load lab list ===
    lab_list_df = st.session_state.lab_list_df
    labs_for_course = lab_list_df[lab_list_df["course"].str.lower() == selected_course.lower()]["lab"].tolist()

    if not labs_for_course:
        st.warning("No lab assigned yet for this course.")
        return

    selected_lab = st.selectbox("Select Lab", labs_for_course)

    # === Load submissions ===
    submission_df = st.session_state.submission_df
    submission_match = submission_df[
        (submission_df["group_name"] == group_name) &
        (submission_df["course"].str.lower() == selected_course.lower()) &
        (submission_df["lab"] == selected_lab)
    ]

    if not submission_match.empty:
        submission_row = submission_match.iloc[0]
        submitted_file = submission_row["file_name"]
        grade = submission_row.get("grade", "")

        st.info(f"Your group has already submitted this lab: **{submitted_file}**")

        if grade:
            st.success(f"✅ Graded: {grade}")
        else:
            st.warning("Submission not graded yet.")

            # Allow deletion
            if st.button("❌ Delete Submission and Re-Upload"):
                st.session_state.submission_df = submission_df[~(
                    (submission_df["group_name"] == group_name) &
                    (submission_df["course"].str.lower() == selected_course.lower()) &
                    (submission_df["lab"] == selected_lab)
                )]

                st.session_state.submission_ws.clear()
                st.session_state.submission_ws.append_row(submission_df.columns.tolist())
                for _, row in st.session_state.submission_df.iterrows():
                    st.session_state.submission_ws.append_row(row.tolist())

                st.success("Submission deleted. You may re-upload now.")
                st.rerun()

    else:
        uploaded_file = st.file_uploader("Upload your lab work (PDF/DOCX)", type=["pdf", "docx"])
        if uploaded_file:
            if st.button("Submit Lab Work"):
                file_name = f"{group_name}_{selected_course}_{selected_lab}_{datetime.now().strftime('%Y%m%d%H%M%S')}".replace(" ", "_") + "." + uploaded_file.name.split(".")[-1]

                # Save file (you can customize this function)
                save_path = save_file_to_drive(uploaded_file, f"/labs/{file_name}")
                # For demonstration, we just assume the filename is saved.

                new_row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    group_name,
                    selected_course,
                    selected_lab,
                    file_name,
                    ""  # grade (empty at this point)
                ]

                # Write to worksheet
                st.session_state.submission_ws.append_row(["timestamp", "group_name", "course", "lab", "file_name", "grade"] if st.session_state.submission_df.empty else [])
                st.session_state.submission_ws.append_row(new_row)

                # Update local DataFrame
                st.session_state.submission_df.loc[len(st.session_state.submission_df)] = new_row

                st.success("✅ Submission successful!")
                st.rerun()
