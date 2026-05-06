import serial
import numpy as np
import time
from collections import deque, Counter
from utils import parse_csi_line, csi_to_amp

SERIAL_PORT = "COM6"
BAUD_RATE = 115200

CSI_LEN = 128
WINDOW_SIZE = 10 #버퍼멈춤 해결하려고 조정

# 현장에서 값 조정
RSSI_IN = -75       # 이보다 크면 구역 안 후보
RSSI_OUT = -85     # 이보다 작으면 구역 밖 후보
MOTION_ON_TH = 1.3
MOTION_OFF_TH = 0.9
MOTION_ON_CONSEC = 1
MOTION_OFF_CONSEC = 2


ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.05)

rssi_buffer = deque(maxlen=WINDOW_SIZE)
amp_buffer = deque(maxlen=WINDOW_SIZE)
state_history = deque(maxlen=7)

current_zone = "IN"
motion_active = False
motion_on_count = 0
motion_off_count = 0

print("=== Zone Detection Demo Started ===")

def detect_intrusion():
    print("DETECT FUNCTION STARTED")
    global current_zone, rssi_buffer, amp_buffer, state_history
    global motion_active, motion_on_count, motion_off_count

    valid_data_found = False

    for _ in range(50):   # 여러 줄 시도
        line = ser.readline().decode(errors="ignore").strip()
        print("LINE:", repr(line))
        if not line or not line.startswith("CSI_DATA"):
            continue   # ✅ 이게 맞음
    
        print("RAW:", repr(line))

        if not line:
            continue

        rssi, csi = parse_csi_line(line, CSI_LEN)
        print("RSSI:", rssi, "CSI len:", len(csi) if csi else None)

        if csi is None:
            continue

        valid_data_found = True
        break   # 유효한 데이터 찾으면 탈출

    # 👇 for문 밖에서 체크해야 함
    if not valid_data_found:
        return motion_active

    amp = csi_to_amp(csi, CSI_LEN)

    rssi_buffer.append(rssi)
    amp_buffer.append(amp)

    if len(amp_buffer) < WINDOW_SIZE:
        return motion_active

    rssi_med = np.median(rssi_buffer)

    w = np.array(amp_buffer)
    # 프레임 간 차이 계산
    diff = np.diff(w, axis=0)

    # 변화량 기준 motion
    motion_score = np.median(np.abs(diff))
    
    print("motion:", motion_score, "RSSI:", rssi_med)
    
    if rssi_med > RSSI_IN:
        current_zone = "IN"
    elif rssi_med < RSSI_OUT:
        current_zone = "OUT"
        amp_buffer.clear()
        state_history.clear()
        motion_active = False
        motion_on_count = 0
        motion_off_count = 0

    # 히스테리시스 + 연속 프레임 확인으로 true/false가 안정적으로 전환되도록 처리
    if current_zone == "OUT":
        motion_active = False
        motion_on_count = 0
        motion_off_count = 0
    else:
        if motion_score >= MOTION_ON_TH:
            motion_on_count += 1
            motion_off_count = 0
        elif motion_score <= MOTION_OFF_TH:
            motion_off_count += 1
            motion_on_count = 0
        else:
            # 상태 유지 구간 → 카운트는 유지 (초기화 금지)
            pass

        if not motion_active and motion_on_count >= MOTION_ON_CONSEC:
            motion_active = True
        elif motion_active and motion_off_count >= MOTION_OFF_CONSEC:
            motion_active = False

    print("FINAL RESULT:", motion_active)
    return motion_active