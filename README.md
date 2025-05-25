# Job Annotation Tool

A Streamlit application for annotating job postings as AI or non-AI jobs, with Google Drive integration for file storage.

## Setup Instructions

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Get your Google Drive API Key:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project
   - Go to "APIs & Services" > "Credentials"
   - Create an API key or use an existing one
   - Make sure the Google Drive API is enabled for your project

3. Run the application:
   ```bash
   streamlit run app.py
   ```

## Usage

1. Enter your Google Drive API key in the input field
2. Enter your Google Drive file ID (you can get this from your Google Drive file URL)
3. Click "Load File" to start annotating
4. For each job posting:
   - Review the title, company, and description
   - Click "AI Job" if the position requires AI skills
   - Click "Non-AI Job" if it doesn't
5. Progress is automatically saved after each annotation

## Features

- Simple Google Drive API key authentication
- Clean, user-friendly interface
- Progress tracking
- Automatic saving
- Session persistence
- Sidebar with instructions

## File Format

The input CSV file should have the following columns:
- TITLE
- COMPANY_NAME
- JOB_DESCRIPTION

The app will automatically add a `finalAnnotation` column where:
- 1 = AI Job
- 0 = Non-AI Job
- Null = Not yet annotated

## Security Note

Your API key is stored only in the session state and is never saved to disk. However, make sure to:
1. Restrict your API key to only the Google Drive API
2. Set appropriate restrictions on your API key in the Google Cloud Console
3. Never share your API key publicly 