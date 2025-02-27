

import streamlit as st
import requests
import json
from datetime import datetime
import base64
from io import BytesIO
import pandas as pd
from PIL import Image
import boto3
import time

# Configure page settings
st.set_page_config(
    page_title="Employee Productivity Tracking",
    page_icon="📊",
    layout="wide"
)

# API Configuration
API_ENDPOINT = 'https://wt7zuh1n3f.execute-api.us-east-1.amazonaws.com/prod/track'


def auto_crop(img):
    """Auto-crop image to remove empty spaces"""
    bbox = img.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def aggressive_compress(img):
    """Aggressively compress image if needed"""
    for size in [(400, 400), (300, 300), (200, 200)]:
        buffer = BytesIO()
        img_copy = img.copy()
        img_copy.thumbnail(size)
        img_copy.save(buffer, format="PNG", optimize=True, compression_level=9)
        buffer.seek(0)
        if len(buffer.getvalue()) <= 250000:
            return buffer
    return None

def verify_png_format(buffer):
    """Verify that the buffer contains PNG data"""
    try:
        img = Image.open(buffer)
        return img.format == 'PNG'
    except Exception:
        return False

def compress_image(uploaded_file):
    """Compress the image and ensure PNG format with size limits"""
    try:
        img = Image.open(uploaded_file)
        
        if img.mode not in ('RGBA', 'RGB'):
            img = img.convert('RGB')
        
        img = auto_crop(img)
        MAX_SIZE = (500, 500)
        img.thumbnail(MAX_SIZE, Image.LANCZOS)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=True, quality=85, compression_level=6)
        buffer.seek(0)
        
        final_size = len(buffer.getvalue())
        if final_size > 250000:
            st.warning("Image is large, attempting further compression...")
            compressed_buffer = aggressive_compress(img)
            if compressed_buffer:
                return compressed_buffer
            
            img = img.convert('L')
            buffer = BytesIO()
            img.save(buffer, format="PNG", optimize=True, quality=70, compression_level=9)
            buffer.seek(0)
            
        return buffer
    except Exception as e:
        st.error(f"Error compressing image: {str(e)}")
        return None

def get_image_base64(file):
    """Convert uploaded file to base64"""
    try:
        bytes_data = file.getvalue()
        base64_string = base64.b64encode(bytes_data).decode()
        return base64_string
    except Exception as e:
        st.error(f"Error converting image to base64: {str(e)}")
        return None

def validate_input(image_base64):
    """Validate the input before sending to API"""
    if not image_base64:
        return False, "No image data provided"
    
    size_in_bytes = len(image_base64.encode('utf-8'))
    if size_in_bytes > 262000:
        return False, f"Image too large ({size_in_bytes} bytes). Maximum allowed is 262144 bytes."
    
    return True, ""

def extract_json_from_markdown(raw_response):
    """Extract JSON content from markdown-formatted string"""
    try:
        # If the input is already JSON-formatted, return it
        if isinstance(raw_response, dict):
            return raw_response
            
        # Look for JSON content between various markers
        markers = ['```json\n', 'json\n', '```python\n', '{']
        for marker in markers:
            json_marker = raw_response.find(marker)
            if json_marker != -1:
                start_idx = json_marker + len(marker)
                content = raw_response[start_idx:].strip()
                
                # Find the end of the JSON object
                if marker.startswith('```'):
                    end_idx = content.find('```')
                    if end_idx != -1:
                        content = content[:end_idx].strip()
                else:
                    # Find the next double newline or end of string
                    end_idx = content.find('\n\n')
                    if end_idx != -1:
                        content = content[:end_idx].strip()
                
                try:
                    # If content starts with newline, strip it
                    content = content.lstrip('\n')
                    return json.loads(content)
                except json.JSONDecodeError:
                    continue
                    
        # If no JSON found with markers, try to find first { and last }
        first_brace = raw_response.find('{')
        last_brace = raw_response.rfind('}')
        if first_brace != -1 and last_brace != -1:
            content = raw_response[first_brace:last_brace + 1]
            return json.loads(content)
            
        return {}
        
    except Exception as e:
        st.error(f"Error extracting JSON from markdown: {e}")
        return {}

def poll_execution_status(execution_arn, max_attempts=30, delay=2):
    """Poll Step Functions execution status"""
    sfn_client = boto3.client('stepfunctions', region_name='us-east-1')
    
    for _ in range(max_attempts):
        try:
            response = sfn_client.describe_execution(
                executionArn=execution_arn
            )
            
            status = response['status']
            
            if status == 'SUCCEEDED':
                output = response.get('output', '{}')
                try:
                    parsed_output = json.loads(output)
                    return {
                        'status': status,
                        'output': parsed_output
                    }
                except json.JSONDecodeError as e:
                    st.error(f"Error parsing Step Functions output: {e}")
                    return {
                        'status': 'ERROR',
                        'error': f"Invalid JSON output"
                    }
                    
            elif status in ['FAILED', 'TIMED_OUT', 'ABORTED']:
                error_info = response.get('error', 'Unknown error')
                st.error(f"Step Functions execution failed: {error_info}")
                return {
                    'status': status,
                    'error': error_info
                }
                
            time.sleep(delay)
            
        except Exception as e:
            st.error(f"Error polling Step Functions: {e}")
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    return {
        'status': 'TIMEOUT',
        'error': 'Maximum polling attempts reached'
    }

def trigger_analysis(image_base64):
    """Trigger the analysis workflow through API Gateway"""
    is_valid, error_message = validate_input(image_base64)
    if not is_valid:
        st.error(error_message)
        return None

    try:
        payload = {
            "input": json.dumps({
                "image_data": image_base64
            }, separators=(',', ':'))
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        with st.spinner('Starting analysis...'):
            response = requests.post(
                API_ENDPOINT,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                execution_arn = result.get('executionArn')
                
                if execution_arn:
                    st.info(f"Analysis started...")
                    
                    status = poll_execution_status(execution_arn)
                    
                    if status.get('status') == 'SUCCEEDED':
                        output = status.get('output', {})
                        
                        # Process Visual Analysis
                        visual_data = {}
                        if 'visual_analysis' in output:
                            raw_visual = output['visual_analysis']
                            if isinstance(raw_visual, dict) and 'raw_response' in raw_visual:
                                visual_data = extract_json_from_markdown(raw_visual['raw_response'])
                            else:
                                visual_data = raw_visual.get('output', {})
                        
                        # Process Activity Pattern
                        activity_data = {}
                        if 'activity_pattern' in output:
                            raw_activity = output['activity_pattern']
                            if isinstance(raw_activity, dict) and 'raw_response' in raw_activity:
                                activity_data = extract_json_from_markdown(raw_activity['raw_response'])
                            else:
                                activity_data = raw_activity.get('output', {})
                        
                        # Process Productivity Assessment
                        productivity_data = {}
                        if 'productivity_assessment' in output:
                            raw_productivity = output['productivity_assessment']
                            if isinstance(raw_productivity, dict) and 'raw_response' in raw_productivity:
                                productivity_data = extract_json_from_markdown(raw_productivity['raw_response'])
                            else:
                                productivity_data = raw_productivity.get('output', {})
                        
                        return {
                            'visual_analysis': visual_data,
                            'activity_pattern': activity_data,
                            'productivity_assessment': productivity_data
                        }
                    else:
                        st.error(f"Analysis failed: {status.get('error')}")
                        return None
                else:
                    st.error("No execution ARN received")
                    return None
            else:
                st.error(f"API Error: {response.status_code}")
                st.error(f"Response: {response.text}")
                return None
                
    except Exception as e:
        st.error(f"Error in analysis: {str(e)}")
        return None

def display_visual_analysis(analysis_data):
    """Display Visual Analysis Results"""
    st.subheader("📸 Visual Analysis Results")
    
    if not analysis_data or not isinstance(analysis_data, dict):
        st.warning("No visual analysis data available")
        return
    
    # Extract content from message if present
    if 'message' in analysis_data:
        content = analysis_data['message'].get('content', [])
        if content and isinstance(content, list):
            analysis_text = content[0].get('text', '')
            st.markdown(analysis_text)
            return
        
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🖥️ Detected Applications")
        for app in analysis_data.get('applications', []):
            st.markdown(f"- {app}")
            
        st.markdown("### 🔍 UI Elements")
        for element in analysis_data.get('ui_elements', []):
            st.markdown(f"- {element}")
    
    with col2:
        st.markdown("### ⏰ Timestamp")
        st.info(analysis_data.get('timestamp', 'No timestamp'))
        
        st.markdown("### 💼 Work Type")
        st.info(analysis_data.get('work_type', 'Unknown'))
    
    if analysis_data.get('interactions'):
        st.markdown("### 🖱️ User Interactions")
        for interaction in analysis_data['interactions']:
            st.markdown(f"- {interaction}")

def display_activity_pattern(pattern_data):
    """Display Activity Pattern Results"""
    st.subheader("📊 Activity Pattern Analysis")
    
    if not pattern_data or not isinstance(pattern_data, dict):
        st.warning("No activity pattern data available")
        return
    
    st.markdown("### 📝 Summary")
    st.info(pattern_data.get('activity_summary', 'No summary available'))
    
    if timeline_data := pattern_data.get('timeline', []):
        st.markdown("### ⏱️ Activity Timeline")
        df = pd.DataFrame(timeline_data)
        st.dataframe(df)
    
    if indicators := pattern_data.get('productivity_indicators', {}):
        st.markdown("### 📈 Productivity Indicators")
        col1, col2, col3 = st.columns(3)
        
        metrics = {
            'Focus Time': indicators.get('focus_time', '0%'),
            'Context Switching': indicators.get('context_switching', '0/hour'),
            'Active Work Ratio': indicators.get('active_work_ratio', '0%')
        }
        
        for col, (metric, value) in zip([col1, col2, col3], metrics.items()):
            with col:
                st.metric(metric, value)

def display_productivity_assessment(assessment_data):
    """Display Productivity Assessment Results"""
    st.subheader("📈 Productivity Assessment")
    
    if not assessment_data or not isinstance(assessment_data, dict):
        st.warning("No productivity assessment data available")
        return
    
    score = assessment_data.get('productivity_score', {})
    overall_score = score.get('overall', 0)
    
    st.markdown("### Overall Score")
    st.progress(overall_score / 100)
    st.metric("Productivity Score", f"{overall_score}%")
    
    if 'breakdown' in score:
        st.markdown("### 🎯 Score Breakdown")
        col1, col2, col3 = st.columns(3)
        breakdown = score['breakdown']
        
        for (category, value), col in zip(breakdown.items(), [col1, col2, col3]):
            with col:
                st.metric(category.title(), f"{value}%")
    
    if recommendations := assessment_data.get('recommendations', []):
        st.markdown("### 💡 Recommendations")
        for rec in recommendations:
            with st.expander(f"📌 {rec['category']}"):
                st.write(f"**Suggestion:** {rec['suggestion']}")
                st.write(f"**Expected Impact:** {rec['expected_impact']}")
    
    if metrics := assessment_data.get('productivity_metrics', {}):
        st.markdown("### 📊 Detailed Metrics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Focus Time", metrics.get('focus_time_ratio', '0%'))
        with col2:
            st.metric("Task Switching Impact", metrics.get('task_switching_cost', 'N/A'))
        with col3:
            st.metric("Productive Hours", metrics.get('productive_hours', '0'))

def main():
    st.title('🎯 Employee Productivity Tracking System')
    
    st.warning("Please note: Images will be compressed to meet size limitations. For best results, use images under 1MB.")
    
    uploaded_file = st.file_uploader(
        "Upload Screenshot",
        type=['png', 'jpg', 'jpeg'],
        help="Upload a screenshot to analyze productivity (Will be converted to PNG)"
    )
    
    if uploaded_file is not None:
        file_size = len(uploaded_file.getvalue()) / 1024
        st.info(f"Original file size: {file_size:.2f} KB")
        
        compressed_file = compress_image(uploaded_file)
        if compressed_file:
            compressed_size = len(compressed_file.getvalue()) / 1024
            st.info(f"Compressed file size: {compressed_size:.2f} KB")
            
            if not verify_png_format(compressed_file):
                st.error("Error: Failed to convert image to PNG format")
                return
                
            st.image(compressed_file, caption='Uploaded Screenshot', use_column_width=True)
            
            if st.button('🔍 Analyze Productivity'):
                image_base64 = get_image_base64(compressed_file)
                
                if image_base64:
                    base64_size = len(image_base64.encode('utf-8'))
                    
                    if base64_size > 262000:
                        st.error(f"Base64 encoded size ({base64_size} bytes) exceeds limit")
                        return
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text('Starting analysis...')
                    result = trigger_analysis(image_base64)
                    
                    if result:
                        with st.container():
                            progress_bar.progress(33)
                            status_text.text('Processing visual analysis...')
                            display_visual_analysis(result.get('visual_analysis'))
                            
                            progress_bar.progress(66)
                            status_text.text('Analyzing activity patterns...')
                            display_activity_pattern(result.get('activity_pattern'))
                            
                            progress_bar.progress(100)
                            status_text.text('Completing productivity assessment...')
                            display_productivity_assessment(result.get('productivity_assessment'))
                            
                            status_text.text('Analysis complete!')
                            
                            report = {
                                'timestamp': datetime.now().isoformat(),
                                'analysis_results': result
                            }
                            st.download_button(
                                label="📥 Download Analysis Report",
                                data=json.dumps(report, indent=2),
                                file_name="productivity_report.json",
                                mime="application/json"
                            )
                    else:
                        st.error("Failed to process the analysis")
                else:
                    st.error("Failed to process the image")

if __name__ == '__main__':
    main()
