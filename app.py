import serial
import numpy as np
import time
from collections import deque, Counter
from fastapi import FastAPI
import threading

# =========================
# 설정
# =========================
SERIAL_PORT = "COM4"
BAUD_RATE = 115200

CSI_LEN = 128
WINDOW_SIZE = 10

RSSI_IN = -36
RSSI_OUT = -44
MOTION_DETECT_TH = 2.0
MOTION_ALERT_TH  = 3.5

# =========================
# FastAPI 앱
# =========================
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 요청 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# 전역 상태 (프론트가 가져갈 값)
current_intrusion = False
current_status = "SAFE"

# =========================
# 유틸 함수
# =========================
def parse_csi_line(line, csi_len=128):
    if not line.startswith("CSI_DATA"):
        return None, None

    parts = line.strip().split(",")
    rssi = None
    csi_values = []

    for p in parts[1:]:
        if p.startswith("RSSI="):
            try:
                rssi = int(p.replace("RSSI=", ""))
            except:
                rssi = None
        else:
            try:
                csi_values.append(int(p))
            except:
                pass

    if rssi is None or len(csi_values) < csi_len:
        return None, None

    return rssi, csi_values[:csi_len]


def csi_to_amp(values, csi_len=128):
    return np.array([
        np.sqrt(values[i] ** 2 + values[i + 1] ** 2)
        for i in range(0, csi_len - 1, 2)
    ])

# =========================
# CSI 처리 스레드
# =========================
def serial_worker():
    global current_intrusion, current_status

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.2)

    rssi_buffer = deque(maxlen=WINDOW_SIZE)
    amp_buffer = deque(maxlen=WINDOW_SIZE)
    state_history = deque(maxlen=7)

    current_zone = "OUT"

    print("=== Zone Detection + API Started ===")

    while True:
        line = ser.readline().decode(errors="ignore").strip()

        rssi, csi = parse_csi_line(line, CSI_LEN)

        if csi is None:
            continue

        amp = csi_to_amp(csi, CSI_LEN)

        rssi_buffer.append(rssi)
        amp_buffer.append(amp)

        if len(amp_buffer) < WINDOW_SIZE:
            continue

        rssi_med = np.median(rssi_buffer)

        w = np.array(amp_buffer)
        mean_over_time = np.mean(w, axis=1)
        motion_score = np.std(mean_over_time)

        # 구역 판정
        if rssi_med > RSSI_IN:
            current_zone = "IN"
        elif rssi_med < RSSI_OUT:
            current_zone = "OUT"
            amp_buffer.clear()
            state_history.clear()

        # 상태 판정
        if current_zone == "OUT":
            raw_state = "SAFE"
        else:
            if motion_score > MOTION_ALERT_TH:
                raw_state = "ALERT"
            elif motion_score > MOTION_DETECT_TH:
                raw_state = "DETECTED"
            else:
                raw_state = "SAFE"

        state_history.append(raw_state)
        final_state = Counter(state_history).most_common(1)[0][0]

        #  프론트로 보낼 값 업데이트
        current_status = final_state
        current_intrusion = True

        print(f"[{time.strftime('%H:%M:%S')}] {final_state} | intrusion={current_intrusion}")


# =========================
# API
# =========================
@app.get("/api/intrusion")
def get_intrusion():
    return {
        "intrusion": True,
        "status": "ALERT"
    }

# =========================
# 실행
# =========================
if __name__ == "__main__":
    # CSI 처리 스레드 시작
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)