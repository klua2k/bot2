from aiogram.utils.formatting import Bold, as_list, as_marked_section


categories = ['Дорогие', 'Простые']

description_for_info_pages = {
    "main": "Добро пожаловать!",
    "about": "Каршеринг простой.\nРежим работы - круглосуточно.",
    "payment": as_marked_section(
        Bold("Варианты оплаты:"),
        "Картой в боте",
        "В здание",
        marker="✅ ",
    ).as_html(),
    'catalog': 'Категории:',
    'cart': 'В корзине ничего нет!'
}