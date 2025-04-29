# lambda/index.py
import json
import os
import urllib.request
import urllib.error
import traceback

def lambda_handler(event, context):
    api_endpoint_base = os.environ.get("NGROK_API_ENDPOINT")
    
    try:
        if not api_endpoint_base:
            print("エラー: 環境変数 'NGROK_API_ENDPOINT' が設定されていません。")
            raise ValueError("API エンドポイントが Lambda 環境変数に設定されていません。")
            
        api_url = f"{api_endpoint_base.rstrip('/')}/generate"
        print(f"Target API URL: {api_url}")

        print("Received event:", json.dumps(event))

        try:
            body = json.loads(event['body'])
            message = body['message']
            conversation_history = body.get('conversationHistory', [])
            if not isinstance(message, str) or not message:
                 raise ValueError("リクエストボディに有効な 'message' が含まれていません。")
            if not isinstance(conversation_history, list):
                 raise ValueError("'conversationHistory' はリスト形式である必要があります。")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"リクエストボディの解析エラー: {e}")
            raise ValueError(f"無効なリクエストボディです: {str(e)}") from e

        print(f"Processing message: {message}")

        request_data = {
            "prompt": message,
            "max_new_tokens": 512, 
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }
        json_data = json.dumps(request_data).encode('utf-8')
        print(f"Payload for FastAPI: {request_data}")

        req = urllib.request.Request(
            api_url,
            data=json_data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'AWS-Lambda-Client/1.0'},
            method='POST'
        )

        assistant_response = None

        try:
            print(f"Calling FastAPI: POST {api_url}")
            with urllib.request.urlopen(req, timeout=30) as response:
                status_code = response.getcode()
                response_body_bytes = response.read()
                response_body_str = response_body_bytes.decode('utf-8')
                print(f"Received response: Status={status_code}, Body={response_body_str[:500]}...")

                if status_code == 200:
                    response_data = json.loads(response_body_str)
                    assistant_response = response_data.get("generated_text") 
                    if assistant_response is None:
                         print("エラー: API応答に 'generated_text' が見つかりません。")
                         raise ValueError("カスタムAPIからの応答形式が無効です")
                    print(f"Extracted assistant response (first 100 chars): {assistant_response[:100]}...")
                else:
                    print(f"エラー: カスタムAPIがステータス {status_code} を返しました。 Body: {response_body_str}")
                    raise urllib.error.HTTPError(api_url, status_code, f"API Error {status_code}", response.headers, response.fp)

        except urllib.error.HTTPError as e:
            error_body = "N/A"
            try:
                error_body = e.read().decode('utf-8')
            except Exception:
                pass
            print(f"カスタムAPI呼び出し中のHTTPエラー: {e.code} - {error_body}")
            raise Exception(f"モデルAPIとの通信エラーが発生しました (HTTP {e.code})。") from e
        except urllib.error.URLError as e:
            print(f"カスタムAPI呼び出し中のURLエラー: {e.reason}")
            raise Exception(f"モデルAPIへの接続に失敗しました ({e.reason})。") from e
        except json.JSONDecodeError:
            print(f"API応答のJSONデコードエラー: {response_body_str}")
            raise ValueError("モデルAPIからの応答を解析できませんでした。") from None

        messages = conversation_history.copy()
        messages.append({
            "role": "user",
            "content": message
        })
        messages.append({
            "role": "assistant",
            "content": assistant_response 
        })

        print("処理成功。応答を返します。")
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

    except ValueError as ve:
        print(f"入力または形式のエラー: {ve}")
        return {
            "statusCode": 400, 
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(ve)
            })
        }
    except Exception as error:
        print(f"Lambdaハンドラで予期せぬエラー発生: {error}")
        traceback.print_exc()

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
                "error": "サーバー内部でエラーが発生しました。"
            })
        }