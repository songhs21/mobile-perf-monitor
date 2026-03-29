#_-_encoding=utf8_-_
#__author__="huiseong.song"
# main.py
import logging
import os
import signal
import sys
import datetime
import subprocess
import state_machine
from multiprocessing import Process, Manager
import adb_utils
import performance_logger

def make_signal_handler(shared, p1):
    def signal_handler(sig, frame):
        logging.warning("\n[!] Ctrl+C 감지")
        shared["running"] = False
        if p1.is_alive():
            p1.terminate()
            p1.join()
        sys.exit(0)
    return signal_handler

if __name__ == "__main__":
    package = "com.epidgames.trickcalrevive"
    device_name = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    manager = Manager()
    shared = manager.dict()
    shared["state"] = "START"
    shared["running"] = True
    shared.get("meminfo", 0)

    session_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = f"Test_Session_{session_time}"
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)
    
    log_filename_jsonl = f"perf_log_{session_time}.jsonl"
    full_log_path = os.path.join(session_dir, log_filename_jsonl)

    # 로그 폴더/파일 생성 및 설정
    log_file_path = os.path.join(session_dir, f"test_run_{session_time}.log")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    lines = device_name.stdout.strip().split('\n')
    if len(lines) > 1:
        device_name = lines[1].split()[0]
    else:
        logging.error("연결된 기기가 없습니다.")
        exit()
    driver = state_machine.create_driver(device_name)
    p1 = None
    try:
        p1 = Process(target=adb_utils.performance_monitor, 
                     args=(shared, device_name, package, 0.5, full_log_path),
                     daemon=True)
        p1.start()
        signal.signal(signal.SIGINT, make_signal_handler(shared, p1))
        state_machine.run_stability_test(1, driver, package, shared, session_dir)

    except KeyboardInterrupt:
        logging.warning("사용자에 의해 중단됨")
    except Exception as e:
        logging.error(f"메인 루프 에러: {e}")
    finally:
        shared["state"] = "IDLE_CHECK"

        # 앱 종료 및 드라이버 정리
        logging.info("애플리케이션 종료 및 드라이버 닫기...")
        shared["running"] = False
        
        try:
            if driver:
                driver.quit()
        except Exception as e:
            logging.error(f"드라이버 종료 중 에러: {e}")

        # 모니터링 프로세스 종료
        if p1 and p1.is_alive():
            p1.terminate()
            p1.join()

    logging.info("모든 자원이 해제되었습니다.")

    logging.info("테스트 종료: 그래프 생성을 시작합니다...")
    try:
        # 개별 함수 대신 통합 함수(draw_all_graphs)를 호출하여 세션 폴더에 저장
        performance_logger.draw_total_graph(full_log_path, session_dir)
        logging.info(f"모든 결과물이 '{session_dir}' 폴더에 저장되었습니다.")
    except Exception as e:
        logging.error(f"그래프 생성 실패: {e}")