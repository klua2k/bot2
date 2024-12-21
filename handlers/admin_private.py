from aiogram import F, Bot, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Product
from filters.chat import IsAdmin, ChatTypeFilter
from kbds.inline import get_callback_btns
from kbds.reply import get_keyboard
from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import (
    orm_change_banner_image,
    orm_get_categories,
    orm_add_product,
    orm_delete_product,
    orm_get_info_pages,
    orm_get_product,
    orm_get_products,
    orm_update_product,
)

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())

ADMIN_KB = get_keyboard(
    "Добавить авто",
    "Каталог авто",
    "Добавить/Изменить баннер",
    placeholder="Выберите действие",
    sizes=(2,),
)

class AddProduct(StatesGroup):
    # Шаги состояний
    name = State()
    description = State()
    category = State()
    price = State()
    image = State()
    status = State()  # Новый шаг для статуса товара
    
    product_for_change = None

    texts = {
        "AddProduct:name": "Введите название товара:",
        "AddProduct:description": "Введите описание товара:",
        "AddProduct:price": "Введите стоимость товара:",
        "AddProduct:image": "Загрузите изображение товара:",
        "AddProduct:status": "Укажите статус товара (свободен или занят):",
    }

# Обработчик команды "admin" с предложением действий
@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await message.answer("Что хотите сделать?", reply_markup=ADMIN_KB)

# Обработчик "Каталог авто" для выбора категории
@admin_router.message(F.text == "Каталог авто")
async def catalog_auto(message: types.Message, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f"category_{category.id}" for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))

# Обработчик callback для выбора категории и тут пытался 2.
@admin_router.callback_query(F.data.startswith("category_"))
async def category_auto_products_callback(callback: types.CallbackQuery, session: AsyncSession):
    category_id = int(callback.data.split("_")[-1])
    

    
    # Передаем include_busy=True для администраторов
    products = await orm_get_products(session, category_id, include_busy=True)

    if not products:
        await callback.message.answer("В этой категории пока нет авто.")
    else:
        for product in products:
            await callback.message.answer_photo(
                product.image,
                caption=f"<strong>{product.name}</strong>\n"
                        f"{product.description}\n"
                        f"Стоимость за час: {round(product.price, 2)}\n"
                        f"Статус: {product.status}",
                reply_markup=get_callback_btns(
                    btns={
                        "Удалить": f"delete_{product.id}",
                        "Изменить": f"change_{product.id}",
                    }
                ),
            )

    await callback.answer()
    await callback.message.answer("ОК, вот список авто ⏫")

# Обработчик удаления авто
@admin_router.callback_query(F.data.startswith('delete_'))
async def delete_products(callback: types.CallbackQuery, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))

    await callback.answer("Авто удален")
    await callback.message.answer("Авто удален!")

################# Микро FSM для загрузки/изменения баннеров ############################

class AddBanner(StatesGroup):
    image = State()

# Отправляем перечень информационных страниц бота и становимся в состояние отправки photo
@admin_router.message(StateFilter(None), F.text == 'Добавить/Изменить баннер')
async def add_image2(message: types.Message, state: FSMContext, session: AsyncSession):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await message.answer(f"Отправьте фото баннера.\nВ описании укажите для какой страницы:\
                         \n{', '.join(pages_names)}")
    await state.set_state(AddBanner.image)

# Добавляем/изменяем изображение в таблице (там уже есть записанные страницы по именам:
# main, catalog, cart(для пустой корзины), about, payment, shipping
@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(f"Введите нормальное название страницы, например:\
                         \n{', '.join(pages_names)}")
        return
    await orm_change_banner_image(session, for_page, image_id,)
    await message.answer("Баннер добавлен/изменен.")
    await state.clear()

# ловим некоррекный ввод
@admin_router.message(AddBanner.image)
async def add_banner2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или отмена")

# Обработчик изменения авто
@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_product_callback(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    product_id = callback.data.split("_")[-1]
    product_for_change = await orm_get_product(session, int(product_id))

    AddProduct.product_for_change = product_for_change

    await callback.answer()
    await callback.message.answer(
        "Введите название авто", reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AddProduct.name)

# Обработчик начала добавления нового товара
@admin_router.message(F.text == "Добавить авто")
async def add_product(message: types.Message, state: FSMContext):
    await message.answer("Введите название товара", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddProduct.name)

# Обработчик отмены
@admin_router.message(StateFilter("*"), Command("отмена"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    await state.clear()
    await message.answer("Действия отменены", reply_markup=ADMIN_KB)

# Обработчик возврата на предыдущий шаг
@admin_router.message(StateFilter("*"), Command("назад"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "назад")
async def back_step_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()

    if current_state == AddProduct.name:
        await message.answer(
            'Предидущего шага нет, или введите название товара или напишите "отмена"'
        )
        return

    previous = None
    for step in AddProduct.__all_states__:
        if step.state == current_state:
            await state.set_state(previous)
            await message.answer(f"Ок, вы вернулись к прошлому шагу \n {AddProduct.texts[previous.state]}")
            return
        previous = step

# Обработчики для ввода данных на каждом шаге
@admin_router.message(AddProduct.name, or_f(F.text, F.text == '.'))
async def add_name(message: types.Message, state: FSMContext):
    if message.text == ".":
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        if len(message.text) >= 100:
            await message.answer("Название товара не должно превышать 100 символов.\nВведите заново")
            return

    
        await state.update_data(name=message.text)
    
    await message.answer("Введите описание авто")
    await state.set_state(AddProduct.description)

@admin_router.message(AddProduct.description, or_f(F.text, F.text == "."))  
async def add_description(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == ".":
        await state.update_data(description=AddProduct.product_for_change.description)
    else:
        await state.update_data(description=message.text)
    categories = await orm_get_categories(session)
    btns = {category.name : str(category.id) for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddProduct.category)

@admin_router.callback_query(AddProduct.category)
async def category_choice(callback: types.CallbackQuery, state: FSMContext , session: AsyncSession):
    if int(callback.data) in [category.id for category in await orm_get_categories(session)]:
        await callback.answer()
        await state.update_data(category=callback.data)
        await callback.message.answer('Теперь введите цену товара.')
        await state.set_state(AddProduct.price)
    else:
        await callback.message.answer('Выберите катеорию из кнопок.')
        await callback.answer()

#Ловим любые некорректные действия, кроме нажатия на кнопку выбора категории
@admin_router.message(AddProduct.category)
async def category_choice2(message: types.Message, state: FSMContext):
    await message.answer("'Выберите катеорию из кнопок.'") 


# Ловим данные для состояние price и потом меняем состояние на image
@admin_router.message(AddProduct.price, F.text)
async def add_price(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(price=AddProduct.product_for_change.price)
    else:
        try:
            float(message.text)
        except ValueError:
            await message.answer("Введите корректное значение цены")
            return

        await state.update_data(price=message.text)
    await message.answer("Загрузите изображение товара")
    await state.set_state(AddProduct.image)

@admin_router.message(AddProduct.image, or_f(F.photo, F.text == ".")) 
async def add_image(message: types.Message, state: FSMContext):
    if message.text and message.text == ".":
        await state.update_data(image=AddProduct.product_for_change.image)
    else:
        await state.update_data(image=message.photo[-1].file_id)

    await message.answer("Введите статус (свободен или занят):")
    await state.set_state(AddProduct.status)

@admin_router.message(AddProduct.status, F.text)
async def add_status(message: types.Message, state: FSMContext, session: AsyncSession):
    status = message.text.lower()
    if status not in ["свободен", "занят"]:
        await message.answer("Введите корректный статус (свободен или занят).")
        return

    await state.update_data(status=status)
    data = await state.get_data()

    try:
        if AddProduct.product_for_change:
            await orm_update_product(session, AddProduct.product_for_change.id, data)
        else:
            await orm_add_product(session, data)
        await message.answer("Товар добавлен/изменен", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}\nОшибка изменения авто.", reply_markup=ADMIN_KB)
    finally:
        await state.clear()

    AddProduct.product_for_change = None

@admin_router.message(AddProduct.image)
async def add_image_invalid(message: types.Message):
    await message.answer("Отправьте фото товара или напишите '.' для сохранения старого изображения.")
