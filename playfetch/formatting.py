from playfetch.models import GameProduct


def truncate(text: str, max_width: int) -> str:
    """Обрезает строку до max_width символов с '...' если слишком длинная."""
    if len(text) <= max_width:
        return text
    return text[: max_width - 3] + "..."


def ansi_link(url: str, text: str) -> str:
    """Создаёт ANSI-гиперссылку (работает в Windows Terminal, VS Code, iTerm2)."""
    return f"\u001b]8;;{url}\u001b\\{text}\u001b]8;;\u001b\\"


def format_table(results: list[GameProduct], convert_to: str | None = None) -> str:
    """Форматирует результаты в таблицу с динамическими колонками."""
    if not results:
        return "Ничего не найдено."

    # Ширины колонок (фиксированные, безопасные)
    W = {"store": 10, "region": 6, "platform": 16, "title": 40, "price": 20, "sub": 18}

    header = (
        f"{'Store':<{W['store']}}"
        f"{'Reg':<{W['region']}}"
        f"{'Platform':<{W['platform']}}"
        f"{'Title':<{W['title']}}"
        f"{'Price':<{W['price']}}"
        f"{'Subscription':<{W['sub']}}"
    )
    sep = "\u2500" * sum(W.values())

    lines = [sep, header, sep]

    for g in results:
        title_display = ansi_link(g.url, truncate(g.title, W["title"] - 1))
        # Длина ANSI-ссылки больше видимой длины — компенсируем
        visible_len = len(g.title)
        if visible_len > W["title"] - 1:
            visible_len = W["title"] - 1
        padding = W["title"] - visible_len

        price_str = g.price
        if convert_to and g.raw_price and g.raw_price > 0:
            from playfetch.currency import CurrencyConverter
            # Конвертация будет вызвана снаружи, здесь просто выводим

        sub_str = g.subscription.subscription_name or "\u2014"

        line = (
            f"{g.store_name:<{W['store']}}"
            f"{g.region:<{W['region']}}"
            f"{g.platform:<{W['platform']}}"
            f"{title_display}{' ' * padding}"
            f"{truncate(price_str, W['price'] - 1):<{W['price']}}"
            f"{truncate(sub_str, W['sub'] - 1):<{W['sub']}}"
        )
        lines.append(line)

    lines.append(sep)
    lines.append(f"Total: {len(results)} result(s)")
    return "\n".join(lines)
