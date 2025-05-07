# lambda/index.py
import json
import os
import boto3
import re  # 正規表現モジュールをインポート
from botocore.exceptions import ClientError
import urllib.request
import urllib.error


# Lambda コンテキストからリージョンを抽出する関数
def extract_region_from_arn(arn):
    # ARN 形式: arn:aws:lambda:region:account-id:function:function-name
    match = re.search('arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "us-east-1"  # デフォルト値

# グローバル変数としてクライアントを初期化（初期値）
bedrock_client = None

# モデルID
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")

# 外部APIの呼び出し (改善版)
def call_external_api():
    api_endpoint_base = os.environ.get("NGROK_ENDPOINT")
    if not api_endpoint_base:
        print("エラー: 環境変数 'NGROK_ENDPOINT' が設定されていません。")
        raise ValueError("API エンドポイントが Lambda 環境変数に設定されていません。")
    
    api_url = f"{api_endpoint_base.rstrip('/')}/generate"
    print(f"Target API URL: {api_url}")

    payload = {'message': 'From Lambda'}
    headers = {'Content-Type': 'application/json'}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            print(f"Response from external API: {response_data[:300]}...")
            return json.loads(response_data)

    except urllib.error.HTTPError as http_err:
        status_code = http_err.code
        try:
            error_body = http_err.read().decode('utf-8')
        except Exception:
            error_body = "(レスポンスボディの読み取りに失敗)"

        print(f"HTTPError: Status {status_code}")
        print(f"Response Body: {error_body}")

        if status_code == 422:
            print("⚠️ 外部APIが HTTP 422 Unprocessable Entity を返しました。リクエスト内容を確認してください。")
        raise Exception(f"外部API呼び出しに失敗しました (HTTP {status_code}): {error_body}")

    except urllib.error.URLError as url_err:
        print(f"URLError: {url_err.reason}")
        raise Exception(f"外部APIへの接続に失敗しました: {url_err.reason}")

    except json.JSONDecodeError:
        print("⚠️ 外部APIからのレスポンスがJSONとして解析できませんでした。")
        raise Exception("外部APIのレスポンスが無効なJSON形式です。")

    except Exception as e:
        print(f"予期しないエラー: {e}")
        raise Exception("外部API呼び出し中に予期しないエラーが発生しました。")



def lambda_handler(event, context):
    try:
        print("Received event:", json.dumps(event))

        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")

        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])

        print("Processing message:", message)

        messages = conversation_history.copy()
        messages.append({"role": "user", "content": message})

        external_response = call_external_api()
        if not external_response:
            raise Exception("No response from external API")

        assistant_response = external_response.get('response', 'Default response from API')

        messages.append({"role": "assistant", "content": assistant_response})

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                "conversationHistory": messages
            })
        }

    except Exception as error:
        print("Error:", str(error))
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(error)
            })
        }