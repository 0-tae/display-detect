### 프로젝트 설명
이 프로젝트는 지정한 화면 영역을 주기적으로 캡처하고, 캡처 이미지에서 템플릿 이미지를 탐지한 뒤 디스코드 채널로 결과를 전송하는 자동화 스크립트입니다.

주요 기능
- 시작 시 1차 사전 탐지 테스트 실행
	- `captured/captured_test.png` 안에서 `search/search_test.png` 탐지 여부를 먼저 확인
	- 콘솔에 PASS/FAIL 출력
- GUI 기반 화면 영역 선택
	- 반투명 전체 화면에서 드래그로 캡처 영역 지정
- 캡처 + 탐지 + 디스코드 전송
	- 캡처 이미지를 `captured` 폴더에 저장
	- `search` 폴더의 템플릿 이미지들과 OpenCV 매칭
	- 기본 캡처 이미지 전송, 탐지 성공 시 추가 알림 전송
- 스케줄 실행
	- 짝수 시간 정각(HH:00)에만 1회 실행


### 실행 방법
1. 라이브러리 설치

```bash
pip install Pillow opencv-python numpy requests
```

2. 디스코드 설정 파일 생성

프로젝트 루트에 `discord.json` 파일을 만들고 아래처럼 입력합니다.

```json
{
	"bot_token": "YOUR_DISCORD_BOT_TOKEN",
	"channel_id": "YOUR_CHANNEL_ID"
}
```

3. 폴더/파일 준비
- `captured/captured_test.png` (1차 테스트용 기준 이미지)
- `search/search_test.png` (1차 테스트용 템플릿 이미지)
- `search` 폴더에는 실제 탐지에 사용할 템플릿 이미지(`.png`, `.jpg`, `.jpeg`)를 추가 가능

4. 실행

```bash
python remind.py
```


### 동작 흐름
1. 프로그램 시작
2. `captured/captured_test.png`와 `search/search_test.png`로 1차 탐지 테스트 수행
3. 콘솔에 탐지 결과 PASS/FAIL 출력
4. `discord.json` 로드(봇 토큰/채널 ID 검증)
5. 반투명 GUI에서 캡처할 화면 영역 선택
6. 선택 즉시 1회 테스트 캡처 실행
	- 이미지 저장
	- 디스코드 전송
	- 템플릿 탐지 후 필요 시 추가 알림 전송
7. 이후 무한 루프 대기
	- 짝수 시간 정각(HH:00)마다 동일 프로세스 1회 실행
