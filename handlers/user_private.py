from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_callback_btns
from database.orm_query import (
    orm_add_to_cart,
    orm_add_user,
)

user_private_router = Router()
registered_users = set()  # Список зарегистрированных пользователей

# Состояния регистрации
class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

# Кнопка для отправки номера телефона
register_phone_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отправить номер телефона", request_contact=True)],
    ],
    resize_keyboard=True
)

@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext, session: AsyncSession):
    user_id = message.from_user.id

    if user_id not in registered_users:
        # Если пользователь не зарегистрирован, начинаем процесс регистрации
        await message.answer(
            "Привет! Для продолжения, пожалуйста, зарегистрируйтесь.\nВведите ваше имя:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationState.waiting_for_name)
    else:
        # Если пользователь зарегистрирован, показываем меню
        media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
        if media:
            await message.answer_photo(
                media.media,
                caption=media.caption,
                reply_markup=reply_markup
            )
        else:
            await message.answer("Извините, каталог недоступно.")

# Обработчик получения имени
@user_private_router.message(RegistrationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_name = message.text
    await state.update_data(name=user_name)
    await message.answer(
        f"Спасибо, {user_name}! Теперь отправьте ваш номер телефона:",
        reply_markup=register_phone_kb
    )
    await state.set_state(RegistrationState.waiting_for_phone)

# Обработчик получения номера телефона
@user_private_router.message(RegistrationState.waiting_for_phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, session: AsyncSession):
    contact = message.contact
    user_id = message.from_user.id

    if contact.user_id == user_id:
        user_data = await state.get_data()
        user_name = user_data.get("name")
        phone_number = contact.phone_number

        # Добавляем пользователя в список зарегистрированных
        registered_users.add(user_id)
        await message.answer(
            f"Регистрация завершена!\nИмя: {user_name}\nТелефон: {phone_number}",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

        # Показываем меню после завершения регистрации
        media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
        if media:
            await message.answer_photo(
                media.media,
                caption=media.caption,
                reply_markup=reply_markup
            )
        else:
            await message.answer("Извините, меню недоступно.")
    else:
        await message.answer("Пожалуйста, отправьте ваш номер телефона с помощью кнопки.")

# Проверка регистрации для других команд
async def ensure_registered(message: types.Message) -> bool:
    if message.from_user.id not in registered_users:
        await message.answer(
            "Пожалуйста, зарегистрируйтесь, чтобы продолжить.",
            reply_markup=register_phone_kb
        )
        return False
    return True

async def add_to_cart(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    user = callback.from_user
    await orm_add_user(
        session,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=None,
    )
    await orm_add_to_cart(session, user_id=user.id, product_id=callback_data.product_id)
    await callback.answer("Авто добавлен в корзину.")



@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    if callback_data.menu_name == "add_to_cart":
        await add_to_cart(callback, callback_data, session)
        return

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        category=callback_data.category,
        page=callback_data.page,
        product_id=callback_data.product_id,
        user_id = callback.from_user.id,
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()