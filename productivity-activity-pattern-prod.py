import boto3
import json
from datetime import datetime

def get_bedrock_client():
    return boto3.client('bedrock-runtime', region_name='us-east-1')

def analyze_productivity(visual_data, bedrock):
    try:
        # Define system message
        system_list = [{
            "text": "You are an AI assistant specialized in analyzing employee productivity based on screen activity and application usage patterns."
        }]

        # Extract the actual content from the nested structure
        content_text = ""
        if isinstance(visual_data, dict):
            if 'output' in visual_data:
                message = visual_data.get('output', {}).get('message', {})
                content = message.get('content', [])
                if content and isinstance(content, list):
                    content_text = content[0].get('text', '')

        # Define user message
        message_list = [{
            "role": "user", 
            "content": [{
                "text": f"""Based on this screen activity data: {content_text}

                Please analyze the employee's productivity and provide:
                
                1. Productivity Summary:
                   - Analyze the type of work being done
                   - Assess the level of task organization
                   - Evaluate the tools and applications being used
                   - Identify any potential productivity patterns
                
                2. Key Metrics:
                   - Work Focus Areas:
                   - Tool Usage Distribution:
                   - Task Organization Score (1-10):
                   - Development Environment Efficiency:
                
                3. Recommendations:
                   - Suggest improvements for workflow
                   - Identify potential productivity bottlenecks
                   - Recommend tool optimizations
                
                Format the response in a clear, analytical manner focusing on productivity insights.
                """
            }]
        }]

        # Configure inference parameters
        inference_config = {
            "maxTokens": 4096,
            "temperature": 0.7,
            "topP": 0.8
        }

        # Prepare request body
        request_body = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": inference_config
        }

        # Invoke the model with streaming response
        response = bedrock.invoke_model_with_response_stream(
            modelId="us.amazon.nova-lite-v1:0",
            body=json.dumps(request_body)
        )

        # Process the response stream
        full_response = ""
        stream = response.get("body")
        if stream:
            for event in stream:
                chunk = event.get("chunk")
                if chunk:
                    chunk_json = json.loads(chunk.get("bytes").decode())
                    content_block_delta = chunk_json.get("contentBlockDelta")
                    if content_block_delta:
                        full_response += content_block_delta.get("delta", {}).get("text", "")

        current_time = datetime.now().isoformat()

        # Structure the response
        return {
            "productivity_analysis": {
                "analysis": full_response,
                "timestamp": current_time,
                "analysis_type": "productivity_assessment",
                "status": "completed"
            }
        }
    except Exception as e:
        current_time = datetime.now().isoformat()
        print(f"Error in analyze_productivity: {str(e)}")
        return {
            "productivity_analysis": {
                "error": str(e),
                "timestamp": current_time,
                "status": "failed"
            }
        }

def lambda_handler(event, context):
    try:
        print("Starting productivity analysis")
        print(f"Event: {json.dumps(event)}")
        
        visual_data = event
        bedrock = get_bedrock_client()
        
        analysis_result = analyze_productivity(visual_data, bedrock)
        
        return analysis_result
        
    except Exception as e:
        current_time = datetime.now().isoformat()
        print(f"Error in lambda_handler: {str(e)}")
        return {
            "error": str(e),
            "timestamp": current_time,
            "status": "failed"
        }
