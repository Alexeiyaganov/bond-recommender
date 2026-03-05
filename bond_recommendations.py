# bond_recommendations.py
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
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
    coupon: float
    maturity_date: str
    yield_to_maturity: float
    duration: float
    credit_rating: str
    sector: str
    volume_24h: float


class BondAnalyzer:
    def __init__(self):
        # Для Vercel API запросы могут быть ограничены
        self.use_mock_data = True  # Переключите на False, если хотите использовать реальные API
        self.api_key = os.environ.get('BOND_API_KEY', 'demo_key')

    def fetch_moex_bonds(self):
        """Получение данных об облигациях (заглушка для Vercel)"""
        if self.use_mock_data:
            return self.generate_mock_bonds()

        try:
            # Реальный запрос к MOEX API
            url = "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities.json"
            response = requests.get(url, timeout=10)
            data = response.json()

            bonds = []
            securities = data.get('securities', {}).get('data', [])
            marketdata = data.get('marketdata', {}).get('data', [])

            for i, sec in enumerate(securities[:20]):  # Берем первые 20 для примера
                if i < len(marketdata):
                    bond = Bond(
                        ticker=sec[0] if len(sec) > 0 else '',
                        name=sec[2] if len(sec) > 2 else '',
                        price=float(marketdata[i][12]) if i < len(marketdata) and marketdata[i][12] else 0,
                        coupon=float(sec[64]) if len(sec) > 64 and sec[64] else 0,
                        maturity_date=sec[17] if len(sec) > 17 else '',
                        yield_to_maturity=float(marketdata[i][23]) / 100 if i < len(marketdata) and marketdata[i][
                            23] else 0,
                        duration=self.calculate_duration(sec),
                        credit_rating=self.get_credit_rating(sec[0]),
                        sector=self.determine_sector(sec[2]),
                        volume_24h=float(marketdata[i][14]) if i < len(marketdata) and marketdata[i][14] else 0
                    )
                    bonds.append(bond)

            return bonds
        except Exception as e:
            print(f"Ошибка получения данных: {e}")
            return self.generate_mock_bonds()

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
            coupon = base_yield * 0.9 + np.random.normal(0, 0.5)
            ytm = base_yield / 100 + np.random.normal(0, 0.01)
            maturity = (datetime.now() + timedelta(days=np.random.randint(365, 365 * 5))).strftime('%Y-%m-%d')
            duration = np.random.uniform(1, 7)
            rating = np.random.choice(ratings, p=weights)
            volume = np.random.uniform(10, 100) * 1e6

            bond = Bond(
                ticker=ticker,
                name=name,
                price=round(price, 2),
                coupon=round(coupon, 2),
                maturity_date=maturity,
                yield_to_maturity=round(ytm, 4),
                duration=round(duration, 2),
                credit_rating=rating,
                sector=sector,
                volume_24h=volume
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

    def get_credit_rating(self, ticker):
        """Получение кредитного рейтинга"""
        ratings = ['AAA', 'AA', 'A', 'BBB', 'BB']
        weights = [0.15, 0.25, 0.3, 0.2, 0.1]
        return np.random.choice(ratings, p=weights)

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
        """Формирование рекомендаций"""
        recommendations = []

        for bond in bonds:
            if bond.price <= 0 or bond.yield_to_maturity <= 0:
                continue

            sharpe = self.calculate_sharpe_ratio(bond)
            yield_per_duration = bond.yield_to_maturity / (bond.duration + 0.01)
            liquidity_score = min(bond.volume_24h / 1000000, 10)

            rating_scores = {'AAA': 5, 'AA': 4, 'A': 3, 'BBB': 2, 'BB': 1, 'B': 0}
            rating_score = rating_scores.get(bond.credit_rating, 0)

            total_score = (
                    bond.yield_to_maturity * 30 +
                    sharpe * 200 +
                    yield_per_duration * 20 +
                    liquidity_score * 1 +
                    rating_score * 20
            )

            recommendations.append({
                'ticker': bond.ticker,
                'name': bond.name,
                'price': round(bond.price, 2),
                'coupon': round(bond.coupon, 2),
                'yield': round(bond.yield_to_maturity * 100, 2),
                'maturity': bond.maturity_date,
                'duration': round(bond.duration, 2),
                'rating': bond.credit_rating,
                'sector': bond.sector,
                'score': round(total_score, 3),
                'sharpe': round(sharpe, 3)
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