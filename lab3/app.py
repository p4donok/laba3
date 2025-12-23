import os
import io
import base64
from flask import Flask, render_template, request, flash
from PIL import Image
import matplotlib.pyplot as plt
import requests
import numpy as np
import keras
from keras.applications.resnet50 import preprocess_input, decode_predictions

app = Flask(__name__)
app.secret_key = 'secret_key_123'

# Папка для загрузок
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RECAPTCHA_SITE_KEY = '6LfnMTQsAAAAANYMEHiH_a6wJOPCLPbHk_BuYhsO' 
RECAPTCHA_SECRET_KEY = '6LfnMTQsAAAAAEvf-yDO5ttST2GQvF2NND2sUXO3'

# Загрузка нейронной сети (делаем один раз при старте)
print("Загрузка нейронной сети ResNet50...")
try:
    resnet = keras.applications.resnet_v2.ResNet50V2(
        include_top=True,
        weights='imagenet',
        classes=1000
    )
    print("Нейронная сеть загружена успешно!")
except Exception as e:
    print(f"Ошибка загрузки нейронной сети: {e}")
    resnet = None

def classify_image(img):
    """Классифицирует изображение с помощью нейронной сети"""
    if resnet is None:
        return "Нейронная сеть не загружена", 0.0
    
    try:
        # Подготовка изображения
        img_resized = img.resize((224, 224))
        img_array = np.array(img_resized) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        
        # Классификация
        predictions = resnet.predict(img_array, verbose=0)
        decoded = decode_predictions(predictions, top=1)[0][0]
        
        # Возвращаем название класса и вероятность
        class_name = decoded[1].replace('_', ' ')
        probability = float(decoded[2])
        
        return class_name, probability
    except Exception as e:
        return f"Ошибка классификации: {str(e)}", 0.0

def create_color_histogram(img, title):
    """Создает гистограмму распределения цветов RGB и возвращает base64"""
    plt.figure(figsize=(6, 4))
    colors = ('r', 'g', 'b')

    for i, color in enumerate(colors):
        histogram = img.histogram()[i * 256:(i + 1) * 256]
        plt.plot(histogram, color=color, alpha=0.7, label=['Red', 'Green', 'Blue'][i])

    plt.title(f'Распределение цветов ({title})')
    plt.xlabel('Значение цвета (0-255)')
    plt.ylabel('Частота')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    # Сохраняем в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()

    # Кодируем в base64 для HTML
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    return img_base64

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Проверка CAPTCHA
        recaptcha_response = request.form.get('g-recaptcha-response')
        if not recaptcha_response:
            flash('Пожалуйста, подтвердите, что вы не робот')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

        # Проверка через Google
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        data = {
            'secret': RECAPTCHA_SECRET_KEY,
            'response': recaptcha_response
        }

        try:
            response = requests.post(verify_url, data=data, timeout=5)
            result = response.json()

            if not result.get('success'):
                flash('Ошибка CAPTCHA. Попробуйте снова.')
                return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        except:
            flash('Ошибка соединения с сервисом CAPTCHA')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

        # Получение файла и угла
        file = request.files.get('image')
        angle = request.form.get('angle', type=float)

        if not file or file.filename == '':
            flash('Выберите изображение')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

        if not angle:
            flash('Укажите угол поворота')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

        try:
            # Открываем изображение
            img = Image.open(file).convert('RGB')

            # Сохраняем оригинал
            original_path = os.path.join(UPLOAD_FOLDER, 'original.jpg')
            img.save(original_path, 'JPEG', quality=90)

            # Поворачиваем
            rotated_img = img.rotate(angle, expand=True)
            rotated_path = os.path.join(UPLOAD_FOLDER, 'rotated.jpg')
            rotated_img.save(rotated_path, 'JPEG', quality=90)

            # Классифицируем изображения
            original_class, original_prob = classify_image(img)
            rotated_class, rotated_prob = classify_image(rotated_img)

            # Создаем гистограммы
            original_histogram = create_color_histogram(img, 'оригинал')
            rotated_histogram = create_color_histogram(rotated_img, 'повёрнутое')

            return render_template('result.html',
                                   original_img='uploads/original.jpg',
                                   rotated_img='uploads/rotated.jpg',
                                   original_histogram=original_histogram,
                                   rotated_histogram=rotated_histogram,
                                   original_class=original_class,
                                   original_prob=original_prob,
                                   rotated_class=rotated_class,
                                   rotated_prob=rotated_prob,
                                   angle=angle)

        except Exception as e:
            flash(f'Ошибка обработки: {str(e)}')

    return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

if __name__ == '__main__':
    # Очистка папки uploads при запуске
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except:
            pass

    app.run(debug=True, host='0.0.0.0', port=5000)
