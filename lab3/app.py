import os
import io
import base64
from flask import Flask, render_template, request, flash, redirect, url_for
from PIL import Image
import matplotlib.pyplot as plt
import requests
import numpy as np

# Настройка TensorFlow - отключаем лишние предупреждения
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import tensorflow as tf

# Импорты из TensorFlow Keras вместо отдельного Keras
from tensorflow.keras.applications.resnet50 import preprocess_input, decode_predictions, ResNet50
from tensorflow.keras.preprocessing import image as keras_image

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# Настройки
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# CAPTCHA ключи (добавьте в Environment Variables на Render)
RECAPTCHA_SITE_KEY = os.environ.get('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.environ.get('RECAPTCHA_SECRET_KEY', '')

# Загружаем предобученную нейросеть ResNet50
try:
    print("Загрузка нейросети ResNet50...")
    model = ResNet50(weights='imagenet')
    print("Нейросеть успешно загружена")
except Exception as e:
    print(f"Ошибка загрузки нейросети: {e}")
    model = None

def allowed_file(filename):
    """Проверка расширения файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_color_histogram(img, title):
    """Создает гистограмму распределения цветов RGB"""
    plt.figure(figsize=(8, 5))
    
    # Преобразуем изображение в numpy массив
    img_array = np.array(img)
    
    # Цвета для каналов
    colors = ('red', 'green', 'blue')
    
    # Строим гистограммы для каждого канала
    for i, color in enumerate(colors):
        # Извлекаем данные одного канала
        channel_data = img_array[:, :, i].flatten()
        
        # Строим гистограмму
        plt.hist(channel_data, bins=50, alpha=0.7, color=color, 
                label=f'{color.upper()} канал', density=True)
    
    plt.title(f'Распределение цветов ({title})', fontsize=14)
    plt.xlabel('Значение пикселя (0-255)', fontsize=12)
    plt.ylabel('Плотность вероятности', fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Сохраняем в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    
    # Кодируем в base64
    return base64.b64encode(buf.read()).decode('utf-8')

def getresult(image_box):
    """Классификация изображения с помощью нейросети (используем model вместо resnet)"""
    if model is None:
        return [("n000000", "Нейросеть не загружена", 0.0)]
    
    try:
        files_count = len(image_box)
        images_resized = []
        
        # Нормализуем изображения и преобразуем в numpy
        for i in range(files_count):
            resized_img = image_box[i].resize((224, 224))
            img_array = keras_image.img_to_array(resized_img)
            img_array = np.expand_dims(img_array, axis=0)
            img_array = preprocess_input(img_array)
            images_resized.append(img_array)
        
        # Если есть изображения для обработки
        if images_resized:
            # Объединяем все изображения в один batch
            images_batch = np.vstack(images_resized)
            
            # Подаем на вход сети
            predictions = model.predict(images_batch)
            
            # Декодируем ответ сети
            decoded = decode_predictions(predictions, top=1)
            return decoded
    
    except Exception as e:
        print(f"Ошибка классификации: {e}")
    
    return [("n000000", "Ошибка обработки", 0.0)]

def verify_captcha(recaptcha_response):
    """Проверка reCAPTCHA"""
    if not RECAPTCHA_SECRET_KEY:
        return True  # Пропускаем если ключ не настроен
    
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

def read_image_files(files_max_count, dir_name):
    """Чтение изображений из каталога"""
    try:
        files = [item for item in os.listdir(dir_name) 
                if os.path.isfile(os.path.join(dir_name, item)) and 
                item.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        
        files_count = min(files_max_count, len(files))
        image_box = []
        
        for file_i in range(files_count):
            img_path = os.path.join(dir_name, files[file_i])
            img = Image.open(img_path)
            image_box.append(img)
        
        return files_count, image_box
    
    except Exception as e:
        print(f"Ошибка чтения файлов: {e}")
        return 0, []

@app.route('/', methods=['GET', 'POST'])
def index():
    """Главная страница с формой"""
    if request.method == 'POST':
        # Проверка CAPTCHA
        recaptcha_response = request.form.get('g-recaptcha-response', '')
        
        if not verify_captcha(recaptcha_response):
            flash('Пожалуйста, подтвердите, что вы не робот')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        # Проверяем файл
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
        
        # Получаем угол поворота
        try:
            angle = float(request.form.get('angle', 0))
        except ValueError:
            flash('Укажите корректный угол поворота')
            return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)
        
        try:
            # Сохраняем оригинальное изображение
            original_filename = 'original_' + file.filename
            original_path = os.path.join(UPLOAD_FOLDER, original_filename)
            
            # Открываем и сохраняем оригинал
            img = Image.open(file).convert('RGB')
            img.save(original_path, 'JPEG', quality=90)
            
            # Поворачиваем изображение
            rotated_img = img.rotate(angle, expand=True)
            rotated_filename = 'rotated_' + file.filename
            rotated_path = os.path.join(UPLOAD_FOLDER, rotated_filename)
            rotated_img.save(rotated_path, 'JPEG', quality=90)
            
            # Создаем гистограммы
            original_histogram = create_color_histogram(img, 'Оригинал')
            rotated_histogram = create_color_histogram(rotated_img, f'Повёрнуто на {angle}°')
            
            # Классификация нейросетью
            neurodic = {}
            try:
                # Создаем список с изображениями для классификации
                images_for_classification = [img, rotated_img]
                decode = getresult(images_for_classification)
                
                for i, elem in enumerate(decode):
                    if i < 2:  # Только для двух изображений
                        title = "Оригинал" if i == 0 else "Повёрнутое"
                        neurodic[f"{title}: {elem[0][1]}"] = f"{elem[0][2]:.3f}"
            except Exception as e:
                print(f"Ошибка нейросети: {e}")
                neurodic["Нейросеть"] = "Ошибка классификации"
            
            # Очищаем старые файлы
            clean_old_files()
            
            return render_template('result.html',
                                 original_img=f'uploads/{original_filename}',
                                 rotated_img=f'uploads/{rotated_filename}',
                                 original_histogram=original_histogram,
                                 rotated_histogram=rotated_histogram,
                                 angle=angle,
                                 neurodic=neurodic)
            
        except Exception as e:
            flash(f'Ошибка обработки изображения: {str(e)}')
    
    return render_template('index.html', site_key=RECAPTCHA_SITE_KEY)

def clean_old_files():
    """Очистка старых файлов из папки uploads"""
    try:
        files = os.listdir(UPLOAD_FOLDER)
        if len(files) > 10:
            files.sort(key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x)))
            for file in files[:-10]:
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, file))
                except:
                    pass
    except:
        pass

@app.route('/health')
def health_check():
    """Проверка работоспособности приложения"""
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
