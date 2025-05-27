import requests
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading
import time

# 카카오 API 설정
CLIENT_ID = "0b74bc4a45114f02d98231b1606e79cd"
REDIRECT_URI = "http://localhost:8080/oauth"
# 필요한 권한 스코프 추가
SCOPE = "talk_message"

# 인증 코드를 받기 위한 웹 서버 핸들러
class KakaoAuthHandler(BaseHTTPRequestHandler):
    code = None
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # URL에서 인증 코드 추출
        query = urlparse(self.path).query
        if query:
            query_components = parse_qs(query)
            if 'code' in query_components:
                KakaoAuthHandler.code = query_components['code'][0]
                html = f"""
                <html>
                <head><title>카카오 인증 성공</title></head>
                <body>
                    <h1>인증에 성공했습니다!</h1>
                    <p>인증 코드: {KakaoAuthHandler.code}</p>
                    <p>이 창을 닫아도 됩니다.</p>
                </body>
                </html>
                """
            else:
                html = """
                <html>
                <head><title>인증 실패</title></head>
                <body>
                    <h1>인증 코드를 찾을 수 없습니다</h1>
                    <p>다시 시도해주세요.</p>
                </body>
                </html>
                """
        else:
            html = """
            <html>
            <head><title>인증 실패</title></head>
            <body>
                <h1>인증 코드를 찾을 수 없습니다</h1>
                <p>다시 시도해주세요.</p>
            </body>
            </html>
            """
            
        self.wfile.write(html.encode())

def get_auth_code():
    """웹 서버를 실행하고 카카오 인증 코드를 받아옵니다."""
    # 로컬 웹 서버 시작
    server = HTTPServer(('localhost', 8080), KakaoAuthHandler)
    print("로컬 서버가 시작되었습니다...")
    
    # 비동기적으로 서버 실행
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # 인증 URL 열기 (scope 파라미터 추가)
    auth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}"
    print(f"카카오 인증 페이지를 엽니다: {auth_url}")
    webbrowser.open(auth_url)
    
    # 인증 코드 대기
    start_time = time.time()
    timeout = 60  # 60초 대기
    
    while KakaoAuthHandler.code is None:
        if time.time() - start_time > timeout:
            print("시간 초과: 인증 코드를 받지 못했습니다.")
            server.shutdown()
            return None
        time.sleep(1)
        
    # 인증 코드를 받았으면 서버 종료
    server.shutdown()
    return KakaoAuthHandler.code

def get_tokens(auth_code):
    """인증 코드로 액세스 토큰과 리프레시 토큰을 받아옵니다."""
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": auth_code
    }
    
    response = requests.post(url, data=data)
    if response.status_code == 200:
        token_data = response.json()
        print("토큰 발급 성공!")
        return token_data
    else:
        print(f"토큰 발급 실패: {response.text}")
        return None

def save_tokens_to_file(token_data, filename="kakao_token.json"):
    """토큰 정보를 파일로 저장합니다."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)
    print(f"토큰이 {filename}에 저장되었습니다.")

def main():
    """메인 함수: 카카오 인증 수행"""
    print("카카오 인증을 시작합니다...")
    auth_code = get_auth_code()
    
    if auth_code:
        print(f"인증 코드를 받았습니다: {auth_code}")
        token_data = get_tokens(auth_code)
        
        if token_data:
            save_tokens_to_file(token_data)
            print("카카오 인증이 완료되었습니다!")
            
            # 토큰 권한 확인
            access_token = token_data.get("access_token")
            if access_token:
                check_token_info(access_token)
    else:
        print("인증에 실패했습니다.")

def check_token_info(access_token):
    """토큰 정보 확인"""
    url = "https://kapi.kakao.com/v1/user/access_token_info"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        token_info = response.json()
        print("토큰 정보:")
        print(json.dumps(token_info, indent=2, ensure_ascii=False))
    else:
        print(f"토큰 정보 확인 실패: {response.text}")
    
    # 사용자 권한 확인
    url = "https://kapi.kakao.com/v2/user/scopes"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        scope_info = response.json()
        print("\n사용자 권한 정보:")
        print(json.dumps(scope_info, indent=2, ensure_ascii=False))
    else:
        print(f"사용자 권한 확인 실패: {response.text}")

if __name__ == "__main__":
    main()
