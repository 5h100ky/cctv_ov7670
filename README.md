# RP2040 Zero + OV7670 CCTV 프로젝트

QQVGA(160×120) 그레이스케일 영상을 USB-CDC로 PC에 스트리밍하는 CCTV.

## 파일 구조
```
cctv_ov7670/
├── firmware/
│   ├── main.py        ← RP2040 메인 (MicroPython)
│   └── ov7670.py      ← OV7670 SCCB 드라이버
├── pc_app/
│   ├── viewer.py      ← PC 뷰어 앱
│   └── requirements.txt
└── WIRING.md          ← 배선표
```

## 설치 및 실행

### 1. 펌웨어 (RP2040 Zero)
1. Thonny IDE 또는 mpremote 사용
2. MicroPython 최신 버전 설치 (`RP2040` 빌드)
3. `firmware/ov7670.py`, `firmware/main.py` 를 RP2040에 업로드
4. `main.py` 실행 (또는 `main.py` → `boot.py`로 이름 변경하면 전원 시 자동 실행)

```bash
# mpremote 로 파일 업로드
mpremote cp firmware/ov7670.py :ov7670.py
mpremote cp firmware/main.py   :main.py
mpremote run firmware/main.py
```

### 2. PC 뷰어
```bash
pip install pyserial pillow
python pc_app/viewer.py            # 자동 포트 감지
python pc_app/viewer.py /dev/ttyACM0  # Linux/Mac
python pc_app/viewer.py COM3          # Windows
```

## 동작 방식

```
[OV7670] --PCLK--> [PIO 캡처] --FIFO--> [Python 루프] --USB CDC--> [PC 뷰어]
                                           (Y채널만 추출)      프레임 프로토콜
```

### 프로토콜 (RP2040 → PC)
| 필드 | 크기 | 값 |
|------|------|-----|
| 매직 | 4B | `0xAA 0x55 0xAA 0x55` |
| 폭   | 2B LE | 160 |
| 높이 | 2B LE | 120 |
| 픽셀 | 160×120 B | 그레이스케일 (Y채널) |

## PC 뷰어 기능
- 실시간 라이브 화면 (4배 확대 표시)
- **스냅샷 저장** (JPG/PNG)
- **녹화** → 프레임별 JPEG 저장
- ffmpeg 가 설치돼 있으면 MP4로 자동 변환 제공

## 문제 해결

| 증상 | 확인사항 |
|------|---------|
| `PID=0x00 VER=0x00` | SCCB 배선 확인, 풀업 저항 필요 |
| 화면 완전 검정 | XCLK 출력 확인 (오실로스코프로 GP15), PWDN→GND 확인 |
| 줄무늬/노이즈 | D0-D7 배선 순서 확인, GND 공통 연결 확인 |
| 포트 미감지 | MicroPython USB-CDC 활성화 여부, 드라이버 설치 확인 |
| FPS 매우 낮음 | 정상 (Python 루프로 처리; 1-5 fps 는 CCTV 용도로 충분) |

## 예상 성능
- 해상도: QQVGA 160×120 (그레이스케일)
- 예상 FPS: 1~5 fps (MicroPython 처리 한계)
- USB 전송: USB-CDC (실제 USB Full Speed 12 Mbps)
