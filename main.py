import asyncio
from playwright.async_api import async_playwright, expect
from loguru import logger
import os
import sys
from config import mm_password, recovery_seed, debug_log, headless_mode, slow_mode
from logo import LOGO

# Удаляем старые логгеры
logger.remove()

# Определяем уровень логирования
log_level = "DEBUG" if debug_log else "INFO"

# Формат логов с цветами
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# Логирование в файл
logger.add("wallet_logs.log", rotation="1 MB", retention="10 days", level=log_level, format=log_format)

# Логирование в консоль (sys.stderr), с цветами
if debug_log:
    logger.add(
        sys.stderr,
        level=log_level,
        format=log_format,
        colorize=True  # Включаем цвет в консоли
    )

# Получаем путь к текущему пользователю
user_profile = os.getenv("USERPROFILE")
# Строим полный путь к расширению
extention_path = os.path.join(user_profile, "AppData", "Local", "Google", "Chrome", "User Data", "Default",
                              "Extensions", "nkbihfbeogaeaoehlefnkodbefgpgknn", "12.9.3_1")

try:
    # Читаем seed-фразу из файла
    with open(recovery_seed, "r", encoding="utf-8") as file:
        # Разделяем фразу на слова
        recovery_phrase = file.read().strip().split()
        if len(recovery_phrase) != 12:
            raise ValueError("Seed phrase должна содержать ровно 12 слов!")
        logger.debug(f"Recovery phrase прочитана успешно")
except FileNotFoundError:
    logger.error(f"Файл не найден по пути: {recovery_seed}")
    print(f"Ошибка: Файл не найден по пути: {recovery_seed}")
    exit(1)
except Exception as e:
    logger.error(f"Неожиданная ошибка: {e}")
    print(f"Ошибка: {e}")
    exit(1)

async def click_test_id(page, test_id):
    """Кликаем по элементу по test_id."""
    try:
        element = page.get_by_test_id(test_id)
        await expect(element).to_be_attached()
        await element.click()
        logger.debug(f"Клик по элементу: {test_id}")
    except Exception as e:
        logger.error(f"Ошибка при клике на {test_id}: {e}")
        raise

async def wait_for_load(page, state='domcontentloaded'):
    """Ожидаем загрузки страницы."""
    await page.wait_for_load_state(state=state)
    logger.debug(f"Страница загрузилась: {state}")

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir='',
            channel='chrome',
            headless=headless_mode,
            slow_mo=slow_mode,
            args=[
                f"--disable-extensions-except={extention_path}",
                f"--load-extension={extention_path}",
            ]
        )
        try:
            # Поиск MetaMask
            while 'MetaMask' not in [await p.title() for p in context.pages]:
                await asyncio.sleep(0.1)

            mm_page = context.pages[1]
            await wait_for_load(mm_page)

            # Согласие с условиями
            await click_test_id(mm_page, 'onboarding-terms-checkbox')

            # Импорт кошелька
            await click_test_id(mm_page, 'onboarding-import-wallet')

            # Отказ от сбора данных
            await click_test_id(mm_page, 'metametrics-no-thanks')

            # Заполнение seed-фразы
            for index, word in enumerate(recovery_phrase):
                seed_input = mm_page.get_by_test_id(f"import-srp__srp-word-{index}")
                await seed_input.fill(word)

            # Подтверждаем восстановление фразы
            await click_test_id(mm_page, 'import-srp-confirm')

            # Проверка, что мы попали на страницу создания пароля
            logger.debug("Проверка создания пароля")
            passwd_1, passwd_2 = [
                mm_page.get_by_test_id(test_id) for test_id in ['create-password-new', 'create-password-confirm']
            ]
            if passwd_1 and passwd_2:
                await passwd_1.fill(mm_password)
                await passwd_2.fill(mm_password)
                await click_test_id(mm_page, 'create-password-terms')
                await click_test_id(mm_page, 'create-password-import')

            # Завершение настройки
            for test_id in ['onboarding-complete-done', 'pin-extension-next', 'pin-extension-done']:
                await click_test_id(mm_page, test_id)

            logger.info("Импорт кошелька завершён успешно!")
            await mm_page.close()
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Ошибка в процессе выполнения: {e}")
        finally:
            await context.close()

if __name__ == '__main__':
    print(LOGO)
    asyncio.run(main())
