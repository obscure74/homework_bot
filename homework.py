"""
Telegram бот для отслеживания статуса домашних работ на Яндекс.Практикуме.

Бот каждые 10 минут опрашивает API Практикума и отправляет уведомления
в Telegram при изменении статуса проверки домашней работы.
"""

import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Any, Dict, List

import requests
import telebot
from dotenv import load_dotenv

import exceptions

# Загружаем переменные окружения из файла .env
load_dotenv()

# Константы окружения
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Константы приложения
RETRY_PERIOD = 600
API_TIMEOUT = 30
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

# Словарь для преобразования статусов
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def check_tokens() -> None:
    """Проверяет наличие всех необходимых переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    error_found = False
    for name, value in tokens.items():
        if not value:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: {name}'
            )
            error_found = True
    if error_found:
        raise exceptions.InvalidTokenError('Отсутствуют необходимые токены')


def send_message(bot: telebot.TeleBot, message: str) -> bool:
    """Отправляет сообщение в Telegram. Возвращает True при успехе."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Бот отправил сообщение: "{message}"')
        return True

    except (telebot.apihelper.ApiException,
            requests.RequestException) as error:
        logger.error(f'Сбой при отправке сообщения: {error}')
        return False


def get_api_answer(timestamp: int) -> Dict[str, Any]:
    """Делает запрос к API сервиса Практикум."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
            timeout=API_TIMEOUT
        )

    except requests.RequestException as error:
        raise exceptions.ApiAnswerError(f'Ошибка запроса к API: {error}')

    if response.status_code != HTTPStatus.OK:
        raise exceptions.ApiAnswerError(
            f'API вернул статус {response.status_code}',
            status_code=response.status_code
        )

    try:
        return response.json()
    except ValueError as error:
        raise exceptions.ApiAnswerError(f'Ошибка парсинга JSON: {error}')


def check_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Проверяет ответ API на соответствие ожидаемой структуре.

    Args:
        response: Ответ API

    Returns:
        list: Список домашних работ

    Raises:
        TypeError: При неверном типе данных
        KeyError: При отсутствии обязательных ключей
    """
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API ожидался как dict, получен {type(response)}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError(
            f'Ключ "homeworks" ожидался как list, получен {type(homeworks)}'
        )

    return homeworks


def parse_status(homework: Dict[str, Any]) -> str:
    """Извлекает статус домашней работы из информации о ней."""
    if not isinstance(homework, dict):
        raise TypeError(
            f'Данные работы ожидались как dict, получен {type(homework)}'
        )

    for key in ('homework_name', 'status'):
        if key not in homework:
            raise KeyError(f'В данных работы отсутствует ключ "{key}"')

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise exceptions.ApiAnswerError(f'Неожиданный статус: {status}')

    return (f'Изменился статус проверки работы "{homework["homework_name"]}". '
            f'{HOMEWORK_VERDICTS[status]}')


def main() -> None:
    """Основная логика работы бота."""
    # Проверяем наличие всех необходимых токенов
    check_tokens()

    # Создаем объект класса бота
    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = ""

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
                    last_error = ""
            else:
                logger.debug('Новых статусов нет')
                timestamp = response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message, exc_info=True)
            if message != last_error:
                if send_message(bot, message):
                    last_error = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    try:
        main()
    except exceptions.InvalidTokenError as error:
        logger.critical(f'Бот принудительно остановлен: {error}')
        sys.exit(1)
    except Exception as e:
        logger.critical(f'Бот упал с критической ошибкой: {e}')
        sys.exit(1)
