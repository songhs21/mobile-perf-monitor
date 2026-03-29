# adb_utils.py
import logging
import subprocess
import time
import datetime
import json
import re
from PIL import Image

# Finsky 캐치 및 단말 조작 타이밍 결정 함수
def wait_for_app_network_log(device_name, package_name="com.epidgames.trickcalrevive", timeout=30):
    logging.info(f"로그 모니터링 시작: {package_name} 네트워크 요청 대기 중...")
    
    # logcat 초기화 및 스트림 생성
    subprocess.run(["adb", "-s", device_name, "logcat", "-c"], check=True)
    process = subprocess.Popen(
        ["adb", "-s", device_name,"logcat", "-v", "time", "-s", "Finsky:*"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',   # 인코딩 강제 지정
        errors='ignore',    # 해석 안 되는 바이트는 무시하여 에러 방지
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )


    start_time = time.time()
    try:
        while time.time() - start_time <= timeout:
            line = process.stdout.readline()
            if line == '' and process.poll() is not None:
                break
            
            #Finsky 탐지 후 반복문 종료
            if "Finsky" in line and package_name in line:
                logging.info(f"네트워크 로그 포착: {line.strip()}")
                return True
            
        logging.info("타임아웃 발생.")
        return False
    finally:
        # 프로세스 종료 체크 및 TASK KILL
        if process.poll() is None:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            process.stdout.close()
            process.wait()
        logging.info("ADB 로그 감시 프로세스가 정리되었습니다.")

def log_system_metrics(iteration, package, shared):
    # 현재 메모리 점유율과 스왑 잔량을 동시에 확인
    current_mem = shared.get('meminfo', 'N/A')
    dirty_mem = shared.get('private_dirty', 'N/A')
    
    swap_cmd = f'adb shell "cat /proc/meminfo | grep SwapFree"'
    swap_info = subprocess.run(
        swap_cmd,
        shell=True,
        capture_output=True,
        text=True
    ).stdout.strip()
    logging.info(f"[METRICS] Iter:{iteration} | Mem:{current_mem}MB | {swap_info}")

def get_screenshot_via_adb(driver):
    if driver.model_name == "SM-F946N":
        remote_path = "/sdcard/screen_tmp.png"
        local_path = "screen_tmp.png"
        subprocess.run(
            ["adb", "-s", driver.adb_id, "shell", "screencap", remote_path],
            capture_output=True
        )
        subprocess.run(
            ["adb", "-s", driver.adb_id, "pull", remote_path, local_path],
            capture_output=True
        )
        try:
            with open(local_path, "rb") as f:
                return f.read()
        except Exception as e:
            logging.error(f"스크린샷 파일 읽기 실패: {e}")
            return None
    else:
        cmd = f"adb -s {driver.adb_id} exec-out screencap -p"
        result = subprocess.run(cmd, shell=True, capture_output=True)
        return result.stdout if result.stdout else None

# cpu/gpu/ram 성능 지표 수집
def performance_monitor(shared, device_name, package, interval, outfile="perf_log.jsonl"):
    mem_re = re.compile(r"TOTAL[:\s]+(\d+)")
    loop_count = 0 
    last_mem_val = 0
    dirty_val = 0
    last_dirty_val = 0

    time.sleep(0.5)

    with open(outfile, "a", encoding="utf-8") as f:
        while shared.get("running", True):
            timestamp = datetime.datetime.now().isoformat()
            current_state = shared.get("state", "UNKNOWN")
            mem_val = shared.get("meminfo", 0)
            dirty_val = shared.get("private_dirty", 0)
            gl_val = shared.get("gl_mtrack", 0)

            # cpu 로그 수집
            cpu_val = 0
            try:
                cmd = f'adb -s {device_name} shell "top -n 1 -b | grep {package}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                if result.stdout:
                        for line in result.stdout.splitlines():
                            if package in line:
                                parts = line.split()
                                # 기기마다 다르므로 % 기호가 있는 문자를 먼저 찾음
                                for p in parts:
                                    if '%' in p:
                                        cpu_val = int(float(p.replace('%', '').replace(',', '.')))
                                        break
                                if cpu_val == 0 and len(parts) > 8:
                                    # %가 없는 경우 대개 8~9번째 열에 위치 (CPU%)
                                    try:
                                        cpu_val = int(float(parts[8].replace(',', '.')))
                                    except: pass
                                if cpu_val > 0: break 
            except subprocess.TimeoutExpired:
                logging.error("ADB 명령 응답 시간 초과 (5초) - CPU 수집 건너뜀")
            except Exception as e:
                logging.error(f"CPU 수집 중 오류: {e}")

            # 2. RAM 수집 (5루프마다 한 번, dumpsys 느려서 매번 하면 부하 생김)
            if loop_count % 5 == 0:
                mem_val = 0
                try:
                    # dumpsys meminfo 느려서 timeout 15초
                    res = subprocess.run(
                        ["adb", "-s", device_name, "shell", "dumpsys", "meminfo", package], 
                        capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15
                    )
                    mem_out = res.stdout

                    pss_kb = None
                    dirty_kb = None
                    gl_kb = None
                    native_heap_kb = None
                    unknown_kb = None
                    egl_kb = None

                    for line in mem_out.splitlines():
                        stripped = line.strip()
                        
                        if stripped.startswith("TOTAL PSS:"):
                            parts = stripped.split()
                            if len(parts) >= 3:
                                try:
                                    pss_kb = int(parts[2])
                                except ValueError:
                                    pass
                            
                        elif stripped.startswith("TOTAL "):
                            parts = stripped.split()
                            if len(parts) >= 3:
                                try:
                                    dirty_kb = int(parts[2])
                                except ValueError:
                                    pass
                        
                        elif stripped.startswith("GL mtrack"):
                            parts = stripped.split()
                            if len(parts) >= 3:
                                try:
                                    gl_kb = int(parts[2])
                                except ValueError:
                                    pass

                        # 누수 추적용 (Native Heap, Unknown, EGL)
                        elif stripped.startswith("Native Heap"):
                            parts = stripped.split()
                            if len(parts) >= 2:
                                try:
                                    native_heap_kb = int(parts[2]) 
                                except ValueError:
                                    pass

                        elif stripped.startswith("Unknown"):
                            parts = stripped.split()
                            if len(parts) >= 2:
                                try:
                                    unknown_kb = int(parts[1])
                                except ValueError:
                                    pass

                        elif stripped.startswith("EGL mtrack"):
                            parts = stripped.split()
                            if len(parts) >= 3:
                                try:
                                    egl_kb = int(parts[2])
                                except ValueError:
                                    pass

                        
                    if pss_kb is not None:
                        mem_val = round(pss_kb / 1024, 2)
                        shared["meminfo"] = mem_val
                        last_mem_val = mem_val

                    if dirty_kb is not None:
                        dirty_val = round(dirty_kb / 1024, 2)
                        shared["private_dirty"] = dirty_val
                        last_dirty_val = dirty_val

                    if gl_kb is not None:
                        gl_val = round(gl_kb / 1024, 2)
                        shared["gl_mtrack"] = gl_val
                    
                    if native_heap_kb is not None:
                        shared["native_heap"] = round(native_heap_kb / 1024, 2)

                    if unknown_kb is not None:
                        shared["unknown_mem"] = round(unknown_kb / 1024, 2)

                    if egl_kb is not None:
                        shared["egl_mtrack"] = round(egl_kb / 1024, 2)
                    
                    else:
                        gl_val = shared.get("gl_mtrack", 0)

                except Exception as e:
                    logging.error(f"메모리 수집 중 예외 발생: {e}")

            # 2. GPU(FPS) 수집 구간
            valid_ts = []
            fps_val = 0.0
            try:
                # 레이어 리스트 획득
                list_res = subprocess.run(["adb", "-s", device_name, "shell", "dumpsys", "SurfaceFlinger", "--list"], 
                                         capture_output=True, text=True, encoding='utf-8', timeout=3)
                
                for line in list_res.stdout.splitlines():
                    if package in line and "(BLAST)" in line:
                        # { } 안에서 레이어 식별자 추출 (예: 812d7d0 SurfaceView[...] (BLAST)#39496)
                        start = line.find('{') + 1
                        end = line.find('}', start)
                        
                        if start > 0 and end > 0:
                            # parentId 제외하고 식별자만 씀
                            full_identity = line[start:end].strip().split(" parentId")[0]
                            
                            # 쉘에서 특수문자 오류 방지용 따옴표 감싸기
                            target_arg = f"'{full_identity}'"
                            gfx_cmd = ["adb", "-s", device_name, "shell", "dumpsys", "SurfaceFlinger", "--latency", target_arg]
                            
                            # 데이터 수집 (자식 프로세스에서도 확인 가능하도록 flush=True)
                            res = subprocess.run(gfx_cmd, capture_output=True, text=True, encoding='utf-8', timeout=2)
                            out = res.stdout.splitlines()
                            
                            # 헤더(16666666) 제외하고 실제 데이터 있을 때만 처리
                            if len(out) > 5:
                                for l in out[1:]:
                                    parts = l.split()
                                    # Vsync 0이거나 이상한 값이면 스킵
                                    if len(parts) == 3 and parts[1] != '0' and len(parts[1]) < 18:
                                        valid_ts.append(int(parts[1]))
                                
                                if valid_ts: break

                if valid_ts:
                    unique_ts = sorted(list(set(valid_ts)))
                    if len(unique_ts) > 5:
                        recent = unique_ts[-61:]
                        diffs = [(recent[i] - recent[i-1]) / 1000000.0 for i in range(1, len(recent))]
                        valid_diffs = [d for d in diffs if 1.0 < d < 100.0]
                        
                        if valid_diffs:
                            avg_ms = sum(valid_diffs) / len(valid_diffs)
                            fps_val = round(1000.0 / avg_ms, 2)
                            if fps_val > 121: fps_val = 120.0
            except Exception as e:
                logging.debug(f"FPS 수집 중 에러: {e}")

            # jsonl 파일에 기록
            record = {
                "time": timestamp,
                "state": current_state,
                "cpu": cpu_val,
                "meminfo": mem_val,
                "private_dirty": dirty_val,
                "gl_mtrack": gl_val,
                "native_heap": shared.get("native_heap", 0),
                "unknown_mem": shared.get("unknown_mem", 0),
                "egl_mtrack": shared.get("egl_mtrack", 0),
                "fps": fps_val
            }


            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            loop_count += 1
            time.sleep(interval)