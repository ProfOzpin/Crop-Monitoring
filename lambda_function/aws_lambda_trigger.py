import boto3
import json
from datetime import datetime, timedelta

def test_lambda_processing():
    """Test Lambda function with different scenarios"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    test_scenarios = [
        {
            'name': 'Recent Scene',
            'params': {
                'start_date': '2024-07-01',
                'end_date': '2024-07-31'
            }
        },
        {
            'name': 'Winter Scene',
            'params': {
                'start_date': '2024-01-01', 
                'end_date': '2024-01-31'
            }
        },
        {
            'name': 'Spring Scene',
            'params': {
                'start_date': '2024-04-01',
                'end_date': '2024-04-30'
            }
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n🧪 Testing: {scenario['name']}")
        
        try:
            response = lambda_client.invoke(
                FunctionName='uae-satellite-processor',
                InvocationType='RequestResponse',
                Payload=json.dumps(scenario['params'])
            )
            
            result = json.loads(response['Payload'].read())
            print(f"✓ {scenario['name']}: {result.get('statusCode', 'Unknown')}")
            
            if result.get('statusCode') == 200:
                body = json.loads(result['body'])
                scene_id = body.get('result', {}).get('scene_id', 'Unknown')
                print(f"  Scene: {scene_id}")
            
        except Exception as e:
            print(f"❌ {scenario['name']} failed: {e}")

if __name__ == "__main__":
    test_lambda_processing()
