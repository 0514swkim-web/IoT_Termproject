import os
os.environ['DISPLAY'] = ':0'

from gpiozero import MotionSensor, TonalBuzzer, LED
from picamera2 import Picamera2
from ultralytics import YOLO
import gspread
from google.oauth2.service_account import Credentials
import time
from datetime import datetime
import pygame

pygame.init()
screen = pygame.display.set_mode((1024, 600))
pygame.display.set_caption('Smart Recycling')
font_big = pygame.font.Font('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', 70)
font_mid = pygame.font.Font('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', 45)
font_small = pygame.font.Font('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', 35)

can_led     = LED(5)
plastic_led = LED(6)
general_led = LED(13)
elec_led    = LED(19)

def all_led_off():
    can_led.off()
    plastic_led.off()
    general_led.off()
    elec_led.off()

def led_on(category):
    all_led_off()
    if category == 'can':
        can_led.on()
    elif category == 'plastic':
        plastic_led.on()
    elif category == 'general':
        general_led.on()
    elif category == 'elec':
        elec_led.on()

recycling_guide = {
    'bottle':     ('캔/페트병', '캔/플라스틱 분리수거', (0, 200, 255),   'can'),
    'laptop':     ('노트북',    '전자제품 수거함',      (255, 200, 0),   'elec'),
    'cell phone': ('휴대폰',    '전자제품 수거함',      (255, 200, 0),   'elec'),
    'book':       ('종이',      '종이 분리수거',        (100, 255, 100), 'general'),
    'person':     ('사람',      '쓰레기 아님!',         (0, 255, 0),     None),
}

ALLOWED = set(recycling_guide.keys())

def get_stats():
    rows = sheet.get_all_values()
    counts = {}
    for row in rows[1:]:
        if len(row) >= 2 and row[1] not in ('감지 객체', 'person', ''):
            counts[row[1]] = counts.get(row[1], 0) + 1
    return counts

def show_waiting():
    screen.fill((0, 0, 0))
    title = font_mid.render('Smart Recycling System', True, (0, 200, 255))
    screen.blit(title, (512 - title.get_width()//2, 30))
    pygame.draw.line(screen, (50, 50, 50), (40, 90), (984, 90), 1)
    subtitle = font_small.render('누적 분리수거 현황', True, (150, 150, 150))
    screen.blit(subtitle, (512 - subtitle.get_width()//2, 105))
    stats = get_stats()
    if not stats:
        msg = font_small.render('아직 인식된 쓰레기가 없어요', True, (100, 100, 100))
        screen.blit(msg, (512 - msg.get_width()//2, 280))
    else:
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:6]
        y = 160
        for obj, count in sorted_stats:
            if obj in recycling_guide:
                label = recycling_guide[obj][0]
                color = recycling_guide[obj][2]
            else:
                label = obj
                color = (255, 100, 100)
            text = font_small.render(f'{label}  {count}개', True, color)
            screen.blit(text, (512 - text.get_width()//2, y))
            y += 55
    pygame.draw.line(screen, (50, 50, 50), (40, 510), (984, 510), 1)
    msg2 = font_small.render('쓰레기를 가져다 대면 자동 인식합니다', True, (80, 80, 80))
    screen.blit(msg2, (512 - msg2.get_width()//2, 530))
    pygame.display.flip()

def show_lcd(name, guide, color):
    screen.fill((0, 0, 0))
    detected_text = font_small.render('감지됨', True, (150, 150, 150))
    screen.blit(detected_text, (512 - detected_text.get_width()//2, 80))
    text1 = font_big.render(name, True, color)
    screen.blit(text1, (512 - text1.get_width()//2, 180))
    pygame.draw.line(screen, (50, 50, 50), (40, 290), (984, 290), 1)
    text2 = font_mid.render(guide, True, (255, 255, 255))
    screen.blit(text2, (512 - text2.get_width()//2, 340))
    pygame.display.flip()

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('/home/wook/credentials.json', scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key('1AFRpN7xXfC9T4xmZfkomtTOfYYkoz9eCNLUiFfF-hSM').sheet1

pir = MotionSensor(17)
buzzer = TonalBuzzer(27)
cam = Picamera2()
cam.configure(cam.create_still_configuration())
cam.start()
model = YOLO('yolov8m.pt')
time.sleep(2)

show_waiting()
print('대기 중... 움직이면 촬영 후 인식!')

MOTION_THRESHOLD = 2.0
COOLDOWN = 5.0
RESULT_DISPLAY_TIME = 5.0
motion_start = None
last_capture = 0
result_shown_at = None

while True:
    now = time.time()

    if result_shown_at and (now - result_shown_at >= RESULT_DISPLAY_TIME):
        result_shown_at = None
        all_led_off()
        show_waiting()

    if pir.motion_detected:
        if motion_start is None:
            motion_start = now
        if (now - motion_start >= MOTION_THRESHOLD) and (now - last_capture >= COOLDOWN):
            filename = f'/home/wook/photos/capture_{int(now)}.jpg'
            cam.capture_file(filename)
            print(f'촬영됨: {filename}')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            detected = False
            results = model(filename, conf=0.25)
            for r in results:
                for box in r.boxes:
                    name = model.names[int(box.cls)]
                    if name not in ALLOWED:
                        continue
                    conf = float(box.conf)
                    print(f'  감지: {name} ({conf:.0%})')
                    sheet.append_row([timestamp, name, f'{conf:.0%}', filename])
                    label, guide, color, category = recycling_guide[name]
                    show_lcd(label, guide, color)
                    if category:
                        led_on(category)
                    buzzer.play('A4')
                    time.sleep(1.5)
                    buzzer.stop()
                    detected = True
                    result_shown_at = now
            if not detected:
                show_waiting()
            last_capture = now
            motion_start = None
    else:
        motion_start = None

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit()
    time.sleep(0.1)
