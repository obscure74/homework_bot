"""
Модуль с пользовательскими исключениями для бота-ассистента.

Содержит иерархию исключений для обработки различных ошибок,
возникающих при работе бота.
"""

from typing import Any, Dict, Optional


class ApiAnswerError(Exception):
    """
    Исключение, возникающее при проблемах с ответом API.

    Attributes:
        message: Описание ошибки
        status_code: HTTP статус код ответа (если доступен)
        response_data: Дополнительные данные ответа (если есть)
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Инициализирует исключение с сообщением и кодом статуса.

        Args:
            message: Описание ошибки
            status_code: HTTP статус код ответа API
            response_data: Дополнительные данные из ответа
        """
        self.status_code = status_code
        self.response_data = response_data
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Форматирует сообщение с учетом кода статуса."""
        base_message = self.message
        if self.status_code:
            base_message = f"{base_message} (Код ответа: {self.status_code})"
        if self.response_data:
            base_message = f"{base_message} | Данные: {self.response_data}"
        return base_message


class SendMessageError(Exception):
    """
    Исключение, возникающее при проблемах с отправкой сообщения в Telegram.

    Attributes:
        message: Описание ошибки
        chat_id: ID чата, в который пытались отправить сообщение
    """

    def __init__(self, message: str, chat_id: Optional[str] = None):
        """
        Инициализирует исключение с сообщением и ID чата.

        Args:
            message: Описание ошибки
            chat_id: ID чата для отправки
        """
        self.chat_id = chat_id
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Форматирует сообщение с учетом ID чата."""
        if self.chat_id:
            return f"{self.message} (Chat ID: {self.chat_id})"
        return self.message


class NotForSendError(Exception):
    """
    Исключение для случаев, когда не нужно отправлять сообщение.

    Используется для ошибок, которые не требуют уведомления пользователя,
    но должны быть залогированы.
    """


class EmptyResponseError(ApiAnswerError):
    """
    Исключение при пустом ответе от API.

    Наследуется от ApiAnswerError для специфичной обработки
    пустых или некорректных ответов от API.
    """


class InvalidTokenError(Exception):
    """
    Исключение при невалидных токенах.

    Attributes:
        token_name: Имя переменной с токеном
        message: Описание ошибки
    """

    def __init__(self, token_name: str, message: str = "Невалидный токен"):
        """
        Инициализирует исключение с именем токена.

        Args:
            token_name: Имя переменной окружения с токеном
            message: Описание ошибки
        """
        self.token_name = token_name
        self.message = message
        super().__init__(f"{message}: {token_name}")
