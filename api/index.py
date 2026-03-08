# api/index.py
from flask import Flask, render_template_string, jsonify, request
import pandas as pd
import json
import os
import sys
from datetime import datetime
import tempfile
import atexit

# Добавляем путь к родительской папке для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем ваш скрипт
try:
    import bond_recommendations
except ImportError as e:
    print(f"Warning: Could not import bond_recommendations: {e}")
    bond_recommendations = None

app = Flask(__name__)

# Используем /tmp для хранения данных (единственное доступное для записи место на Vercel)
DATA_DIR = '/tmp/bond_data'
os.makedirs(DATA_DIR, exist_ok=True)

# Пути к файлам
RECOMMENDATIONS_JSON = os.path.join(DATA_DIR, 'recommendations.json')
RECOMMENDATIONS_CSV = os.path.join(DATA_DIR, 'recommendations.csv')

# HTML шаблон (тот же, что и в web_dashboard.py)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bond Recommendations Dashboard</title>
    <meta http-equiv="refresh" content="300">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
        h1 { color: #333; }
        .timestamp { color: #666; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th { background-color: #4CAF50; color: white; padding: 12px; text-align: left; }
        td { padding: 10px; border-bottom: 1px solid #ddd; }
        tr:hover { background-color: #f5f5f5; }
        .rank-1 { background-color: #ffd700; }
        .rank-2 { background-color: #c0c0c0; }
        .rank-3 { background-color: #cd7f32; }
        .filters { margin: 20px 0; padding: 15px; background-color: #f9f9f9; border-radius: 5px; }
        .filter-group { display: inline-block; margin-right: 20px; }
        select, input { padding: 8px; border-radius: 3px; border: 1px solid #ddd; }
        button { padding: 8px 15px; background-color: #4CAF50; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #45a049; }
        .warning { background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Рекомендации по облигациям</h1>
        <div class="timestamp">Последнее обновление: {{ timestamp }}</div>

        {% if warning %}
        <div class="warning">{{ warning }}</div>
        {% endif %}

        <div class="filters">
            <h3>Фильтры:</h3>
            <div class="filter-group">
                <label>Мин. доходность (%):</label>
                <input type="number" id="minYield" value="7" min="0" max="30" step="0.5">
            </div>
            <div class="filter-group">
                <label>Макс. дюрация (лет):</label>
                <input type="number" id="maxDuration" value="8" min="0" max="20" step="1">
            </div>
            <div class="filter-group">
                <label>Мин. рейтинг:</label>
                <select id="minRating">
                    <option value="AAA">AAA</option>
                    <option value="AA">AA</option>
                    <option value="A">A</option>
                    <option value="BBB" selected>BBB</option>
                </select>
            </div>
            <button onclick="applyFilters()">Применить фильтры</button>
            <button onclick="location.reload()" style="background-color: #6c757d;">Обновить страницу</button>
        </div>

        <div id="recommendations">
            {{ table_html|safe }}
        </div>
    </div>

    <script>
        function applyFilters() {
            const minYield = document.getElementById('minYield').value;
            const maxDuration = document.getElementById('maxDuration').value;
            const minRating = document.getElementById('minRating').value;

            window.location.href = `/?minYield=${minYield}&maxDuration=${maxDuration}&minRating=${minRating}`;
        }

        // Автообновление каждые 5 минут
        setTimeout(() => location.reload(), 300000);
    </script>
</body>
</html>
'''


def load_recommendations():
    """Загрузка рекомендаций из JSON файла"""
    try:
        if os.path.exists(RECOMMENDATIONS_JSON):
            with open(RECOMMENDATIONS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading recommendations: {e}")
    return None


def save_recommendations(data):
    """Сохранение рекомендаций в JSON файл"""
    try:
        with open(RECOMMENDATIONS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving recommendations: {e}")
        return False


@app.route('/')
def dashboard():
    """Главная страница с дашбордом"""
    try:
        # Загружаем последние рекомендации
        data = load_recommendations()

        if not data:
            # Если данных нет, пробуем сгенерировать
            if bond_recommendations:
                try:
                    bond_recommendations.main()
                    data = load_recommendations()
                except Exception as e:
                    return render_template_string(
                        HTML_TEMPLATE,
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        table_html="<p>Ошибка генерации данных. Пожалуйста, попробуйте позже.</p>",
                        warning=f"Ошибка: {str(e)}"
                    )
            else:
                # Демо-данные для тестирования
                data = generate_demo_data()

        if not data:
            return render_template_string(
                HTML_TEMPLATE,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                table_html="<p>Нет данных для отображения</p>"
            )

        df = pd.DataFrame(data)

        # Применяем фильтры из URL
        min_yield = request.args.get('minYield', 7, type=float)
        max_duration = request.args.get('maxDuration', 8, type=float)
        min_rating = request.args.get('minRating', 'BBB')

        # Фильтрация
        rating_order = {'AAA': 5, 'AA': 4, 'A': 3, 'BBB': 2, 'BB': 1, 'B': 0, 'CCC': -1}

        filtered_df = df.copy()
        filtered_df = filtered_df[filtered_df['yield'] >= min_yield]
        filtered_df = filtered_df[filtered_df['duration'] <= max_duration]

        if 'rating' in filtered_df.columns:
            filtered_df['rating_score'] = filtered_df['rating'].map(rating_order).fillna(0)
            min_rating_score = rating_order.get(min_rating, 2)
            filtered_df = filtered_df[filtered_df['rating_score'] >= min_rating_score]

        # Сортируем по скорингу
        if 'score' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('score', ascending=False)

        # Добавляем ранг
        filtered_df.insert(0, 'rank', range(1, len(filtered_df) + 1))

        # Форматируем для отображения
        display_df = filtered_df.copy()
        for col in ['price', 'coupon', 'duration']:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):.2f}" if x else '0.00')

        if 'yield' in display_df.columns:
            display_df['yield'] = display_df['yield'].apply(lambda x: f"{float(x):.2f}%")

        if 'score' in display_df.columns:
            display_df['score'] = display_df['score'].apply(lambda x: f"{float(x):.3f}")

        # Выбираем колонки для отображения
        display_columns = ['rank', 'ticker', 'name', 'price', 'coupon', 'yield',
                           'duration', 'rating', 'sector', 'score']
        display_columns = [col for col in display_columns if col in display_df.columns]

        # Создаем HTML таблицу
        if not display_df.empty:
            table_html = display_df[display_columns].to_html(
                classes='table',
                index=False,
                escape=False,
                na_rep='-'
            )
        else:
            table_html = "<p>Нет данных, соответствующих фильтрам</p>"

        return render_template_string(
            HTML_TEMPLATE,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=table_html,
            warning=None
        )
    except Exception as e:
        return render_template_string(
            HTML_TEMPLATE,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=f"<p>Ошибка: {str(e)}</p>",
            warning="Произошла ошибка при загрузке данных"
        )


@app.route('/health')
def health():
    """Endpoint для проверки здоровья"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'data_dir': DATA_DIR,
        'data_exists': os.path.exists(RECOMMENDATIONS_JSON)
    })


@app.route('/update-bonds')
def update_bonds():
    """Эндпоинт для запуска обновления данных (для cron-job.org)"""
    if not bond_recommendations:
        return jsonify({
            'status': 'error',
            'message': 'bond_recommendations module not available'
        }), 500

    try:
        # Запускаем обновление
        bond_recommendations.main()

        # Проверяем, что данные сохранились
        if os.path.exists(RECOMMENDATIONS_JSON):
            return jsonify({
                'status': 'success',
                'message': 'Data updated successfully',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': 'Update completed but data file not found',
                'timestamp': datetime.now().isoformat()
            }), 202
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/recommendations')
def api_recommendations():
    """API для получения данных в JSON формате"""
    data = load_recommendations()
    if data:
        return jsonify(data)
    return jsonify({'error': 'No data available'}), 404


@app.route('/debug')
def debug():
    """Отладочная информация"""
    info = {
        'cwd': os.getcwd(),
        'data_dir': DATA_DIR,
        'data_exists': os.path.exists(RECOMMENDATIONS_JSON),
        'files_in_data': os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else [],
        'bond_recommendations_available': bond_recommendations is not None,
        'python_version': sys.version,
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(info)


@app.route('/debug-data')
def debug_data():
    """Отладочная информация о данных"""
    try:
        # Запускаем анализ напрямую
        analyzer = bond_recommendations.BondAnalyzer()
        bonds = analyzer.fetch_moex_bonds()

        if bonds:
            recommendations = analyzer.get_recommendations(bonds)

            info = {
                'total_bonds_fetched': len(bonds),
                'total_recommendations': len(recommendations) if not recommendations.empty else 0,
                'sample_bonds': [
                    {
                        'ticker': b.ticker,
                        'name': b.name,
                        'price': b.price,
                        'coupon_rub': b.coupon_rub,
                        'ytm': b.yield_to_maturity
                    }
                    for b in bonds[:5]
                ],
                'using_mock': analyzer.use_mock_data,
                'timestamp': datetime.now().isoformat()
            }

            if not recommendations.empty:
                info['sample_recommendations'] = recommendations.head(3).to_dict('records')
        else:
            info = {'error': 'No bonds returned'}

        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


def generate_demo_data():
    """Генерация демо-данных для тестирования"""
    demo_data = [
        {
            'ticker': 'SU29007RMFS5',
            'name': 'ОФЗ 29007',
            'price': 98.50,
            'coupon': 7.15,
            'yield': 7.35,
            'maturity': '2027-12-15',
            'duration': 3.2,
            'rating': 'AAA',
            'sector': 'Government',
            'score': 8.7
        },
        {
            'ticker': 'RU000A101VR0',
            'name': 'Сбер Sb27R',
            'price': 101.20,
            'coupon': 8.50,
            'yield': 8.15,
            'maturity': '2029-03-21',
            'duration': 4.1,
            'rating': 'AAA',
            'sector': 'Finance',
            'score': 9.2
        },
        {
            'ticker': 'RU000A1025J6',
            'name': 'Газпром Капитал',
            'price': 97.80,
            'coupon': 9.20,
            'yield': 9.45,
            'maturity': '2030-06-10',
            'duration': 5.8,
            'rating': 'AA',
            'sector': 'Oil & Gas',
            'score': 9.8
        }
    ]
    save_recommendations(demo_data)
    return demo_data


# При запуске приложения пробуем загрузить или создать данные
with app.app_context():
    if not load_recommendations() and bond_recommendations:
        try:
            print("Generating initial data...")
            bond_recommendations.main()
        except Exception as e:
            print(f"Error generating initial data: {e}")
            generate_demo_data()

# Для локальной разработки
if __name__ == '__main__':
    app.run(debug=True, port=5000)