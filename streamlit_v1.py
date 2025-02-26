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
API_ENDPOINT = 'https://c4zltovync.execute-api.us-east-1.amazonaws.com/prod/track'

def compress_image(uploaded_file):
    """Compress the image if it's too large"""
    try:
        img = Image.open(uploaded_file)
        
        # Convert to RGB if needed
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
            
        # Calculate target size
        MAX_SIZE = (800, 800)
        img.thumbnail(MAX_SIZE, Image.LANCZOS)
        
        # Save to buffer
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
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
        
    # Check size (API Gateway has a 10MB limit, but we'll use 6MB to be safe)
    size_in_bytes = len(image_base64.encode('utf-8'))
    if size_in_bytes > 6 * 1024 * 1024:  # 6MB
        return False, "Image too large. Please use a smaller image."
        
    return True, ""

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
                return {
                    'status': status,
                    'output': response.get('output')
                }
            elif status in ['FAILED', 'TIMED_OUT', 'ABORTED']:
                return {
                    'status': status,
                    'error': response.get('error')
                }
                
            time.sleep(delay)
            
        except Exception as e:
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
    # Validate input first
    is_valid, error_message = validate_input(image_base64)
    if not is_valid:
        st.error(error_message)
        return None

    try:
        # Format the input payload according to Step Functions requirements
        payload = {
            "input": json.dumps({
                "screenshot_url": f"s3://employee-productivity-screenshots-prod/{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.png",
                "image_data": image_base64
            })
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
                    st.info(f"Analysis started. Execution ARN: {execution_arn}")
                    
                    # Poll for execution status
                    with st.spinner('Waiting for analysis to complete...'):
                        status = poll_execution_status(execution_arn)
                        if status.get('status') == 'SUCCEEDED':
                            output = json.loads(status.get('output', '{}'))
                            return {
                                'visual_analysis': output.get('visual_analysis', {}),
                                'activity_pattern': output.get('activity_pattern', {}),
                                'productivity_assessment': output.get('productivity_assessment', {})
                            }
                        else:
                            st.error(f"Analysis failed: {status.get('error')}")
                            return None
                else:
                    st.error("No execution ARN received")
                    return None
            else:
                st.error(f"Error: API returned status code {response.status_code}")
                st.error(f"Response: {response.text}")
                return None
                
    except Exception as e:
        st.error(f"Error triggering analysis: {str(e)}")
        return None

def display_visual_analysis(analysis_data):
    """Display Visual Analysis Results"""
    st.subheader("📸 Visual Analysis Results")
    
    if not analysis_data:
        st.warning("No visual analysis data available")
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
        st.info(analysis_data.get('timestamp', 'No timestamp detected'))
        
        st.markdown("### 💼 Work Type")
        st.info(analysis_data.get('work_type', 'Unknown work type'))
    
    if analysis_data.get('interactions'):
        st.markdown("### 🖱️ User Interactions")
        for interaction in analysis_data['interactions']:
            st.markdown(f"- {interaction}")

def display_activity_pattern(pattern_data):
    """Display Activity Pattern Results"""
    st.subheader("📊 Activity Pattern Analysis")
    
    if not pattern_data:
        st.warning("No activity pattern data available")
        return
    
    # Activity Summary
    st.markdown("### 📝 Summary")
    st.info(pattern_data.get('activity_summary', 'No summary available'))
    
    # Timeline
    if timeline_data := pattern_data.get('timeline', []):
        st.markdown("### ⏱️ Activity Timeline")
        df = pd.DataFrame(timeline_data)
        st.dataframe(df)
    
    # Productivity Indicators
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
    
    if not assessment_data:
        st.warning("No productivity assessment data available")
        return
    
    # Overall Score
    score = assessment_data.get('productivity_score', {})
    overall_score = score.get('overall', 0)
    
    # Display overall score
    st.markdown("### Overall Score")
    st.progress(overall_score / 100)
    st.metric("Productivity Score", f"{overall_score}%")
    
    # Score Breakdown
    if 'breakdown' in score:
        st.markdown("### 🎯 Score Breakdown")
        col1, col2, col3 = st.columns(3)
        breakdown = score['breakdown']
        
        for (category, value), col in zip(breakdown.items(), [col1, col2, col3]):
            with col:
                st.metric(category, f"{value}%")
    
    # Recommendations
    if recommendations := assessment_data.get('recommendations', []):
        st.markdown("### 💡 Recommendations")
        for rec in recommendations:
            with st.expander(f"📌 {rec['category']}"):
                st.write(f"**Suggestion:** {rec['suggestion']}")
                st.write(f"**Expected Impact:** {rec['expected_impact']}")
    
    # Metrics
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
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload Screenshot",
        type=['png', 'jpg', 'jpeg'],
        help="Upload a screenshot to analyze productivity"
    )
    
    if uploaded_file is not None:
        # Compress and display the uploaded image
        compressed_file = compress_image(uploaded_file)
        if compressed_file:
            st.image(compressed_file, caption='Uploaded Screenshot', use_container_width=True)
            
            if st.button('🔍 Analyze Productivity'):
                image_base64 = base64.b64encode(compressed_file.getvalue()).decode()
                
                if image_base64:
                    # Create progress indicators
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Trigger analysis workflow
                    status_text.text('Starting analysis...')
                    result = trigger_analysis(image_base64)
                    
                    if result:
                        # Display results
                        with st.container():
                            progress_bar.progress(33)
                            status_text.text('Processing visual analysis...')
                            display_visual_analysis(result['visual_analysis'])
                            
                            progress_bar.progress(66)
                            status_text.text('Analyzing activity patterns...')
                            display_activity_pattern(result['activity_pattern'])
                            
                            progress_bar.progress(100)
                            status_text.text('Completing productivity assessment...')
                            display_productivity_assessment(result['productivity_assessment'])
                            
                            status_text.text('Analysis complete!')
                            
                            # Add download button for report
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
