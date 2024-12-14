import io
import os
import tempfile
import requests
from decouple import config
from zipfile import ZipFile
from telebot import TeleBot, types
import mimetypes
import logging
import concurrent.futures
import pandas as pd
import json


TOKEN = config('TELEGRAM_TOKEN')
API_KEY = config('API_KEY')

API_URL = "http://84.201.152.196:8020/v1/completions"

logging.basicConfig(filename='bot.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def log_error(message, exception=None):
    if exception:
        logging.error(f"{message} - {str(exception)}")
    else:
        logging.error(message)

def log_info(message):
    logging.info(message)

def validate_file_type(file_name):
    mime_type, _ = mimetypes.guess_type(file_name)
    if mime_type in ['text/plain', 'application/python', 'application/zip', 'application/json', 'text/csv']:
        return True
    return False

def create_report(contents):
    try:
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.md') as temp_file:
            temp_file.write(contents)
            return temp_file.name
    except Exception as e:
        log_error("Ошибка при создании отчета", e)
        return f"Ошибка при создании отчета: {str(e)}"

def call_model_api(messages) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "mistral-nemo-instruct-2407",
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.3
    }
    try:
        response = requests.post(API_URL, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result.get('choices', [{}])[0].get('message', {}).get('content', 'Не удалось получить ответ от модели')
    except requests.exceptions.RequestException as e:
        log_error("Ошибка при обращении к API", e)
        return f"Ошибка при обращении к API: {str(e)}"

def process_file(file) -> str:
    try:
        messages = [
            {"role": "system", "content": "Пиши на русском языке"},
            {"role": "user", "content": f'''Ты — бот, который проверяет код на наличие ошибок, нарушений лучших практик и других потенциальных проблем. Твоя задача — анализировать присланный код и давать обратную связь в виде списка пунктов. Каждый пункт должен содержать:

Описание ошибки или проблемы.
Причину, почему это является ошибкой или плохой практикой.
Рекомендации по исправлению или улучшению.
Если возможно, предложи альтернативное решение или улучшение для данного участка кода.
Ты не должен переписывать код, а только указывать на ошибки и предложить пути их исправления.

Ты не должен объяснять общие концепции программирования, а сосредоточиться только на конкретных ошибках и улучшениях в присланном коде. Ответ должен быть структурирован по пунктам, чтобы было легко понять, что и где нужно исправить.

Обрати внимание на следующие типы проблем:

Ошибки синтаксиса.
Проблемы с производительностью.
Нарушения стиля кодирования.
Недостаток комментариев и документации.
Использование устаревших или небезопасных методов.
Отвечай только на те ошибки, которые реально можно исправить или улучшить.: {file}'''}
        ]
        model_response = call_model_api(messages)
        report = create_report(f"Результат обработки файла: {model_response}")
        return report
    except Exception as e:
        log_error("Ошибка при обработке файла", e)
        return f"Ошибка при обработке файла: {str(e)}"

def process_csv_file(file_contents):
    df = pd.read_csv(io.StringIO(file_contents))
    errors = []
    for column in df.columns:
        if df[column].isnull().any():
            errors.append(f"Столбец {column} содержит пропуски.")
    return '\n'.join(errors) if errors else "Ошибок нет в данных CSV."

def process_json_file(file_contents):
    try:
        data = json.loads(file_contents)
        errors = []
        if isinstance(data, list):
            for idx, entry in enumerate(data):
                if not isinstance(entry, dict):
                    errors.append(f"Элемент в JSON на строке {idx+1} не является словарем.")
        else:
            errors.append("Введенные данные не являются массивом объектов JSON.")
        return '\n'.join(errors) if errors else "Ошибок нет в данных JSON."
    except json.JSONDecodeError as e:
        return f"Ошибка декодирования JSON: {str(e)}"

def process_archive(zip_file) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as report_file:
            with ZipFile(io.BytesIO(zip_file), 'r') as archive:
                files = archive.namelist()
                chunks = []
                current_chunk = ""
                max_chunk_size = 1500

                for file in files:
                    with archive.open(file) as nested_file:
                        file_contents = nested_file.read().decode('utf-8')
                        if len(current_chunk) + len(file_contents) > max_chunk_size:
                            chunks.append(current_chunk)
                            current_chunk = file_contents
                        else:
                            current_chunk += f"Содержимое файла {file}:\n{file_contents}\n\n"

                if current_chunk:
                    chunks.append(current_chunk)

                for chunk in chunks:
                    messages = [
                        {"role": "system", "content": "Пиши на русском языке"},
                        {"role": "user", "content": f'''Ты — бот, который проверяет код на наличие ошибок, нарушений лучших практик и других потенциальных проблем. Твоя задача — анализировать присланный код и давать обратную связь в виде списка пунктов. Каждый пункт должен содержать:

Описание ошибки или проблемы.
Причину, почему это является ошибкой или плохой практикой.
Рекомендации по исправлению или улучшению.
Если возможно, предложи альтернативное решение или улучшение для данного участка кода.
Ты не должен переписывать код, а только указывать на ошибки и предложить пути их исправления.

Ты не должен объяснять общие концепции программирования, а сосредоточиться только на конкретных ошибках и улучшениях в присланном коде. Ответ должен быть структурирован по пунктам, чтобы было легко понять, что и где нужно исправить.

Обрати внимание на следующие типы проблем:

Ошибки синтаксиса.
Проблемы с производительностью.
Нарушения стиля кодирования.
Недостаток комментариев и документации.
Использование устаревших или небезопасных методов.
Отвечай только на те ошибки, которые реально можно исправить или улучшить.: {chunk}'''}
                    ]
                    model_response = call_model_api(messages)
                    report_file.write(f"Результат обработки архива:\n{model_response}\n\n")
        
        return report_file.name
    except Exception as e:
        log_error("Ошибка при обработке архива или файлов", e)
        return f"Ошибка при обработке архива или файлов: {str(e)}"

def remove_temp_file(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            log_info(f"Временный файл {file_path} удален.")
        else:
            log_info(f"Файл {file_path} не найден для удаления.")
    except Exception as e:
        log_error(f"Ошибка при удалении файла {file_path}", e)

bot = TeleBot(TOKEN)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        if not validate_file_type(message.document.file_name):
            bot.reply_to(message, "Извините, я не могу обработать этот тип файла.")
            return

        if message.document.file_name.endswith('.zip'):
            result_report = process_archive(downloaded_file)
            r_type = "архив"
        elif message.document.file_name.endswith('.csv'):
            result_report = process_csv_file(downloaded_file.decode('utf-8'))
            r_type = "файл CSV"
        elif message.document.file_name.endswith('.json'):
            result_report = process_json_file(downloaded_file.decode('utf-8'))
            r_type = "файл JSON"
        else:
            result_report = process_file(downloaded_file)
            r_type = "файл"

        bot.reply_to(message, f"Ваш {r_type} был обработан, результаты прикреплены к сообщению.")
        with open(result_report, "rb") as report_file:
            bot.send_document(chat_id=message.chat.id, document=report_file)

        remove_temp_file(result_report)

    except Exception as e:
        log_error("Произошла ошибка", e)
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "Привет! Я бот для проверки проектов. Отправьте мне файл или архив для обработки.")

@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    bot.reply_to(message, "Я не знаю, что делать с этим. Пожалуйста, отправьте мне файл или архив для обработки.")

if __name__ == '__main__':
    log_info("Bot started")
    bot.infinity_polling()
