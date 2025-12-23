import os
import io
import base64
from flask import Flask, render_template, request, flash
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import requests
import numpy as np

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# настройки
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

RECAPTCHA_SITE_KEY = os.environ.get('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.environ.get('RECAPTCHA_SECRET_KEY', '')

def allowed_file(filename):
    """Проверка расширения файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def add_watermark(img):
    """Добавляет текстовую вотермарку в правый нижний угол"""
    watermark_img = img.copy()
    draw = ImageDraw.Draw(watermark_img)
    
    watermark_text = "WATERMARK"
    
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except:
            font = ImageFont.load_default()
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    
    img_width, img_height = watermark_img.size
    
    # получаем размер текста
    try:
        text_bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except:
        text_width, text_height = draw.textsize(watermark_text, font=font)
    
    x = img_width - text_width - 20
    y = img_height - text_height - 20
    
    # тень
    draw.text((x + 2, y + 2), watermark_text, font=font, fill=(0, 0, 0, 120))

    draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 160))
    
    return watermark_img

def create_color_histogram(img, title):
    """Создает гистограмму распределения цветов RGB"""
    plt.figure(figsize=(8, 5))
    
    # преобразуем изображение в numpy массив
    img_array = np.array(img)
    
    # цвета для каналов
    colors = ('red', 'green', 'blue')
    
    # строим гистограммы для каждого канала
    for i, color in enumerate(colors):
        # Извлекаем данные одного канала
        channel_data = img_array[:, :, i].flatten()
        
        # строим гистограмму
        plt.hist(channel_data, bins=50, alpha=0.7, color=color, 
                label=f'{color.upper()} канал', density=True)
    
    plt.title(f'Распределение цветов ({title})', fontsize=14)
    plt.xlabel('Значение пикселя (0-255)', fontsize=12)
    plt.ylabel('Плотность вероятности', fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # сохраняем в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    
    # кодируем в base64
    return base64.b64encode(buf.read()).decode('utf-8')

def verify_captcha(recaptcha_response):
    """Проверка reCAPTCHA"""
    if not RECAPTCHA_SECRET_KEY:
        return True  # пропускаем если ключ не настроен
    
    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    data = {
        'secret': RECAPTCHA_SECRET_KEY,
        'response': recaptcha_response
    }
    
    try:
        response = requests.post(verify_url, data=data, timeout=5)
        result = response.json()
        return result.get('success', False)
    except:
        return False

def image_to_base64(img):
    """Конвертирует изображение PIL в base64 строку"""
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

@app.route('/', methods=['GET', 'POST'])
def index():
    """Главная страница с формой"""
    if request.method == 'POST':
        # проверка капчи
        recaptcha_response = request.form.get('g-recaptcha-response', '')
        
        if not verify_captcha(recaptcha_response):
            flash('Пожалуйста, подтвердите, что вы не робот')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        # проверяем файл
        if 'image' not in request.files:
            flash('Не выбран файл изображения')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        file = request.files['image']
        
        if file.filename == '':
            flash('Не выбран файл изображения')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        if not allowed_file(file.filename):
            flash('Разрешены только файлы: PNG, JPG, JPEG, GIF')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        # получаем угол поворота
        try:
            angle = float(request.form.get('angle', 0))
        except ValueError:
            flash('Укажите корректный угол поворота')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        add_watermark_flag = request.form.get('watermark') == 'on'
        
        try:
            # открываем изображение
            img = Image.open(file).convert('RGB')
            
            # Уменьшаем размер для оптимизации
            if img.size[0] > 1000 or img.size[1] > 1000:
                img.thumbnail((800, 800))
            
            # конвертируем оригинальное изображение в base64
            original_base64 = image_to_base64(img)
            
            # создаем повернутое изображение
            rotated_img = img.rotate(angle, expand=True)
            rotated_base64 = image_to_base64(rotated_img)
            
            # добавляем вотермарку если нужно
            watermarked_base64 = None
            if add_watermark_flag:
                watermarked_img = add_watermark(img)
                watermarked_base64 = image_to_base64(watermarked_img)
            
            # создаем гистограммы
            original_histogram = create_color_histogram(img, 'Оригинал')
            rotated_histogram = create_color_histogram(rotated_img, f'Повёрнуто на {angle}°')
            
            return render_template('result.html',
                                 original_img=original_base64,
                                 rotated_img=rotated_base64,
                                 watermarked_img=watermarked_base64,
                                 original_histogram=original_histogram,
                                 rotated_histogram=rotated_histogram,
                                 angle=angle,
                                 watermark_added=add_watermark_flag)
            
        except Exception as e:
            flash(f'Ошибка обработки изображения: {str(e)}')
    
    return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

@app.route('/health')
def health_check():
    """Проверка работоспособности приложения"""
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
