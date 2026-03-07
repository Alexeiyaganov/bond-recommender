# bond_recommendations.py
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
import time  # <--- ДОБАВЛЕНО: для пауз между запросами
from dataclasses import dataclass
from typing import List, Dict
import warnings

warnings.filterwarnings('ignore')

# Определяем директорию для данных
DATA_DIR = '/tmp/bond_data' if os.path.exists('/tmp') else './data'
os.makedirs(DATA_DIR, exist_ok=True)


@dataclass
class Bond:
    ticker: str
    name: str
    price: float
    coupon: float  # Годовой купон в процентах
    coupon_rub: float  # <--- ИСПРАВЛЕНО: теперь обязательное поле
    coupon_period: int  # <--- ИСПРАВЛЕНО: теперь обязательное поле
    maturity_date: str
    yield_to_maturity: float
    duration: float
    credit_rating: str
    sector: str
    volume_24h: float
    lot_size: int = 10  # Размер лота (обычно 10 облигаций)

    def monthly_payment(self, lots=1):
        """Расчет ежемесячного дохода при покупке указанного количества лотов"""
        total_bonds = lots * self.lot_size
        yearly_coupon_income = total_bonds * self.coupon_rub
        monthly_income = yearly_coupon_income / 12
        return round(monthly_income, 2)

    def investment_amount(self, lots=1):
        """Сумма инвестиций для покупки указанного количества лотов"""
        total_bonds = lots * self.lot_size
        return round(total_bonds * self.price, 2)


class BondAnalyzer:
    def __init__(self):
        # Для Vercel API запросы могут быть ограничены
        self.use_mock_data = False  # Режим реальных данных
        self.api_key = os.environ.get('BOND_API_KEY', 'demo_key')

    def fetch_moex_bonds(self):
        """Получение реальных данных с Московской биржи"""
        try:
            # Получаем данные о торгах
            market_url = "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities.json"

            # <--- ДОБАВЛЕНО: параметры для оптимизации запроса
            params = {
                'iss.meta': 'off',
                'limit': 100,
            }

            response = requests.get(market_url, params=params, timeout=10)
            data = response.json()

            securities = data.get('securities', {}).get('data', [])
            marketdata = data.get('marketdata', {}).get('data', [])

            print(f"Получено {len(securities)} ценных бумаг из MOEX")

            # Получаем дополнительные данные по купонам
            bonds = []
            for i, sec in enumerate(securities[:50]):  # Берем топ-50 для начала
                if i >= len(marketdata):
                    continue

                ticker = sec[0] if len(sec) > 0 else ''
                name = sec[2] if len(sec) > 2 else ''
                short_name = sec[3] if len(sec) > 3 else ''  # <--- ДОБАВЛЕНО: короткое имя

                # Используем короткое имя, если длинное пустое
                display_name = name or short_name

                price = float(marketdata[i][12]) if marketdata[i][12] else 0

                # Получаем данные о купонах
                coupon_data = self.fetch_coupon_data(ticker)

                # <--- ИСПРАВЛЕНО: передаем все обязательные поля
                bond = Bond(
                    ticker=ticker,
                    name=display_name,
                    price=price,
                    coupon=coupon_data['coupon_percent'],
                    coupon_rub=coupon_data['coupon_rub'],  # Теперь передаем
                    coupon_period=coupon_data['period_months'],  # Теперь передаем
                    maturity_date=sec[17] if len(sec) > 17 else '',
                    yield_to_maturity=float(marketdata[i][23]) / 100 if marketdata[i][23] else 0,
                    duration=self.calculate_duration(sec),
                    credit_rating=self.get_credit_rating_fallback(ticker),  # <--- ИСПРАВЛЕНО
                    sector=self.determine_sector(name),
                    volume_24h=float(marketdata[i][14]) if marketdata[i][14] else 0,
                    lot_size=self.get_lot_size(ticker)
                )
                bonds.append(bond)

                # <--- ДОБАВЛЕНО: пауза между запросами
                if i % 10 == 0 and i > 0:
                    time.sleep(0.5)

            print(f"Успешно обработано {len(bonds)} облигаций")
            return bonds

        except Exception as e:
            print(f"Ошибка получения данных с MOEX: {e}")
            return self.generate_mock_bonds()  # Запасной вариант

    def fetch_coupon_data(self, ticker):
        """Получение данных о купонах по конкретной облигации"""
        try:
            url = f"https://iss.moex.com/iss/securities/{ticker}/bondization.json"
            response = requests.get(url, timeout=5)
            data = response.json()

            # Парсим данные о купонах
            coupons = data.get('coupons', {}).get('data', [])
            if coupons and len(coupons) > 0:
                # Берем первый купон как пример
                coupon_rub = float(coupons[0][7]) if len(coupons[0]) > 7 and coupons[0][7] else 0
                coupon_percent = float(coupons[0][6]) if len(coupons[0]) > 6 and coupons[0][6] else 0

                # Определяем период выплаты
                period_months = 3  # По умолчанию
                if len(coupons) > 1 and len(coupons[1]) > 5:
                    try:
                        date1 = datetime.strptime(coupons[0][5], '%Y-%m-%d')
                        date2 = datetime.strptime(coupons[1][5], '%Y-%m-%d')
                        period_days = (date2 - date1).days
                        period_months = max(1, round(period_days / 30.44))
                    except:
                        pass

                return {
                    'coupon_rub': coupon_rub,
                    'coupon_percent': coupon_percent,
                    'period_months': period_months
                }
        except Exception as e:
            print(f"Ошибка получения купонов для {ticker}: {e}")

        # Данные по умолчанию, если не удалось получить
        return {
            'coupon_rub': np.random.uniform(30, 100),
            'coupon_percent': np.random.uniform(7, 12),
            'period_months': 3
        }

    def get_lot_size(self, ticker):
        """Определение размера лота (обычно 1 или 10)"""
        if ticker.startswith('SU'):  # ОФЗ обычно лот 1
            return 1
        return 10  # Корпоративные часто лот 10

    # <--- ДОБАВЛЕНО: новая функция для расчета дюрации из даты
    def calculate_duration_from_maturity(self, maturity_date):
        """Расчет дюрации на основе даты погашения"""
        if not maturity_date:
            return 3.0

        try:
            maturity = datetime.strptime(maturity_date, '%Y-%m-%d')
            today = datetime.now()
            years = (maturity - today).days / 365.25
            return max(0.1, min(30, round(years, 2)))
        except:
            return 3.0

    # <--- ДОБАВЛЕНО: временная заглушка для рейтинга
    def get_credit_rating_fallback(self, ticker):
        """Временная заглушка для рейтинга"""
        # ОФЗ - самые надежные
        if ticker.startswith('SU'):
            return 'AAA'
        # Корпоративные - разные
        ratings = ['AAA', 'AA', 'A', 'BBB']
        weights = [0.2, 0.3, 0.3, 0.2]
        return np.random.choice(ratings, p=weights)

    def generate_mock_bonds(self):
        """Генерация тестовых данных"""
        bonds = []
        names = [
            ('ОФЗ 26238', 'Government', 7.2),
            ('Сбер Sb31R', 'Finance', 8.1),
            ('Газпром GAZP-28', 'Oil & Gas', 8.8),
            ('РЖД 28', 'Transport', 8.3),
            ('ВТБ П-27', 'Finance', 8.9),
            ('Лукойл 26', 'Oil & Gas', 7.9),
            ('МТС 29', 'Telecom', 9.2),
            ('Роснефть 27', 'Oil & Gas', 8.5),
            ('АЛРОСА 28', 'Mining', 9.0),
            ('Совкомфлот 26', 'Transport', 8.7)
        ]

        ratings = ['AAA', 'AA', 'A', 'BBB']
        weights = [0.2, 0.3, 0.3, 0.2]

        for i, (name, sector, base_yield) in enumerate(names):
            ticker = f"RU{i:06d}"
            price = np.random.normal(100, 5)
            coupon_percent = base_yield * 0.9 + np.random.normal(0, 0.5)
            coupon_rub = price * (coupon_percent / 100)  # <--- ИСПРАВЛЕНО: рассчитываем купон в рублях
            ytm = base_yield / 100 + np.random.normal(0, 0.01)
            maturity = (datetime.now() + timedelta(days=np.random.randint(365, 365 * 5))).strftime('%Y-%m-%d')
            duration = np.random.uniform(1, 7)
            rating = np.random.choice(ratings, p=weights)
            volume = np.random.uniform(10, 100) * 1e6

            # <--- ИСПРАВЛЕНО: передаем все обязательные поля
            bond = Bond(
                ticker=ticker,
                name=name,
                price=round(price, 2),
                coupon=round(coupon_percent, 2),
                coupon_rub=round(coupon_rub, 2),  # Добавлено
                coupon_period=3,  # Добавлено (по умолчанию 3 месяца)
                maturity_date=maturity,
                yield_to_maturity=round(ytm, 4),
                duration=round(duration, 2),
                credit_rating=rating,
                sector=sector,
                volume_24h=volume,
                lot_size=10  # Добавлено
            )
            bonds.append(bond)

        return bonds

    def calculate_duration(self, sec_data):
        """Упрощенный расчет дюрации"""
        try:
            maturity = sec_data[17] if len(sec_data) > 17 else ''
            if maturity:
                maturity_date = datetime.strptime(maturity, '%Y-%m-%d')
                today = datetime.now()
                years = (maturity_date - today).days / 365.25
                return max(0.1, min(10, years))
        except:
            pass
        return np.random.uniform(1, 5)

    # <--- ИСПРАВЛЕНО: старая функция get_credit_rating теперь не используется
    # но оставляем для совместимости
    def get_credit_rating(self, ticker):
        """Устаревшая функция, используйте get_credit_rating_fallback"""
        return self.get_credit_rating_fallback(ticker)

    def determine_sector(self, name):
        """Определение сектора эмитента"""
        sectors = {
            'ОФЗ': 'Government',
            'Сбер': 'Finance',
            'ВТБ': 'Finance',
            'Газпром': 'Oil & Gas',
            'Роснефть': 'Oil & Gas',
            'Лукойл': 'Oil & Gas',
            'РЖД': 'Transport',
            'МТС': 'Telecom',
            'АЛРОСА': 'Mining',
            'Совкомфлот': 'Transport'
        }

        for key, sector in sectors.items():
            if key in name:
                return sector
        return 'Other'

    def calculate_sharpe_ratio(self, bond):
        """Расчет коэффициента Шарпа"""
        risk_free_rate = 0.07
        if bond.yield_to_maturity > 0 and bond.duration > 0:
            excess_return = bond.yield_to_maturity - risk_free_rate
            volatility = bond.duration * 0.01
            return excess_return / volatility if volatility > 0 else 0
        return 0

    def get_recommendations(self, bonds: List[Bond]) -> pd.DataFrame:
        """Формирование рекомендаций с расчетом дохода"""
        recommendations = []

        for bond in bonds:
            if bond.price <= 0 or bond.yield_to_maturity <= 0:
                continue

            # Базовые метрики
            sharpe = self.calculate_sharpe_ratio(bond)

            # <--- ДОБАВЛЕНО: расчет дохода для разных сумм инвестиций
            inv_amount = bond.investment_amount(1)  # 1 лот
            monthly_income = bond.monthly_payment(1)

            # Оценка выгодности
            monthly_yield = (monthly_income / inv_amount * 100) if inv_amount > 0 else 0

            rating_scores = {'AAA': 5, 'AA': 4, 'A': 3, 'BBB': 2, 'BB': 1, 'B': 0}
            rating_score = rating_scores.get(bond.credit_rating, 0)

            # <--- ИСПРАВЛЕНО: обновленная формула скоринга
            total_score = (
                    monthly_yield * 0.3 +  # Важность месячного дохода
                    bond.yield_to_maturity * 100 * 0.3 +  # Важность годовой доходности
                    (10 - bond.duration) * 0.2 +  # Чем короче, тем лучше
                    rating_score * 0.2  # Важность рейтинга
            )

            # <--- ДОБАВЛЕНО: новые поля в рекомендациях
            recommendations.append({
                'ticker': bond.ticker,
                'name': bond.name,
                'price': round(bond.price, 2),
                'lot_size': bond.lot_size,
                'min_investment': round(inv_amount, 2),  # Минимальная сумма для покупки
                'coupon_rub': round(bond.coupon_rub, 2),
                'coupon_period': f"{bond.coupon_period} мес",
                'monthly_income': round(monthly_income, 2),  # Ежемесячный доход с 1 лота
                'yield_pa': round(bond.yield_to_maturity * 100, 2),
                'monthly_yield': round(monthly_yield, 2),  # Месячная доходность в %
                'maturity': bond.maturity_date,
                'duration': round(bond.duration, 2),
                'rating': bond.credit_rating,
                'sector': bond.sector,
                'score': round(total_score, 3)
            })

        df = pd.DataFrame(recommendations)
        if not df.empty:
            df = df.sort_values('score', ascending=False)

        return df


def save_recommendations(df: pd.DataFrame, filename='recommendations.json'):
    """Сохранение рекомендаций в JSON (в /tmp)"""
    try:
        filepath = os.path.join(DATA_DIR, filename)
        data = df.to_dict(orient='records')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(data)} recommendations to {filepath}")

        # Также сохраняем в CSV для совместимости
        csv_path = os.path.join(DATA_DIR, 'recommendations.csv')
        df.to_csv(csv_path, index=False)

        return True
    except Exception as e:
        print(f"Error saving recommendations: {e}")
        return False


def main():
    """Основная функция для запуска анализа"""
    print(f"Starting bond analysis at {datetime.now()}")
    print(f"Using data directory: {DATA_DIR}")

    analyzer = BondAnalyzer()
    bonds = analyzer.fetch_moex_bonds()

    if bonds:
        recommendations = analyzer.get_recommendations(bonds)

        if not recommendations.empty:
            success = save_recommendations(recommendations)
            if success:
                print(f"Successfully saved {len(recommendations)} recommendations")

                # <--- ДОБАВЛЕНО: вывод топ-5 в консоль
                print("\nТоп-5 рекомендаций:")
                top5 = recommendations.head(5)
                for idx, row in top5.iterrows():
                    print(f"{row['ticker']} | {row['name']} | Доход: {row['monthly_income']}₽/мес | Доходность: {row[
                        'yield_pa']}%")

                return True
            else:
                print("Failed to save recommendations")
        else:
            print("No recommendations generated")
    else:
        print("No bonds data available")

    return False


if __name__ == "__main__":
    main()