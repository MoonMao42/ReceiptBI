<div align="center">
  
  <img src="docs/images/logo.png" width="400" alt="QueryGPT">
  
  <br/>
  
  <p>
    <a href="README.md">English</a> •
    <a href="docs/README_CN.md">简体中文</a> •
    <a href="#">Español</a>
  </p>
  
  <br/>
  
  [![License](https://img.shields.io/badge/Licencia-MIT-yellow.svg?style=for-the-badge)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![OpenInterpreter](https://img.shields.io/badge/OpenInterpreter-0.4.3-green.svg?style=for-the-badge)](https://github.com/OpenInterpreter/open-interpreter)
  [![Stars](https://img.shields.io/github/stars/MoonMao42/ReceiptBI?style=for-the-badge&color=yellow)](https://github.com/MoonMao42/ReceiptBI/stargazers)
  
  <br/>
  
  <h3>Un agente inteligente de análisis de datos basado en OpenInterpreter</h3>
  <p><i>Conversa con tu base de datos en lenguaje natural</i></p>
  
</div>

<br/>

---

## 📋 Descripción del Proyecto

**QueryGPT** es un sistema inteligente de consulta y análisis de datos que revoluciona la forma en que interactuamos con bases de datos. Utilizando tecnología de IA de vanguardia, permite a usuarios de todos los niveles técnicos realizar análisis complejos de datos simplemente escribiendo en lenguaje natural.

### ¿Qué es QueryGPT?

QueryGPT es un agente de IA que actúa como tu analista de datos personal. No solo convierte lenguaje natural en SQL, sino que:
- **Explora autónomamente** tus datos para entender su estructura
- **Razona como un analista humano** investigando anomalías y validando resultados
- **Ejecuta código Python** para análisis estadísticos avanzados y machine learning
- **Visualiza automáticamente** los resultados en gráficos interactivos
- **Muestra su proceso de pensamiento** en tiempo real (Chain-of-Thought)

## ✨ Características Principales

### 🤖 Capacidades del Agente IA

#### Exploración Autónoma de Datos
- El agente examina proactivamente la estructura de tablas y datos de muestra
- Descubre relaciones entre tablas automáticamente
- Identifica patrones y anomalías sin intervención humana

#### Razonamiento Multi-ronda
- Cuando encuentra problemas, investiga profundamente como un analista real
- Valida resultados mediante múltiples verificaciones
- Auto-corrige errores y optimiza consultas

#### Proceso de Pensamiento Transparente
- Visualización en tiempo real del razonamiento del agente (Chain-of-Thought)
- Posibilidad de intervenir y guiar el proceso en cualquier momento
- Historial completo de decisiones y acciones tomadas

### 📊 Análisis de Datos Avanzado

#### SQL + Python Integrado
- No limitado a consultas SQL simples
- Ejecuta código Python complejo para:
  - Análisis estadístico avanzado
  - Machine learning y predicciones
  - Procesamiento de datos personalizado
  - Cálculos matemáticos complejos

#### Visualización Inteligente
- Selección automática del mejor tipo de gráfico según los datos
- Gráficos interactivos con Plotly
- Dashboards personalizables
- Exportación en múltiples formatos (HTML, PNG, PDF)

#### Comprensión de Términos de Negocio
- Entiende conceptos empresariales nativamente:
  - Crecimiento interanual (YoY) y mensual (MoM)
  - Tasas de retención y conversión
  - Análisis de cohortes
  - KPIs y métricas empresariales

### 🌍 Soporte Multiidioma

QueryGPT soporta **10 idiomas** principales para una experiencia global:
- 🇪🇸 Español
- 🇬🇧 Inglés
- 🇨🇳 Chino (Simplificado y Tradicional)
- 🇷🇺 Ruso
- 🇵🇹 Portugués
- 🇫🇷 Francés
- 🇰🇷 Coreano
- 🇩🇪 Alemán
- 🇯🇵 Japonés

### 🔒 Seguridad y Control

- **Permisos de solo lectura**: Protección contra modificaciones accidentales
- **Prevención de inyección SQL**: Filtrado automático de comandos peligrosos
- **Enmascaramiento de datos sensibles**: Protección de información confidencial
- **Auditoría completa**: Registro de todas las consultas y acciones

## 🛠 Stack Tecnológico

### Backend
- **Python 3.10+**: Lenguaje principal del servidor
- **Flask**: Framework web ligero y flexible
- **OpenInterpreter 0.4.3**: Motor de ejecución de código IA
- **SQLAlchemy**: ORM para gestión de base de datos
- **Pandas**: Procesamiento y análisis de datos
- **NumPy**: Cálculos numéricos avanzados

### Frontend
- **HTML5/CSS3**: Estructura y estilos modernos
- **JavaScript ES6+**: Lógica de interfaz interactiva
- **Plotly.js**: Visualizaciones interactivas
- **Bootstrap 5**: Framework CSS responsivo
- **Marked.js**: Renderizado de Markdown

### Base de Datos
- **MySQL**: Sistema principal de gestión de datos
- **PostgreSQL**: Soporte alternativo
- **SQLite**: Para desarrollo y pruebas
- Compatibilidad con cualquier base de datos SQL

### IA y Modelos
- **GPT-4/GPT-3.5**: Modelos de OpenAI
- **Claude**: Modelos de Anthropic
- **Gemini**: Modelos de Google
- **Ollama**: Modelos locales (Llama, Qwen, etc.)

## 🚀 Inicio Rápido

### Instalación Inicial

```bash
# 1. Clonar el repositorio
git clone https://github.com/MoonMao42/ReceiptBI.git
cd QueryGPT

# 2. Ejecutar script de configuración (configura automáticamente el entorno)
./setup.sh

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu editor favorito y configurar:
# - OPENAI_API_KEY: Tu clave API de OpenAI
# - Información de conexión a base de datos

# 4. Iniciar el servicio
./start.sh
```

### Uso Posterior

```bash
# Inicio rápido directo
./quick_start.sh
```

El servicio se ejecuta en http://localhost:5000 por defecto

> **Nota**: Si el puerto 5000 está ocupado, el sistema seleccionará automáticamente el siguiente puerto disponible (5001-5010).

### Configuración de Base de Datos

1. **Crear usuario de solo lectura** (recomendado por seguridad):
```sql
CREATE USER 'querygpt_reader'@'localhost' IDENTIFIED BY 'tu_contraseña_segura';
GRANT SELECT ON tu_base_datos.* TO 'querygpt_reader'@'localhost';
FLUSH PRIVILEGES;
```

2. **Configurar conexión en .env**:
```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=tu_base_datos
DB_USER=querygpt_reader
DB_PASSWORD=tu_contraseña_segura
```

## 💡 Uso

### Ejemplos de Consultas

#### Consultas Básicas
- "Muéstrame las ventas del último mes"
- "¿Cuántos clientes tenemos en cada ciudad?"
- "Lista los 10 productos más vendidos"

#### Análisis Avanzado
- "Analiza la tendencia de ventas y predice los próximos 3 meses"
- "Calcula la tasa de retención de clientes por cohorte mensual"
- "Encuentra correlaciones entre el precio del producto y el volumen de ventas"

#### Visualizaciones
- "Crea un gráfico de barras con las ventas por categoría"
- "Genera un dashboard con KPIs principales del negocio"
- "Muestra la distribución geográfica de clientes en un mapa"

### Modos de Operación

#### Modo Usuario
- Interfaz simplificada con resultados finales
- Visualizaciones automáticas
- Respuestas en lenguaje natural

#### Modo Desarrollador
- Vista completa del código SQL generado
- Logs de ejecución detallados
- Acceso a resultados raw
- Debugging paso a paso

### API REST

#### Endpoint Principal
```http
POST /api/chat
Content-Type: application/json

{
  "message": "Analiza las ventas del último trimestre",
  "model": "gpt-4",
  "stream": true,
  "conversation_id": "uuid-opcional"
}
```

#### Respuesta
```json
{
  "success": true,
  "result": {
    "content": [
      {
        "type": "text",
        "content": "He analizado las ventas del último trimestre..."
      },
      {
        "type": "chart",
        "url": "/output/chart_ventas_trimestre.html"
      }
    ],
    "sql_query": "SELECT ...",
    "execution_time": 1.23
  },
  "conversation_id": "uuid-xxx"
}
```

## 📋 Requisitos del Sistema

### Hardware Mínimo
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Disco**: 10 GB espacio libre

### Hardware Recomendado
- **CPU**: 4+ cores
- **RAM**: 8 GB o más
- **Disco**: 20 GB espacio libre
- **GPU**: Opcional, mejora el rendimiento con modelos locales

### Software
- **Sistema Operativo**: Linux, macOS, Windows (con WSL2)
- **Python**: 3.10.x (requerido específicamente para OpenInterpreter 0.4.3)
- **Node.js**: 14+ (para desarrollo frontend)
- **Base de Datos**: MySQL 5.7+, PostgreSQL 10+, o SQLite

### Requisitos de Red
- Conexión a Internet para modelos cloud (OpenAI, Claude, etc.)
- Puerto 5000 disponible (configurable)
- Acceso a la base de datos objetivo

## 🔧 Configuración Avanzada

### Modelos Personalizados

Añade modelos personalizados en `config/models.json`:

```json
{
  "models": [
    {
      "name": "Mi Modelo Local",
      "id": "modelo-local",
      "type": "ollama",
      "api_base": "http://localhost:11434/v1",
      "api_key": "opcional"
    }
  ]
}
```

### Despliegue con Docker

```bash
# Construir imagen
docker build -t querygpt .

# Ejecutar contenedor
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  querygpt
```

### Configuración de Producción

```bash
# Usar gunicorn para producción
gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app

# Con nginx como proxy reverso
# Ver docs/DEPLOYMENT.md para configuración completa
```

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

### ¿Qué significa esto?

La Licencia MIT es una de las licencias de software libre más permisivas:

- ✅ **Uso comercial**: Puedes usar QueryGPT en proyectos comerciales
- ✅ **Modificación**: Puedes modificar el código según tus necesidades
- ✅ **Distribución**: Puedes distribuir el software
- ✅ **Uso privado**: Puedes usar el software privadamente
- ❗ **Sin garantía**: El software se proporciona "tal cual"
- ❗ **Sin responsabilidad**: Los autores no son responsables de daños

## 👥 Comunidad y Soporte

### Obtener Ayuda
- 📖 [Documentación completa](https://github.com/MoonMao42/ReceiptBI/wiki)
- 💬 [Discusiones en GitHub](https://github.com/MoonMao42/ReceiptBI/discussions)
- 🐛 [Reportar problemas](https://github.com/MoonMao42/ReceiptBI/issues)

### Contribuir
¡Las contribuciones son bienvenidas! Por favor:

1. Fork el proyecto
2. Crea tu rama de características (`git checkout -b feature/CaracteristicaIncreible`)
3. Commit tus cambios (`git commit -m 'Añadir CaracteristicaIncreible'`)
4. Push a la rama (`git push origin feature/CaracteristicaIncreible`)
5. Abre un Pull Request

### Autor
- **Creador**: MoonMao42
- **GitHub**: [@MoonMao42](https://github.com/MoonMao42)
- **Creado**: Agosto 2025

## ⭐ Apoya el Proyecto

Si encuentras útil QueryGPT, considera:
- ⭐ Dar una estrella al repositorio
- 🔀 Compartir con colegas y amigos
- 📝 Escribir sobre tu experiencia
- 🤝 Contribuir con código o documentación

---

<div align="center">
  <p>Hecho con ❤️ para la comunidad de análisis de datos</p>
  <p>
    <a href="https://github.com/MoonMao42/ReceiptBI">GitHub</a> •
    <a href="https://github.com/MoonMao42/ReceiptBI/wiki">Wiki</a> •
    <a href="https://github.com/MoonMao42/ReceiptBI/discussions">Discusiones</a>
  </p>
</div>