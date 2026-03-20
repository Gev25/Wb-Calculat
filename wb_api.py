import requests
import logging
from datetime import datetime, timedelta

# Настройка логов специально для API, чтобы видеть ошибки запросов
logger = logging.getLogger(__name__)

def get_daily_stats(token):
    """
    Получает заказы за вчерашний день через API Статистики WB.
    Используется метод /api/v1/supplier/orders.
    """
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    
    # Вычисляем вчерашнюю дату
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Заголовки с токеном из личного кабинета (категория Статистика)
    headers = {
        "Authorization": token,
        "Accept": "application/json"
    }
    
    # Параметр dateFrom определяет, с какого момента выгружать данные
    params = {
        "dateFrom": yesterday_date,
        "flag": 1 # 1 - по дате обновления, 0 - по дате создания
    }
    
    try:
        # Делаем запрос к серверу WB
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            orders = response.json()
            
            # Оставляем только те заказы, которые были созданы именно вчера
            daily_orders = [
                order for order in orders 
                if order.get('date', '').startswith(yesterday_date)
            ]
            
            # Считаем общую сумму заказов и их количество
            total_sum = sum(order.get('priceWithDisc', 0) for order in daily_orders)
            
            return {
                "sum": total_sum,
                "count": len(daily_orders),
                "date": yesterday_date
            }
            
        elif response.status_code == 401:
            logger.error("Ошибка API WB: Невалидный токен (401).")
            return None
        elif response.status_code == 429:
            logger.warning("Ошибка API WB: Слишком много запросов (429).")
            return None
        else:
            logger.error(f"Ошибка API WB: Статус {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("Ошибка API WB: Время ожидания истекло.")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка API WB: {e}")
        return None

def check_token_validity(token):
    """
    Простая проверка токена на работоспособность.
    """
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    headers = {"Authorization": token}
    params = {"dateFrom": datetime.now().strftime('%Y-%m-%d')}
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        return res.status_code == 200
    except:
        return False