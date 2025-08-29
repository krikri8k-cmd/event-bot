import time

import requests
from bs4 import BeautifulSoup


def discover_event_ics_links(list_url: str, *, per_page_delay=1.0) -> list[str]:
    """
    Парсит страницу списка событий Nexudus, заходит в карточки и выцепляет ссылку .ics ("Add to calendar").
    Возвращает список .ics-URL по событиям.
    """
    r = requests.get(list_url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # 1) ссылки на карточки событий (селектор может отличаться по теме сайта; оставим общий)
    card_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/events/" in href and href.count("/") >= 3:
            # грубый фильтр: ссылки вида /en/events/event-name-12345
            if href.startswith("http"):
                card_links.append(href)
            else:
                # относительные → абсолютные
                from urllib.parse import urljoin

                card_links.append(urljoin(list_url, href))
    card_links = list(dict.fromkeys(card_links))  # uniq, preserve order

    ics_links = []
    for link in card_links[:50]:  # ограничим, чтобы не сканить бесконечно
        time.sleep(per_page_delay)
        rr = requests.get(link, timeout=20)
        if rr.status_code != 200:
            continue
        ss = BeautifulSoup(rr.text, "html.parser")
        # ищем .ics
        for a in ss.find_all("a", href=True):
            href = a["href"]
            if (
                href.endswith(".ics")
                or "format=ical" in href
                or "calendar" in a.get_text("", strip=True).lower()
            ):
                if href.startswith("http"):
                    ics_links.append(href)
                else:
                    from urllib.parse import urljoin

                    ics_links.append(urljoin(link, href))
                break  # на карточке обычно одна "Add to calendar"
    return list(dict.fromkeys(ics_links))
