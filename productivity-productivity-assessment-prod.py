import boto3
import json

def get_bedrock_client():
    return boto3.client('bedrock-runtime', region_name='us-east-1')

def assess_productivity(activity_data, bedrock):
    try:
        # Define system message
        system_list = [{
            "text": "You are an AI assistant specialized in analyzing productivity patterns and providing detailed assessments with recommendations."
        }]

        # Define user message
        message_list = [{
            "role": "user", 
            "content": [{
                "text": f"""Based on this activity data: {json.dumps(activity_data)}
                
                Analyze the productivity and provide the assessment in this format:
                {{
                    "productivity_score": {{
                        "overall": score_0_to_100,
                        "breakdown": {{
                            "focus": score,
                            "efficiency": score,
                            "task_completion": score
                        }}
                    }},
                    "recommendations": [
                        {{
                            "category": "category",
                            "suggestion": "detailed suggestion",
                            "expected_impact": "predicted improvement"
                        }}
                    ],
                    "productivity_metrics": {{
                        "focus_time_ratio": "percentage",
                        "task_switching_cost": "impact",
                        "productive_hours": "number"
                    }}
                }}"""
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

        # Parse the response as JSON
        try:
            return json.loads(full_response)
        except json.JSONDecodeError:
            return {"error": "Failed to parse response as JSON", "raw_response": full_response}

    except Exception as e:
        print(f"Error in assess_productivity: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        print("Starting productivity assessment")
        print(f"Event: {json.dumps(event)}")
        
        activity_data = event.get('activity_pattern', {})
        bedrock = get_bedrock_client()
        
        assessment = assess_productivity(activity_data, bedrock)
        
        return assessment
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise
