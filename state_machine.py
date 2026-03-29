# state_machine.py
import time
import logging
import subprocess
from PIL import Image
import io
import os
import json
import image_utils
import adb_utils
import datetime
from appium import webdriver
from appium.webdriver.webdriver import AppiumOptions


def create_driver(device_name):
    config_path = 'config.json'
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"필수 설정 파일이 없습니다: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        conf = json.load(f)
    
    # 세션 끊겼을 때 앱 안 죽이고 다시 붙는 용도
    options = AppiumOptions()
    options.set_capability('automationName', 'uiautomator2')
    options.set_capability('deviceName', device_name)
    options.set_capability('platformName', 'Android')
    options.set_capability('appPackage', 'com.epidgames.trickcalrevive')
    options.set_capability('noReset', True)
    options.set_capability('fullReset', False)
    options.set_capability('newCommandTimeout', 300)
    options.set_capability('adbExecTimeout', 60000)
    options.set_capability('appium:uiautomator2ServerReadTimeout', 60000)
    options.set_capability('uiautomator2ServerLaunchTimeout', 90000)

    logging.info(f"드라이버 세션 재연결 시도 중... ({device_name})")

    driver = webdriver.Remote("http://127.0.0.1:4723", options=options)

    actual_name = driver.capabilities.get('deviceName')
    driver.adb_id = actual_name
    device_model = driver.capabilities.get('deviceModel')
    driver.model_name = device_model
    driver.states = conf['ui_states']
    driver.actions = conf['actions']
    driver.dev_cfg = conf['devices'].get(driver.model_name, conf['devices']['DEFAULT'])

    print(f"device_name: {device_name}")
    print(f"dev_cfg: {driver.dev_cfg}")


    size = driver.get_window_size()
    # 두 값 중 큰 값을 무조건 W로 할당하여 회전 이슈 방어
    raw_w, raw_h = size['width'], size['height']
    driver.W = max(raw_w, raw_h)
    driver.H = min(raw_w, raw_h)

    return driver

def tap_by_coordinates(driver, x, y):
    x, y = int(x), int(y)
    driver.tap([(x, y)])

    logging.info(f"터치 좌표: ({x}, {y})")

def scroll_by_coordinates(driver, coordinate, duration_ms=300):
    try:
        start_x, start_y = int(coordinate[0][0]), int(coordinate[0][1])
        end_x, end_y = int(coordinate[1][0]), int(coordinate[1][1])

        logging.info(f"스크롤 시도: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
        
        # ActionBuilder 쓰면 속도가 일정하지 않아서 swipe 직접 호출
        driver.swipe(start_x, start_y, end_x, end_y, duration_ms)
        
        logging.info("스크롤 명령 전송 완료")
    except Exception as e:
        logging.error(f"스크롤 함수 내부에서 die: {e}")


def force_focus(driver, package_name):
    cmd = ["adb", "-s", driver.adb_id, "shell", "monkey", "-p", package_name, 
           "-c", "android.intent.category.LAUNCHER", "1"]
    subprocess.run(cmd, capture_output=True)

# 엘레나 감지>팝업감지>다시 시도 클릭>팝업, 엘라나 사라졌는지 탐지>기존 화면으로 되돌아감
def handle_network(driver):
    tx = int(driver.W * 0.593)
    ty = int(driver.H * 0.690)

    logging.info(f"네트워크 팝업 대응: ({tx}, {ty}) 클릭")
    tap_by_coordinates(driver, tx, ty)
    time.sleep(3)

    state, _ = detect_state(driver)
    return state

def handle_title(driver, state, package):
    act = driver.actions

    x_steps = list(range(act['TITLE_SCAN_X'][0], act['TITLE_SCAN_X'][1], act['TITLE_SCAN_X'][2]))
    y_steps = list(range(act['TITLE_SCAN_Y'][0], act['TITLE_SCAN_Y'][1], act['TITLE_SCAN_Y'][2]))

    logging.info(f"현재 위치: {state} | 동작: 터치")
    for y_s in y_steps:
        for x_s in x_steps:
            tx = int(driver.W * x_s / 100)
            ty = int(driver.H * y_s / 100)

            # if driver.adb_id == "emulator-5554":
            #     force_focus(driver, package)
            #     time.sleep(0.5)
            print("터치 위치: ", tx, ty)
            tap_by_coordinates(driver, tx, ty)
            time.sleep(2)
            
            state, _ = detect_state(driver)
            if state != "TITLE":
                logging.info("타이틀 화면 종료 감지")
                return
    logging.warning("타이틀 화면의 모든 좌표를 터치했으나 상태가 변하지 않음")

def handle_lobby(driver, state):
    act = driver.actions
    
    logging.info(f"현재 위치: {state} | 동작: 터치")
    
    tx = int(driver.W * act['LOBBY_TO_CHAR']["x"])
    ty = int(driver.H * act['LOBBY_TO_CHAR']["y"])

    print("터치 위치: ", tx, ty)
    tap_by_coordinates(driver, tx, ty)
    time.sleep(3)

    state, _ = detect_state(driver)
    if state != "LOBBY":
        return state
    return state


def handle_character(driver, state, package):
    act = driver.actions

    logging.info(f"현재 위치: {state} | 동작: 스크롤")
    time.sleep(1.5)
    
    mid_x = int(driver.W * act['SCROLL_START']["x"])
    top_y = int(driver.H * act['SCROLL_END']["y"])
    bottom_y = int(driver.H * act['SCROLL_START']["y"])

    scroll_points = [[mid_x, bottom_y], [mid_x, top_y]]
    
    for _ in range(3):
        # if driver.adb_id == "127.0.0.1:5555":
        #     force_focus(driver, package)
        #     time.sleep(0.5)
        scroll_by_coordinates(driver, scroll_points)
        time.sleep(0.5)

    scroll_points.reverse()
    for _ in range(3):
        # if driver.adb_id == "127.0.0.1:5555":
        #     force_focus(driver, package)
        #     time.sleep(0.5)
        scroll_by_coordinates(driver, scroll_points)
        time.sleep(0.5)
    
    tx = int(driver.W * act['BTN_BACK']["x"])
    ty = int(driver.H * act['BTN_BACK']["y"])

    logging.info(f"돌아가기 버튼 클릭 시도: ({tx}, {ty})")
    tap_by_coordinates(driver, tx, ty)

    time.sleep(2)
    new_state, _ = detect_state(driver)
    if new_state == 'LOBBY':
        new_state = 'LOBBY SLEEP'
    return new_state


def handle_exception(driver, iteration, state, package, log_dir):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    adb_id = driver.adb_id

    is_alive_res = subprocess.run(
        ["adb", "-s", adb_id, "shell", f"pidof {package}"],
        capture_output=True, text=True
    ).stdout.strip()
    is_alive = bool(is_alive_res)

    prefix = "ERROR" if is_alive else "DEATH_SCENE"
    screenshot_file = f"{log_dir}/{prefix}_{iteration}_{state}_{timestamp}.png"
    
    subprocess.run(f"adb -s {adb_id} shell screencap -p /sdcard/last_screen.png", shell=True)
    subprocess.run(f"adb -s {adb_id} pull /sdcard/last_screen.png {screenshot_file}", shell=True)
    
    logcat = subprocess.run(["adb", "-s", adb_id, "logcat", "-d", "*:V"], capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    cpu_dump = subprocess.run(["adb", "-s", adb_id, "shell", "top", "-n", "1", "-b"], capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    mem_dump = subprocess.run(["adb", "-s", adb_id, "shell", "dumpsys", "meminfo", package], capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    gfx_dump = subprocess.run(["adb", "-s", adb_id, "shell", "dumpsys", "gfxinfo", package], capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    lmk_logs = subprocess.run(["adb", "-s", adb_id, "shell", "logcat -d -t 5000 | grep -Ei 'lowmemorykiller|Killing|ZuiMemoryCleaner'"], capture_output=True, text=True, shell=True, encoding="utf-8", errors="ignore").stdout
    
    # 로그 파일 작성
    dumps = {
        "cpu": cpu_dump,
        "mem": mem_dump,
        "gfx": gfx_dump,
        "lmk": lmk_logs,
        "logcat": logcat,
    }

    for name, content in dumps.items():
        path = f"{log_dir}/{name}_{iteration}_{state}_{timestamp}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=== DEVICE: {adb_id} | ALIVE: {is_alive} ===\n")
            f.write(content)
        logging.error(f"[EXCEPTION] {name} 로그 저장: {path}")


    logging.error(
        f"[EXCEPTION] iter={iteration}, state={state}, "
        f"screenshot={screenshot_file}, logcat={logcat}"
    )
    
    if is_alive:
        logging.warning(f"[RECOVERY] 앱 생존. 세션 초기화 진행.")
        subprocess.run(["adb", "-s", adb_id, "shell", "am", "force-stop", "io.appium.uiautomator2.server"])
        return False
    else:
        logging.error(f"[CRITICAL] 앱({package}) 종료 감지. 원인 파악 및 재시작 준비.")
        
        exit_reason = subprocess.run(
            ["adb", "-s", adb_id, "shell", "am", "get-historical-process-exit-reasons", package],
            capture_output=True, text=True, encoding="utf-8", errors="ignore"
        ).stdout

        logcat_path = f"{log_dir}/logcat_{iteration}_{state}_{timestamp}.txt"
        with open(logcat_path, "a", encoding="utf-8") as f:
            f.write("\n" + "="*50 + "\n")
            f.write("--- [ OS OFFICIAL EXIT REASON (LATEST) ] ---\n")
            f.write(exit_reason)

        subprocess.run(["adb", "-s", adb_id, "shell", "am", "force-stop", package])
        subprocess.run(["adb", "-s", adb_id, "shell", "am", "force-stop", "io.appium.uiautomator2.server"])
        
        return True

# 상태 감지
def detect_state(driver):
    try:
        raw_bytes = adb_utils.get_screenshot_via_adb(driver)
        if not raw_bytes or len(raw_bytes) < 1000: # 너무 작으면 정상 PNG가 아님
            logging.warning("스크린샷 데이터를 받지 못했습니다. 재시도합니다.")
            return "UNKNOWN", None
        act = driver.states
        with Image.open(io.BytesIO(raw_bytes)) as img:
            w, h = img.size
            print(w, h )
            # 타이틀 컬러 값, 위치 좌표
            title_ratio = act["TITLE"]["ratio"]
            title_rgb = act["TITLE"]["rgb"]
            # 로딩 컬러 값, 위치 좌표
            loading_ratio = act["LOADING"]["ratio"]
            loading_rgb = act["LOADING"]["rgb"]
            # 로비 컬러 값, 위치 좌표
            lobby_ratio = act["LOBBY"]["ratio"]
            lobby_rgb = act["LOBBY"]["rgb"]
            # 사도 컬러 값, 위치 좌표
            char_ratio = act["CHARACTER"]["ratio"]
            char_rgb =  act["CHARACTER"]["rgb"]
            # 네트워크 대기 및 팝업 컬러 값, 위치 좌표 
            network_ratio =  act["NETWORK"]["ratio"]
            network_rgb = act["NETWORK"]["rgb"]
            popup_ratio =act["POPUP"]["ratio"]
            popup_rgb =  act["POPUP"]["rgb"]

            tx, ty = int(w * title_ratio[0]), int(h * title_ratio[1])
            ldx, ldy = int(w * loading_ratio[0]), int(h * loading_ratio[1])
            lbx, lby = int(w * lobby_ratio[0]), int(h * lobby_ratio[1])
            cx, cy = int(w * char_ratio[0]), int(h * char_ratio[1])
            nx, ny = int(w * network_ratio[0]), int(h * network_ratio[1])
            px, py = int(w * popup_ratio[0]), int(h * popup_ratio[1])

            cfg = driver.dev_cfg
            lby += cfg.get('lby_offset', 0)
            cy += cfg.get('cy_offset', 0)

            avg_t = image_utils.get_pixel_average(img, tx, ty)
            avg_ld = image_utils.get_pixel_average(img, ldx, ldy)
            avg_lb = image_utils.get_pixel_average(img, lbx, lby)
            avg_c = image_utils.get_pixel_average(img, cx, cy)
            avg_n = image_utils.get_pixel_average(img, nx, ny)
            avg_p = image_utils.get_pixel_average(img, px, py)



            if image_utils.is_color_match(avg_p, popup_rgb, 40):
                return "POPUP", raw_bytes
            
            elif image_utils.is_color_match(avg_n, network_rgb, 13):
                return "NETWORK", raw_bytes
            
            elif image_utils.is_color_match(avg_t, title_rgb, 45):
                return "TITLE", raw_bytes

            elif image_utils.is_color_match(avg_ld, loading_rgb, 40):
                return "LOADING", raw_bytes
            
            elif image_utils.is_color_match(avg_lb, lobby_rgb, 40):
                return "LOBBY", raw_bytes
            
            elif image_utils.is_color_match(avg_c, char_rgb, 50):
                text = image_utils.get_text_from_character(driver, img)
                logging.info(text)
                if text and isinstance(text, str):
                    logging.info(f"OCR 결과: {text}")
                    if '사도' in text or '사 도' in text:
                        return "CHARACTER", raw_bytes
                return "UNKNOWN", raw_bytes # 글자 판독 실패 시 UNKNOWN으로 넘김
            
            else:
                return "UNKNOWN", raw_bytes
    except Exception as e:
        logging.error(f"ADB 스크린샷 실패: {e}")
        return "UNKNOWN", None

# 메인 테스트 루프
def run_stability_test(iterations, driver, PACKAGE, shared, log_dir):
    adb_id_backup = driver.adb_id if driver else "Unknown"
    state = "STARTUP"
    last_known_state = "STARTUP"

    for i in range(1, iterations + 1):
            logging.info(f"\n[테스트 {i}/{iterations}회차] 시작")
            try:
                # 기존 태스크 종료 및 재실행
                driver.terminate_app(PACKAGE)
                time.sleep(1)
                driver.activate_app(PACKAGE)
                time.sleep(1)

                subprocess.run(["adb", "-s", driver.adb_id, "shell", "dumpsys", "gfxinfo", PACKAGE, "reset"])
                adb_utils.wait_for_app_network_log(driver.adb_id)
                time.sleep(3)

                max_scan_attempts = 15
                scan_count = 0
                unknown_streak = 0
                character_visit_count = 0  
                character_visit_roop_count = 200
                
                while scan_count <= max_scan_attempts:
                    try:
                        # 화면 탐지 및 상태 저장
                        state, current_screenshot = detect_state(driver)
                        shared["state"] = state

                        if state != "UNKNOWN":
                            last_known_state = state
                        logging.info(f"현재 위치: {state}")

                        if state in ["LOBBY SLEEP", "NETWORK", "UNKNOWN"]:
                            current_interval = 2.0
                        elif state == "LOADING":
                            current_interval = 1.0
                        else:
                            current_interval = 0.5 
                        # 상태 변수에 따른 핸들러 동작
                        if state == "TITLE":
                            handle_title(driver, state, PACKAGE)
                            time.sleep(current_interval)
                        
                        elif state == "LOADING":
                            unknown_streak = 0
                            print('로딩중')
                            time.sleep(current_interval)

                        elif state == "CHARACTER":
                            # 한 세션 내에서 반복 횟수를 누적하여 메모리 우상향(Leak) 여부 확인
                            handle_character(driver, state, PACKAGE)
                            character_visit_count += 1
                            unknown_streak = 0
                            adb_utils.log_system_metrics(character_visit_count, PACKAGE, shared)
                            logging.info(f"현재 반복 횟수: {character_visit_count}/{character_visit_roop_count}")

                            if character_visit_count >= character_visit_roop_count:
                                logging.info(f"목표 달성: CHARACTER 화면 {character_visit_count}회 작업 완료")
                                
                                
                                logging.info(f"🏁 최종 대기 후 메모리 점유율: {shared.get('meminfo', 'N/A')}MB")
                                time.sleep(current_interval)
                                break 

                        elif state == "LOBBY":
                            if character_visit_count > 0:
                                logging.info(f"로비 복귀 (현재 반복: {character_visit_count})")
                            handle_lobby(driver, state)
                            time.sleep(current_interval)

                        elif state == "NETWORK":
                            logging.info("네트워크 지연 화면 감지")
                            scan_count += 1
                            time.sleep(2)
                                
                        elif state == "POPUP":
                            scan_count += 1
                            state = handle_network(driver)
                            if state not in ["POPUP", "NETWORK"]:
                                logging.info(f"네트워크 재연결 성공 (현재 위치: {state})")
                                scan_count = 0

                        elif state == "UNKNOWN":
                            logging.info(f"UNKNOWN 감지 (이전 상태: {last_known_state})")
                            scan_count += 1
                            unknown_streak += 1

                            if unknown_streak == 1:
                                try:
                                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    
                                    mem_dump = subprocess.run(
                                        ["adb", "-s", driver.adb_id, "shell", "dumpsys", "meminfo", PACKAGE],
                                        capture_output=True, text=True, encoding="utf-8", errors="ignore"
                                    ).stdout
                                    with open(os.path.join(log_dir, f"mem_{i}_UNKNOWN_{timestamp}.txt"), "w", encoding="utf-8") as f:
                                        f.write(f"=== DEVICE: {driver.adb_id} | ALIVE: True ===\n")
                                        f.write(mem_dump)

                                    lmk_dump = subprocess.run(
                                        ["adb", "-s", driver.adb_id, "shell", "logcat", "-d", "-t", "50", "-s", "lowmemorykiller"],
                                        capture_output=True, text=True, encoding="utf-8", errors="ignore"
                                    ).stdout
                                    with open(os.path.join(log_dir, f"lmk_{i}_UNKNOWN_{timestamp}.txt"), "w", encoding="utf-8") as f:
                                        f.write(f"=== DEVICE: {driver.adb_id} | ALIVE: True ===\n")
                                        f.write(lmk_dump)

                                except Exception as dump_err:
                                    logging.error(f"UNKNOWN 즉시 덤프 수집 실패: {dump_err}")

                            # 프로세스 확인 
                            pid = subprocess.run(
                                ["adb", "-s", driver.adb_id, "shell", f"pidof {PACKAGE}"],
                                capture_output=True, text=True
                            ).stdout.strip()

                            if not pid:
                                logging.error("앱 프로세스 사라짐 감지 (UNKNOWN 구간)")
                                raise Exception("APP_PROCESS_GONE")
                            
                            # 타임아웃 기준 (2초 인터벌 기준 30회 = 약 60초)
                            if unknown_streak >= 30:
                                logging.error("UNKNOWN 종료 원인: 앱 살아있으나 화면 감지 60초 초과 (UI 변화 또는 팝업)")
                                raise Exception("UNKNOWN_TIMEOUT")
    

                            # UNKNOWN 초반 1~2회만 스크린샷
                            if unknown_streak <= 2 and current_screenshot:
                                try:
                                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    error_filename = f"UNKNOWN_iter{i}_{timestamp}.png"
                                    error_path = os.path.join(log_dir, error_filename)

                                    with open(error_path, "wb") as f:
                                        f.write(current_screenshot)

                                    logging.info(f"UNKNOWN 스크린샷 저장: {error_filename}")
                                except Exception as screenshot_err:
                                    logging.error(f"스크린샷 저장 오류: {screenshot_err}")

                            # driver ping으로 세션 살아있는지 체크
                            try:
                                _ = driver.current_activity
                            except Exception:
                                logging.warning("Driver 세션 불안정 감지 - 재연결 시도 (앱은 유지)")
                                driver = create_driver(driver.adb_id)

                            time.sleep(2)
                            continue
                
                    except Exception as e:
                            # handle_exception 호출 및 세션 복구 판단
                            is_critical = handle_exception(driver, i, state, PACKAGE, log_dir)

                            if not is_critical:
                                logging.warning(f"드라이버 재연결 시도 중: {adb_id_backup}")
                                try:
                                    if driver:
                                            driver.quit()
                                            logging.info("드라이버 세션 종료 완료.")
                                except Exception as e:
                                    logging.debug(f"드라이버 세션 이미 종료됨: {e}")

                                try:
                                    driver = create_driver(adb_id_backup)
                                    time.sleep(2)
                                    scan_count = 0
                                    continue 
                                except Exception as ce:
                                    logging.error(f"드라이버 재생성 실패: {ce}")
                                    is_critical = True

                            if is_critical:
                                logging.error("회차 중단: 앱 종료 후 다음 회차로 진행")
                                break
            
            except Exception as e:
                logging.error(f"[FOR-LOOP ERROR] {e}")
                handle_exception(driver, i, state, PACKAGE, log_dir)
    logging.info("모든 테스트 완료")