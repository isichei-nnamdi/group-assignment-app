import streamlit as st
import pandas as pd
import json
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from io import BytesIO


def student_submission_page(group_info, selected_course, student_email, client, sheet_id, creds):
    st.markdown("---")
    st.subheader("📤 Group Lab Submission")

    group_name = group_info['group_name']
    st.info(f"You're in **{group_name}** for the course **{selected_course}**")

    # ========== Load Labs ==========
    @st.cache_data
    def load_lab_list(_client, _sheet_id, selected_course):
        try:
            ws = _client.open_by_key(_sheet_id).worksheet("Labs")
            data = ws.get_all_values()
            df = pd.DataFrame(data[1:], columns=data[0])  # Skip header row
            filtered_labs = df[df['Course'].str.lower() == selected_course.lower()]['Lab Name'].dropna().unique()
            return sorted(filtered_labs)
        except Exception as e:
            st.error(f"Unable to load lab list: {e}")
            return []


    lab_list = load_lab_list(client, sheet_id, selected_course)
    if not lab_list:
        st.warning("No labs found for this course.")
        return

    selected_lab = st.selectbox("Select Lab to Submit", lab_list)

    # # ========== Load Submissions ==========
    # def load_submissions_df(_client, _sheet_id):
    #     try:
    #         ws = _client.open_by_key(_sheet_id).worksheet("Submissions")
    #     except:
    #         ws = _client.open_by_key(_sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
    #         ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_link", "graded", "grade"])

    #     records = ws.get_all_values()
    #     df = pd.DataFrame(records[1:], columns=records[0]) if len(records) > 1 else pd.DataFrame(columns=[
    #         "timestamp", "group_name", "course", "lab", "submitted_by",
    #         "file_name", "file_link", "graded", "grade"
    #     ])
    #     return ws, df

    # ========== Load Submissions ==========
    def load_submissions_df(_client, _sheet_id):
        try:
            ws = _client.open_by_key(_sheet_id).worksheet("Submissions")
        except WorksheetNotFound:
            # Only create if it truly does not exist
            ws = _client.open_by_key(_sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
            ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_link", "graded", "grade"])
        except Exception as e:
            # Any other error: surface it rather than silently wiping data
            raise RuntimeError(f"Failed to load Submissions sheet: {e}")
    
        records = ws.get_all_values()
        if len(records) > 1:
            df = pd.DataFrame(records[1:], columns=records[0])
        else:
            df = pd.DataFrame(columns=[
                "timestamp", "group_name", "course", "lab", "submitted_by",
                "file_name", "file_link", "graded", "grade"
            ])
        return ws, df

    # ========== Upload to Google Drive ==========
    def upload_to_drive(file_bytes, filename, folder_id, creds):
        try:
            service = build("drive", "v3", credentials=creds)
    
            file_metadata = {
                "name": filename,
                "parents": [folder_id]
            }
    
            media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype="application/octet-stream")
    
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True  # ✅ Allow file creation in Shared Drives
            ).execute()
    
            file_id = uploaded_file.get("id")
    
            # Make the file public
            permission = {"type": "anyone", "role": "reader"}
            service.permissions().create(
                fileId=file_id,
                body=permission,
                supportsAllDrives=True  # ✅ Required for Shared Drives
            ).execute()
    
            return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    
        except Exception as e:
            st.error(f"🚫 Drive upload failed:\n\n**{e}**\n\n📌 Check folder ID, sharing settings, and permission scopes.")
            return None

    # Load submission data
    submissions_ws, submissions_df = load_submissions_df(client, sheet_id)

    # Check for existing submission
    existing = submissions_df[
        (submissions_df["group_name"].str.lower() == group_name.lower()) &
        (submissions_df["course"].str.lower() == selected_course.lower()) &
        (submissions_df["lab"].str.lower() == selected_lab.lower())
    ]

    # If already submitted
    if not existing.empty:
        st.success(f"✅ Submission already made for {selected_lab}.")
        submitted_by = existing['submitted_by'].iloc[0]
        file_name = existing['file_name'].iloc[0]
        file_link = existing['file_link'].iloc[0]
        grade = existing['grade'].iloc[0]
        graded_status = existing['graded'].iloc[0].strip().lower()

        st.markdown(f"📎 **File:** [{file_name}]({file_link})")
        st.markdown(f"👤 **Submitted by:** {submitted_by}")

        with st.expander("🔍 Preview Submission", expanded=True):
            # ========== File Preview ==========
            file_ext = file_name.lower().split('.')[-1]
    
            if file_ext == "pdf":
                preview_url = file_link.replace("/view?usp=sharing", "/preview")
                st.components.v1.iframe(preview_url, height=600)
    
            elif file_ext in ["doc", "docx", "ppt", "pptx", "xls", "xlsx"]:
                try:
                    # Extract the file ID from the Drive link
                    file_id = file_link.split("/d/")[1].split("/")[0]
                    preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
                    st.components.v1.iframe(preview_url, height=600)
                except Exception as e:
                    st.warning(f"⚠️ Unable to preview the document: {e}")

    
            elif file_ext == "ipynb":
                # from urllib.parse import quote
                # st.markdown(f"[📘 View Notebook via nbviewer](https://nbviewer.org/url/{quote(file_link, safe='')})")
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

    
            elif file_ext in ["png", "jpg", "jpeg", "gif"]:
                st.image(file_link, caption=file_name, use_column_width=True)

            # elif file_ext == "py":
            #     import requests
            
            #     try:
            #         # Extract file ID from the Google Drive link
            #         file_id = file_link.split("/d/")[1].split("/")[0]
            #         download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
            #         headers = {"Authorization": f"Bearer {creds.token}"}
            
            #         response = requests.get(download_url, headers=headers)
            
            #         if response.status_code == 200:
            #             code_content = response.text
            #             st.code(code_content, language='python')
            #         else:
            #             st.warning("⚠️ Unable to fetch the Python file content for preview.")
            #     except Exception as e:
            #         st.warning(f"⚠️ Error displaying .py file: {e}")

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

            else:
                st.info("⚠️ Preview not supported for this file type.")

        if graded_status == "yes":
            st.success(f"📝 This submission has been graded: **{grade}**")
        else:
            # if st.button("🗑️ Delete Submission and Re-upload"):
            #     submissions_df = submissions_df.drop(existing.index)
            #     submissions_ws.clear()
            #     submissions_ws.append_row(submissions_df.columns.tolist())
            #     for _, row in submissions_df.iterrows():
            #         submissions_ws.append_row(list(row))
            #     st.success("Deleted. You can now re-upload.")
            #     st.rerun()
            # ========== Delete Specific Submission ==========
            def delete_submission(ws, group_name, course, lab):
                """
                Deletes only the row for the given group/course/lab combination.
                Does NOT clear the whole sheet.
                """
                rows = ws.get_all_values()
                if not rows:
                    return False
            
                headers = rows[0]
                target_idx = None
            
                for idx, row in enumerate(rows[1:], start=2):  # Start=2 because Sheets are 1-indexed and row 1 is headers
                    if (
                        row[headers.index("group_name")].strip().lower() == group_name.strip().lower()
                        and row[headers.index("course")].strip().lower() == course.strip().lower()
                        and row[headers.index("lab")].strip().lower() == lab.strip().lower()
                    ):
                        target_idx = idx
                        break
            
                if target_idx:
                    ws.delete_rows(target_idx)
                    return True
                return False
            
            # Usage inside your delete button logic:
            if st.button("🗑️ Delete Submission and Re-upload"):
                deleted = delete_submission(submissions_ws, group_name, selected_course, selected_lab)
                if deleted:
                    st.success("Submission deleted. You can now re-upload.")
                    st.rerun()
                else:
                    st.warning("No matching submission found to delete.")


    # If not submitted yet
    else:
        uploaded = st.file_uploader("📎 Upload Lab Document", type=["pdf", "docx", "ipynb", "py", "xlsx", "csv", "txt"])
    
        if uploaded:
            file_bytes = uploaded.read()  # Store immediately to avoid loss
            st.session_state['uploaded_file_bytes'] = file_bytes
            st.session_state['uploaded_file_name'] = uploaded.name
    
        if 'uploaded_file_bytes' in st.session_state and st.button("Submit Lab Report"):
            file_bytes = st.session_state['uploaded_file_bytes']
            filename = st.session_state['uploaded_file_name']
            folder_id = st.secrets["google_service_account"]["drive_folder_id"]
            drive_link = upload_to_drive(file_bytes, filename, folder_id, creds)
    
            if not drive_link:
                st.error("❌ File upload failed.")
                return
    
            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                group_name, selected_course, selected_lab,
                student_email, filename, drive_link, "No", ""
            ]
            submissions_ws.append_row(new_row)
            st.success("✅ Submission uploaded and saved!")
            st.balloons()
            st.session_state.pop('uploaded_file_bytes', None)
            st.session_state.pop('uploaded_file_name', None)
            st.rerun()

