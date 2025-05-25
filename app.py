import streamlit as st
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import os
import pickle
import json
from dotenv import load_dotenv
import base64
from pathlib import Path

# Load environment variables
load_dotenv()

st.write("Secrets keys:", list(st.secrets.keys()))

# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']

def get_google_drive_service():
    """Get Google Drive service using OAuth."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_dict = json.loads(st.secrets["credentials"]["json"])
            flow = InstalledAppFlow.from_client_config(credentials_dict, SCOPES)
            creds = flow.run_console()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def list_drive_files(service, query=None):
    """List files in Google Drive."""
    try:
        results = service.files().list(
            pageSize=100,
            q=query,
            fields="nextPageToken, files(id, name, mimeType)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"Error listing files: {str(e)}")
        return []

def download_file_from_drive(file_id, service):
    """Download a file from Google Drive."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except Exception as e:
        st.error(f"Error downloading file: {str(e)}")
        return None

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'selected_file' not in st.session_state:
    st.session_state.selected_file = None

# Login screen
if not st.session_state.authenticated:
    st.title("Job Annotation Tool")
    st.header("Login")
    
    # Center the login button
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("""
        <style>
        .login-button {
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 20px 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        if st.button("Login with Google", type="primary", use_container_width=True):
            try:
                # This will trigger the OAuth flow
                service = get_google_drive_service()
                st.session_state.authenticated = True
                st.session_state.service = service
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {str(e)}")
    
    # Instructions
    with st.sidebar:
        st.header("Setup Instructions")
        st.markdown("""
        1. Click "Login with Google"
        2. Authorize the app in your browser
        3. Select a file to start annotating
        """)
    
    st.stop()

# Main app
st.title("Job Annotation Tool")

# File selection
st.header("Step 1: Select File")

try:
    # Get list of CSV files
    files = list_drive_files(st.session_state.service, "mimeType='text/csv'")
    
    if not files:
        st.warning("No CSV files found in your Google Drive.")
        st.stop()
    
    # Create a dictionary of file names to IDs
    file_options = {f"{file['name']} ({file['id']})": file['id'] for file in files}
    
    # File selector
    selected_file_name = st.selectbox(
        "Select a CSV file to annotate",
        options=list(file_options.keys()),
        index=0 if not st.session_state.selected_file else list(file_options.keys()).index(st.session_state.selected_file)
    )
    
    selected_file_id = file_options[selected_file_name]
    
    if st.button("Load File") or (st.session_state.selected_file != selected_file_name):
        st.session_state.selected_file = selected_file_name
        file = download_file_from_drive(selected_file_id, st.session_state.service)
        if file:
            df = pd.read_csv(file)
            
            if 'finalAnnotation' not in df.columns:
                df['finalAnnotation'] = None
            
            st.session_state.df = df
            st.session_state.current_index = 0
            st.success("File loaded successfully!")
            st.rerun()

except Exception as e:
    st.error(f"Error: {str(e)}")
    if "invalid_grant" in str(e).lower():
        # Clear the token if it's invalid
        if os.path.exists('token.pickle'):
            os.remove('token.pickle')
        st.session_state.authenticated = False
        st.rerun()

# Annotation interface
if st.session_state.df is not None:
    st.header("Step 2: Annotate Jobs")
    
    df = st.session_state.df
    current_index = st.session_state.current_index
    
    # Find the next unannotated row
    while current_index < len(df) and pd.notna(df.loc[current_index, 'finalAnnotation']):
        current_index += 1
    
    if current_index >= len(df):
        st.success("All jobs have been annotated!")
    else:
        st.subheader(f"Job {current_index + 1} of {len(df)}")
        
        # Display job details
        st.markdown("### Title")
        st.write(df.loc[current_index, 'TITLE'])
        
        st.markdown("### Company")
        st.write(df.loc[current_index, 'COMPANY_NAME'])
        
        st.markdown("### Description")
        st.write(df.loc[current_index, 'JOB_DESCRIPTION'])
        
        # Annotation buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("AI Job", type="primary"):
                df.loc[current_index, 'finalAnnotation'] = 1
                st.session_state.df = df
                st.session_state.current_index = current_index + 1
                # Save to Google Drive
                try:
                    media = MediaIoBaseUpload(
                        io.BytesIO(df.to_csv(index=False).encode()),
                        mimetype='text/csv',
                        resumable=True
                    )
                    file = st.session_state.service.files().update(
                        fileId=selected_file_id,
                        media_body=media
                    ).execute()
                    st.success("Progress saved!")
                except Exception as e:
                    st.error(f"Error saving to Google Drive: {str(e)}")
                st.rerun()
        
        with col2:
            if st.button("Non-AI Job"):
                df.loc[current_index, 'finalAnnotation'] = 0
                st.session_state.df = df
                st.session_state.current_index = current_index + 1
                # Save to Google Drive
                try:
                    media = MediaIoBaseUpload(
                        io.BytesIO(df.to_csv(index=False).encode()),
                        mimetype='text/csv',
                        resumable=True
                    )
                    file = st.session_state.service.files().update(
                        fileId=selected_file_id,
                        media_body=media
                    ).execute()
                    st.success("Progress saved!")
                except Exception as e:
                    st.error(f"Error saving to Google Drive: {str(e)}")
                st.rerun()
        
        # Progress bar
        progress = (df['finalAnnotation'].notna().sum() / len(df)) * 100
        st.progress(progress / 100)
        st.write(f"Progress: {progress:.1f}%")

# Sidebar
with st.sidebar:
    st.header("Instructions")
    st.markdown("""
    1. Select a CSV file from your Google Drive
    2. Click 'Load File' to start
    3. For each job:
        - Review the title, company, and description
        - Click 'AI Job' if the position requires AI skills
        - Click 'Non-AI Job' if it doesn't
    4. Progress is automatically saved after each annotation
    """)
    
    if st.button("Logout"):
        if os.path.exists('token.pickle'):
            os.remove('token.pickle')
        st.session_state.authenticated = False
        st.session_state.clear()
        st.rerun()