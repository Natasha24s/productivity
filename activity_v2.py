import boto3
import json
from datetime import datetime

def get_bedrock_client():
    return boto3.client('bedrock-runtime', region_name='us-east-1')

def analyze_productivity(visual_data, bedrock):
    try:
        # Extract content from nested structure
        content_text = ""
        if isinstance(visual_data, dict):
            if 'output' in visual_data:
                message = visual_data.get('output', {}).get('message', {})
                content = message.get('content', [])
                if content and isinstance(content, list):
                    content_text = content[0].get('text', '')

        # Simplified prompt for concise summary
        message_list = [{
            "role": "user", 
            "content": [{
                "text": f"""Based on this screen activity data: {content_text}
                Provide a single paragraph summary of the employee's activities and productivity level.
                Keep it concise and focus on key observations only."""
            }]
        }]

        # Configure inference parameters
        request_body = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": [{"text": "You are a concise productivity analyzer."}],
            "inferenceConfig": {
                "maxTokens": 200,
                "temperature": 0.7,
                "topP": 0.8
            }
        }

        # Get response from Bedrock
        response = bedrock.invoke_model_with_response_stream(
            modelId="us.amazon.nova-lite-v1:0",
            body=json.dumps(request_body)
        )

        # Process stream
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

        return {
            "productivity_analysis": {
                "summary": full_response,
                "timestamp": current_time,
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
        bedrock = get_bedrock_client()
        analysis_result = analyze_productivity(event, bedrock)
        return analysis_result
    except Exception as e:
        current_time = datetime.now().isoformat()
        return {
            "error": str(e),
            "timestamp": current_time,
            "status": "failed"
        }
