import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import json
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

def grading_page(client, sheet_id, creds, groups_df):
    st.subheader("📝 Grade Lab Submissions")

    # Load Labs sheet
    try:
        labs_ws = client.open_by_key(sheet_id).worksheet("Labs")
        labs_data = labs_ws.get_all_values()

        if len(labs_data) <= 1:
            st.warning("⚠️ No lab records found in the Labs sheet.")
            return

        labs_df = pd.DataFrame(labs_data[1:], columns=[h.strip() for h in labs_data[0]])
        labs_df.columns = ["Lab Name" if "lab" in c.lower() else "Course" if "course" in c.lower() else c for c in labs_df.columns]
        course_options = sorted(labs_df["Course"].dropna().unique())
    except Exception as e:
        st.error(f"❌ Error loading Labs sheet: {e}")
        return

    selected_course = st.selectbox("Select Course", course_options, key="grade_course")
    lab_options = sorted(labs_df[labs_df["Course"].str.lower() == selected_course.lower()]["Lab Name"].dropna().unique())
    if not lab_options:
        st.warning("No labs found for selected course.")
        return
    selected_lab = st.selectbox("Select Lab to Grade", lab_options, key="grade_lab")

    # Load Submissions
    try:
        submissions_ws = client.open_by_key(sheet_id).worksheet("Submissions")
        data = submissions_ws.get_all_values()
        if len(data) <= 1:
            st.info("No submissions found yet.")
            return
        submissions_df = pd.DataFrame(data[1:], columns=data[0])
    except Exception as e:
        st.error(f"❌ Error loading Submissions sheet: {e}")
        return

    filtered = submissions_df[
        (submissions_df["course"].str.lower() == selected_course.lower()) &
        (submissions_df["lab"].str.lower() == selected_lab.lower())
    ]

    if filtered.empty:
        st.info("No submissions found for this course and lab.")
        return

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
                    file_id = file_link.split("/d/")[1].split("/")[0]
                    st.components.v1.iframe(f"https://drive.google.com/file/d/{file_id}/preview", height=600)
                elif file_ext == "ipynb":
                    file_id = file_link.split("/d/")[1].split("/")[0]
                    drive_service = build("drive", "v3", credentials=creds)
                    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
                    file_buffer = BytesIO()
                    downloader = MediaIoBaseDownload(file_buffer, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    notebook = json.load(BytesIO(file_buffer.getvalue()))
                    for cell in notebook.get("cells", []):
                        if cell["cell_type"] == "markdown":
                            st.markdown("".join(cell["source"]), unsafe_allow_html=True)
                        elif cell["cell_type"] == "code":
                            st.code("".join(cell["source"]), language="python")
                elif file_ext == "py":
                    file_id = file_link.split("/d/")[1].split("/")[0]
                    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                    headers = {"Authorization": f"Bearer {creds.token}"}
                    response = requests.get(download_url, headers=headers)
                    if response.ok:
                        st.code(response.text, language="python")
                    else:
                        st.warning("Could not preview .py file")
                elif file_ext in ["png", "jpg", "jpeg", "gif"]:
                    st.image(file_link, use_column_width=True)
                else:
                    st.info("⚠️ File preview not supported.")
            except Exception as e:
                st.error(f"Preview error: {e}")

        score = st.text_input(f"Enter grade for {row['group_name']}", key=f"score_{idx}")
        if st.button(f"✅ Submit Grade for {row['group_name']}", key=f"submit_{idx}"):
            try:
                row_idx = idx + 2  # Adjust for 1-based index and header row
                submissions_ws.update_cell(row_idx, submissions_df.columns.get_loc("graded") + 1, "Yes")
                submissions_ws.update_cell(row_idx, submissions_df.columns.get_loc("grade") + 1, score)

                grade_sheet_name = f"{selected_course}_{selected_lab}".replace(" ", "_")
                try:
                    grade_ws = client.open_by_key(sheet_id).worksheet(grade_sheet_name)
                except:
                    grade_ws = client.open_by_key(sheet_id).add_worksheet(grade_sheet_name, rows="1000", cols="10")
                    grade_ws.append_row(["timestamp", "course", "lab", "group_name", "name", "email", "score"])

                group_students = groups_df[groups_df["group_name"] == row["group_name"]]
                for _, student in group_students.iterrows():
                    grade_ws.append_row([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        selected_course, selected_lab,
                        row['group_name'], student['name'], student['email'], score
                    ])

                st.success(f"✅ Grade saved for {row['group_name']}")
                st.rerun()

            except Exception as e:
                st.error(f"❌ Failed to grade: {e}")
