"""Утилиты для добавления реферальных кодов к URL событий"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def add_referral_to_url(url: str, referral_code: str | None, referral_param: str = "ref") -> str:
    """
    Добавляет реферальный параметр к URL

    Args:
        url: Оригинальный URL
        referral_code: Реферальный код
        referral_param: Название параметра (по умолчанию: 'ref')

    Returns:
        URL с добавленным реферальным параметром
    """
    if not url or not referral_code:
        return url

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    # Добавляем реферальный код (не перезаписываем, если уже есть)
    if referral_param not in params:
        params[referral_param] = [referral_code]

    new_query = urlencode(params, doseq=True)
    new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    return new_url


def get_event_url_with_referral(event: dict) -> str | None:
    """
    Получает URL события с добавленным реферальным кодом (если есть)

    Args:
        event: Словарь с данными события (должен содержать 'url', 'referral_code', 'referral_param')

    Returns:
        URL с реферальным кодом или оригинальный URL
    """
    url = event.get("url")
    if not url:
        return None

    referral_code = event.get("referral_code")
    referral_param = event.get("referral_param", "ref")

    if referral_code:
        return add_referral_to_url(url, referral_code, referral_param)

    return url
