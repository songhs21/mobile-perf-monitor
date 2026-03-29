# image_utils.py
import math
import pytesseract
from PIL import Image
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import AppiumOptions
import numpy as np
import cv2
import logging

pytesseract.pytesseract.tesseract_cmd = 'C:/Tesseract-OCR/tesseract.exe'
# 색상 판정
def is_color_match(target_rgb, base_rgb, threshold=35):
    # 유클리드 거리 계산
    distance = math.sqrt(sum([(a - b) ** 2 for a, b in zip(target_rgb, base_rgb)]))
    return distance <= threshold

def get_pixel_average(img, center_x, center_y):
    w, h = img.size
    r_sum = g_sum = b_sum = count = 0

    # 중심점 기준 3x3 범위의 총 9개 픽셀 수집
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            nx, ny = center_x + dx, center_y + dy
            if 0 <= nx < w and 0 <= ny < h:
                r, g, b = img.getpixel((nx, ny))[:3]
                r_sum += r
                g_sum += g
                b_sum += b
                count += 1
    
    if count == 0:
        return (0, 0, 0)
    
    return (int(r_sum / count), int(g_sum / count), int(b_sum / count))

def get_text_from_popup(png_data):
        try:
            full_img = Image.open(png_data)
            w, h = full_img.size

            left, top, right, bottom = w * 0.210, h * 0.333, w * 0.781, h * 0.717
            cropped_img = full_img.crop((left, top, right, bottom))

            img_np = cv2.cvtColor(np.array(cropped_img), cv2.COLOR_RGB2BGR)
            img_np = cv2.resize(img_np, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)


            # 붉은색 글자 (RGB: 240, 95, 110 → BGR 변환)
            lower_red = np.array([90, 75, 220])
            upper_red = np.array([130, 115, 255])
            mask_red = cv2.inRange(img_np, lower_red, upper_red)

            # 갈색 글자 (RGB: 56, 50, 34 → BGR 변환)
            lower_brown = np.array([14, 30, 36])
            upper_brown = np.array([54, 70, 76])
            mask_brown = cv2.inRange(img_np, lower_brown, upper_brown)

            # 붉은색 + 갈색 마스크 합치기 (팝업 글자 두 가지 색상 대응)
            combined_mask = cv2.bitwise_or(mask_red, mask_brown)

            # 4. 흰 배경에 검은 글씨로 반전 및 노이즈 제거
            final_processed = cv2.bitwise_not(combined_mask)
            final_processed = cv2.medianBlur(final_processed, 3)

            # 5. 결과 저장 (디버깅용)
            final_img = Image.fromarray(final_processed)
            final_img.save("network_error_popup.png")
            
            # 6. OCR 판독
            print(f"파일[{png_data}] 판독 시작...")
            custom_config = r'--oem 3 --psm 6'
            detected_text = pytesseract.image_to_string(final_img, lang='kor', config=custom_config)

            print("="*30)
            print(f"최종 판독 결과: {detected_text.strip()}")
            print("="*30)

            return detected_text
        
        except Exception as e:
            print(f"에러 발생: {e}")

def get_text_from_character(driver, pil_img):
        try:
            w, h = pil_img.size
            
            left, top, right, bottom = w * 0.0643, h * 0.0166, w * 0.1241, h * 0.0579
            
            bottom += driver.dev_cfg.get('cy_offset', 0)
            cropped_img = pil_img.crop((left, top, right, bottom))

            img_np = cv2.cvtColor(np.array(cropped_img), cv2.COLOR_RGB2BGR)
            img_np = cv2.resize(img_np, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)

            # 밝은 연두, 어두운 연두 배경 (RGB: 36/76, 30/70, 14/54 → BGR 변환)
            lower_brown = np.array([14, 30, 36])
            upper_brown = np.array([54, 70, 76])
            mask_brown = cv2.inRange(img_np, lower_brown, upper_brown)

            # 4. 흰 배경에 검은 글씨로 반전 및 노이즈 제거
            final_processed = cv2.bitwise_not(mask_brown)
            final_processed = cv2.medianBlur(final_processed, 3)

            # 5. 결과 저장 (디버깅용)
            final_img = Image.fromarray(final_processed)
            final_img.save("character_ocr_debug.png")
            
            # 6. OCR 판독
            custom_config = r'--oem 3 --psm 7'
            detected_text = pytesseract.image_to_string(final_img, lang='kor', config=custom_config)

            result = detected_text.strip() if detected_text else ""
            logging.info(f"인식된 텍스트: {result}")
            
            return result
        except Exception as e:
            print(f"OCR 에러 발생: {e}")
            return ""