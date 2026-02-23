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
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

# Словарь для преобразования статусов
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Глобальные переменные для отслеживания состояния
_last_error_message = ""
_last_status_message = ""


def check_tokens() -> bool:
    """
    Проверяет наличие всех необходимых переменных окружения.

    Returns:
        bool: True если все токены присутствуют, иначе False
    """
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    missing_tokens = [
        name for name, value in tokens.items()
        if value is None or value == ''
    ]

    if missing_tokens:
        for token in missing_tokens:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: "{token}"'
            )
        logger.critical('Программа принудительно остановлена.')
        return False

    logger.info('Все необходимые переменные окружения успешно загружены')
    return True


def send_message(bot: telebot.TeleBot, message: str) -> None:
    """
    Отправляет сообщение в Telegram чат.

    Args:
        bot: Экземпляр класса TeleBot
        message: Текст сообщения

    Raises:
        exceptions.SendMessageError: При ошибке отправки
    """
    global _last_error_message, _last_status_message

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Бот отправил сообщение: "{message}"')
        _last_status_message = message

    except telebot.apihelper.ApiException as error:
        error_msg = f'Сбой при отправке сообщения в Telegram: {error}'
        logger.error(error_msg)
        raise exceptions.SendMessageError(error_msg, TELEGRAM_CHAT_ID)

    except Exception as error:
        error_msg = f'Неожиданная ошибка при отправке в Telegram: {error}'
        logger.error(error_msg)
        raise exceptions.SendMessageError(error_msg, TELEGRAM_CHAT_ID)


def get_api_answer(timestamp: int) -> Dict[str, Any]:
    """
    Делает запрос к API сервиса Практикум Домашка.

    Args:
        timestamp: Временная метка

    Returns:
        dict: Ответ API

    Raises:
        exceptions.ApiAnswerError: При ошибках запроса
    """
    params = {'from_date': timestamp}

    logger.debug(
        f'Начинаем запрос к API {ENDPOINT} с параметрами: {params}'
    )

    if not PRACTICUM_TOKEN:
        raise exceptions.ApiAnswerError('Отсутствует токен Практикума')

    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
            timeout=30
        )

    except requests.Timeout:
        error_msg = 'Превышен таймаут при запросе к API'
        logger.error(error_msg)
        raise exceptions.ApiAnswerError(error_msg)

    except requests.RequestException as error:
        error_msg = f'Ошибка при запросе к API: {error}'
        logger.error(error_msg)
        raise exceptions.ApiAnswerError(error_msg)

    if response.status_code != HTTPStatus.OK:
        error_msg = f'Эндпоинт {ENDPOINT} недоступен'
        status_msg = f'{error_msg}. Код ответа API: {response.status_code}'
        logger.error(status_msg)
        raise exceptions.ApiAnswerError(
            error_msg,
            status_code=response.status_code
        )

    try:
        return response.json()
    except ValueError as error:
        error_msg = f'Ошибка парсинга JSON: {error}'
        logger.error(error_msg)
        raise exceptions.ApiAnswerError(error_msg)


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
        raise TypeError('Ответ API должен быть словарем')

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError('Ключ "homeworks" должен содержать список')

    if not homeworks:
        logger.debug('В ответе API нет новых статусов')

    return homeworks


def parse_status(homework: Dict[str, Any]) -> str:
    """
    Извлекает статус домашней работы из информации о ней.

    Args:
        homework: Информация о домашней работе

    Returns:
        str: Сообщение для отправки

    Raises:
        KeyError: При отсутствии обязательных ключей
        TypeError: При неверных типах данных
        exceptions.ApiAnswerError: При неожиданном статусе
    """
    if not isinstance(homework, dict):
        raise TypeError('Аргумент homework должен быть словарем')

    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')

    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ "status"')

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        error_msg = f'Неожиданный статус домашней работы: {homework_status}'
        logger.error(error_msg)
        raise exceptions.ApiAnswerError(error_msg)

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def process_homeworks(
    bot: telebot.TeleBot,
    homeworks: List[Dict[str, Any]],
    last_status: str
) -> str:
    """
    Обрабатывает список домашних работ и отправляет уведомления.

    Args:
        bot: Экземпляр бота
        homeworks: Список домашних работ
        last_status: Последний отправленный статус

    Returns:
        str: Обновленный last_status
    """
    if not homeworks:
        logger.debug('Новых статусов нет')
        return last_status

    latest_homework = homeworks[0]
    message = parse_status(latest_homework)

    if message != last_status:
        send_message(bot, message)
        logger.info('Отправлено уведомление об изменении статуса')
        return message

    logger.debug('Статус домашней работы не изменился')
    return last_status


def handle_expected_error(
    bot: telebot.TeleBot,
    error: Exception,
    last_error: str
) -> str:
    """
    Обрабатывает ожидаемые ошибки (KeyError, TypeError, ApiAnswerError).

    Args:
        bot: Экземпляр бота
        error: Исключение
        last_error: Последняя отправленная ошибка

    Returns:
        str: Обновленный last_error
    """
    message = f'Сбой в работе программы: {error}'
    logger.error(message)

    if message != last_error:
        try:
            send_message(bot, message)
            return message
        except exceptions.SendMessageError:
            pass

    return last_error


def handle_unexpected_error(
    bot: telebot.TeleBot,
    error: Exception,
    last_error: str
) -> str:
    """
    Обрабатывает неожиданные ошибки.

    Args:
        bot: Экземпляр бота
        error: Исключение
        last_error: Последняя отправленная ошибка

    Returns:
        str: Обновленный last_error
    """
    message = f'Неожиданная ошибка в работе бота: {error}'
    logger.error(message, exc_info=True)

    if message != last_error:
        try:
            send_message(bot, message)
            return message
        except exceptions.SendMessageError:
            pass

    return last_error


def main() -> None:
    """Основная логика работы бота."""
    # Проверяем наличие всех необходимых токенов
    if not check_tokens():
        sys.exit(1)

    # Создаем объект класса бота
    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    local_last_error = ""
    local_last_status = ""

    logger.info('Бот успешно запущен и начинает работу')

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            local_last_status = process_homeworks(
                bot, homeworks, local_last_status
            )

            timestamp = response.get('current_date', timestamp)

        except (KeyError, TypeError, exceptions.ApiAnswerError) as error:
            local_last_error = handle_expected_error(
                bot, error, local_last_error
            )

        except exceptions.SendMessageError:
            pass

        except Exception as error:
            local_last_error = handle_unexpected_error(
                bot, error, local_last_error
            )

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
