# api/index.py
from flask import Flask, render_template_string, jsonify, request
import pandas as pd
import json
import os
import sys
from datetime import datetime
import tempfile
import atexit
import traceback  # <--- ДОБАВЛЕНО: для отладки

# Добавляем путь к родительской папке для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем ваш скрипт
try:
    import bond_recommendations

    print("✅ bond_recommendations imported successfully")
except ImportError as e:
    print(f"❌ Could not import bond_recommendations: {e}")
    bond_recommendations = None

app = Flask(__name__)

# Используем /tmp для хранения данных (единственное доступное для записи место на Vercel)
DATA_DIR = '/tmp/bond_data'
os.makedirs(DATA_DIR, exist_ok=True)

# Пути к файлам
RECOMMENDATIONS_JSON = os.path.join(DATA_DIR, 'recommendations.json')
RECOMMENDATIONS_CSV = os.path.join(DATA_DIR, 'recommendations.csv')

# HTML шаблон с обновленными названиями колонок
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bond Recommendations Dashboard</title>
    <meta http-equiv="refresh" content="300">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; }
        .container { max-width: 1400px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
        h1 { color: #333; }
        .timestamp { color: #666; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 0.9em; }
        th { background-color: #4CAF50; color: white; padding: 12px; text-align: left; position: sticky; top: 0; }
        td { padding: 10px; border-bottom: 1px solid #ddd; }
        tr:hover { background-color: #f5f5f5; }
        .rank-1 { background-color: #ffd700; }
        .rank-2 { background-color: #c0c0c0; }
        .rank-3 { background-color: #cd7f32; }
        .money { font-family: 'Courier New', monospace; font-weight: bold; color: #27ae60; }
        .filters { margin: 20px 0; padding: 15px; background-color: #f9f9f9; border-radius: 5px; }
        .filter-group { display: inline-block; margin-right: 20px; }
        select, input { padding: 8px; border-radius: 3px; border: 1px solid #ddd; }
        button { padding: 8px 15px; background-color: #4CAF50; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #45a049; }
        .warning { background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .summary { background: #e8f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .summary-item { display: inline-block; margin-right: 30px; }
        .summary-label { color: #34495e; font-size: 0.9em; }
        .summary-value { font-size: 1.3em; font-weight: bold; color: #2980b9; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Рекомендации по облигациям</h1>
        <div class="timestamp">Последнее обновление: {{ timestamp }}</div>

        {% if warning %}
        <div class="warning">{{ warning }}</div>
        {% endif %}

        <div class="summary">
            <div class="summary-item">
                <div class="summary-label">💰 Всего облигаций</div>
                <div class="summary-value" id="totalCount">{{ total_count }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">📈 Лучшая доходность</div>
                <div class="summary-value" id="bestYield">{{ best_yield }}</div>
            </div>
        </div>

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
    </script>
</body>
</html>
'''


def load_recommendations():
    """Загрузка рекомендаций из JSON файла"""
    try:
        if os.path.exists(RECOMMENDATIONS_JSON):
            with open(RECOMMENDATIONS_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"✅ Loaded {len(data)} recommendations from {RECOMMENDATIONS_JSON}")
                return data
        else:
            print(f"⚠️ File not found: {RECOMMENDATIONS_JSON}")
    except Exception as e:
        print(f"❌ Error loading recommendations: {e}")
    return None


def save_recommendations(data):
    """Сохранение рекомендаций в JSON файл"""
    try:
        with open(RECOMMENDATIONS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved {len(data)} recommendations to {RECOMMENDATIONS_JSON}")
        return True
    except Exception as e:
        print(f"❌ Error saving recommendations: {e}")
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
                print("🔄 Generating initial data...")
                try:
                    bond_recommendations.main()
                    data = load_recommendations()
                except Exception as e:
                    print(f"❌ Error generating data: {e}")
                    traceback.print_exc()
                    return render_template_string(
                        HTML_TEMPLATE,
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        table_html="<p>Ошибка генерации данных. Пожалуйста, попробуйте позже.</p>",
                        warning=f"Ошибка: {str(e)}",
                        total_count=0,
                        best_yield="0%"
                    )
            else:
                # Демо-данные для тестирования
                print("🔄 Using demo data...")
                data = generate_demo_data()

        if not data:
            print("⚠️ No data available")
            return render_template_string(
                HTML_TEMPLATE,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                table_html="<p>Нет данных для отображения</p>",
                total_count=0,
                best_yield="0%"
            )

        # Преобразуем в DataFrame
        df = pd.DataFrame(data)
        print(f"📊 DataFrame columns: {list(df.columns)}")
        print(f"📊 DataFrame shape: {df.shape}")

        # Проверяем, есть ли нужные колонки
        required_cols = ['yield', 'duration']
        for col in required_cols:
            if col not in df.columns:
                print(f"⚠️ Column {col} not found in data")
                # Пробуем найти альтернативы
                if col == 'yield' and 'yield_pa' in df.columns:
                    df['yield'] = df['yield_pa']
                elif col == 'yield' and 'ytm' in df.columns:
                    df['yield'] = df['ytm'] * 100

        # Применяем фильтры из URL
        min_yield = request.args.get('minYield', 0, type=float)  # <--- ИЗМЕНЕНО: по умолчанию 0
        max_duration = request.args.get('maxDuration', 100, type=float)  # <--- ИЗМЕНЕНО: большое значение
        min_rating = request.args.get('minRating', 'CCC')  # <--- ИЗМЕНЕНО: минимальный рейтинг

        print(f"🔍 Filters - min_yield: {min_yield}, max_duration: {max_duration}, min_rating: {min_rating}")

        filtered_df = df.copy()

        # Применяем фильтры только если колонки существуют
        if 'yield' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['yield'] >= min_yield]
        if 'duration' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['duration'] <= max_duration]

        if 'rating' in filtered_df.columns and min_rating != 'CCC':
            rating_order = {'AAA': 5, 'AA': 4, 'A': 3, 'BBB': 2, 'BB': 1, 'B': 0, 'CCC': -1}
            filtered_df['rating_score'] = filtered_df['rating'].map(rating_order).fillna(-1)
            min_rating_score = rating_order.get(min_rating, -1)
            filtered_df = filtered_df[filtered_df['rating_score'] >= min_rating_score]

        # Сортируем по скорингу или доходности
        if 'score' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('score', ascending=False)
        elif 'yield' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('yield', ascending=False)

        # Добавляем ранг
        if not filtered_df.empty:
            filtered_df.insert(0, 'rank', range(1, len(filtered_df) + 1))

        # Форматируем для отображения
        display_df = filtered_df.copy()

        # Определяем колонки для отображения
        display_columns = ['rank']

        # Добавляем колонки, которые есть в данных
        for col in ['ticker', 'name', 'price', 'coupon_rub', 'monthly_income', 'yield_pa', 'yield',
                    'duration', 'rating', 'sector']:
            if col in display_df.columns:
                display_columns.append(col)

        # Если нет новых полей, используем старые
        if len(display_columns) <= 1:
            display_columns = ['rank', 'ticker', 'name', 'price', 'coupon', 'yield',
                               'duration', 'rating', 'sector', 'score']
            display_columns = [col for col in display_columns if col in display_df.columns]

        # Форматирование чисел
        for col in display_df.columns:
            if col in ['price', 'coupon_rub', 'monthly_income']:
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):,.0f} ₽" if pd.notna(x) else '-')
            elif col == 'yield_pa':
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):.2f}%" if pd.notna(x) else '-')
            elif col == 'yield':
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):.2f}%" if pd.notna(x) else '-')
            elif col == 'duration':
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):.1f} лет" if pd.notna(x) else '-')
            elif col == 'coupon':
                display_df[col] = display_df[col].apply(lambda x: f"{float(x):.2f}%" if pd.notna(x) else '-')

        # Создаем HTML таблицу
        if not display_df.empty:
            table_html = display_df[display_columns].to_html(
                classes='table',
                index=False,
                escape=False,
                na_rep='-'
            )
            total_count = len(display_df)
            best_yield = f"{display_df['yield_pa'].iloc[0]}" if 'yield_pa' in display_df.columns else f"{
            display_df['yield'].iloc[0]}" if 'yield' in display_df.columns else "0%"
        else:
            table_html = "<p>Нет данных, соответствующих фильтрам</p>"
            total_count = 0
            best_yield = "0%"

        return render_template_string(
            HTML_TEMPLATE,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=table_html,
            warning=None,
            total_count=total_count,
            best_yield=best_yield
        )
    except Exception as e:
        print(f"❌ Error in dashboard: {e}")
        traceback.print_exc()
        return render_template_string(
            HTML_TEMPLATE,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=f"<p>Ошибка: {str(e)}</p>",
            warning="Произошла ошибка при загрузке данных",
            total_count=0,
            best_yield="0%"
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
        result = bond_recommendations.main()

        # Проверяем, что данные сохранились
        if os.path.exists(RECOMMENDATIONS_JSON):
            return jsonify({
                'status': 'success',
                'message': 'Data updated successfully',
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': 'Update completed but data file not found',
                'timestamp': datetime.now().isoformat()
            }), 202
    except Exception as e:
        print(f"❌ Error in update_bonds: {e}")
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/recommendations')
def api_recommendations():
    """API для получения данных в JSON формате"""
    data = load_recommendations()
    if data:
        return jsonify(data)
    return jsonify({'error': 'No data available', 'data_dir': DATA_DIR}), 404


@app.route('/debug')
def debug():
    """Отладочная информация"""
    try:
        files = os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else []
        data_content = None
        if os.path.exists(RECOMMENDATIONS_JSON):
            with open(RECOMMENDATIONS_JSON, 'r') as f:
                data_content = json.load(f)[:2] if os.path.getsize(RECOMMENDATIONS_JSON) > 0 else []

        info = {
            'cwd': os.getcwd(),
            'data_dir': DATA_DIR,
            'data_dir_exists': os.path.exists(DATA_DIR),
            'data_file_exists': os.path.exists(RECOMMENDATIONS_JSON),
            'files_in_data': files,
            'sample_data': data_content,
            'bond_recommendations_available': bond_recommendations is not None,
            'python_version': sys.version,
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/debug-data')
def debug_data():
    """Отладочная информация о данных"""
    try:
        if not bond_recommendations:
            return jsonify({'error': 'bond_recommendations not available'}), 500

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
                info['recommendations_columns'] = list(recommendations.columns)
        else:
            info = {'error': 'No bonds returned'}

        return jsonify(info)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


def generate_demo_data():
    """Генерация демо-данных для тестирования с правильными названиями полей"""
    demo_data = [
        {
            'ticker': 'SU29007RMFS5',
            'name': 'ОФЗ 29007',
            'price': 98.50,
            'coupon_rub': 71.50,  # <--- ИЗМЕНЕНО
            'monthly_income': 595.83,  # <--- ДОБАВЛЕНО
            'yield_pa': 7.35,  # <--- ИЗМЕНЕНО
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
            'coupon_rub': 85.00,
            'monthly_income': 708.33,
            'yield_pa': 8.15,
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
            'coupon_rub': 92.00,
            'monthly_income': 766.67,
            'yield_pa': 9.45,
            'maturity': '2030-06-10',
            'duration': 5.8,
            'rating': 'AA',
            'sector': 'Oil & Gas',
            'score': 9.8
        }
    ]
    save_recommendations(demo_data)
    print("✅ Demo data generated and saved")
    return demo_data


# При запуске приложения пробуем загрузить или создать данные
with app.app_context():
    if not load_recommendations():
        if bond_recommendations:
            try:
                print("🔄 Generating initial data with bond_recommendations...")
                bond_recommendations.main()
            except Exception as e:
                print(f"❌ Error generating initial data: {e}")
                traceback.print_exc()
                print("🔄 Falling back to demo data...")
                generate_demo_data()
        else:
            print("🔄 bond_recommendations not available, using demo data...")
            generate_demo_data()

# Для локальной разработки
if __name__ == '__main__':
    app.run(debug=True, port=5000)