<div align="center">
  
  <img src="../images/logo.png" width="400" alt="QueryGPT">
  
  <br/>
  
  <p>
    <a href="README.md">English</a> •
    <a href="docs/README_CN.md">简体中文</a> •
    <a href="#">Русский</a>
  </p>
  
  <br/>
  
  [![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![OpenInterpreter](https://img.shields.io/badge/OpenInterpreter-0.4.3-green.svg?style=for-the-badge)](https://github.com/OpenInterpreter/open-interpreter)
  [![Stars](https://img.shields.io/badge/Stars-MoonMao42/ReceiptBI-yellow.svg?style=for-the-badge&color=yellow)](https://github.com/MoonMao42/ReceiptBI/stargazers)
  
  <br/>
  
  <h3>Интеллектуальный агент для анализа данных на основе OpenInterpreter</h3>
  <p><i>Общайтесь с вашей базой данных на естественном языке</i></p>
  
</div>

## ✨ Ключевые преимущества

**Думает как аналитик данных**
- **Автономное исследование**: Проактивно изучает структуру таблиц и образцы данных
- **Многоэтапная проверка**: Повторная валидация при обнаружении аномалий для точности
- **Сложный анализ**: Не только SQL — может выполнять Python для статистики и ML
- **Видимое мышление**: Отображение хода рассуждений агента в реальном времени (Chain-of-Thought)

## 📸 Скриншоты системы

<img src="../images/agent-thinking-en.png" width="100%" alt="Интерфейс QueryGPT"/>

**Прозрачная визуализация мыслительного процесса ИИ.**

---

<img src="../images/data-visualization-en.png" width="100%" alt="Визуализация данных"/>

**Автоматическая генерация интерактивных графиков, мгновенные инсайты.**

---

<img src="../images/developer-view-en.png" width="100%" alt="Режим разработчика"/>

**Полностью прозрачное исполнение кода, поддержка SQL и Python.**

## 🌟 Возможности

### Ядро агента
- **Автономное изучение данных**: Понимание структуры и связей
- **Многошаговое рассуждение**: Глубокий анализ проблем
- **Chain-of-Thought**: Визуализация хода мыслей в реальном времени
- **Контекстная память**: Учет истории диалога

### Аналитические возможности
- **SQL + Python**: Сложная обработка данных не ограничена SQL
- **Статистика**: Корреляции, прогнозы, аномалии
- **Бизнес-термины**: Нативное понимание YoY, MoM, ретеншн, повторных покупок
- **Умная визуализация**: Автовыбор лучшего типа графика

### Особенности системы
- **Мультимодельность**: GPT-5, Claude, Gemini, локальные Ollama
- **Гибкое развертывание**: Облако или локально, данные не покидают периметр
- **История**: Сохранение процесса анализа, шэринг
- **Безопасность**: Только чтение, защита от SQL-инъекций, маскирование данных
- **Экспорт**: Excel, PDF, HTML и др.

## 📦 Технические требования

- Python 3.10.x (обязательно, зависимость OpenInterpreter 0.4.3)
- База данных, совместимая с MySQL

> Windows: запускать в WSL (не PowerShell/CMD)

## 📊 Сравнение продуктов

| Сравнение | **QueryGPT** | Vanna AI | DB-GPT | TableGPT | Text2SQL.AI |
|-----------|:------------:|:--------:|:------:|:--------:|:-----------:|
| **Стоимость** | **✅ Бесплатно** | ⭕ Платно | ✅ Бесплатно | ❌ Платно | ❌ Платно |
| **Open Source** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Локальное развертывание** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Запуск Python-кода** | **✅ Полная среда** | ❌ | ❌ | ❌ | ❌ |
| **Визуализация** | **✅ Программируемая** | ⭕ Пресеты | ✅ Богатая | ✅ Богатая | ⭕ Базовая |
| **Бизнес-термины** | **✅ Нативно** | ⭕ Базово | ✅ Хорошо | ✅ Отлично | ⭕ Базово |
| **Автономность агента** | **✅** | ❌ | ⭕ Базово | ⭕ Базово | ❌ |
| **Видимые рассуждения** | **✅** | ❌ | ❌ | ❌ | ❌ |
| **Расширяемость** | **✅ Без ограничений** | ❌ | ❌ | ❌ | ❌ |

### Наши ключевые отличия
- **Полная среда Python**: реальное окружение, можно писать любой код
- **Неограниченная расширяемость**: ставьте библиотеки без ожидания релизов
- **Автономное исследование**: не одноразовые запросы, а активное расследование
- **Прозрачность мышления**: видно, о чем «думает» ИИ, можно вмешаться
- **По-настоящему бесплатно**: MIT-лицензия, без paywall

## 🚀 Быстрый старт

### Первое использование

```bash
# 1. Клонирование
git clone https://github.com/MoonMao42/ReceiptBI.git
cd QueryGPT

# 2. Установка
./setup.sh

# 3. Запуск
./start.sh
```

### Повторный запуск

```bash
./start.sh
```

Сервис по умолчанию: http://localhost:5000

> **Примечание**: при занятом 5000 порте автоматически выбирается доступный 5001–5010

## ⚙️ Инструкции по настройке

### Базовая конфигурация

1. **Копировать .env**
   ```bash
   cp .env.example .env
   ```
2. **Заполнить .env**
   - `OPENAI_API_KEY` — ключ OpenAI
   - `OPENAI_BASE_URL` — адрес API (опционально)
   - Параметры подключения к БД

### Семантический слой (опционально)

Усиливает понимание бизнес-терминов. **Опционально, без него базовые функции работают.**

1. **Копировать пример**
   ```bash
   cp backend/semantic_layer.json.example backend/semantic_layer.json
   ```
2. **Адаптировать под бизнес** (DB mapping / ключевые таблицы / быстрый индекс)

## 📁 Структура проекта

```
QueryGPT/
├── backend/
│   ├── app.py
│   ├── database.py
│   ├── interpreter_manager.py
│   ├── history_manager.py
│   └── config_loader.py
├── frontend/
│   ├── templates/
│   └── static/
│       ├── css/
│       └── js/
├── docs/
├── logs/
├── output/
├── requirements.txt
└── .env.example
```

## 🔌 API

### Запрос

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Показать продажи за текущий месяц",
  "model": "default"
}
```

### История

```http
GET /api/history/conversations
GET /api/history/conversation/:id
DELETE /api/history/conversation/:id
```

### Health-check

```http
GET /api/health
```

## 🔒 Информация по безопасности

- Только чтение (SELECT, SHOW, DESCRIBE)
- Фильтрация опасных SQL
- Пользователи БД — с правами только чтения

## 📄 Лицензия

MIT License — см. файл [LICENSE](LICENSE)

## 🆕 Последние обновления

- 2025-09-05 — оптимизация старта: удален авто-батч тест моделей при первом заходе

## 👨‍💻 Автор

- **Автор**: MoonMao42
- **GitHub**: [@MoonMao42](https://github.com/MoonMao42)
- **Создано**: Август 2025

## ⭐ Star History

<div align="center">
  <a href="https://star-history.com/#MoonMao42/ReceiptBI&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date" />
    </picture>
  </a>
</div>

## 🤝 Вклад

Приветствуются Issues и Pull Requests.

1. Форкните проект
2. Создайте ветку (`git checkout -b feature/AmazingFeature`)
3. Закоммитьте изменения (`git commit -m 'Add some AmazingFeature'`)
4. Запушьте ветку (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request
